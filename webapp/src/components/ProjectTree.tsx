// Project tree (left panel): user folders → projects → tracks → products / report / exports, like the QGIS browser.
// Folders are workspace metadata (projects/.folders.json): moving a project between folders moves nothing on disk.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { api, type Folder, type FolderTree, type ProjectSummary, type Workspace } from "../api";
import { t, ts } from "../i18n";
import { useApp } from "../state";
import { fmt, StatusDot } from "../ui";

const OPEN_KEY = "geoeyes.tree.open";

function useOpenSet() {
  const [open, setOpen] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(OPEN_KEY) ?? "null") ?? ["f:Vietnam", "f:Vietnam/Hanoi"]);
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
    } catch {
      /* storage unavailable */
    }
  }, [open]);
  const toggle = (k: string, force?: boolean) =>
    setOpen((s) => {
      const n = new Set(s);
      if (force ?? !n.has(k)) n.add(k);
      else n.delete(k);
      return n;
    });
  return { open, toggle };
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" className={`flex-none transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
      <path d="M4 2.5 7.5 6 4 9.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" className="flex-none text-[#7f93b3]" aria-hidden>
      {open ? (
        <path d="M1.5 4.5v8h11l2-5.5H4L2.5 12" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      ) : (
        <path d="M1.5 3.5h4.5l1.5 1.5h7v8h-13z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      )}
    </svg>
  );
}

function Eye({ on }: { on: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8s-2.4 4.5-6.5 4.5S1.5 8 1.5 8z" fill="none" stroke="currentColor" strokeWidth="1.3" />
      {on ? <circle cx="8" cy="8" r="2.1" fill="currentColor" /> : <path d="M3 13 13 3" stroke="currentColor" strokeWidth="1.3" />}
    </svg>
  );
}

// ------------------------------------------------------------------ folder tree edits
function removeProject(tree: FolderTree, name: string): FolderTree {
  const strip = (f: Folder): Folder => ({ ...f, projects: f.projects.filter((p) => p !== name), folders: f.folders.map(strip) });
  return { folders: tree.folders.map(strip), projects: tree.projects.filter((p) => p !== name) };
}

function mapFolder(tree: FolderTree, path: string, fn: (f: Folder) => Folder | null): FolderTree {
  const walk = (list: Folder[], prefix: string): Folder[] =>
    list.flatMap((f) => {
      const p = prefix ? `${prefix}/${f.name}` : f.name;
      if (p === path) {
        const r = fn(f);
        return r ? [r] : [];
      }
      return [{ ...f, folders: walk(f.folders, p) }];
    });
  return { ...tree, folders: walk(tree.folders, "") };
}

function folderAt(tree: FolderTree, path: string): Folder | null {
  let list = tree.folders;
  let found: Folder | null = null;
  for (const part of path.split("/")) {
    found = list.find((f) => f.name === part) ?? null;
    if (!found) return null;
    list = found.folders;
  }
  return found;
}

/** Every project of a folder and its subfolders. */
function projectsIn(f: Folder): string[] {
  return [...f.projects, ...f.folders.flatMap(projectsIn)];
}

/** The folder removed; with ``keep`` its projects and subfolders go to its parent (or the root). */
function deleteFolder(tree: FolderTree, path: string, keep: boolean): FolderTree {
  const f = folderAt(tree, path);
  if (!f) return tree;
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : null;
  let out = mapFolder(tree, path, () => null);
  if (!keep) return out;
  if (parent) out = mapFolder(out, parent, (x) => ({ ...x, projects: [...x.projects, ...f.projects], folders: [...x.folders, ...f.folders] }));
  else out = { folders: [...out.folders, ...f.folders], projects: [...out.projects, ...f.projects] };
  return out;
}

function moveProject(tree: FolderTree, name: string, folderPath: string | null): FolderTree {
  const t = removeProject(tree, name);
  if (!folderPath) return { ...t, projects: [...t.projects, name] };
  return mapFolder(t, folderPath, (f) => ({ ...f, projects: [...f.projects, name] }));
}

