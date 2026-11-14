import { ArrowRight, Download, GitCompareArrows, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, tileUrl } from "../api/client";
import { useAOIs, useCategories, useChangeRun, useChangeRuns, useExperiments, useInvalidate, useProducts, useRegionsGeo } from "../api/hooks";
import type { ChangeRun, ExportRow, RegionProps } from "../api/types";
import { DeltaRamp, LegendRow } from "../components/map/Legend";
import { MapView, type MapLayer } from "../components/map/MapView";
import { ObservationSelect } from "../components/ObservationSelect";
import { Button, Card, Empty, Field, Input, JobProgress, KV, Notice, PageHeader, Select, StatusBadge, Tabs } from "../components/ui";
import { EVIDENCE, fmtDate, fmtDateTime, fmtHa, fmtNum, fmtPct, signed } from "../lib/format";
import { useApp } from "../stores/app";

const PARAM_LABELS: Record<string, string> = {
  forest_hi: "Forest if P(tree) ≥",
  forest_lo: "Non-forest if P(tree) ≤",
  min_delta: "Minimum |ΔP(tree)|",
  max_entropy: "Max normalised entropy",
  spectral_ndvi_drop: "ΔNDVI support threshold",
  spectral_nbr_drop: "ΔNBR support threshold",
  min_mapping_unit_ha: "Minimum mapping unit (ha)",
  opening_px: "Edge suppression (px)",
  coreg_max_shift_px: "Max residual shift (px)",
};

