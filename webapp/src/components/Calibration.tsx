// The calibration of a product in the Validation tab: the one applied (GNSS, else a tie to another product), the
// calibrated GeoPackage, and the tie of a product with no GNSS station to another product of the same ground.
// Method: geoeyes.validation.tie (one rate correction, compared over the same period, as vertical rates).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CalibrationBrief } from "../api";
import { t, ts } from "../i18n";
import { Button, fmt, Panel } from "../ui";

/** Where a calibration comes from, in a few words: "GNSS MMX1" or "tie to mexico_s1 v7 (GNSS MMX1)". */
export function calibrationSource(c: CalibrationBrief): string {
  if (c.source === "gnss") return `GNSS ${c.stations.join(", ")}`;
  const ref = c.reference_product ? `${c.reference_product.split("_").slice(0, 2).join("_")} v${c.reference_product.split("_v").pop()}` : "?";
  return t("tie to {ref}", { ref }) + (c.reference_calibration ? ` (${c.reference_calibration})` : "");
}

export function Calibration({ name, product }: { name: string; product: string }) {
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ["tie", name, product], queryFn: () => api.tie(name, product), enabled: !!product });
  const meta = useQuery({ queryKey: ["layer-meta", name, product], queryFn: () => api.layer(name, product), enabled: !!product, staleTime: Infinity });
  const b = meta.data?.bounds;
  const cands = useQuery({
    queryKey: ["tie-candidates", b?.join(",")],
    queryFn: () => api.catalogSearch(b!),
    enabled: !!b,
    staleTime: 60_000,
  });
  const others = (cands.data?.products ?? []).filter((p) => p.id !== product && (p.in_area?.n ?? 1) > 0);
  const [ref, setRef] = useState("");
  const reference = ref || (others[0] ? `${others[0].project}/${others[0].id}` : "");
  const [busy, setBusy] = useState<"" | "tie" | "export" | "remove">("");
  const [err, setErr] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const act = async (k: "tie" | "export" | "remove", f: () => Promise<unknown>) => {
    setErr("");
    setBusy(k);
    try {
      await f();
      await qc.invalidateQueries({ queryKey: ["tie", name, product] });
      await qc.invalidateQueries({ queryKey: ["layer"] });
    } catch (e) {
      setErr(ts((e as Error).message));
    } finally {
      setBusy("");
    }
  };
  const active = st.data?.active ?? null;
  const tie = st.data?.tie ?? null;

  return (
    <Panel className="px-4 py-3 text-[13px]">
      <div className="font-semibold">{t("Calibration applied")}</div>
      <div className="mt-1 text-ink-2">
        {active ? (
          <>
            {calibrationSource(active)}: <span className="font-mono">{fmt.vel(active.rate_offset_mm_yr)} mm/yr</span>{" "}
            {t("along the line of sight. On the map: the Calibrated switch of the layer; the product files stay as they are.")}
          </>
        ) : (
          t("None: compare with GNSS above, or tie this product to another product of the same ground below.")
        )}
      </div>
      {active && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button disabled={!!busy} onClick={() => act("export", async () => setFiles((await api.exportCalibrated(name, product)).files))}>
            {busy === "export" ? t("Writing…") : t("Write the calibrated GeoPackage + CSV")}
          </Button>
          {files.length > 0 && (
            <span className="text-[12px] text-muted">
              {files
                .filter((f) => /\.(gpkg|csv)$/.test(f))
                .map((f) => {
                  const file = f.split(/[\\/]/).pop()!;
                  return (
                    <a key={file} href={api.exportUrl(name, product, file)} className="mr-3 font-mono text-accent hover:underline">
                      {file}
                    </a>
                  );
                })}
            </span>
          )}
        </div>
      )}

      <div className="mt-4 border-t border-line pt-3">
        <div className="font-semibold">{t("Tie to another product")}</div>
        <div className="mt-0.5 text-muted">
          {t(
            "For a product with no GNSS station: one rate correction from another product of the same ground (and its own calibration), compared over this product's period and as vertical rates. A gain between the two is reported, not corrected: it comes from the periods or the geometries.",
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            value={reference}
            onChange={(e) => setRef(e.target.value)}
            aria-label={t("Reference product")}
            className="h-8 max-w-full min-w-0 rounded-md border border-line-2 bg-sunken px-2 text-[12.5px] text-ink"
          >
            {others.length === 0 && <option value="">{cands.isLoading ? t("Looking for products…") : t("No other product over this one")}</option>}
            {others.map((p) => (
              <option key={`${p.project}/${p.id}`} value={`${p.project}/${p.id}`}>
                {p.project} · v{p.id.split("_v").pop()} · {fmt.sensor(p.sensor)} {p.first_date}..{p.last_date}
              </option>
            ))}
          </select>
          <Button variant="primary" disabled={!reference || !!busy} onClick={() => act("tie", () => api.tieRun(name, product, reference))}>
            {busy === "tie" ? t("Tying…") : tie ? t("Tie again") : t("Tie")}
          </Button>
          {tie && (
            <Button disabled={!!busy} onClick={() => act("remove", () => api.tieRemove(name, product))}>
              {t("Remove the tie")}
            </Button>
          )}
        </div>
        {err && <div className="mt-2 text-[12.5px] text-bad">{err}</div>}
        {tie && (
          <div className="mt-3 grid gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-2">
            {(
              [
                [t("Reference"), `${tie.reference_product}${tie.calibration.reference_calibration ? ` (${tie.calibration.reference_calibration})` : ""}`],
                [t("Reference rate over"), `${tie.window[0]} .. ${tie.window[1]} (${t("this product: {a} .. {b}", { a: tie.target_period[0], b: tie.target_period[1] })})`],
                [t("Common cells"), `${fmt.int(tie.n_cells)} · ${t("correlation")} ${fmt.num(tie.corr, 2)} · ${t("gain")} ${fmt.num(tie.slope, 2)}`],
                [t("Median vertical rate"), `${t("reference")} ${fmt.vel(tie.median_reference_mm_yr)} · ${t("this product")} ${fmt.vel(tie.median_target_mm_yr)} mm/yr`],
                [t("Correction"), `${fmt.vel(tie.calibration.rate_offset_mm_yr)} mm/yr LOS (${fmt.vel(tie.calibration.vertical_offset_mm_yr)} ${t("vertical")}) · ${t("spread over the cells")} ±${fmt.num(tie.spread_mm_yr)}`],
              ] as [string, string][]
            ).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="shrink-0 text-muted">{k}</span>
                <span className="min-w-0 font-mono text-[11.5px] text-ink-2">{v}</span>
              </div>
            ))}
            {tie.warnings.map((w) => (
              <div key={w} className="rounded-md bg-warn-bg px-2 py-1 text-warn-ink sm:col-span-2">
                {ts(w)}
              </div>
            ))}
            {active?.source === "gnss" && (
              <div className="text-muted sm:col-span-2">{t("This product has its own GNSS calibration: it is the one applied, the tie is kept for comparison.")}</div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
