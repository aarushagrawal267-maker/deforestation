import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { api, tileUrl } from "../api/client";
import { useDatasets, useInvalidate, useProducts, useTrainingRegions } from "../api/hooks";
import type { Job, TrainingRegion } from "../api/types";
import { ClassLegend } from "../components/map/Legend";
import { MapView, type MapLayer } from "../components/map/MapView";
import { SpectralStrip } from "../components/SpectralStrip";
import { Badge, Button, Card, JobProgress, KV, Notice, PageHeader, Spinner, Tabs } from "../components/ui";
import { CLASS_COLORS, CLASS_NAMES, fmtDate, fmtPct } from "../lib/format";
import { useApp } from "../stores/app";

function DatasetCard({ d }: { d: Record<string, any> }) {
  return (
    <Card title={d.name} subtitle={d.provider}>
      <KV
        rows={[
          ["Version", d.versions ?? "—"],
          ["Resolution", d.resolution],
          ["CRS", d.crs ?? "—"],
          ["Licence", d.licence],
          ["Role in Sylva", <span className="text-[12px]">{d.role}</span>],
          ["Source", <a className="text-accent-strong underline" href={d.source ?? d.official_source} target="_blank" rel="noreferrer">link</a>],
        ]}
      />
      {d.status && <div className="mt-2"><Notice tone="warn">{d.status}</Notice></div>}
      <ul className="mt-3 list-disc space-y-1 pl-4 text-[12px] text-muted">
        {(d.limitations ?? []).map((l: string) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </Card>
  );
}

const ROLE_TONE: Record<string, string> = {
  train: "border-accent/50 text-accent-strong",
  val: "border-uncertain/50 text-uncertain",
  test: "border-gain/50 text-gain",
};

export default function DatasetsPage() {
  const { data: ds, isLoading } = useDatasets();
  const { data: tr } = useTrainingRegions();
  const aoiId = useApp((s) => s.aoiId);
  const { data: products } = useProducts(aoiId);
  const invalidate = useInvalidate();
  const [sel, setSel] = useState<string>("");
  const [layer, setLayer] = useState<"truecolor" | "labels" | "worldcover" | "lossyear">("labels");
  const [jobId, setJobId] = useState<string | null>(null);
  const region: TrainingRegion | undefined = tr?.regions.find((r) => r.name === sel) ?? tr?.regions.find((r) => r.built);

  const layers = useMemo<MapLayer[]>(() => {
    if (!region?.built) return [];
    const l: MapLayer[] = [{ id: "sylva-r-img", kind: "raster", tiles: tileUrl("region", region.name, "truecolor") }];
    if (layer !== "truecolor") l.push({ id: "sylva-r-lab", kind: "raster", tiles: tileUrl("region", region.name, layer), opacity: 0.8 });
    return l;
  }, [region, layer]);

  if (isLoading || !ds) return <Spinner />;
  const counts = tr?.regions.filter((r) => r.built).reduce(
    (acc, r) => {
      Object.entries(r.label_report?.class_counts ?? {}).forEach(([k, v]) => (acc[Number(k)] += v));
      return acc;
    },
    [0, 0, 0, 0, 0],
  );
  const total = counts?.reduce((a, b) => a + b, 0) || 1;

  return (
    <div>
      <PageHeader
        eyebrow="Dataset explorer"
        title="Data sources, labels and provenance"
        description="All imagery is real Copernicus Sentinel-2 L2A. Training labels are model-generated reference products (ESA WorldCover, optionally Dynamic World), not independent ground truth. Hansen GFC is the most independent reference available (different sensor and algorithm)."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <DatasetCard d={ds.sentinel2} />
        <DatasetCard d={ds.worldcover} />
        <DatasetCard d={ds.hansen} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card title="Spectral bands used by the U-Net" subtitle="10 input channels, surface reflectance">
          <SpectralStrip selected={ds.bands.map((b: { name: string }) => b.name)} />
          <table className="mt-3 w-full text-[12px]">
            <tbody className="divide-y divide-line">
              {ds.bands.map((b: Record<string, any>) => (
                <tr key={b.name}>
                  <td className="num py-1 text-ink">{b.name}</td>
                  <td className="text-ink-2">{b.common}</td>
                  <td className="num text-muted">{b.wavelength_nm} nm</td>
                  <td className="text-[11px] text-muted">{b.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Label scheme" subtitle="WorldCover classes mapped to Sylva segmentation classes">
          <table className="w-full text-[12px]">
            <tbody className="divide-y divide-line">
              {ds.worldcover_mapping
                .filter((m: { code: number }) => m.code !== 0)
                .map((m: { code: number; name: string; sylva_class: number }) => (
                  <tr key={m.code}>
                    <td className="num py-1 text-muted">{m.code}</td>
                    <td className="text-ink-2">{m.name}</td>
                    <td>
                      {m.sylva_class === 255 ? (
                        <span className="text-faint">ignored</span>
                      ) : (
                        <span className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CLASS_COLORS[m.sylva_class] }} />
                          {CLASS_NAMES[m.sylva_class]}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] leading-relaxed text-muted">
            Also ignored (label 255): pixels within 1 px of a class boundary, pixels with Hansen loss in 2020–2022 (label year ±1), and pixels masked
            as cloud/shadow/no-data in the training imagery. Snow/ice and moss/lichen are outside the initial tropical scope.
          </p>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card
          bodyClass="p-0"
          title="Training regions"
          subtitle={`Label year ${tr?.label_year} · split by whole region to prevent spatial leakage`}
          actions={
            <div className="flex items-center gap-2">
              <Tabs
                value={layer}
                onChange={setLayer}
                items={[
                  { value: "truecolor", label: "Imagery" },
                  { value: "labels", label: "Labels" },
                  { value: "worldcover", label: "WorldCover" },
                  { value: "lossyear", label: "Hansen loss" },
                ]}
              />
              <Button
                size="sm"
                onClick={async () => {
                  const j = await api.post<Job>("/datasets/regions/build");
                  setJobId(j.id);
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" /> Build missing
              </Button>
            </div>
          }
        >
          <div className="relative h-[420px]">
            <MapView layers={layers} fitBounds={region?.bbox ?? null} fitKey={region?.name} />
            {layer === "labels" && (
              <div className="absolute bottom-3 left-3 rounded-lg border border-line bg-canvas/90 p-3">
                <ClassLegend />
                <div className="mt-1 text-[11px] text-faint">transparent = ignored</div>
              </div>
            )}
          </div>
          {jobId && (
            <div className="p-3">
              <JobProgress jobId={jobId} onDone={() => invalidate("training-regions")} />
            </div>
          )}
        </Card>
        <Card title="Regions" subtitle="Click to view">
          <ul className="divide-y divide-line">
            {tr?.regions.map((r) => (
              <li key={r.name}>
                <button className="w-full py-2 text-left" onClick={() => setSel(r.name)}>
                  <div className="flex items-center justify-between">
                    <span className={r.name === region?.name ? "text-[13px] text-accent-strong" : "text-[13px] text-ink"}>{r.name}</span>
                    <span className="flex items-center gap-1.5">
                      <Badge className={ROLE_TONE[r.role]}>{r.role}</Badge>
                      {!r.built && <Badge className="border-line text-faint">not built</Badge>}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted">{r.description}</div>
                  {r.built && (
                    <div className="num mt-0.5 text-[11px] text-faint">
                      {fmtDate(r.acquired?.[0])} · {r.selection?.mode} · valid {fmtPct(r.selection?.valid_fraction, 0)} · labelled {fmtPct(r.label_report?.labelled_fraction, 0)}
                    </div>
                  )}
                </button>
              </li>
            ))}
          </ul>
          {counts && (
            <div className="mt-3 border-t border-line pt-3">
              <div className="mb-1 text-[11px] text-muted">Labelled pixels, all built regions</div>
              <div className="flex h-3 overflow-hidden rounded">
                {counts.map((c, i) => (
                  <div key={i} title={`${CLASS_NAMES[i]}: ${c.toLocaleString()}`} style={{ width: `${(c / total) * 100}%`, background: CLASS_COLORS[i] }} />
                ))}
              </div>
              <div className="mt-1.5 grid grid-cols-2 gap-x-3 text-[11px]">
                {counts.map((c, i) => (
                  <div key={i} className="flex justify-between">
                    <span className="text-ink-2">{CLASS_NAMES[i]}</span>
                    <span className="num text-muted">{fmtPct(c / total)}</span>
                  </div>
                ))}
              </div>
              {counts[2] / total < 0.01 && (
                <div className="mt-2">
                  <Notice tone="warn">Bare / sparse is rare (&lt; 1% of labels) in these tropical regions; expect weak performance for that class.</Notice>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      {region?.built && region.label_report && (
        <div className="mt-4">
          <Card title={`Label report · ${region.name}`} subtitle={region.label_source}>
            <div className="grid gap-4 md:grid-cols-2">
              <KV
                rows={[
                  ["Label type", region.label_type],
                  ["Scenes", <span className="num text-[11px]">{region.scene_ids?.join(", ")}</span>],
                  ["Total pixels", region.label_report.total_pixels.toLocaleString()],
                  ["Labelled", fmtPct(region.label_report.labelled_fraction)],
                ]}
              />
              <KV
                rows={[
                  ["Ignored: class boundary", (region.label_report.ignored_class_boundary ?? 0).toLocaleString()],
                  ["Ignored: Hansen recent loss", (region.label_report.ignored_hansen_recent_loss ?? 0).toLocaleString()],
                  ["Ignored: invalid imagery", (region.label_report.ignored_invalid_imagery ?? 0).toLocaleString()],
                  ["Ignored: out of scope / no data", (region.label_report.ignored_reference_nodata_or_out_of_scope ?? 0).toLocaleString()],
                ]}
              />
            </div>
          </Card>
        </div>
      )}

      <div className="mt-4">
        <Card title="Monitoring observations (current AOI)" subtitle="Acquisition metadata, cloud and missing data">
          {!products?.length ? (
            <div className="text-[12px] text-muted">No observations ingested for this AOI.</div>
          ) : (
            <table className="w-full text-[12px]">
              <thead className="text-left text-[11px] text-muted">
                <tr>
                  <th className="py-1">Acquired</th>
                  <th>Scenes</th>
                  <th>Baselines</th>
                  <th>Valid</th>
                  <th>Cloud</th>
                  <th>Shadow</th>
                  <th>Buffer</th>
                  <th>No data</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {products.map((p) => (
                  <tr key={p.id}>
                    <td className="py-1.5">{fmtDate(p.acquired)}</td>
                    <td className="num text-[11px] text-muted">{p.scene_ids.join(", ")}</td>
                    <td className="num text-muted">{p.processing_baselines.join(", ")}</td>
                    <td className="num">{fmtPct(p.valid_fraction)}</td>
                    <td className="num text-muted">{fmtPct(p.quality_summary["cloud"])}</td>
                    <td className="num text-muted">{fmtPct(p.quality_summary["cloud shadow"])}</td>
                    <td className="num text-muted">{fmtPct(p.quality_summary["cloud/shadow buffer"])}</td>
                    <td className="num text-muted">{fmtPct(p.quality_summary["no data"])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      <div className="mt-4">
        <DatasetCard d={ds.dynamic_world} />
      </div>
    </div>
  );
}
