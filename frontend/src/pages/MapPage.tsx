import clsx from "clsx";
import { Crosshair, ExternalLink, Eye, EyeOff, Layers, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, tileUrl } from "../api/client";
import { useAOIs, useChangeRuns, useProducts, useRegionsGeo, useSegmentations } from "../api/hooks";
import type { RegionProps } from "../api/types";
import { ClassLegend, DeltaRamp, LegendRow, ProbabilityRamp } from "../components/map/Legend";
import { MapView, type MapLayer } from "../components/map/MapView";
import { SwipeCompare } from "../components/map/SwipeCompare";
import { ObservationSelect } from "../components/ObservationSelect";
import { Badge, Select, Tabs } from "../components/ui";
import { EVIDENCE, fmtCoord, fmtDate, fmtHa, fmtPct, signed } from "../lib/format";
import { useApp } from "../stores/app";

type LayerKey = "imagery" | "prob" | "class" | "change" | "delta" | "regions" | "worldcover" | "hansen" | "aoi";

const LAYER_META: Record<LayerKey, { label: string; group: string }> = {
  imagery: { label: "Satellite imagery", group: "Observation" },
  prob: { label: "Forest probability (later)", group: "Model" },
  class: { label: "Segmentation classes", group: "Model" },
  change: { label: "Change categories", group: "Change" },
  delta: { label: "Δ forest probability", group: "Change" },
  regions: { label: "Potential change regions", group: "Change" },
  worldcover: { label: "ESA WorldCover 2021", group: "Reference" },
  hansen: { label: "Hansen GFC loss year", group: "Reference" },
  aoi: { label: "AOI boundary", group: "Context" },
};