export default function ChangePage() {
  const aoiId = useApp((s) => s.aoiId);
  const { data: aois } = useAOIs();
  const aoi = aois?.find((a) => a.id === aoiId);
  const { data: products } = useProducts(aoiId);
  const { data: runs } = useChangeRuns(aoiId);
  const { data: exps } = useExperiments();
  const { data: cats } = useCategories();
  const invalidate = useInvalidate();
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [extraId, setExtraId] = useState("");
  const [expId, setExpId] = useState("");
  const [params, setParams] = useState<Record<string, number | boolean>>({});
  const [showParams, setShowParams] = useState(false);
  const [selectedRun, setSelectedRun] = useState("");
  const [layer, setLayer] = useState<"change" | "delta" | "before" | "after">("change");
  const [err, setErr] = useState<string | null>(null);
  const [exportRow, setExportRow] = useState<ExportRow | null>(null);
  const [sel, setSel] = useState<RegionProps | null>(null);

  const runId = selectedRun || runs?.[0]?.id || "";
  const { data: run } = useChangeRun(runId);
  const { data: fc } = useRegionsGeo(run?.status === "succeeded" ? run.id : null);
  const trained = exps?.filter((e) => e.checkpoint) ?? [];
  const defaults = cats?.default_params ?? {};

  const submit = async () => {
    setErr(null);
    try {
      const r = await api.post<ChangeRun>("/change-runs", {
        aoi_id: aoiId,
        before_id: beforeId,
        after_id: afterId,
        extra_ids: extraId ? [extraId] : [],
        experiment_id: expId || undefined,
        params,
      });
      setSelectedRun(r.id);
      invalidate("change-runs", "overview");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const doExport = async (format: string) => {
    if (!run) return;
    try {
      setExportRow(await api.post<ExportRow>("/exports", { source_type: "change_run", source_id: run.id, format }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const layers = useMemo<MapLayer[]>(() => {
    if (!run || run.status !== "succeeded") return [];
    const l: MapLayer[] = [
      { id: "sylva-base", kind: "raster", tiles: tileUrl("product", layer === "before" ? run.before_id : run.after_id, "truecolor") },
    ];
    if (layer === "change") l.push({ id: "sylva-ch", kind: "raster", tiles: tileUrl("change", run.id, "change"), opacity: 0.85 });
    if (layer === "delta") l.push({ id: "sylva-ch", kind: "raster", tiles: tileUrl("change", run.id, "delta"), opacity: 0.85 });
    if (fc) l.push({ id: "sylva-regions", kind: "regions", data: fc, selectedId: sel?.id });
    if (aoi) l.push({ id: "sylva-aoi", kind: "outline", data: { type: "Feature", geometry: aoi.geometry, properties: {} } });
    return l;
  }, [run, layer, fc, aoi, sel?.id]);

  const s = run?.summary;
  const h = run?.headline;
  const lossFeats = (fc?.features ?? []).filter((f) => f.properties?.change_type === "potential_loss");

  return (
    <div>
      <PageHeader
        eyebrow="Change detection centre"
        title="Multi-date forest change"
        description="Compare calibrated U-Net forest probabilities from an earlier and a later observation on the same 10 m grid. Pixels need high P(tree) before and low P(tree) after (plus quality checks) to count as potential forest loss. Results are potential changes, not verified deforestation."
      />
      {err && (
        <div className="mb-4">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card title="New analysis" subtitle={aoi?.name}>
            <div className="space-y-3">
              <Field label="Earlier observation">
                <ObservationSelect products={products} value={beforeId} onChange={setBeforeId} aria-label="Earlier observation" />
              </Field>
              <Field label="Later observation">
                <ObservationSelect products={products} value={afterId} onChange={setAfterId} aria-label="Later observation" />
              </Field>
              <Field label="Persistence check (optional)" hint="A third, later observation: loss is 'persistent' if still non-forest">
                <ObservationSelect products={products} value={extraId} onChange={setExtraId} placeholder="None" />
              </Field>
              <Field label="Model">
                <Select value={expId} onChange={(e) => setExpId(e.target.value)}>
                  <option value="">Active model</option>
                  {trained.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name} · val mIoU {e.best_val_miou?.toFixed(3)}
                    </option>
                  ))}
                </Select>
              </Field>
              <button className="flex items-center gap-1.5 text-xs text-muted hover:text-ink" onClick={() => setShowParams((v) => !v)}>
                <SlidersHorizontal className="h-3.5 w-3.5" /> Decision thresholds
              </button>
              {showParams && (
                <div className="grid grid-cols-2 gap-2 rounded-lg border border-line bg-sunken p-2.5">
                  {Object.entries(PARAM_LABELS).map(([k, label]) => (
                    <Field key={k} label={label}>
                      <Input
                        type="number"
                        step="0.05"
                        value={String(params[k] ?? defaults[k] ?? "")}
                        onChange={(e) => setParams((p) => ({ ...p, [k]: Number(e.target.value) }))}
                      />
                    </Field>
                  ))}
                  <label className="col-span-2 flex items-center gap-2 text-[11px] text-ink-2">
                    <input
                      type="checkbox"
                      checked={Boolean(params.require_spectral_support ?? defaults.require_spectral_support)}
                      onChange={(e) => setParams((p) => ({ ...p, require_spectral_support: e.target.checked }))}
                    />
                    Require spectral support (ΔNDVI or ΔNBR drop) for loss
                  </label>
                </div>
              )}
              <Button variant="primary" className="w-full" disabled={!beforeId || !afterId || beforeId === afterId} onClick={submit}>
                <GitCompareArrows className="h-4 w-4" /> Run multi-date analysis
              </Button>
              {products && products.length < 2 && (
                <Notice tone="info">
                  At least two observations are needed. Ingest them in the <Link to="/explorer" className="underline">Image Explorer</Link>; prefer the same
                  season (e.g. both dry season) to limit phenological change.
                </Notice>
              )}
              {run && ["queued", "running"].includes(run.status) && <JobProgress jobId={run.job_id} onDone={() => invalidate("change-runs", "change-run", "overview")} />}
            </div>
          </Card>
          <Card title="Previous analyses">
            {!runs?.length ? (
              <Empty title="No analyses yet" />
            ) : (
              <ul className="divide-y divide-line">
                {runs.map((r) => (
                  <li key={r.id}>
                    <button className="flex w-full items-center justify-between gap-2 py-2 text-left text-[12.5px]" onClick={() => setSelectedRun(r.id)}>
                      <span>
                        <span className={r.id === runId ? "text-accent-strong" : "text-ink"}>
                          {fmtDate(r.before_acquired)} → {fmtDate(r.after_acquired)}
                        </span>
                        <span className="num block text-[10px] text-faint">
                          {r.id} · {fmtDateTime(r.created_at)}
                        </span>
                      </span>
                      <StatusBadge status={r.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card
            bodyClass="p-0"
            title={run ? `${fmtDate(run.before_acquired)} → ${fmtDate(run.after_acquired)}` : "Results"}
            subtitle={run ? `Run ${run.id} · model ${run.experiment_id}` : undefined}
            actions={
              <Tabs
                value={layer}
                onChange={setLayer}
                items={[
                  { value: "change", label: "Categories" },
                  { value: "delta", label: "ΔP(tree)" },
                  { value: "before", label: "Earlier" },
                  { value: "after", label: "Later" },
                ]}
              />
            }
          >
            <div className="relative h-[520px] overflow-hidden rounded-b-xl">
              {run?.status === "succeeded" ? (
                <MapView layers={layers} fitBounds={aoi?.bbox} fitKey={run.id} onFeatureClick={(f) => setSel(f.properties as unknown as RegionProps)} />
              ) : (
                <div className="flex h-full items-center justify-center">
                  <Empty title={run ? `Run ${run.status}` : "No analysis selected"}>
                    {run?.status === "failed" ? "See job log in History." : "Select two observations and run the analysis."}
                  </Empty>
                </div>
              )}
              {run?.status === "succeeded" && s && (
                <div className="absolute bottom-3 left-3 w-60 space-y-1.5 rounded-lg border border-line bg-canvas/90 p-3">
                  {layer === "delta" ? (
                    <DeltaRamp />
                  ) : (
                    cats?.categories
                      .filter((c) => c.key !== "stable_nonforest")
                      .map((c) => (
                        <LegendRow
                          key={c.key}
                          swatch={c.key === "uncertain" ? "hatch-uncertain" : c.key === "invalid" ? "hatch-invalid" : ""}
                          label={c.name}
                          value={fmtHa(s.category_areas[c.key]?.hectares)}
                        />
                      ))
                  )}
                </div>
              )}
              {sel && (
                <div className="absolute right-14 top-3 w-72 space-y-1.5 rounded-lg border border-line bg-surface/95 p-3 text-[12px]">
                  <div className="num text-ink">{sel.id}</div>
                  <div className={`w-fit rounded-md border px-1.5 py-0.5 text-[11px] ${EVIDENCE[sel.evidence_level]?.tone}`}>{EVIDENCE[sel.evidence_level]?.label}</div>
                  <KV
                    rows={[
                      ["Area", `${fmtHa(sel.area_ha)} ± ${sel.area_uncertainty_ha.toFixed(2)}`],
                      ["P(tree)", `${sel.p_tree_before?.toFixed(2)} → ${sel.p_tree_after?.toFixed(2)}`],
                      ["ΔNBR", signed(sel.delta_nbr, 3)],
                    ]}
                  />
                  <Link className="flex items-center gap-1 text-accent-strong hover:underline" to={`/investigate/${sel.id}`}>
                    Investigate <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              )}
            </div>
          </Card>

          {run?.status === "succeeded" && s && h && (
            <>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card title="Forest cover estimate">
                  <KV
                    rows={[
                      ["Earlier (predicted)", fmtHa(h.tree_cover_before_ha)],
                      ["Later (predicted)", fmtHa(h.tree_cover_after_ha)],
                      ["Valid on both dates", fmtPct(h.valid_fraction_both_dates)],
                    ]}
                  />
                </Card>
                <Card title="Potential change">
                  <KV
                    rows={[
                      [<span className="text-loss">Potential loss</span>, `${fmtHa(h.potential_loss_ha)} ± ${fmtNum(h.potential_loss_uncertainty_ha, 1)}`],
                      ["Loss regions (≥ MMU)", h.n_loss_regions],
                      [<span className="text-gain">Potential gain</span>, fmtHa(h.potential_gain_ha)],
                      ["Uncertain pixels", fmtHa(s.category_areas.uncertain.hectares)],
                    ]}
                  />
                </Card>
                <Card title="Quality & provenance">
                  <KV
                    rows={[
                      ["Residual shift", `${s.coregistration.magnitude.toFixed(2)} px${s.coregistration.applied ? " (corrected)" : ""}`],
                      ["Calibrated model", s.calibrated ? "yes (temperature scaling)" : "no"],
                      ["Checkpoint", <span className="num text-[10px]">{s.checkpoint_sha256.slice(0, 12)}…</span>],
                      ["Reference", <span className="text-[11px]">{s.hansen_reference ?? "—"}</span>],
                    ]}
                  />
                </Card>
              </div>
              <Card
                title={`Potential forest-loss regions (${lossFeats.length})`}
                subtitle={s.area_note}
                actions={
                  <div className="flex flex-wrap gap-1.5">
                    {["geojson", "gpkg", "csv", "geotiff", "bundle"].map((f) => (
                      <Button key={f} size="sm" onClick={() => doExport(f)}>
                        <Download className="h-3 w-3" /> {f}
                      </Button>
                    ))}
                  </div>
                }
              >
                {exportRow && (
                  <a className="mb-3 block text-xs text-accent-strong underline" href={exportRow.download_url}>
                    Download export {exportRow.id} ({exportRow.format})
                  </a>
                )}
                <div className="max-h-80 overflow-y-auto">
                  <table className="w-full text-[12px]">
                    <thead className="sticky top-0 bg-surface text-left text-[10.5px] uppercase tracking-[0.08em] text-muted">
                      <tr>
                        <th className="py-1.5">Region</th>
                        <th>Area</th>
                        <th>P(tree) before → after</th>
                        <th>ΔNDVI</th>
                        <th>ΔNBR</th>
                        <th>Hansen</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {lossFeats
                        .map((f) => f.properties as unknown as RegionProps)
                        .sort((a, b) => b.area_ha - a.area_ha)
                        .map((p) => (
                          <tr key={p.id} className="hover:bg-raised">
                            <td className="num py-1.5">
                              <Link to={`/investigate/${p.id}`} className="text-ink hover:text-accent-strong">
                                {p.id}
                              </Link>
                            </td>
                            <td className="num">{fmtHa(p.area_ha)}</td>
                            <td className="num">
                              {p.p_tree_before?.toFixed(2)} → {p.p_tree_after?.toFixed(2)}
                            </td>
                            <td className="num">{signed(p.delta_ndvi, 2)}</td>
                            <td className="num">{signed(p.delta_nbr, 2)}</td>
                            <td className="num">{fmtPct(p.hansen_loss_fraction ?? null, 0)}</td>
                            <td>
                              <span className={`rounded border px-1 py-0.5 text-[10px] ${EVIDENCE[p.evidence_level]?.tone}`}>{EVIDENCE[p.evidence_level]?.label}</span>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
