import clsx from "clsx";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useExports, useHistory, useJob, useJobs } from "../api/hooks";
import { Badge, Button, Card, Empty, PageHeader, StatusBadge, Tabs } from "../components/ui";
import { fmtBytes, fmtDate, fmtDateTime, fmtHa, fmtPct } from "../lib/format";

const TYPE_TONE: Record<string, string> = {
  observation: "border-line-strong text-ink-2",
  change_run: "border-loss/50 text-loss",
  segmentation: "border-accent/50 text-accent-strong",
  experiment: "border-gain/50 text-gain",
  export: "border-uncertain/50 text-uncertain",
};

function describe(type: string, d: Record<string, any>) {
  switch (type) {
    case "observation":
      return `${fmtDate(d.acquired)} · ${d.kind} · ${d.scene_ids.length} scene(s) · valid ${fmtPct(d.valid_fraction, 0)}`;
    case "change_run":
      return `${fmtDate(d.before_acquired)} → ${fmtDate(d.after_acquired)} · ${d.status}${
        d.headline?.potential_loss_ha != null ? ` · potential loss ${fmtHa(d.headline.potential_loss_ha)} in ${d.headline.n_loss_regions} regions` : ""
      } · model ${d.experiment_id}`;
    case "segmentation":
      return `${fmtDate(d.acquired)} · ${d.status}${d.summary ? ` · tree cover ${fmtHa(d.summary.tree_cover_ha)}` : ""}`;
    case "experiment":
      return `${d.name} · ${d.status} · best val mIoU ${d.best_val_miou?.toFixed(3) ?? "—"}`;
    case "export":
      return `${d.source_type} ${d.source_id} · ${d.format} · ${fmtBytes(d.size_bytes)}`;
    default:
      return "";
  }
}

function JobLog({ id }: { id: string }) {
  const { data } = useJob(id);
  return <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-sunken p-3 text-[11px] text-ink-2">{data?.log || data?.error || "No log"}</pre>;
}

export default function HistoryPage() {
  const { data: items } = useHistory();
  const { data: jobs } = useJobs();
  const { data: exports } = useExports();
  const [tab, setTab] = useState<"analyses" | "jobs" | "exports">("analyses");
  const [filter, setFilter] = useState("");
  const [openJob, setOpenJob] = useState<string | null>(null);
  const shown = items?.filter((i) => !filter || i.type === filter) ?? [];
  return (
    <div>
      <PageHeader
        eyebrow="Monitoring history"
        title="Everything Sylva has processed"
        description="Areas analysed, observation dates, dataset identifiers, model versions, change results, processing timestamps and exports. All of it is stored in the local SQLite database."
        actions={
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: "analyses", label: "Records" },
              { value: "jobs", label: "Jobs" },
              { value: "exports", label: "Exports" },
            ]}
          />
        }
      />
      {tab === "analyses" && (
        <Card
          actions={
            <div className="flex flex-wrap gap-1">
              {["", "change_run", "observation", "segmentation", "experiment", "export"].map((t) => (
                <button key={t} onClick={() => setFilter(t)} className={clsx("rounded-md px-2 py-0.5 text-[11px]", filter === t ? "bg-raised text-ink" : "text-muted hover:text-ink")}>
                  {t ? t.replace("_", " ") : "all"}
                </button>
              ))}
            </div>
          }
          title={`${shown.length} records`}
        >
          {!shown.length ? (
            <Empty title="Nothing recorded yet" />
          ) : (
            <ul className="divide-y divide-line">
              {shown.map((i) => (
                <li key={i.type + i.id} className="flex items-start justify-between gap-4 py-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge className={TYPE_TONE[i.type]}>{i.type.replace("_", " ")}</Badge>
                      <span className="num text-[12px] text-ink">{i.id}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[12px] text-muted">{describe(i.type, i.detail)}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-[11px] text-faint">{fmtDateTime(i.at)}</span>
                    {i.type === "change_run" && (
                      <Link className="text-[11px] text-accent-strong hover:underline" to={`/map?run=${i.id}`}>
                        reopen
                      </Link>
                    )}
                    {i.type === "export" && (
                      <a className="text-[11px] text-accent-strong hover:underline" href={(i.detail as { download_url: string }).download_url}>
                        download
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {tab === "jobs" && (
        <Card title="Background jobs" subtitle="Executed by the worker process; logs are the worker's real output">
          {!jobs?.length ? (
            <Empty title="No jobs yet" />
          ) : (
            <ul className="divide-y divide-line">
              {jobs.map((j) => (
                <li key={j.id} className="py-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-[12.5px]">
                      <StatusBadge status={j.status} />
                      <span className="text-ink">{j.type}</span>
                      <span className="num text-[11px] text-faint">{j.id}</span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-muted">
                      <span className="num">{Math.round(j.progress * 100)}%</span>
                      <span>{fmtDateTime(j.created_at)}</span>
                      {["queued", "running"].includes(j.status) && (
                        <Button size="sm" variant="danger" onClick={() => api.post(`/jobs/${j.id}/cancel`)}>
                          Cancel
                        </Button>
                      )}
                      <button className="text-accent-strong hover:underline" onClick={() => setOpenJob(openJob === j.id ? null : j.id)}>
                        {openJob === j.id ? "hide log" : "log"}
                      </button>
                    </div>
                  </div>
                  <div className="truncate text-[11px] text-muted">{j.message}</div>
                  {openJob === j.id && <JobLog id={j.id} />}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {tab === "exports" && (
        <Card title="Exports">
          {!exports?.length ? (
            <Empty title="No exports yet">Export results from the Change Detection, Segmentation or Investigation pages.</Empty>
          ) : (
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-[10.5px] uppercase tracking-[0.08em] text-muted">
                <tr>
                  <th className="py-1">Export</th>
                  <th>Source</th>
                  <th>Format</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {exports.map((x) => (
                  <tr key={x.id}>
                    <td className="num py-1.5">{x.id}</td>
                    <td className="text-muted">
                      {x.source_type} · <span className="num">{x.source_id}</span>
                    </td>
                    <td>{x.format}</td>
                    <td className="num">{fmtBytes(x.size_bytes)}</td>
                    <td className="text-[11px] text-muted">{fmtDateTime(x.created_at)}</td>
                    <td>
                      <a className="text-accent-strong hover:underline" href={x.download_url}>
                        download
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