export default function MapPage() {
  const aoiId = useApp((s) => s.aoiId);
  const [params, setParams] = useSearchParams();
  const { data: aois } = useAOIs();
  const aoi = aois?.find((a) => a.id === aoiId);
  const { data: runs } = useChangeRuns(aoiId);
  const { data: products } = useProducts(aoiId);
  const { data: segs } = useSegmentations(aoiId);
  const doneRuns = runs?.filter((r) => r.status === "succeeded") ?? [];
  const runId = params.get("run") ?? doneRuns[0]?.id ?? "";
  const run = doneRuns.find((r) => r.id === runId);
  const [obsId, setObsId] = useState("");
  const [render, setRender] = useState("truecolor");
  const [mode, setMode] = useState<"single" | "swipe">("single");
  const [vis, setVis] = useState<Record<LayerKey, boolean>>({
    imagery: true,
    prob: false,
    class: false,
    change: true,
    delta: false,
    regions: true,
    worldcover: false,
    hansen: false,
    aoi: true,
  });
  const [opacity, setOpacity] = useState<Record<string, number>>({ change: 0.8, prob: 0.8, class: 0.75, delta: 0.8, worldcover: 0.7, hansen: 0.85 });
  const [refReady, setRefReady] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<RegionProps | null>(null);
  const [pixel, setPixel] = useState<Record<string, any> | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const { data: regionsFc } = useRegionsGeo(run?.id, !!run);
  const focus = useApp((s) => s.focus);

  const imageryId = obsId || run?.after_id || products?.[products.length - 1]?.id || "";
  const segForObs = segs?.find((s) => s.product_id === imageryId && s.status === "succeeded");

  useEffect(() => {
    if (!aoiId) return;
    for (const [k, layer] of [
      ["worldcover", "worldcover2021"],
      ["hansen", "hansen_lossyear"],
    ] as const) {
      if (vis[k] && !refReady[layer]) {
        api.post(`/aois/${aoiId}/reference/${layer}`).then(() => setRefReady((r) => ({ ...r, [layer]: true }))).catch(() => undefined);
      }
    }
  }, [vis, aoiId, refReady]);

  const layers = useMemo<MapLayer[]>(() => {
    const l: MapLayer[] = [];
    if (imageryId) l.push({ id: "sylva-img", kind: "raster", tiles: tileUrl("product", imageryId, render), visible: vis.imagery });
    if (aoiId && refReady.worldcover2021)
      l.push({ id: "sylva-wc", kind: "raster", tiles: tileUrl("aoiref", `${aoiId}:worldcover2021`), visible: vis.worldcover, opacity: opacity.worldcover });
    if (aoiId && refReady.hansen_lossyear)
      l.push({ id: "sylva-hansen", kind: "raster", tiles: tileUrl("aoiref", `${aoiId}:hansen_lossyear`), visible: vis.hansen, opacity: opacity.hansen });
    if (run) {
      l.push({ id: "sylva-prob", kind: "raster", tiles: tileUrl("change", run.id, "prob_after"), visible: vis.prob, opacity: opacity.prob });
      l.push({ id: "sylva-delta", kind: "raster", tiles: tileUrl("change", run.id, "delta"), visible: vis.delta, opacity: opacity.delta });
      l.push({ id: "sylva-change", kind: "raster", tiles: tileUrl("change", run.id, "change"), visible: vis.change, opacity: opacity.change });
    }
    if (segForObs) l.push({ id: "sylva-class", kind: "raster", tiles: tileUrl("seg", segForObs.id, "class"), visible: vis.class, opacity: opacity.class });
    if (run && regionsFc) l.push({ id: "sylva-regions", kind: "regions", data: regionsFc, visible: vis.regions, selectedId: selected?.id });
    if (aoi) l.push({ id: "sylva-aoi", kind: "outline", data: { type: "Feature", geometry: aoi.geometry, properties: {} }, visible: vis.aoi });
    return l;
  }, [imageryId, render, vis, opacity, run, regionsFc, aoi, aoiId, refReady, segForObs, selected?.id]);

  const fit = focus?.bbox ?? (selected ? null : aoi?.bbox);

  const onMapClick = async (ll: { lng: number; lat: number }) => {
    if (!imageryId) return;
    setSelected(null);
    try {
      const segParam = segForObs ? `&segmentation_id=${segForObs.id}` : "";
      const r = await api.get<Record<string, any>>(`/products/${imageryId}/pixel?lon=${ll.lng}&lat=${ll.lat}${segParam}`);
      setPixel(r);
    } catch {
      setPixel(null);
    }
  };

  const layerRow = (k: LayerKey, available: boolean, hint?: string) => (
    <div key={k} className={clsx("rounded-md px-2 py-1.5", !available && "opacity-45")}>
      <div className="flex items-center justify-between gap-2">
        <button
          disabled={!available}
          onClick={() => setVis((v) => ({ ...v, [k]: !v[k] }))}
          className="flex items-center gap-2 text-left text-[12px] text-ink-2 hover:text-ink disabled:cursor-not-allowed"
          aria-pressed={vis[k]}
        >
          {vis[k] && available ? <Eye className="h-3.5 w-3.5 text-accent-strong" /> : <EyeOff className="h-3.5 w-3.5" />}
          {LAYER_META[k].label}
        </button>
      </div>
      {!available && hint && <div className="pl-5.5 text-[10px] text-faint">{hint}</div>}
      {available && vis[k] && opacity[k] !== undefined && (
        <input
          aria-label={`${LAYER_META[k].label} opacity`}
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={opacity[k]}
          onChange={(e) => setOpacity((o) => ({ ...o, [k]: Number(e.target.value) }))}
          className="mt-1 h-1 w-full accent-[#3faf86]"
        />
      )}
    </div>
  );

  const swipeLeft: MapLayer[] = run
    ? [
        { id: "sylva-l-img", kind: "raster", tiles: tileUrl("product", run.before_id, render) },
        ...(aoi ? [{ id: "sylva-l-aoi", kind: "outline" as const, data: { type: "Feature" as const, geometry: aoi.geometry, properties: {} } }] : []),
      ]
    : [];
  const swipeRight: MapLayer[] = run
    ? [
        { id: "sylva-r-img", kind: "raster", tiles: tileUrl("product", run.after_id, render) },
        ...(regionsFc && vis.regions ? [{ id: "sylva-r-regions", kind: "regions" as const, data: regionsFc, selectedId: selected?.id }] : []),
      ]
    : [];

  return (
    <div className="relative h-full">
      {mode === "swipe" && run ? (
        <SwipeCompare
          left={swipeLeft}
          right={swipeRight}
          leftLabel={`Earlier · ${fmtDate(run.before_acquired)}`}
          rightLabel={`Later · ${fmtDate(run.after_acquired)}`}
          fitBounds={aoi?.bbox}
          fitKey={aoi?.id}
        />
      ) : (
        <MapView
          layers={layers}
          fitBounds={fit}
          fitKey={focus?.key ?? aoi?.id}
          onFeatureClick={(f) => {
            setPixel(null);
            setSelected(f.properties as unknown as RegionProps);
          }}
          onMapClick={onMapClick}
        />
      )}

      {/* Layer panel */}
      <div className={clsx("absolute left-3 top-3 z-10 w-72 rounded-xl border border-line bg-surface/95 shadow-xl", !panelOpen && "w-auto")}>
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <button className="flex items-center gap-2 text-[12px] font-semibold" onClick={() => setPanelOpen((o) => !o)}>
            <Layers className="h-4 w-4 text-accent-strong" /> Layers
          </button>
          {panelOpen && (
            <Tabs
              value={mode}
              onChange={setMode}
              items={[
                { value: "single", label: "Map" },
                { value: "swipe", label: "Swipe" },
              ]}
            />
          )}
        </div>
        {panelOpen && (
          <div className="max-h-[calc(100vh-11rem)] space-y-3 overflow-y-auto p-3">
            <div className="space-y-2">
              <label className="block text-[10px] uppercase tracking-[0.12em] text-muted">Change analysis</label>
              <Select value={runId} onChange={(e) => setParams(e.target.value ? { run: e.target.value } : {})} aria-label="Change run">
                <option value="">None</option>
                {doneRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    {fmtDate(r.before_acquired)} → {fmtDate(r.after_acquired)}
                  </option>
                ))}
              </Select>
              <label className="block text-[10px] uppercase tracking-[0.12em] text-muted">Imagery</label>
              <ObservationSelect products={products} value={obsId} onChange={setObsId} placeholder={run ? "Later observation of run" : "Latest observation"} />
              <Select value={render} onChange={(e) => setRender(e.target.value)} aria-label="Imagery rendering">
                <option value="truecolor">True colour (B4 B3 B2)</option>
                <option value="falsecolor">False colour (B8 B4 B3)</option>
                <option value="swir">SWIR composite (B12 B8A B4)</option>
                <option value="ndvi">NDVI</option>
              </Select>
            </div>
            {mode === "single" && (
              <div className="space-y-0.5">
                {(["Observation", "Model", "Change", "Reference", "Context"] as const).map((g) => (
                  <div key={g}>
                    <div className="px-2 pb-0.5 pt-2 text-[10px] uppercase tracking-[0.12em] text-faint">{g}</div>
                    {(Object.keys(LAYER_META) as LayerKey[])
                      .filter((k) => LAYER_META[k].group === g)
                      .map((k) =>
                        layerRow(
                          k,
                          k === "imagery"
                            ? !!imageryId
                            : k === "class"
                              ? !!segForObs
                              : ["prob", "change", "delta", "regions"].includes(k)
                                ? !!run
                                : true,
                          k === "class" ? "Run segmentation on this observation" : "Select a completed change analysis",
                        ),
                      )}
                  </div>
                ))}
              </div>
            )}
            <div className="space-y-2 border-t border-line pt-3">
              {vis.change && run && (
                <div className="space-y-1">
                  <LegendRow swatch="bg-loss" label="Potential forest loss" />
                  <LegendRow swatch="bg-gain" label="Potential vegetation gain" />
                  <LegendRow swatch="hatch-uncertain" label="Uncertain change" />
                  <LegendRow swatch="bg-forest/50" label="Stable forest" />
                  <LegendRow swatch="hatch-invalid" label="Cloud / invalid" />
                </div>
              )}
              {vis.prob && run && <ProbabilityRamp />}
              {vis.delta && run && <DeltaRamp />}
              {vis.class && segForObs && <ClassLegend />}
              {vis.hansen && <div className="text-[10px] text-muted">Hansen loss year: yellow (2001) → red (2025), 30 m</div>}
            </div>
          </div>
        )}
      </div>

      {/* Inspector */}
      {(selected || pixel) && (
        <div className="absolute right-14 top-3 z-10 w-80 rounded-xl border border-line bg-surface/95 shadow-xl" data-testid="inspector">
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <span className="flex items-center gap-2 text-[12px] font-semibold">
              <Crosshair className="h-4 w-4 text-accent-strong" />
              {selected ? "Detected region" : "Pixel inspector"}
            </span>
            <button aria-label="Close" onClick={() => (setSelected(null), setPixel(null))}>
              <X className="h-4 w-4 text-muted hover:text-ink" />
            </button>
          </div>
          {selected && (
            <div className="space-y-2 p-3 text-[12px]">
              <div className="num text-[13px] text-ink">{selected.id}</div>
              <div className="flex flex-wrap gap-1">
                <Badge className={selected.change_type === "potential_gain" ? "border-gain/50 text-gain" : "border-loss/50 text-loss"}>
                  {selected.change_type === "potential_gain" ? "Potential gain" : "Potential forest loss"}
                </Badge>
                <Badge className={EVIDENCE[selected.evidence_level]?.tone}>{EVIDENCE[selected.evidence_level]?.label}</Badge>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="text-muted">Area</dt>
                <dd className="num text-right">
                  {fmtHa(selected.area_ha)} <span className="text-muted">± {selected.area_uncertainty_ha?.toFixed(2)}</span>
                </dd>
                <dt className="text-muted">Location</dt>
                <dd className="num text-right text-[11px]">{fmtCoord(selected.centroid_lon, selected.centroid_lat)}</dd>
                <dt className="text-muted">P(tree) before → after</dt>
                <dd className="num text-right">
                  {selected.p_tree_before?.toFixed(2)} → {selected.p_tree_after?.toFixed(2)}
                </dd>
                <dt className="text-muted">ΔNDVI / ΔNBR</dt>
                <dd className="num text-right">
                  {signed(selected.delta_ndvi, 2)} / {signed(selected.delta_nbr, 2)}
                </dd>
                <dt className="text-muted">Hansen loss overlap</dt>
                <dd className="num text-right">{fmtPct(selected.hansen_loss_fraction ?? null, 0)}</dd>
              </dl>
              <Link to={`/investigate/${selected.id}`} className="flex items-center gap-1 text-accent-strong hover:underline">
                Investigate region <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
          )}
          {pixel && !selected && (
            <div className="space-y-2 p-3 text-[12px]">
              <div className="num text-[11px] text-muted">
                {fmtCoord(pixel.lon, pixel.lat)} · row {pixel.row} col {pixel.col}
              </div>
              <div>
                Quality: <span className={pixel.quality === "valid" ? "text-accent-strong" : "text-uncertain"}>{pixel.quality}</span>
              </div>
              <div className="grid grid-cols-5 gap-1">
                {Object.entries(pixel.reflectance as Record<string, number | null>).map(([b, v]) => (
                  <div key={b} className="rounded bg-sunken px-1 py-0.5 text-center">
                    <div className="text-[9px] text-faint">{b}</div>
                    <div className="num text-[11px]">{v?.toFixed(3) ?? "—"}</div>
                  </div>
                ))}
              </div>
              <div className="num flex justify-between text-[11px]">
                {Object.entries(pixel.indices as Record<string, number | null>).map(([k, v]) => (
                  <span key={k}>
                    <span className="text-muted">{k}</span> {v?.toFixed(3) ?? "—"}
                  </span>
                ))}
              </div>
              {pixel.probabilities ? (
                <div className="space-y-0.5">
                  {Object.entries(pixel.probabilities as Record<string, number | null>).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-[11px]">
                      <span className="w-28 text-muted">{k}</span>
                      <div className="h-1.5 flex-1 rounded bg-sunken">
                        <div className="h-full rounded bg-accent" style={{ width: `${(v ?? 0) * 100}%` }} />
                      </div>
                      <span className="num w-9 text-right">{v?.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[11px] text-faint">Run segmentation on this observation to inspect model probabilities.</div>
              )}
            </div>
          )}
        </div>
      )}

      {!imageryId && (
        <div className="absolute inset-x-0 bottom-8 mx-auto w-fit rounded-lg border border-line bg-surface/95 px-4 py-2 text-xs text-muted">
          No observations for this AOI yet. Add one in the <Link to="/explorer" className="text-accent-strong underline">Image Explorer</Link>.
        </div>
      )}
    </div>
  );
}
