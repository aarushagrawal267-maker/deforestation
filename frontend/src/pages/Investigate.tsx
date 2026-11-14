import clsx from "clsx";
import { ArrowLeft, Check, Download, Map as MapIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, chipUrl, tileUrl } from "../api/client";
import { useChangeRuns, useInvalidate, useRegion, useRegions } from "../api/hooks";
import type { ExportRow } from "../api/types";
import { MapView, type MapLayer } from "../components/map/MapView";
import { Badge, Button, Card, Empty, Field, Input, KV, Notice, PageHeader, Select, Spinner } from "../components/ui";
import { EVIDENCE, fmtCoord, fmtDate, fmtHa, fmtPct, signed } from "../lib/format";
import { useApp } from "../stores/app";

function padBbox(b: number[], f = 1.2): [number, number, number, number] {
  const w = Math.max(b[2] - b[0], 0.004);
  const h = Math.max(b[3] - b[1], 0.004);
  const cx = (b[0] + b[2]) / 2;
  const cy = (b[1] + b[3]) / 2;
  const s = Math.max(w, h) * (1 + f) / 2;
  return [cx - s, cy - s, cx + s, cy + s];
}

function RegionList() {
  const aoiId = useApp((s) => s.aoiId);
  const { data: runs } = useChangeRuns(aoiId);
  const done = runs?.filter((r) => r.status === "succeeded") ?? [];
  const [runId, setRunId] = useState("");
  const [type, setType] = useState("potential_loss");
  const [evidence, setEvidence] = useState("");
  const [minArea, setMinArea] = useState(0);
  const rid = runId || done[0]?.id;
  const { data: regions, isLoading } = useRegions({ run_id: rid, change_type: type, evidence_level: evidence, min_area_ha: minArea, sort: "area_desc" });
  return (
    <div>
      <PageHeader
        eyebrow="Forest loss investigation"
        title="Detected regions"
        description="Every region flagged by a change analysis, with its evidence. Open one to inspect imagery from both dates, spectral indicators and reference-data comparison, and record an analyst assessment."
      />
      <Card>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Analysis">
            <Select value={rid ?? ""} onChange={(e) => setRunId(e.target.value)}>
              {done.map((r) => (
                <option key={r.id} value={r.id}>
                  {fmtDate(r.before_acquired)} → {fmtDate(r.after_acquired)} ({r.id})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Change type">
            <Select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="potential_loss">Potential forest loss</option>
              <option value="potential_gain">Potential vegetation gain</option>
            </Select>
          </Field>
          <Field label="Evidence">
            <Select value={evidence} onChange={(e) => setEvidence(e.target.value)}>
              <option value="">Any</option>
              <option value="corroborated_hansen">Corroborated by Hansen GFC</option>
              <option value="spectrally_supported">Spectrally supported</option>
              <option value="potential">Model only</option>
            </Select>
          </Field>
          <Field label="Minimum area (ha)">
            <Input type="number" min={0} step={0.5} value={minArea} onChange={(e) => setMinArea(Number(e.target.value))} />
          </Field>
        </div>
      </Card>
      <div className="mt-4">
        {isLoading ? (
          <Spinner />
        ) : !regions?.length ? (
          <Empty title="No regions match">Run a change analysis or relax the filters.</Empty>
        ) : (
          <Card bodyClass="p-0">
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-[10.5px] uppercase tracking-[0.08em] text-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2">Region</th>
                  <th>Location</th>
                  <th>Area</th>
                  <th>P(tree)</th>
                  <th>ΔNBR</th>
                  <th>Hansen overlap</th>
                  <th>Evidence</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {regions.map((r) => (
                  <tr key={r.id} className="hover:bg-raised">
                    <td className="num px-4 py-2">
                      <Link className="text-ink hover:text-accent-strong" to={`/investigate/${r.id}`}>
                        {r.id}
                      </Link>
                    </td>
                    <td className="num text-[11px] text-muted">{fmtCoord(r.centroid_lon, r.centroid_lat)}</td>
                    <td className="num">
                      {fmtHa(r.area_ha)} <span className="text-faint">±{r.area_uncertainty_ha.toFixed(2)}</span>
                    </td>
                    <td className="num">
                      {r.properties.p_tree_before?.toFixed(2)} → {r.properties.p_tree_after?.toFixed(2)}
                    </td>
                    <td className="num">{signed(r.properties.delta_nbr, 2)}</td>
                    <td className="num">{fmtPct(r.properties.hansen_loss_fraction ?? null, 0)}</td>
                    <td>
                      <span className={`rounded border px-1.5 py-0.5 text-[10.5px] ${EVIDENCE[r.evidence_level]?.tone}`}>{EVIDENCE[r.evidence_level]?.label}</span>
                    </td>
                    <td className="text-[11px] text-muted">{r.review_status.replace(/_/g, " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}

function Indicator({ label, before, after, delta }: { label: string; before: number | null; after: number | null; delta: number | null }) {
  const bar = (v: number | null) => (v === null ? 0 : ((v + 1) / 2) * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-ink-2">{label}</span>
        <span className={clsx("num", (delta ?? 0) < -0.1 ? "text-loss" : (delta ?? 0) > 0.1 ? "text-gain" : "text-muted")}>Δ {signed(delta, 3)}</span>
      </div>
      {[
        ["before", before],
        ["after", after],
      ].map(([k, v]) => (
        <div key={k as string} className="flex items-center gap-2 text-[10.5px]">
          <span className="w-10 text-faint">{k}</span>
          <div className="relative h-1.5 flex-1 rounded bg-sunken">
            <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
            <div className="h-full rounded bg-ink-2/70" style={{ width: `${bar(v as number | null)}%` }} />
          </div>
          <span className="num w-12 text-right text-ink-2">{(v as number | null)?.toFixed(3) ?? "—"}</span>
        </div>
      ))}
    </div>
  );
}

function RegionDetail({ id }: { id: string }) {
  const { data: r, isLoading, refetch } = useRegion(id);
  const nav = useNavigate();
  const focusOn = useApp((s) => s.focusOn);
  const invalidate = useInvalidate();
  const [render, setRender] = useState("truecolor");
  const [review, setReview] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [exportRow, setExportRow] = useState<ExportRow | null>(null);

  const layers = useMemo<MapLayer[]>(() => {
    if (!r) return [];
    return [
      { id: "sylva-after", kind: "raster", tiles: tileUrl("product", r.run.after_id, "truecolor") },
      { id: "sylva-change", kind: "raster", tiles: tileUrl("change", r.run.id, "change"), opacity: 0.45 },
      {
        id: "sylva-region",
        kind: "regions",
        data: { type: "FeatureCollection", features: [{ type: "Feature", id: r.id, geometry: r.geometry!, properties: { ...r.properties } }] },
        selectedId: r.id,
      },
    ];
  }, [r]);

  if (isLoading || !r) return <Spinner />;
  const p = r.properties;
  const box = padBbox(p.bbox);
  const ladder = [
    { ok: true, label: "U-Net probability drop", detail: `P(tree) ${p.p_tree_before?.toFixed(2)} → ${p.p_tree_after?.toFixed(2)} (Δ ${signed(p.delta_p_tree, 2)})` },
    {
      ok: (p.spectral_support_fraction ?? 0) >= 0.5,
      label: "Spectral support",
      detail: `${fmtPct(p.spectral_support_fraction ?? null, 0)} of pixels with ΔNDVI or ΔNBR ≤ −0.10`,
    },
    {
      ok: (p.hansen_loss_fraction ?? 0) >= 0.3,
      label: "Hansen GFC corroboration",
      detail:
        p.hansen_loss_fraction == null
          ? String(r.run_summary.hansen_reference ?? "not available for these dates")
          : `${fmtPct(p.hansen_loss_fraction, 0)} of area has Hansen loss in the period (threshold 30%)`,
    },
    {
      ok: p.persistent === true,
      label: "Persistence",
      detail: p.persistence_fraction == null ? "no later observation used" : `${fmtPct(p.persistence_fraction, 0)} still non-forest later`,
    },
  ];
  const save = async () => {
    await api.put(`/regions/${r.id}/review`, { review_status: review ?? r.review_status, analyst_notes: notes ?? r.analyst_notes });
    refetch();
    invalidate("regions");
  };
  const doExport = async () => setExportRow(await api.post<ExportRow>("/exports", { source_type: "region", source_id: r.id, format: "geojson" }));

  return (
    <div>
      <button onClick={() => nav("/investigate")} className="mb-3 flex items-center gap-1 text-xs text-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> All regions
      </button>
      <PageHeader
        eyebrow={p.change_type === "potential_gain" ? "Potential vegetation gain" : "Potential forest loss"}
        title={r.id}
        description={
          <>
            {fmtCoord(p.centroid_lon, p.centroid_lat)} · {r.run.aoi_name} · detected between {fmtDate(p.date_before)} and {fmtDate(p.date_after)}.
            This is a suspected forest-cover change; it is not a verified deforestation event and its cause cannot be determined from imagery alone.
          </>
        }
        actions={
          <>
            <Button
              onClick={() => {
                focusOn(box);
                nav(`/map?run=${r.run.id}`);
              }}
            >
              <MapIcon className="h-4 w-4" /> View on map
            </Button>
            <Button onClick={doExport}>
              <Download className="h-4 w-4" /> GeoJSON
            </Button>
          </>
        }
      />
      {exportRow && (
        <a className="mb-3 block text-xs text-accent-strong underline" href={exportRow.download_url}>
          Download {exportRow.id}.zip
        </a>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card
            title="Before / after imagery"
            subtitle="Sentinel-2 chips of the region on both dates (outline on map below)"
            actions={
              <Select className="h-7 w-44 text-xs" value={render} onChange={(e) => setRender(e.target.value)}>
                <option value="truecolor">True colour</option>
                <option value="falsecolor">False colour (B8 B4 B3)</option>
                <option value="swir">SWIR (B12 B8A B4)</option>
                <option value="ndvi">NDVI</option>
              </Select>
            }
          >
            <div className="grid grid-cols-2 gap-3">
              {(
                [
                  ["Earlier", r.before],
                  ["Later", r.after],
                ] as const
              ).map(([lbl, pr]) => {
                return (
                  <figure key={lbl}>
                    <img
                      src={chipUrl(pr.id, box, render, 512)}
                      alt={`${lbl} observation chip`}
                      className="aspect-square w-full rounded-lg border border-line bg-sunken object-cover"
                    />
                    <figcaption className="mt-1 flex justify-between text-[11px] text-muted">
                      <span>
                        {lbl} · {fmtDate(pr.acquired)}
                      </span>
                      <span className="num">{pr.scene_ids[0]?.slice(0, 22)}</span>
                    </figcaption>
                  </figure>
                );
              })}
            </div>
          </Card>
          <Card bodyClass="p-0" title="Location">
            <div className="relative h-[340px] overflow-hidden rounded-b-xl">
              <MapView layers={layers} fitBounds={box} fitKey={r.id} />
            </div>
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Measurements">
            <KV
              rows={[
                ["Area (geodesic)", `${fmtHa(r.area_ha)} ± ${r.area_uncertainty_ha.toFixed(2)} ha`],
                ["Mapped pixels", `${p.pixel_count} × 100 m²`],
                ["Centroid", <span className="num text-[11px]">{fmtCoord(p.centroid_lon, p.centroid_lat)}</span>],
                ["Earlier observation", fmtDate(p.date_before)],
                ["Later observation", fmtDate(p.date_after)],
                ["P(tree) earlier", p.p_tree_before?.toFixed(3) ?? "—"],
                ["P(tree) later", p.p_tree_after?.toFixed(3) ?? "—"],
                ["Mean predictive entropy", `${p.entropy_before?.toFixed(2)} → ${p.entropy_after?.toFixed(2)}`],
                ["Distance to cloud / no-data", p.distance_to_invalid_m == null ? "—" : `${Math.round(p.distance_to_invalid_m)} m`],
                ["Model confidence", r.run_summary.calibrated ? "calibrated (temperature scaling)" : "uncalibrated: probabilities not interpretable as confidence"],
              ]}
            />
            <p className="mt-2 text-[10.5px] leading-relaxed text-faint">{String(r.run_summary.area_note ?? "")}</p>
          </Card>
          <Card title="Spectral indicators" subtitle="Supporting evidence only">
            <div className="space-y-3">
              <Indicator label="NDVI · greenness" before={p.ndvi_before} after={p.ndvi_after} delta={p.delta_ndvi} />
              <Indicator label="NBR · structure / burn" before={p.nbr_before} after={p.nbr_after} delta={p.delta_nbr} />
              <Indicator label="NDMI · canopy moisture" before={p.ndmi_before} after={p.ndmi_after} delta={p.delta_ndmi} />
              {p.possible_fire_related && <Notice tone="warn">Strong NBR drop (dNBR ≤ −0.27): possibly fire-related. The cause is not established.</Notice>}
            </div>
          </Card>
          <Card title="Evidence ladder">
            <ol className="space-y-2">
              {ladder.map((s) => (
                <li key={s.label} className="flex gap-2.5">
                  <span className={clsx("mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border", s.ok ? "border-accent bg-accent/20" : "border-line-strong")}>
                    {s.ok && <Check className="h-2.5 w-2.5 text-accent-strong" />}
                  </span>
                  <div>
                    <div className="text-[12.5px] text-ink">{s.label}</div>
                    <div className="text-[11px] text-muted">{s.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-muted">
              Overall: <Badge className={EVIDENCE[r.evidence_level]?.tone}>{EVIDENCE[r.evidence_level]?.label}</Badge>
            </div>
            <p className="mt-2 text-[11px] text-muted">
              Reference comparison: WorldCover tree fraction before = {fmtPct(p.worldcover_tree_fraction ?? null, 0)} (
              {String(r.run_summary.worldcover_reference ?? "n/a")}).
            </p>
          </Card>
          <Card title="Analyst assessment" subtitle="Your visual interpretation, stored with the region">
            <div className="space-y-2">
              <Select value={review ?? r.review_status} onChange={(e) => setReview(e.target.value)}>
                <option value="unreviewed">Unreviewed</option>
                <option value="likely_loss">Likely forest loss (visual)</option>
                <option value="likely_false_positive">Likely false positive</option>
                <option value="uncertain">Uncertain</option>
              </Select>
              <Input placeholder="Notes" value={notes ?? r.analyst_notes} onChange={(e) => setNotes(e.target.value)} />
              <Button size="sm" variant="primary" onClick={save}>
                Save assessment
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default function InvestigatePage() {
  const { id } = useParams();
  return id ? <RegionDetail id={id} /> : <RegionList />;
}
