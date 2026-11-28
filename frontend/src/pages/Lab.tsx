import clsx from "clsx";
import { Play, Square, Star } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { useExperiment, useExperiments, useInvalidate, useSettings, useTrainingRegions } from "../api/hooks";
import type { Experiment } from "../api/types";
import { LossCurves, MiouCurve } from "../components/charts";
import { SpectralStrip } from "../components/SpectralStrip";
import { Badge, Button, Card, Empty, Field, Input, JobProgress, KV, Notice, PageHeader, Select, StatusBadge } from "../components/ui";
import { fmtDateTime, fmtNum } from "../lib/format";

const ALL_BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"];

function NewExperiment({ onCreated }: { onCreated: (id: string) => void }) {
  const { data: tr } = useTrainingRegions();
  const built = tr?.regions.filter((r) => r.built) ?? [];
  const [name, setName] = useState("unet-experiment");
  const [bands, setBands] = useState<string[]>(ALL_BANDS);
  const [cfg, setCfg] = useState({ base: 16, depth: 4, epochs: 10, batch_size: 8, samples_per_epoch: 240, lr: 0.002, loss: "ce_dice", dropout: 0.1 });
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const role = (n: string, def: string) => roles[n] ?? def;
  const split = (want: string) => built.filter((r) => role(r.name, r.role) === want).map((r) => r.name);

  const submit = async () => {
    setErr(null);
    try {
      const e = await api.post<Experiment>("/experiments", {
        name,
        bands,
        ...cfg,
        train_regions: split("train"),
        val_regions: split("val"),
        test_regions: split("test"),
      });
      onCreated(e.id);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const num = (k: keyof typeof cfg, label: string, step = 1) => (
    <Field label={label}>
      <Input type="number" step={step} value={String(cfg[k])} onChange={(e) => setCfg((c) => ({ ...c, [k]: Number(e.target.value) }))} />
    </Field>
  );
  return (
    <Card title="Configure a training run" subtitle="U-Net trained from random initialisation on this project's regions">
      <div className="space-y-3">
        <Field label="Experiment name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={`Input bands (${bands.length})`}>
          <SpectralStrip multi selected={bands} onToggle={(b) => setBands((s) => (s.includes(b) ? s.filter((x) => x !== b) : [...s, b]))} />
        </Field>
        <div className="grid grid-cols-3 gap-2">
          {num("base", "Base width")}
          {num("depth", "Depth")}
          {num("dropout", "Dropout", 0.05)}
          {num("epochs", "Epochs")}
          {num("batch_size", "Batch size")}
          {num("samples_per_epoch", "Crops / epoch", 16)}
          {num("lr", "Learning rate", 0.0005)}
          <Field label="Loss">
            <Select value={cfg.loss} onChange={(e) => setCfg((c) => ({ ...c, loss: e.target.value }))}>
              <option value="ce_dice">CE + Dice</option>
              <option value="ce">Cross-entropy</option>
              <option value="dice">Dice</option>
            </Select>
          </Field>
        </div>
        <Field label="Region split" hint="Whole regions only: a region can't be in training and validation/test">
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-line bg-sunken p-2">
            {built.map((r) => (
              <div key={r.name} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="min-w-0 truncate text-ink-2" title={r.name}>{r.name}</span>
                <div className="w-24 shrink-0">
                <Select className="h-7 text-[12px]" value={role(r.name, r.role)} onChange={(e) => setRoles((x) => ({ ...x, [r.name]: e.target.value }))}>
                  <option value="train">train</option>
                  <option value="val">val</option>
                  <option value="test">test</option>
                  <option value="off">unused</option>
                </Select>
                </div>
              </div>
            ))}
          </div>
        </Field>
        {err && <Notice tone="error">{err}</Notice>}
        <Button variant="primary" className="w-full" onClick={submit} disabled={!bands.length || !built.length}>
          <Play className="h-4 w-4" /> Start training
        </Button>
        <p className="text-[11px] text-muted">
          On a CPU laptop, base width 16 / 10 epochs takes roughly 15–40 min; width 32 / 25 epochs takes a few hours. Progress below comes from the
          worker's real epoch records.
        </p>
      </div>
    </Card>
  );
}

function ExperimentDetail({ id }: { id: string }) {
  const { data: e } = useExperiment(id);
  const { data: settings } = useSettings();
  const invalidate = useInvalidate();
  if (!e) return null;
  const active = settings?.active_experiment_id === e.id;
  const cal = (e.result as Record<string, any> | null)?.calibration;
  return (
    <div className="space-y-4">
      <Card
        title={
          <span className="flex items-center gap-2">
            {e.name} <StatusBadge status={e.status} /> {active && <Badge className="border-accent/50 text-accent-strong">active model</Badge>}
          </span>
        }
        subtitle={`${e.id} · created ${fmtDateTime(e.created_at)}`}
        actions={
          <div className="flex gap-2">
            {["queued", "running"].includes(e.status) && (
              <Button size="sm" variant="danger" onClick={() => api.post(`/experiments/${e.id}/cancel`).then(() => invalidate("experiment", "experiments"))}>
                <Square className="h-3 w-3" /> Cancel
              </Button>
            )}
            {e.checkpoint && !active && (
              <Button size="sm" onClick={() => api.post(`/experiments/${e.id}/activate`).then(() => invalidate("settings", "overview"))}>
                <Star className="h-3 w-3" /> Use for analysis
              </Button>
            )}
          </div>
        }
      >
        {["queued", "running"].includes(e.status) && (
          <div className="mb-3">
            <JobProgress jobId={e.job_id} onDone={() => invalidate("experiment", "experiments")} />
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <KV
            rows={[
              ["Best validation mIoU", e.best_val_miou?.toFixed(4) ?? "—"],
              ["Best epoch", e.best_epoch ?? "—"],
              ["Epochs run", e.epochs?.length ?? 0],
              ["Parameters", e.n_params ? e.n_params.toLocaleString() : "—"],
              ["Device", e.device ?? "—"],
              ["Calibration", cal ? `T = ${cal.temperature.toFixed(3)}, ECE ${cal.ece_before.toFixed(4)} → ${cal.ece_after.toFixed(4)}` : "—"],
            ]}
          />
          <KV
            rows={[
              ["Bands", <span className="num text-[11px]">{e.config.bands.join(" ")}</span>],
              ["Architecture", `U-Net · base ${e.config.base} · depth ${e.config.depth}`],
              ["Train regions", <span className="text-[11px]">{e.config.train_regions.join(", ")}</span>],
              ["Validation", <span className="text-[11px]">{e.config.val_regions.join(", ")}</span>],
              ["Test (held out)", <span className="text-[11px]">{e.config.test_regions.join(", ")}</span>],
              ["Checkpoint SHA-256", <span className="num text-[11px]">{e.checkpoint_sha256?.slice(0, 16) ?? "—"}</span>],
            ]}
          />
        </div>
      </Card>
      {e.epochs && e.epochs.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Loss curves">
            <LossCurves epochs={e.epochs} />
          </Card>
          <Card title="Validation IoU (held-out regions)">
            <MiouCurve epochs={e.epochs} />
          </Card>
        </div>
      ) : (
        <Empty title="No epochs recorded yet">Curves appear after the first epoch completes.</Empty>
      )}
    </div>
  );
}

export default function LabPage() {
  const { data: exps } = useExperiments();
  const { data: settings } = useSettings();
  const [selected, setSelected] = useState<string | null>(null);
  const invalidate = useInvalidate();
  const id = selected ?? exps?.[0]?.id ?? null;
  return (
    <div>
      <PageHeader
        eyebrow="Model laboratory"
        title="Train and compare U-Net experiments"
        description="Sylva's segmentation model is a U-Net implemented in PyTorch and trained from scratch on Sentinel-2 imagery of this project's regions. No external or pretrained model is used. Every curve and metric here comes from an actual training run."
      />
      <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <NewExperiment
            onCreated={(nid) => {
              setSelected(nid);
              invalidate("experiments");
            }}
          />
        </div>
        <div className="space-y-4">
          <Card title="Experiments" subtitle="Click to inspect; compare validation results">
            {!exps?.length ? (
              <Empty title="No experiments yet">Configure and start a training run.</Empty>
            ) : (
              <table className="w-full text-[13px]">
                <thead className="text-left text-[11px] text-muted">
                  <tr>
                    <th className="py-1.5">Name</th>
                    <th>Status</th>
                    <th>Bands</th>
                    <th>Width/depth</th>
                    <th>Params</th>
                    <th>Best val mIoU</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {exps.map((e) => (
                    <tr key={e.id} onClick={() => setSelected(e.id)} className={clsx("cursor-pointer hover:bg-raised", e.id === id && "bg-accent-soft/40")}>
                      <td className="py-2">
                        {e.name} {settings?.active_experiment_id === e.id && <Star className="inline h-3 w-3 text-accent-strong" />}
                        <div className="num text-[11px] text-faint">{e.id}</div>
                      </td>
                      <td>
                        <StatusBadge status={e.status} />
                      </td>
                      <td className="num">{e.config.bands.length}</td>
                      <td className="num">
                        {e.config.base}/{e.config.depth}
                      </td>
                      <td className="num">{e.n_params ? `${fmtNum(e.n_params / 1e6, 2)}M` : "—"}</td>
                      <td className="num">{e.best_val_miou?.toFixed(4) ?? "—"}</td>
                      <td className="text-[11px] text-muted">{fmtDateTime(e.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          {id && <ExperimentDetail id={id} />}
        </div>
      </div>
    </div>
  );
}
