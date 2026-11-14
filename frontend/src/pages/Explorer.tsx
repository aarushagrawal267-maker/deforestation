import clsx from "clsx";
import { Download, PenSquare, Search, Trash2, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { api, tileUrl } from "../api/client";
import { useAOIs, useInvalidate, useProducts, useSceneSearch } from "../api/hooks";
import type { Job, Product, Scene } from "../api/types";
import { AcquisitionTimeline } from "../components/AcquisitionTimeline";
import { MapView, type MapLayer } from "../components/map/MapView";
import { SwipeCompare } from "../components/map/SwipeCompare";
import { ObservationSelect } from "../components/ObservationSelect";
import { BANDS, SpectralStrip } from "../components/SpectralStrip";
import { Button, Card, Empty, Field, Input, JobProgress, KV, Notice, PageHeader, Select, Tabs } from "../components/ui";
import { fmtDate, fmtNum, fmtPct } from "../lib/format";
import { useApp } from "../stores/app";

type Render = "truecolor" | "falsecolor" | "swir" | "ndvi" | "band";

export default function ExplorerPage() {
  const { aoiId, setAoiId } = useApp();
  const { data: aois } = useAOIs();
  const aoi = aois?.find((a) => a.id === aoiId);
  const { data: products } = useProducts(aoiId);
  const invalidate = useInvalidate();
  const search = useSceneSearch();

  const year = new Date().getUTCFullYear();
  const [start, setStart] = useState(`${year - 1}-06-01`);
  const [end, setEnd] = useState(`${year - 1}-09-30`);
  const [maxCloud, setMaxCloud] = useState(20);
  const [provider, setProvider] = useState("earth-search");
  const [picked, setPicked] = useState<string[]>([]);
  const [mode, setMode] = useState<"single" | "composite">("single");
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [drawMode, setDrawMode] = useState(false);
  const [drawn, setDrawn] = useState<[number, number, number, number] | null>(null);
  const [newName, setNewName] = useState("");

  const [viewId, setViewId] = useState("");
  const [compareId, setCompareId] = useState("");
  const [render, setRender] = useState<Render>("truecolor");
  const [band, setBand] = useState("B8");
  const [view, setView] = useState<"single" | "compare">("single");

  const scenes = search.data ?? [];
  const pickedScenes = scenes.filter((s) => picked.includes(s.id));
  const viewProduct = products?.find((p) => p.id === (viewId || products?.[products.length - 1]?.id));

  const runSearch = () => {
    if (!aoiId) return;
    setPicked([]);
    setErr(null);
    search.mutate({ aoi_id: aoiId, start, end, max_cloud: maxCloud, provider }, { onError: (e) => setErr(String(e.message)) });
  };

  const toggleScene = (s: Scene) => {
    if (mode === "single") {
      // a single acquisition = all tiles of the same day/platform
      const sameDay = scenes.filter((x) => x.date === s.date && x.platform === s.platform).map((x) => x.id);
      setPicked((p) => (p.includes(s.id) ? [] : sameDay));
    } else {
      setPicked((p) => (p.includes(s.id) ? p.filter((x) => x !== s.id) : [...p, s.id].slice(0, 12)));
    }
  };

  const ingest = async () => {
    if (!aoiId || picked.length === 0) return;
    setErr(null);
    try {
      const j = await api.post<Job>("/products/ingest", { aoi_id: aoiId, scene_ids: picked, mode, provider });
      setJobId(j.id);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  const createAoi = async () => {
    if (!drawn) return;
    setErr(null);
    try {
      const a = await api.post<{ id: string }>("/aois", { name: newName || "New monitoring area", bbox: drawn });
      invalidate("aois");
      setAoiId(a.id);
      setDrawn(null);
      setNewName("");
      setDrawMode(false);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  const importGeojson = async (file: File) => {
    setErr(null);
    try {
      const gj = JSON.parse(await file.text());
      const geom = gj.type === "FeatureCollection" ? gj.features[0]?.geometry : gj.type === "Feature" ? gj.geometry : gj;
      const a = await api.post<{ id: string }>("/aois", { name: file.name.replace(/\.(geo)?json$/i, ""), geometry: geom });
      invalidate("aois");
      setAoiId(a.id);
    } catch (e) {
      setErr(`GeoJSON import failed: ${(e as Error).message}`);
    }
  };

  const deleteProduct = async (p: Product) => {
    if (!confirm(`Delete observation ${p.id} (${fmtDate(p.acquired)})?`)) return;
    try {
      await api.del(`/products/${p.id}`);
      invalidate("products");
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  const layers = useMemo<MapLayer[]>(() => {
    const l: MapLayer[] = [];
    if (viewProduct) l.push({ id: "sylva-view", kind: "raster", tiles: tileUrl("product", viewProduct.id, render, render === "band" ? band : undefined) });
    if (aoi) l.push({ id: "sylva-aoi", kind: "outline", data: { type: "Feature", geometry: aoi.geometry, properties: {} } });
    if (drawn)
      l.push({
        id: "sylva-drawn",
        kind: "draw",
        color: "#5cc79f",
        data: {
          type: "Feature",
          properties: {},
          geometry: { type: "Polygon", coordinates: [[[drawn[0], drawn[1]], [drawn[2], drawn[1]], [drawn[2], drawn[3]], [drawn[0], drawn[3]], [drawn[0], drawn[1]]]] },
        },
      });
    return l;
  }, [viewProduct, render, band, aoi, drawn]);

  const compareProduct = products?.find((p) => p.id === compareId);

  return (
    <div>
      <PageHeader
        eyebrow="Satellite image explorer"
        title="Sentinel-2 observations"
        description="Search available Sentinel-2 Level-2A acquisitions for the monitoring area, inspect cloud cover, and turn chosen acquisitions into analysis-ready observations (AOI window only, masked and resampled onto the AOI's 10 m UTM grid)."
      />
      {err && (
        <div className="mb-4">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-4">
          <Card
            bodyClass="p-0"
            title={
              <span className="flex items-center gap-3">
                Imagery viewer
                <Tabs
                  value={view}
                  onChange={setView}
                  items={[
                    { value: "single", label: "Single" },
                    { value: "compare", label: "Compare dates" },
                  ]}
                />
              </span>
            }
            actions={
              <div className="flex items-center gap-2">
                <Button size="sm" variant={drawMode ? "primary" : "secondary"} onClick={() => setDrawMode((d) => !d)}>
                  <PenSquare className="h-3.5 w-3.5" /> {drawMode ? "Drag on map…" : "Draw new AOI"}
                </Button>
                <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-lg border border-line-strong bg-raised px-2.5 text-xs">
                  <Upload className="h-3.5 w-3.5" /> GeoJSON
                  <input type="file" accept=".json,.geojson" className="hidden" onChange={(e) => e.target.files?.[0] && importGeojson(e.target.files[0])} />
                </label>
              </div>
            }
          >
            <div className="relative h-[480px] overflow-hidden rounded-b-xl">
              {view === "compare" && viewProduct && compareProduct ? (
                <SwipeCompare
                  left={[{ id: "sylva-a", kind: "raster", tiles: tileUrl("product", viewProduct.id, render, render === "band" ? band : undefined) }]}
                  right={[{ id: "sylva-b", kind: "raster", tiles: tileUrl("product", compareProduct.id, render, render === "band" ? band : undefined) }]}
                  leftLabel={fmtDate(viewProduct.acquired)}
                  rightLabel={fmtDate(compareProduct.acquired)}
                  fitBounds={aoi?.bbox}
                  fitKey={aoi?.id}
                />
              ) : (
                <MapView
                  layers={layers}
                  fitBounds={drawn ?? aoi?.bbox}
                  fitKey={aoi?.id}
                  drawMode={drawMode}
                  onDraw={(b) => {
                    setDrawn(b);
                    setDrawMode(false);
                  }}
                />
              )}
              {drawn && (
                <div className="absolute bottom-3 left-3 z-10 flex w-80 flex-col gap-2 rounded-lg border border-line bg-surface/95 p-3">
                  <div className="num text-[11px] text-muted">{drawn.map((v) => v.toFixed(4)).join(", ")}</div>
                  <Input placeholder="Name of the new area" value={newName} onChange={(e) => setNewName(e.target.value)} />
                  <div className="flex gap-2">
                    <Button variant="primary" size="sm" onClick={createAoi}>
                      Create AOI
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDrawn(null)}>
                      Discard
                    </Button>
                  </div>
                </div>
              )}
              {view === "compare" && !compareProduct && (
                <div className="absolute inset-x-0 top-3 z-10 mx-auto w-fit rounded-lg bg-surface/95 px-3 py-1.5 text-xs text-muted">
                  Choose a second observation below to compare.
                </div>
              )}
            </div>
            <div className="grid gap-3 border-t border-line p-4 md:grid-cols-3">
              <Field label="Observation">
                <ObservationSelect products={products} value={viewProduct?.id ?? ""} onChange={setViewId} />
              </Field>
              {view === "compare" ? (
                <Field label="Compare with">
                  <ObservationSelect products={products} value={compareId} onChange={setCompareId} />
                </Field>
              ) : (
                <div />
              )}
              <Field label="Rendering">
                <Select value={render} onChange={(e) => setRender(e.target.value as Render)} aria-label="Rendering">
                  <option value="truecolor">True colour · B4 B3 B2</option>
                  <option value="falsecolor">False colour (vegetation) · B8 B4 B3</option>
                  <option value="swir">SWIR composite · B12 B8A B4</option>
                  <option value="ndvi">NDVI</option>
                  <option value="band">Single band</option>
                </Select>
              </Field>
              {render === "band" && (
                <div className="md:col-span-3">
                  <SpectralStrip selected={[band]} onToggle={setBand} />
                  <div className="mt-1 text-[11px] text-muted">
                    Showing {band}: {BANDS.find((b) => b.name === band)?.label}, {BANDS.find((b) => b.name === band)?.nm} nm
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card title="Ingested observations" subtitle={aoi ? `${products?.length ?? 0} analysis-ready observation(s) for ${aoi.name}` : ""}>
            {!products?.length ? (
              <Empty title="No observations yet">Search for acquisitions on the right and ingest one or more.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12.5px]">
                  <thead className="text-left text-[11px] uppercase tracking-[0.08em] text-muted">
                    <tr>
                      <th className="py-1.5">Acquired</th>
                      <th>Type</th>
                      <th>Scenes</th>
                      <th>Valid</th>
                      <th>Cloud</th>
                      <th>Shadow</th>
                      <th>Collection</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {products.map((p) => (
                      <tr key={p.id} className={clsx(p.id === viewProduct?.id && "bg-accent-soft/40")}>
                        <td className="py-2">
                          <button className="text-ink hover:underline" onClick={() => setViewId(p.id)}>
                            {fmtDate(p.acquired)}
                          </button>
                          <div className="num text-[10px] text-faint">{p.id}</div>
                        </td>
                        <td className="text-ink-2">{p.kind.replace(/_/g, " ")}</td>
                        <td className="num max-w-[16rem] truncate text-[11px] text-muted" title={p.scene_ids.join("\n")}>
                          {p.scene_ids.length} · {p.mgrs_tile}
                        </td>
                        <td className="num">{fmtPct(p.valid_fraction)}</td>
                        <td className="num text-muted">{fmtPct(p.quality_summary["cloud"])}</td>
                        <td className="num text-muted">{fmtPct(p.quality_summary["cloud shadow"])}</td>
                        <td className="text-[11px] text-muted">{p.collection}</td>
                        <td className="text-right">
                          <button aria-label="Delete observation" onClick={() => deleteProduct(p)} className="text-faint hover:text-danger">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          {viewProduct && (
            <Card title="Processing history" subtitle={viewProduct.attribution ?? undefined}>
              <ol className="list-decimal space-y-1 pl-4 text-[12px] text-ink-2">
                {viewProduct.processing.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Search acquisitions" subtitle="Available Sentinel-2 L2A scenes intersecting the AOI">
            <div className="grid grid-cols-2 gap-3">
              <Field label="From">
                <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              </Field>
              <Field label="To">
                <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
              </Field>
              <Field label={`Max scene cloud: ${maxCloud}%`}>
                <input type="range" min={0} max={100} value={maxCloud} onChange={(e) => setMaxCloud(Number(e.target.value))} className="mt-3 w-full accent-[#3faf86]" />
              </Field>
              <Field label="Collection">
                <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
                  <option value="earth-search">Collection 1 L2A</option>
                  <option value="earth-search-legacy">Legacy L2A (gap filler)</option>
                </Select>
              </Field>
            </div>
            <Button className="mt-3 w-full" variant="primary" onClick={runSearch} loading={search.isPending} disabled={!aoiId}>
              <Search className="h-4 w-4" /> Search catalogue
            </Button>
            {search.isSuccess && scenes.length === 0 && (
              <div className="mt-3">
                <Notice tone="warn">
                  No scenes found. Try a wider date range or higher cloud limit. Collection 1 has gaps in some periods (e.g. 2022); try
                  the legacy collection.
                </Notice>
              </div>
            )}
          </Card>

          {scenes.length > 0 && (
            <Card
              title={`${scenes.length} acquisitions`}
              subtitle="Scene cloud cover is for the whole tile; AOI validity is computed on ingest"
              actions={
                <Tabs
                  value={mode}
                  onChange={(m) => {
                    setMode(m);
                    setPicked([]);
                  }}
                  items={[
                    { value: "single", label: "Single date" },
                    { value: "composite", label: "Composite" },
                  ]}
                />
              }
            >
              <AcquisitionTimeline scenes={scenes} start={start} end={end} selected={picked} onSelect={toggleScene} />
              <ul className="mt-3 max-h-80 divide-y divide-line overflow-y-auto">
                {scenes.map((s) => (
                  <li key={s.id}>
                    <button
                      onClick={() => toggleScene(s)}
                      className={clsx("flex w-full items-center gap-3 px-1 py-1.5 text-left", picked.includes(s.id) && "bg-accent-soft/50")}
                    >
                      {s.thumbnail ? (
                        <img src={s.thumbnail} alt="" loading="lazy" className="h-10 w-10 rounded object-cover" />
                      ) : (
                        <div className="h-10 w-10 rounded bg-raised" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between text-[12.5px]">
                          <span>{fmtDate(s.datetime)}</span>
                          <span className={clsx("num text-[11px]", (s.cloud_cover ?? 100) < 10 ? "text-accent-strong" : "text-uncertain")}>
                            ☁ {fmtNum(s.cloud_cover, 1)}%
                          </span>
                        </div>
                        <div className="num truncate text-[10px] text-faint">
                          {s.platform} · {s.mgrs_tile} · baseline {s.processing_baseline}
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="mt-3 space-y-2 border-t border-line pt-3">
                <KV
                  rows={[
                    ["Selected", `${pickedScenes.length} scene(s)`],
                    ["Mode", mode === "single" ? "single acquisition (same-day tiles mosaicked)" : "per-pixel median composite"],
                  ]}
                />
                <Button className="w-full" variant="primary" disabled={!picked.length} onClick={ingest}>
                  <Download className="h-4 w-4" /> Ingest as observation
                </Button>
                <JobProgress jobId={jobId} onDone={() => invalidate("products", "overview")} />
              </div>
            </Card>
          )}
          {aoi && (
            <Card title="Area of interest">
              <KV
                rows={[
                  ["Name", aoi.name],
                  ["Area (bbox)", `${fmtNum(aoi.area_km2, 1)} km²`],
                  ["Grid", `${aoi.grid.width} × ${aoi.grid.height} px @ 10 m`],
                  ["CRS", aoi.grid.crs],
                  ["Bounds", <span className="num text-[11px]">{aoi.bbox.map((v) => v.toFixed(3)).join(", ")}</span>],
                ]}
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
