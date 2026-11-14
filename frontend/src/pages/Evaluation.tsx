import { Play } from "lucide-react";
import { useMemo, useState } from "react";
import { api, tileUrl } from "../api/client";
import { useEvaluation, useEvaluations, useExperiment, useExperiments, useInvalidate, useSettings, useTrainingRegions } from "../api/hooks";
import type { Evaluation } from "../api/types";
import { ConfusionMatrix, LossCurves, Reliability } from "../components/charts";
import { ClassLegend } from "../components/map/Legend";
import { MapView, type MapLayer } from "../components/map/MapView";
import { Button, Card, Empty, JobProgress, Notice, PageHeader, Select, Stat, Tabs } from "../components/ui";
import { CLASS_COLORS, fmtDateTime, fmtPct } from "../lib/format";

const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3));

export default function EvaluationPage() {
  const { data: exps } = useExperiments();
  const { data: settings } = useSettings();
  const trained = exps?.filter((e) => e.checkpoint) ?? [];
  const [expId, setExpId] = useState("");
  const eid = expId || settings?.active_experiment_id || trained[0]?.id || "";
  const { data: exp } = useExperiment(eid);
  const { data: evals } = useEvaluations(eid);
  const invalidate = useInvalidate();
  const latest = evals?.[0];
  const { data: ev } = useEvaluation(latest?.id);
  const r = ev?.result;
  const [region, setRegion] = useState("");
  const [cmp, setCmp] = useState<"pred" | "labels" | "imagery">("pred");
  const [err, setErr] = useState<string | null>(null);
  const reg = region || r?.per_region[0]?.region || "";

  const run = async () => {
    setErr(null);
    try {
      await api.post<Evaluation>("/evaluations", { experiment_id: eid });
      invalidate("evaluations");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const layers = useMemo<MapLayer[]>(() => {
    if (!ev || !reg) return [];
    const l: MapLayer[] = [{ id: "sylva-ev-img", kind: "raster", tiles: tileUrl("region", reg, "truecolor") }];
    if (cmp === "pred") l.push({ id: "sylva-ev-x", kind: "raster", tiles: tileUrl("evalpred", `${ev.id}:${reg}`), opacity: 0.85 });
    if (cmp === "labels") l.push({ id: "sylva-ev-x", kind: "raster", tiles: tileUrl("region", reg, "labels"), opacity: 0.85 });
    return l;
  }, [ev, reg, cmp]);

  const ref = r?.overall_reference_agreement;
  const han = r?.overall_hansen_tree_agreement;
  const { data: tr } = useTrainingRegions();
  const regionBbox = tr?.regions.find((x) => x.name === reg)?.bbox ?? null;

  return (
    <div>
      <PageHeader
        eyebrow="Model evaluation"
        title="Held-out geographic evaluation"
        description="Metrics are computed on test regions that were never used for training or threshold tuning. They measure agreement with the WorldCover-derived reference labels (themselves model outputs) and with Hansen GFC tree cover. Neither is accuracy against independent ground truth."
        actions={
          <>
            <Select className="w-64" value={eid} onChange={(e) => setExpId(e.target.value)}>
              {trained.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} ({e.id})
                </option>
              ))}
            </Select>
            <Button variant="primary" onClick={run} disabled={!eid}>
              <Play className="h-4 w-4" /> Evaluate on test regions
            </Button>
          </>
        }
      />
      {err && <Notice tone="error">{err}</Notice>}
      {latest && ["queued", "running"].includes(latest.status) && (
        <div className="mb-4">
          <JobProgress jobId={latest.job_id} onDone={() => invalidate("evaluations", "evaluation")} />
        </div>
      )}
      {!trained.length ? (
        <Empty title="No trained model">Train a U-Net in the Model Laboratory first.</Empty>
      ) : !r ? (
        <Empty title="Not yet evaluated">Run an evaluation to compute test-region metrics for this model.</Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <Stat label="Mean IoU" value={f3(ref?.mean_iou)} sub="vs reference labels" />
            <Stat label="Mean Dice / F1" value={f3(ref?.mean_dice)} />
            <Stat label="Overall agreement" value={fmtPct(ref?.overall_accuracy)} sub={`${(ref?.pixels ?? 0).toLocaleString()} px`} />
            <Stat label="Macro precision" value={f3(ref?.macro_precision)} />
            <Stat label="Macro recall" value={f3(ref?.macro_recall)} />
            <Stat label="Tree F1 vs Hansen" tone="forest" value={f3(han?.f1)} sub="30 m, treecover ≥ 30%" />
          </div>
          <div className="mt-1 text-[11px] text-faint">
            Evaluation {ev?.id} · {fmtDateTime(ev?.created_at)} · test regions: {r.regions.join(", ")}
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Per-class metrics" subtitle="Against WorldCover-derived reference labels, test regions">
              <table className="w-full text-[12.5px]">
                <thead className="text-left text-[10.5px] uppercase tracking-[0.08em] text-muted">
                  <tr>
                    <th className="py-1">Class</th>
                    <th>IoU</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>F1</th>
                    <th>Support</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {ref?.per_class.map((c, i) => (
                    <tr key={c.class}>
                      <td className="py-1.5">
                        <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CLASS_COLORS[i] }} />
                        {c.class}
                      </td>
                      <td className="num">{f3(c.iou)}</td>
                      <td className="num">{f3(c.precision)}</td>
                      <td className="num">{f3(c.recall)}</td>
                      <td className="num">{f3(c.f1)}</td>
                      <td className="num text-muted">{c.support.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Confusion matrix" subtitle="Test regions, pixels">
              {ref && <ConfusionMatrix cm={ref.confusion_matrix} />}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Geographic validation" subtitle="Results per held-out region">
              <table className="w-full text-[12.5px]">
                <thead className="text-left text-[10.5px] uppercase tracking-[0.08em] text-muted">
                  <tr>
                    <th className="py-1">Region</th>
                    <th>mIoU</th>
                    <th>Tree IoU</th>
                    <th>Agreement</th>
                    <th>Tree F1 vs Hansen</th>
                    <th>Valid</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {r.per_region.map((p) => (
                    <tr key={p.region} className="cursor-pointer hover:bg-raised" onClick={() => setRegion(p.region)}>
                      <td className="py-1.5">{p.region}</td>
                      <td className="num">{f3(p.reference_agreement.mean_iou)}</td>
                      <td className="num">{f3(p.reference_agreement.per_class[0].iou)}</td>
                      <td className="num">{fmtPct(p.reference_agreement.overall_accuracy)}</td>
                      <td className="num">{f3(p.hansen_tree_agreement.f1)}</td>
                      <td className="num text-muted">{fmtPct(p.valid_fraction, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Calibration" subtitle={r.calibration ? `Temperature ${r.calibration.temperature.toFixed(3)} fitted on validation regions` : "Not calibrated"}>
              {r.calibration ? (
                <>
                  <Reliability bins={r.calibration.reliability} />
                  <div className="text-[11px] text-muted">
                    Expected calibration error {r.calibration.ece_before.toFixed(4)} → {r.calibration.ece_after.toFixed(4)} (validation pixels).
                  </div>
                </>
              ) : (
                <div className="text-xs text-muted">No calibration available.</div>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Card
              bodyClass="p-0"
              title={`Prediction vs reference · ${reg}`}
              actions={
                <Tabs
                  value={cmp}
                  onChange={setCmp}
                  items={[
                    { value: "pred", label: "U-Net prediction" },
                    { value: "labels", label: "Reference labels" },
                    { value: "imagery", label: "Imagery" },
                  ]}
                />
              }
            >
              <div className="relative h-[420px] overflow-hidden rounded-b-xl">
                <MapView layers={layers} fitBounds={regionBbox} fitKey={`${reg}-${regionBbox ? 1 : 0}`} />
                <div className="absolute bottom-3 left-3 rounded-lg border border-line bg-canvas/90 p-3">
                  <ClassLegend />
                </div>
              </div>
            </Card>
            <Card title="Training history" subtitle={exp?.name}>
              {exp?.epochs?.length ? <LossCurves epochs={exp.epochs} /> : <div className="text-xs text-muted">No epochs</div>}
              <ul className="mt-3 list-disc space-y-1 pl-4 text-[11px] text-muted">
                {r.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
