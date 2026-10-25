// Project tree (left panel): user folders → projects → tracks → products / report / exports, like the QGIS browser.
// Folders are workspace metadata (projects/.folders.json): moving a project between folders moves nothing on disk.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { api, type Folder, type FolderTree, type ProjectSummary, type Workspace } from "../api";
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
  project: ProjectSummary;
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
        .filter((p) => [p.name, p.description ?? "", ...p.tracks.map((t) => t.track_id)].some((x) => x.toLowerCase().includes(s)))
        .map((p) => p.name),
    );
  }, [q, ws]);

  if (!ws) {
    return <div className="p-4 text-[13px] text-muted">Loading workspace…</div>;
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
    const name = prompt("New folder name")?.trim();
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
            aria-label={isOpen ? "Collapse" : "Expand"}
          >
            <Chevron open={isOpen} />
          </span>
          <StatusDot status={p.status} />
          <span className="truncate font-mono text-[12.5px]">{p.name}</span>
          {p.status === "running" && <span className="ml-auto text-[11px] text-[#7cd2ff]">running</span>}
          {p.status === "failed" && <span className="ml-auto text-[11px] text-bad">failed</span>}
        </Row>
        {isOpen &&
          p.tracks.map((t) => {
            const tk = `t:${p.name}/${t.track_id}`;
            const tOpen = !open.has(`x:${tk}`);
            const pid = t.product?.id;
            const layer = pid ? layers.find((l) => l.key === `${p.name}/${pid}`) : undefined;
            return (
              <div key={t.track_id}>
                <Row depth={depth + 1} onClick={() => toggle(`x:${tk}`)}>
                  <span className="flex w-4 justify-center text-muted">
                    <Chevron open={tOpen} />
                  </span>
                  <span className="truncate text-[12.5px]">
                    {fmt.sensor(t.sensor)} <span className="text-muted">{t.direction.slice(0, 4)}{t.relative_orbit != null ? ` ${String(t.relative_orbit).padStart(3, "0")}` : ""}</span>
                  </span>
                </Row>
                {tOpen && (
                  <>
                    {t.product ? (
                      <Row
                        depth={depth + 2}
                        onClick={() => showProduct(p.name, t.product!.id, { open: true })}
                        className="pr-1"
                      >
                        <span className="w-4" />
                        <span className="truncate text-[12.5px]">
                          Product <span className="font-mono text-muted">v{t.product.version}</span>
                        </span>
                        <button
                          type="button"
                          title={layer?.visible ? "Hide on the map" : "Show on the map"}
                          aria-pressed={!!layer?.visible}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (layer) toggleLayer(layer.key);
                            else showProduct(p.name, t.product!.id);
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
                        <span className="text-[12px] italic">no product yet</span>
                      </Row>
                    )}
                    {t.product?.report && (
                      <Row depth={depth + 2} onClick={() => open_(api.fileUrl(p.name, t.product!.id, "report.pdf"))}>
                        <span className="w-4" />
                        <span className="text-[12.5px]">Report</span>
                        <span className="ml-auto text-[11px] text-muted">PDF ↗</span>
                      </Row>
                    )}
                    <Row depth={depth + 2} onClick={() => go({ page: "project", name: p.name, tab: "pipeline" })}>
                      <span className="w-4" />
                      <span className="text-[12.5px]">Pipeline</span>
                      <span className="ml-auto flex gap-0.5">
                        {["acquire", "build_stack", "ps", "build_product", "export", "report"].map((ph) => (
                          <span
                            key={ph}
                            title={`${ph}: ${t.phases[ph]?.status ?? "not run"}`}
                            className="h-1.5 w-2.5 rounded-sm"
                            style={{
                              background:
                                { done: "#3ecf8e", running: "#7cd2ff", failed: "#ff8a8a", interrupted: "#f5b84b" }[
                                  t.phases[ph]?.status ?? ""
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
        <Row depth={depth} onClick={() => toggle(k)} dropTarget={drop(path)}>
          <span className="flex w-4 justify-center text-muted">
            <Chevron open={isOpen} />
          </span>
          <FolderIcon open={isOpen} />
          <span
            className="truncate font-medium"
            onDoubleClick={(e) => {
              e.stopPropagation();
              const name = prompt("Rename folder", f.name)?.trim();
              if (name && name !== f.name) save.mutate(mapFolder(tree, path, (x) => ({ ...x, name })));
            }}
          >
            {f.name}
          </span>
          <span className="ml-auto text-[11px] text-faint">{count(f)}</span>
          {empty && (
            <button
              type="button"
              title="Delete empty folder"
              className="hidden h-5 w-5 items-center justify-center rounded text-faint group-hover:flex hover:text-bad"
              onClick={(e) => (e.stopPropagation(), save.mutate(mapFolder(tree, path, () => null)))}
            >
              ×
            </button>
          )}
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
        <span className="text-[11px] font-semibold tracking-[1.2px] text-muted">PROJECTS</span>
        <button
          type="button"
          onClick={() => go({ page: "new" })}
          title="New project"
          className="ml-auto flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-accent hover:bg-raised"
        >
          <span aria-hidden className="text-[15px] leading-none">+</span> Project
        </button>
        <button
          type="button"
          onClick={addFolder}
          title="New folder"
          className="flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-muted hover:bg-raised hover:text-ink"
        >
          <span aria-hidden className="text-[15px] leading-none">+</span> Folder
        </button>
      </div>
      <div className="px-3 pb-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter projects…"
          aria-label="Filter projects"
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
        Drag projects onto folders · double-click a folder to rename
      </div>

      {menu && (
        <div
          ref={menuRef}
          role="menu"
          style={{ left: menu.x, top: menu.y }}
          className="fixed z-50 min-w-48 rounded-lg border border-line-2 bg-panel py-1 text-[13px] shadow-2xl shadow-black/50"
        >
          {[
            { label: "Open project", on: () => go({ page: "project", name: menu.project.name }) },
            { label: "Plan (what would run)", on: () => go({ page: "project", name: menu.project.name, tab: "pipeline" }) },
            {
              label: menu.project.status === "running" ? "Running…" : "Run now",
              disabled: menu.project.status === "running",
              on: () => runNow.mutate(menu.project.name),
            },
            ...menu.project.tracks
              .filter((t) => t.product)
              .flatMap((t) => [
                { label: `Show ${t.track_id} on the map`, on: () => showProduct(menu.project.name, t.product!.id, { open: true }) },
                ...(t.product!.report
                  ? [{ label: `Open report (${t.track_id})`, on: () => open_(api.fileUrl(menu.project.name, t.product!.id, "report.pdf")) }]
                  : []),
              ]),
          ].map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              disabled={"disabled" in it && it.disabled}
              onClick={() => (setMenu(null), it.on())}
              className="block w-full px-3 py-1.5 text-left text-ink-2 hover:bg-raised hover:text-ink disabled:opacity-50"
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
