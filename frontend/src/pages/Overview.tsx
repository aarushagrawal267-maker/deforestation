import { ArrowRight, GitCompareArrows, Satellite } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { tileUrl } from "../api/client";
import { useOverview } from "../api/hooks";
import { MapView, type MapLayer } from "../components/map/MapView";
import { LegendRow } from "../components/map/Legend";
import { Button, Card, Empty, Notice, PageHeader, Spinner, Stat, StatusBadge } from "../components/ui";
import { EVIDENCE, fmtDate, fmtDateTime, fmtHa, fmtNum, fmtPct } from "../lib/format";
import { useApp } from "../stores/app";

export default function OverviewPage() {
  const aoiId = useApp((s) => s.aoiId);
  const { data, isLoading } = useOverview(aoiId);
  const change = data?.latest_change;
  const latestObs = data?.observations[0];
  const prevObs = data?.observations[1];

  const layers = useMemo<MapLayer[]>(() => {
    const l: MapLayer[] = [];
    if (change) {
      l.push({ id: "sylva-after", kind: "raster", tiles: tileUrl("product", change.after_id, "truecolor") });
      l.push({ id: "sylva-change", kind: "raster", tiles: tileUrl("change", change.id, "change"), opacity: 0.85 });
    } else if (latestObs) {
      l.push({ id: "sylva-after", kind: "raster", tiles: tileUrl("product", latestObs.id, "truecolor") });
    }
    if (data?.aoi) l.push({ id: "sylva-aoi", kind: "outline", data: { type: "Feature", geometry: data.aoi.geometry, properties: {} } });
    return l;
  }, [change, latestObs, data?.aoi]);

  if (isLoading) return <Spinner />;
  if (!data?.aoi) return <Empty title="No monitoring area">Create an area of interest in the Image Explorer.</Empty>;
  const s = change?.summary;
  const h = change?.headline;
  const lossFrac = h?.tree_cover_before_ha ? (h.potential_loss_ha ?? 0) / h.tree_cover_before_ha : null;

  return (
    <div>
      <PageHeader
        eyebrow="Forest intelligence overview"
        title={data.aoi.name}
        description={
          <>
            {data.aoi.description} Figures below come from the latest completed analysis of available Sentinel-2 acquisitions; this
            is not a live feed.
          </>
        }
        actions={
          <>
            <Link to="/explorer">
              <Button>
                <Satellite className="h-4 w-4" /> Add observation
              </Button>
            </Link>
            <Link to="/change">
              <Button variant="primary">
                <GitCompareArrows className="h-4 w-4" /> Run change detection
              </Button>
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Latest observation"
          value={<span className="text-[18px]">{fmtDate(change?.after_acquired ?? latestObs?.acquired)}</span>}
          sub={change ? "later date of latest analysis" : latestObs ? `${data.n_observations} observation(s) ingested` : "none ingested yet"}
        />
        <Stat
          label="Previous observation"
          value={<span className="text-[18px]">{fmtDate(change?.before_acquired ?? prevObs?.acquired)}</span>}
          sub={change ? "earlier date of latest analysis" : "—"}
        />
        <Stat
          label="Predicted tree cover"
          tone="forest"
          swatch="bg-forest"
          value={h?.tree_cover_after_ha != null ? fmtNum(h.tree_cover_after_ha / 100, 1) : "—"}
          unit={h?.tree_cover_after_ha != null ? "km²" : undefined}
          sub={h?.tree_cover_before_ha != null ? `earlier: ${fmtNum(h.tree_cover_before_ha / 100, 1)} km² · valid pixels, P(tree) ≥ 0.5` : "run an analysis"}
        />
        <Stat
          label="Valid observations"
          value={fmtPct(h?.valid_fraction_both_dates ?? latestObs?.valid_fraction)}
          sub={h ? "pixels valid on both dates" : "pixels valid in latest observation"}
        />
        <Stat
          label="Potential forest loss"
          tone="loss"
          swatch="bg-loss"
          value={h?.potential_loss_ha != null ? fmtNum(h.potential_loss_ha, 1) : "—"}
          unit={h?.potential_loss_ha != null ? "ha" : undefined}
          sub={h ? `± ${fmtNum(h.potential_loss_uncertainty_ha, 1)} ha boundary · ${h.n_loss_regions} regions · ${fmtPct(lossFrac, 2)} of tree cover` : "—"}
        />
        <Stat
          label="Potential vegetation gain"
          tone="gain"
          swatch="bg-gain"
          value={h?.potential_gain_ha != null ? fmtNum(h.potential_gain_ha, 1) : "—"}
          unit={h?.potential_gain_ha != null ? "ha" : undefined}
          sub={h ? `${h.n_gain_regions} regions ≥ MMU` : "—"}
        />
        <Stat
          label="Cloud / invalid"
          tone="uncertain"
          value={s ? fmtPct(s.category_areas.invalid.fraction) : latestObs ? fmtPct(1 - latestObs.valid_fraction) : "—"}
          sub="cloud, shadow, buffer or no data"
        />
        <Stat
          label="Model"
          value={<span className="text-[18px]">{data.model?.name ?? "not trained"}</span>}
          sub={
            data.model
              ? `val mIoU ${data.model.best_val_miou?.toFixed(3) ?? "—"} · ${data.model.calibrated ? "calibrated" : "uncalibrated"}${
                  data.model_evaluation?.summary ? ` · test mIoU ${data.model_evaluation.summary.mean_iou?.toFixed(3)}` : ""
                }`
              : "train in Model Lab"
          }
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Card
          title="Latest analysis"
          subtitle={change ? `${fmtDate(change.before_acquired)} → ${fmtDate(change.after_acquired)}` : "No completed change analysis yet"}
          actions={
            change && (
              <Link to={`/map?run=${change.id}`} className="flex items-center gap-1 text-[12px] text-accent-strong hover:underline">
                Open map <ArrowRight className="h-3 w-3" />
              </Link>
            )
          }
          bodyClass="p-0"
        >
          <div className="relative h-[380px] overflow-hidden rounded-b-xl">
            <MapView layers={layers} fitBounds={data.aoi.bbox} fitKey={data.aoi.id + (change?.id ?? "")} />
            {change && s && (
              <div className="absolute bottom-3 left-3 w-56 space-y-1.5 rounded-lg border border-line bg-canvas/90 p-3">
                <LegendRow swatch="bg-loss" label="Potential forest loss" value={fmtHa(s.category_areas.potential_loss.hectares)} />
                <LegendRow swatch="bg-gain" label="Potential gain" value={fmtHa(s.category_areas.potential_gain.hectares)} />
                <LegendRow swatch="hatch-uncertain" label="Uncertain" value={fmtHa(s.category_areas.uncertain.hectares)} />
                <LegendRow swatch="hatch-invalid" label="Cloud / invalid" value={fmtHa(s.category_areas.invalid.hectares)} />
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          {change?.headline.evidence_counts && (
            <Card title="Evidence ladder" subtitle="How potential-loss regions are supported">
              <div className="space-y-2">
                {(["corroborated_hansen", "spectrally_supported", "potential"] as const).map((k) => (
                  <div key={k} className="flex items-center justify-between text-[13px]">
                    <span className={`rounded-md border px-2 py-0.5 text-[11px] ${EVIDENCE[k].tone}`}>{EVIDENCE[k].label}</span>
                    <span className="num text-ink">{change.headline.evidence_counts?.[k] ?? 0}</span>
                  </div>
                ))}
                <p className="pt-1 text-[11px] leading-relaxed text-muted">
                  {s?.hansen_reference ?? "Hansen reference not available."} Regions are potential changes; none is a verified
                  deforestation event.
                </p>
              </div>
            </Card>
          )}
          <Card title="Analysis history" subtitle="Most recent change-detection runs for this area">
            {data.recent_runs.length === 0 ? (
              <Empty title="No analyses yet">
                Ingest at least two observations in the Image Explorer, then compare them in the Change Detection Centre.
              </Empty>
            ) : (
              <ul className="divide-y divide-line">
                {data.recent_runs.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 py-2 text-[13px]">
                    <div>
                      <div className="text-ink">
                        {fmtDate(r.before_acquired)} → {fmtDate(r.after_acquired)}
                      </div>
                      <div className="num text-[11px] text-muted">
                        {r.id} · {fmtDateTime(r.created_at)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {r.headline.potential_loss_ha != null && <span className="num text-[12px] text-loss">{fmtHa(r.headline.potential_loss_ha)}</span>}
                      <StatusBadge status={r.status} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {!data.model && (
            <Notice tone="warn">
              No trained model is active. Train the U-Net from scratch in the <Link className="underline" to="/lab">Model Laboratory</Link>{" "}
              before running segmentation or change detection.
            </Notice>
          )}
        </div>
      </div>
    </div>
  );
}