// ------------------------------------------------------------------ rows
function Row({
  depth,
  children,
  active,
  onClick,
  onContextMenu,
  draggable,
  onDragStart,
  dropTarget,
  className = "",
}: {
  depth: number;
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
  draggable?: boolean;
  onDragStart?: (e: DragEvent) => void;
  dropTarget?: { onDrop: (e: DragEvent) => void };
  className?: string;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      role="treeitem"
      tabIndex={-1}
      onClick={onClick}
      onContextMenu={onContextMenu}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={dropTarget ? (e) => (e.preventDefault(), setOver(true)) : undefined}
      onDragLeave={dropTarget ? () => setOver(false) : undefined}
      onDrop={dropTarget ? (e) => (setOver(false), dropTarget.onDrop(e)) : undefined}
      style={{ paddingLeft: 8 + depth * 14 }}
      className={`group flex h-8 cursor-pointer items-center gap-2 rounded-md pr-2 text-[13px] select-none ${
        active ? "bg-raised text-ink" : "text-ink-2 hover:bg-[#131f35]"
      } ${over ? "ring-1 ring-accent" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

interface Menu {
  x: number;
  y: number;
  project?: ProjectSummary;
  folder?: string;         // path of a folder
}

/** Delete a folder: keep its projects (moved up) or move them to the trash (typed confirmation). */
function DeleteFolder({ path, folder, running, busy, error, onCancel, onConfirm }: {
  path: string;
  folder: Folder;
  running: string[];
  busy: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: (keep: boolean) => void;
}) {
  const [keep, setKeep] = useState(true);
  const [typed, setTyped] = useState("");
  const names = projectsIn(folder);
  const blocked = !keep && running.length > 0;
  const ok = keep || (typed.trim() === folder.name && !blocked);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={t("Delete folder")}>
      <div className="w-full max-w-md rounded-xl border border-line-2 bg-panel p-5 shadow-2xl">
        <div className="text-[15px] font-semibold">{t("Delete folder “{name}”", { name: path })}</div>
        <div className="mt-1 text-[12.5px] text-muted">
          {names.length ? t("{n} project(s) inside: {list}", { n: names.length, list: names.join(", ") }) : t("The folder is empty.")}
        </div>
        {names.length > 0 && (
          <div className="mt-3 space-y-2 text-[13px]">
            <label className="flex cursor-pointer gap-2 rounded-lg border border-line p-2.5 hover:bg-raised">
              <input type="radio" className="mt-0.5 accent-[#4cc2ff]" checked={keep} onChange={() => setKeep(true)} />
              <span>
                <span className="font-medium">{t("Delete the folder only")}</span>
                <span className="block text-[12px] text-muted">{t("Its projects and subfolders move to the parent folder. Nothing is deleted on disk.")}</span>
              </span>
            </label>
            <label className="flex cursor-pointer gap-2 rounded-lg border border-line p-2.5 hover:bg-raised">
              <input type="radio" className="mt-0.5 accent-[#ff8a8a]" checked={!keep} onChange={() => setKeep(false)} />
              <span>
                <span className="font-medium text-[#ffb3b3]">{t("Delete the folder and its projects")}</span>
                <span className="block text-[12px] text-muted">{t("The project folders move to the workspace trash (trash/), from where they can be restored by moving them back.")}</span>
              </span>
            </label>
            {!keep && (
              <div className="pl-1">
                {blocked && <div className="mb-1 text-[12px] text-bad">{t("Running now: {list}. Stop the runs first.", { list: running.join(", ") })}</div>}
                <label className="text-[12px] text-muted">
                  {t("Type the folder name to confirm:")}{" "}
                  <span className="font-mono text-ink-2">{folder.name}</span>
                  <input
                    autoFocus
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2 font-mono text-[13px] text-ink focus:border-accent focus:outline-none"
                  />
                </label>
              </div>
            )}
          </div>
        )}
        {error && <div className="mt-2 text-[12.5px] text-bad">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="h-9 rounded-lg border border-line-2 px-3.5 text-[13px] hover:bg-raised">
            {t("Cancel")}
          </button>
          <button
            type="button"
            disabled={!ok || busy}
            onClick={() => onConfirm(keep || names.length === 0)}
            className="h-9 rounded-lg border border-[#5c2424] bg-[#2a1414] px-3.5 text-[13px] text-[#ffb3b3] hover:bg-[#3a1a1a] disabled:opacity-50"
          >
            {busy ? t("Deleting…") : t("Delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ProjectTree({ ws }: { ws: Workspace | undefined }) {
  const { route, go, layers, showProduct, toggleLayer } = useApp();
  const { open, toggle } = useOpenSet();
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState<Menu | null>(null);
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: api.saveFolders,
    onSuccess: (tree) => qc.setQueryData<Workspace>(["workspace"], (w) => (w ? { ...w, tree } : w)),
  });
  const runNow = useMutation({
    mutationFn: (name: string) => api.run(name),
    onSettled: () => qc.invalidateQueries({ queryKey: ["workspace"] }),
  });
  const menuRef = useRef<HTMLDivElement>(null);
  const [del, setDel] = useState<{ path: string; busy: boolean; error: string } | null>(null);
  const trash = useMutation({
    mutationFn: api.trashProjects,
    onSuccess: (r) => qc.setQueryData<Workspace>(["workspace"], (w) => (w ? { ...w, tree: r.tree } : w)),
    onSettled: () => qc.invalidateQueries({ queryKey: ["workspace"] }),
  });
  const confirmDelete = async (keep: boolean) => {
    if (!del || !ws) return;
    const f = folderAt(ws.tree, del.path);
    if (!f) return setDel(null);
    setDel({ ...del, busy: true, error: "" });
    try {
      let tree = ws.tree;
      if (!keep) {
        const r = await trash.mutateAsync(projectsIn(f));
        tree = r.tree;
      }
      await save.mutateAsync(deleteFolder(tree, del.path, keep));
      setDel(null);
    } catch (e) {
      setDel({ ...del, busy: false, error: ts((e as Error).message) });
    }
  };

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => !menuRef.current?.contains(e.target as Node) && setMenu(null);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMenu(null);
    addEventListener("mousedown", close);
    addEventListener("keydown", esc);
    return () => (removeEventListener("mousedown", close), removeEventListener("keydown", esc));
  }, [menu]);

  const match = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s || !ws) return null;
    return new Set(
      Object.values(ws.projects)
        .filter((p) => [p.name, p.description ?? "", ...p.tracks.map((x) => x.track_id)].some((x) => x.toLowerCase().includes(s)))
        .map((p) => p.name),
    );
  }, [q, ws]);

  if (!ws) {
    return <div className="p-4 text-[13px] text-muted">{t("Loading workspace…")}</div>;
  }
  const tree = ws.tree;
  const visibleIn = (f: Folder): boolean => !match || f.projects.some((p) => match.has(p)) || f.folders.some(visibleIn);
  const drop = (folderPath: string | null) => ({
    onDrop: (e: DragEvent) => {
      const name = e.dataTransfer.getData("text/geoeyes-project");
      if (name) save.mutate(moveProject(tree, name, folderPath));
    },
  });

  const addFolder = () => {
    const name = prompt(t("New folder name"))?.trim();
    if (name) save.mutate({ ...tree, folders: [...tree.folders, { name, projects: [], folders: [] }] });
  };

  const renderProject = (p: ProjectSummary | undefined, depth: number) => {
    if (!p || (match && !match.has(p.name))) return null;
    const k = `p:${p.name}`;
    const isOpen = open.has(k) || !!match;
    const active = route.page === "project" && route.name === p.name;
    return (
      <div key={p.name} role="group">
        <Row
          depth={depth}
          active={active}
          draggable
          onDragStart={(e) => e.dataTransfer.setData("text/geoeyes-project", p.name)}
          onClick={() => go({ page: "project", name: p.name })}
          onContextMenu={(e) => (e.preventDefault(), setMenu({ x: e.clientX, y: e.clientY, project: p }))}
        >
          <span
            className="flex h-5 w-4 items-center justify-center text-muted hover:text-ink"
            onClick={(e) => (e.stopPropagation(), toggle(k))}
            aria-label={isOpen ? t("Collapse") : t("Expand")}
          >
            <Chevron open={isOpen} />
          </span>
          <StatusDot status={p.status} />
          <span className="truncate font-mono text-[12.5px]">{p.name}</span>
          {p.status === "running" && <span className="ml-auto text-[11px] text-[#7cd2ff]">{t("running")}</span>}
          {p.status === "failed" && <span className="ml-auto text-[11px] text-bad">{t("failed")}</span>}
        </Row>
        {isOpen &&
          p.tracks.map((tr) => {
            const tk = `t:${p.name}/${tr.track_id}`;
            const tOpen = !open.has(`x:${tk}`);
            const pid = tr.product?.id;
            const layer = pid ? layers.find((l) => l.key === `${p.name}/${pid}`) : undefined;
            return (
              <div key={tr.track_id}>
                <Row depth={depth + 1} onClick={() => toggle(`x:${tk}`)}>
                  <span className="flex w-4 justify-center text-muted">
                    <Chevron open={tOpen} />
                  </span>
                  <span className="truncate text-[12.5px]">
                    {fmt.sensor(tr.sensor)} <span className="text-muted">{tr.direction.slice(0, 4)}{tr.relative_orbit != null ? ` ${String(tr.relative_orbit).padStart(3, "0")}` : ""}</span>
                  </span>
                </Row>
                {tOpen && (
                  <>
                    {tr.product ? (
                      <Row
                        depth={depth + 2}
                        onClick={() => showProduct(p.name, tr.product!.id, { open: true })}
                        className="pr-1"
                      >
                        <span className="w-4" />
                        <span className="truncate text-[12.5px]">
                          {t("Product")} <span className="font-mono text-muted">v{tr.product.version}</span>
                        </span>
                        <button
                          type="button"
                          title={layer?.visible ? t("Hide on the map") : t("Show on the map")}
                          aria-pressed={!!layer?.visible}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (layer) toggleLayer(layer.key);
                            else showProduct(p.name, tr.product!.id);
                          }}
                          className={`ml-auto flex h-6 w-7 items-center justify-center rounded ${
                            layer?.visible ? "text-accent" : "text-faint hover:text-ink"
                          }`}
                        >
                          <Eye on={!!layer?.visible} />
                        </button>
                      </Row>
                    ) : (
                      <Row depth={depth + 2} className="cursor-default text-faint hover:bg-transparent">
                        <span className="w-4" />
                        <span className="text-[12px] italic">{t("no product yet")}</span>
                      </Row>
                    )}
                    {tr.product?.report && (
                      <Row depth={depth + 2} onClick={() => open_(api.fileUrl(p.name, tr.product!.id, "report.pdf"))}>
                        <span className="w-4" />
                        <span className="text-[12.5px]">{t("Report")}</span>
                        <span className="ml-auto text-[11px] text-muted">PDF ↗</span>
                      </Row>
                    )}
                    <Row depth={depth + 2} onClick={() => go({ page: "project", name: p.name, tab: "pipeline" })}>
                      <span className="w-4" />
                      <span className="text-[12.5px]">{t("Pipeline")}</span>
                      <span className="ml-auto flex gap-0.5">
                        {["acquire", "build_stack", "ps", "build_product", "export", "report"].map((ph) => (
                          <span
                            key={ph}
                            title={`${ph}: ${tr.phases[ph]?.status ?? t("not run")}`}
                            className="h-1.5 w-2.5 rounded-sm"
                            style={{
                              background:
                                { done: "#3ecf8e", running: "#7cd2ff", failed: "#ff8a8a", interrupted: "#f5b84b" }[
                                  tr.phases[ph]?.status ?? ""
                                ] ?? "#22324d",
                            }}
                          />
                        ))}
                      </span>
                    </Row>
                  </>
                )}
              </div>
            );
          })}
      </div>
    );
  };

  const renderFolder = (f: Folder, depth: number, prefix: string): ReactNode => {
    if (!visibleIn(f)) return null;
    const path = prefix ? `${prefix}/${f.name}` : f.name;
    const k = `f:${path}`;
    const isOpen = open.has(k) || !!match;
    const count = (x: Folder): number => x.projects.length + x.folders.reduce((a, s) => a + count(s), 0);
    const empty = count(f) === 0 && f.folders.length === 0;
    return (
      <div key={path} role="group">
        <Row depth={depth} onClick={() => toggle(k)} dropTarget={drop(path)} onContextMenu={(e) => (e.preventDefault(), setMenu({ x: e.clientX, y: e.clientY, folder: path }))}>
          <span className="flex w-4 justify-center text-muted">
            <Chevron open={isOpen} />
          </span>
          <FolderIcon open={isOpen} />
          <span
            className="truncate font-medium"
            onDoubleClick={(e) => {
              e.stopPropagation();
              const name = prompt(t("Rename folder"), f.name)?.trim();
              if (name && name !== f.name) save.mutate(mapFolder(tree, path, (x) => ({ ...x, name })));
            }}
          >
            {f.name}
          </span>
          <span className="ml-auto text-[11px] text-faint">{count(f)}</span>
          <button
            type="button"
            title={t("Delete folder")}
            aria-label={t("Delete folder")}
            className="hidden h-5 w-5 items-center justify-center rounded text-faint group-hover:flex hover:text-bad"
            onClick={(e) => (e.stopPropagation(), empty ? save.mutate(mapFolder(tree, path, () => null)) : setDel({ path, busy: false, error: "" }))}
          >
            ×
          </button>
        </Row>
        {isOpen && (
          <>
            {f.folders.map((s) => renderFolder(s, depth + 1, path))}
            {f.projects.map((n) => renderProject(ws.projects[n], depth + 1))}
          </>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">{t("PROJECTS")}</span>
        <button
          type="button"
          onClick={() => go({ page: "new" })}
          title={t("New project")}
          className="ml-auto flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-accent hover:bg-raised"
        >
          <span aria-hidden className="text-[15px] leading-none">+</span> {t("Project")}
        </button>
        <button
          type="button"
          onClick={addFolder}
          title={t("New folder")}
          className="flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-muted hover:bg-raised hover:text-ink"
        >
          <span aria-hidden className="text-[15px] leading-none">+</span> {t("Folder")}
        </button>
      </div>
      <div className="px-3 pb-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("Filter projects…")}
          aria-label={t("Filter projects")}
          className="h-8 w-full rounded-md border border-line-2 bg-[#0a1322] px-2.5 text-[13px] text-ink placeholder:text-faint focus:border-accent focus:outline-none"
        />
      </div>
      <div role="tree" className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
        {tree.folders.map((f) => renderFolder(f, 0, ""))}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={drop(null).onDrop}
          className={tree.projects.length ? "" : "min-h-6"}
        >
          {tree.projects.map((n) => renderProject(ws.projects[n], 0))}
        </div>
      </div>
      <div className="border-t border-line px-3 py-2 text-[11px] text-faint" title={ws.root}>
        {t("Drag projects onto folders · double-click a folder to rename · right-click for more")}
      </div>

      {del && folderAt(tree, del.path) && (
        <DeleteFolder
          path={del.path}
          folder={folderAt(tree, del.path)!}
          running={projectsIn(folderAt(tree, del.path)!).filter((n) => ws.projects[n]?.status === "running")}
          busy={del.busy}
          error={del.error}
          onCancel={() => setDel(null)}
          onConfirm={confirmDelete}
        />
      )}

      {menu && (
        <div
          ref={menuRef}
          role="menu"
          style={{ left: menu.x, top: menu.y }}
          className="fixed z-50 min-w-48 rounded-lg border border-line-2 bg-panel py-1 text-[13px] shadow-2xl shadow-black/50"
        >
          {(menu.folder
            ? [
                {
                  label: t("Rename folder"),
                  on: () => {
                    const f = folderAt(tree, menu.folder!);
                    const name = f && prompt(t("Rename folder"), f.name)?.trim();
                    if (f && name && name !== f.name) save.mutate(mapFolder(tree, menu.folder!, (x) => ({ ...x, name })));
                  },
                },
                { label: t("Delete folder…"), danger: true, on: () => setDel({ path: menu.folder!, busy: false, error: "" }) },
              ]
            : menu.project
              ? [
            { label: t("Open project"), on: () => go({ page: "project", name: menu.project!.name }) },
            { label: t("Plan (what would run)"), on: () => go({ page: "project", name: menu.project!.name, tab: "pipeline" }) },
            {
              label: menu.project.status === "running" ? t("Running…") : t("Run now"),
              disabled: menu.project.status === "running",
              on: () => runNow.mutate(menu.project!.name),
            },
            ...menu.project.tracks
              .filter((tr) => tr.product)
              .flatMap((tr) => [
                { label: t("Show {track} on the map", { track: tr.track_id }), on: () => showProduct(menu.project!.name, tr.product!.id, { open: true }) },
                ...(tr.product!.report
                  ? [{ label: t("Open report ({track})", { track: tr.track_id }), on: () => open_(api.fileUrl(menu.project!.name, tr.product!.id, "report.pdf")) }]
                  : []),
              ]),
            {
              label: t("Move to the trash…"),
              danger: true,
              disabled: menu.project.status === "running",
              on: () => {
                const name = menu.project!.name;
                if (confirm(t("Move the project “{name}” to the workspace trash (trash/)? It can be restored by moving its folder back.", { name })))
                  trash.mutate([name], { onError: (e) => alert(ts((e as Error).message)) });
              },
            },
          ]
              : []
          ).map((it: { label: string; on: () => void; disabled?: boolean; danger?: boolean }) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              disabled={it.disabled}
              onClick={() => (setMenu(null), it.on())}
              className={`block w-full px-3 py-1.5 text-left hover:bg-raised disabled:opacity-50 ${it.danger ? "text-[#ffb3b3] hover:text-[#ffd0d0]" : "text-ink-2 hover:text-ink"}`}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function open_(url: string) {
  window.open(url, "_blank", "noopener");
}
