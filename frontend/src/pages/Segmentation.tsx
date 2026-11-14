import { Download, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { api, tileUrl } from "../api/client";
import { useAOIs, useExperiments, useInvalidate, useProducts, useSegmentations, useSettings } from "../api/hooks";
import type { ExportRow, Segmentation } from "../api/types";
import { ClassLegend, ProbabilityRamp } from "../components/map/Legend";
import { MapView, type MapLayer } from "../components/map/MapView";
import { SwipeCompare } from "../components/map/SwipeCompare";
import { ObservationSelect } from "../components/ObservationSelect";
import { Button, Card, Empty, Field, JobProgress, KV, Notice, PageHeader, Select, StatusBadge, Tabs } from "../components/ui";
import { CLASS_COLORS, fmtDate, fmtHa, fmtPct } from "../lib/format";
import { useApp } from "../stores/app";

const KEYS = ["tree", "other_veg", "bare", "water", "built"];
const NAMES = ["Tree cover", "Other vegetation", "Bare / sparse", "Water", "Built-up"];

export default function SegmentationPage() {
  const aoiId = useApp((s) => s.aoiId);
  const { data: aois } = useAOIs();
  const aoi = aois?.find((a) => a.id === aoiId);
  const { data: products } = useProducts(aoiId);
  const { data: segs } = useSegmentations(aoiId);
  const { data: exps } = useExperiments();
  const { data: settings } = useSettings();
  const invalidate = useInvalidate();
  const [productId, setProductId] = useState("");
  const [expId, setExpId] = useState("");
  const [selectedSeg, setSelectedSeg] = useState<string>("");
  const [layer, setLayer] = useState<"prob" | "class" | "entropy">("prob");
  const [view, setView] = useState<"overlay" | "swipe">("overlay");
  const [opacity, setOpacity] = useState(0.8);
  const [err, setErr] = useState<string | null>(null);
  const [pixel, setPixel] = useState<Record<string, any> | null>(null);
  const [exportRow, setExportRow] = useState<ExportRow | null>(null);

  const trained = exps?.filter((e) => e.checkpoint) ?? [];
  const seg: Segmentation | undefined = segs?.find((s) => s.id === selectedSeg) ?? segs?.find((s) => s.status === "succeeded");
  const segProduct = products?.find((p) => p.id === seg?.product_id);

  const run = async () => {
    setErr(null);
    try {
      const s = await api.post<Segmentation>("/segmentations", { product_id: productId, experiment_id: expId || undefined });
      setSelectedSeg(s.id);
      invalidate("segmentations");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const doExport = async () => {
    if (!seg) return;
    try {
      setExportRow(await api.post<ExportRow>("/exports", { source_type: "segmentation", source_id: seg.id, format: "bundle" }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const overlay: MapLayer[] = useMemo(() => {
    const l: MapLayer[] = [];
    if (segProduct) l.push({ id: "sylva-img", kind: "raster", tiles: tileUrl("product", segProduct.id, "truecolor") });
    if (seg?.status === "succeeded") l.push({ id: "sylva-seg", kind: "raster", tiles: tileUrl("seg", seg.id, layer), opacity });
    if (aoi) l.push({ id: "sylva-aoi", kind: "outline", data: { type: "Feature", geometry: aoi.geometry, properties: {} } });
    return l;
  }, [segProduct, seg, layer, opacity, aoi]);

  const inspect = async (ll: { lng: number; lat: number }) => {
    if (!segProduct || !seg) return;
    try {
      setPixel(await api.get(`/products/${segProduct.id}/pixel?lon=${ll.lng}&lat=${ll.lat}&segmentation_id=${seg.id}`));
    } catch {
      setPixel(null);
    }
  };

  const s = seg?.summary;
  return (
    <div>
      <PageHeader
        eyebrow="Forest segmentation centre"
        title="U-Net tree-cover segmentation"
        description="Run the project's own U-Net (trained from scratch on this project's data) on an observation to produce calibrated per-pixel class probabilities. Predictions are the model's estimate of tree cover, not reference or ground-truth tree cover."
      />
      {err && (
        <div className="mb-4">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card title="New segmentation">
            <div className="space-y-3">
              <Field label="Observation">
                <ObservationSelect products={products} value={productId} onChange={setProductId} />
              </Field>
              <Field label="Model" hint="Default: the active model">
                <Select value={expId} onChange={(e) => setExpId(e.target.value)}>
                  <option value="">Active model</option>
                  {trained.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name} · val mIoU {e.best_val_miou?.toFixed(3)} {e.id === settings?.active_experiment_id ? "(active)" : ""}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button variant="primary" className="w-full" disabled={!productId || (!trained.length && !settings?.active_experiment_id)} onClick={run}>
                <Play className="h-4 w-4" /> Run U-Net
              </Button>
              {!trained.length && <Notice tone="warn">No trained model yet. Train one in the Model Laboratory.</Notice>}
              {seg && ["queued", "running"].includes(seg.status) && <JobProgress jobId={seg.job_id} onDone={() => invalidate("segmentations")} />}
            </div>
          </Card>
          <Card title="Segmentation runs">
            {!segs?.length ? (
              <Empty title="No runs yet" />
            ) : (
              <ul className="divide-y divide-line">
                {segs.map((r) => (
                  <li key={r.id}>
                    <button className="flex w-full items-center justify-between py-2 text-left text-[12.5px]" onClick={() => setSelectedSeg(r.id)}>
                      <span>
                        <span className={r.id === seg?.id ? "text-accent-strong" : "text-ink"}>{fmtDate(r.acquired)}</span>
                        <span className="num block text-[10px] text-faint">{r.id}</span>
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
            title={seg ? `Prediction · ${fmtDate(seg.acquired)}` : "Prediction"}
            actions={
              <div className="flex items-center gap-2">
                <Tabs
                  value={layer}
                  onChange={setLayer}
                  items={[
                    { value: "prob", label: "P(tree)" },
                    { value: "class", label: "Classes" },
                    { value: "entropy", label: "Uncertainty" },
                  ]}
                />
                <Tabs
                  value={view}
                  onChange={setView}
                  items={[
                    { value: "overlay", label: "Overlay" },
                    { value: "swipe", label: "Swipe" },
                  ]}
                />
              </div>
            }
          >
            <div className="relative h-[520px] overflow-hidden rounded-b-xl">
              {seg?.status === "succeeded" && segProduct ? (
                view === "swipe" ? (
                  <SwipeCompare
                    left={[{ id: "sylva-l", kind: "raster", tiles: tileUrl("product", segProduct.id, "truecolor") }]}
                    right={[{ id: "sylva-r", kind: "raster", tiles: tileUrl("seg", seg.id, layer) }]}
                    leftLabel="Sentinel-2 true colour"
                    rightLabel={layer === "prob" ? "U-Net P(tree)" : layer === "class" ? "U-Net classes" : "Predictive entropy"}
                    fitBounds={aoi?.bbox}
                    fitKey={seg.id}
                  />
                ) : (
                  <MapView layers={overlay} fitBounds={aoi?.bbox} fitKey={seg.id} onMapClick={inspect} />
                )
              ) : (
                <div className="flex h-full items-center justify-center">
                  <Empty title="No completed segmentation">Choose an observation and run the U-Net.</Empty>
                </div>
              )}
              {seg?.status === "succeeded" && view === "overlay" && (
                <div className="absolute bottom-3 left-3 w-52 space-y-2 rounded-lg border border-line bg-canvas/90 p-3">
                  {layer === "prob" && <ProbabilityRamp />}
                  {layer === "class" && <ClassLegend />}
                  {layer === "entropy" && <div className="text-[11px] text-ink-2">Normalised entropy: dark = confident, bright = uncertain</div>}
                  <input aria-label="Overlay opacity" type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} className="w-full accent-[#3faf86]" />
                </div>
              )}
              {pixel?.probabilities && view === "overlay" && (
                <div className="absolute right-14 top-3 w-64 space-y-1 rounded-lg border border-line bg-surface/95 p-3 text-[11px]">
                  <div className="num text-muted">
                    {pixel.lat.toFixed(5)}, {pixel.lon.toFixed(5)} · {pixel.quality}
                  </div>
                  {Object.entries(pixel.probabilities as Record<string, number | null>).map(([k, v], i) => (
                    <div key={k} className="flex items-center gap-2">
                      <span className="w-24 text-ink-2">{k}</span>
                      <div className="h-1.5 flex-1 rounded bg-sunken">
                        <div className="h-full rounded" style={{ width: `${(v ?? 0) * 100}%`, background: CLASS_COLORS[i] }} />
                      </div>
                      <span className="num w-8 text-right">{v?.toFixed(2) ?? "—"}</span>
                    </div>
                  ))}
                  <div className="num pt-1 text-faint">NDVI {pixel.indices.NDVI?.toFixed(3)}</div>
                </div>
              )}
            </div>
          </Card>

          {s && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Predicted cover" subtitle="Valid pixels only; calibrated probabilities">
                <KV
                  rows={[
                    ["Predicted tree cover (P ≥ 0.5)", fmtHa(s.tree_cover_ha)],
                    ["…of valid area", fmtPct(s.tree_cover_fraction_of_valid)],
                    ["Uncertain (0.4 < P < 0.6)", fmtHa(s.tree_cover_uncertain_ha)],
                    ["Valid area", `${fmtHa(s.valid_area_ha)} (${fmtPct(s.valid_fraction)})`],
                    ["Mean predictive entropy", s.mean_entropy?.toFixed(3) ?? "—"],
                  ]}
                />
                <p className="mt-2 text-[11px] leading-relaxed text-muted">{s.area_note}</p>
              </Card>
              <Card
                title="Class areas (argmax)"
                actions={
                  <Button size="sm" onClick={doExport}>
                    <Download className="h-3.5 w-3.5" /> Export GeoTIFFs
                  </Button>
                }
              >
                <div className="space-y-1.5">
                  {KEYS.map((k, i) => {
                    const v = s.class_areas_ha[k] ?? 0;
                    const tot = Object.values(s.class_areas_ha).reduce((a, b) => a + b, 0) || 1;
                    return (
                      <div key={k} className="flex items-center gap-2 text-[12px]">
                        <span className="w-28 text-ink-2">{NAMES[i]}</span>
                        <div className="h-2 flex-1 rounded bg-sunken">
                          <div className="h-full rounded" style={{ width: `${(v / tot) * 100}%`, background: CLASS_COLORS[i] }} />
                        </div>
                        <span className="num w-20 text-right">{fmtHa(v)}</span>
                      </div>
                    );
                  })}
                </div>
                {exportRow && (
                  <a className="mt-3 block text-xs text-accent-strong underline" href={exportRow.download_url}>
                    Download {exportRow.id}.zip (probabilities, class map, entropy, provenance)
                  </a>
                )}
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
