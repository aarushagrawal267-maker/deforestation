import clsx from "clsx";
import { AlertTriangle, Info, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes, InputHTMLAttributes } from "react";
import { useJob } from "../../api/hooks";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 pb-6">
      <div className="max-w-3xl">
        {eyebrow && <div className="mb-2 text-[12px] font-medium text-accent">{eyebrow}</div>}
        <h1 className="font-display text-[30px] leading-tight font-medium text-ink">{title}</h1>
        {description && <p className="mt-2 text-[14px] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClass,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={clsx("rounded-xl border border-line bg-surface", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-[13px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[12px] text-muted">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={clsx("p-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  unit,
  sub,
  tone,
  swatch,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  tone?: "loss" | "gain" | "forest" | "uncertain";
  swatch?: string;
}) {
  const toneClass = tone
    ? { loss: "text-loss", gain: "text-gain", forest: "text-accent-strong", uncertain: "text-uncertain" }[tone]
    : "text-ink";
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-4">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
        {swatch && <span className={clsx("inline-block h-2 w-2 rounded-sm", swatch)} />}
        {label}
      </div>
      <div className={clsx("num mt-2 text-[24px] leading-none font-medium", toneClass)}>
        {value}
        {unit && <span className="ml-1 text-[14px] text-muted">{unit}</span>}
      </div>
      {sub && <div className="mt-2 text-[12px] text-muted">{sub}</div>}
    </div>
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  loading,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        size === "sm" ? "h-7 px-2.5 text-[12px]" : "h-9 px-3.5 text-[13px]",
        variant === "primary" && "bg-accent text-canvas hover:bg-accent-strong",
        variant === "secondary" && "border border-line-strong bg-raised text-ink hover:border-accent/60",
        variant === "ghost" && "text-ink-2 hover:bg-raised hover:text-ink",
        variant === "danger" && "border border-danger/40 text-danger hover:bg-danger/10",
        className,
      )}
    >
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", className)}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    succeeded: "border-accent/40 text-accent-strong",
    completed: "border-accent/40 text-accent-strong",
    running: "border-gain/50 text-gain",
    queued: "border-line-strong text-ink-2",
    failed: "border-danger/50 text-danger",
    cancelled: "border-line-strong text-muted",
    created: "border-line-strong text-muted",
  };
  return (
    <Badge className={map[status] ?? "border-line text-muted"}>
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
      {status}
    </Badge>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-faint">{hint}</span>}
    </label>
  );
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={clsx(
        "h-9 w-full rounded-lg border border-line-strong bg-sunken px-2.5 text-[13px] text-ink outline-none focus:border-accent",
        className,
      )}
    />
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={clsx(
        "h-9 w-full rounded-lg border border-line-strong bg-sunken px-2.5 text-[13px] text-ink outline-none focus:border-accent",
        className,
      )}
    />
  );
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-10 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <div className="text-[14px] font-medium text-ink">{title}</div>
      {children && <div className="mt-1 max-w-md text-[12px] leading-relaxed text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-muted">
      <Loader2 className="h-4 w-4 animate-spin" /> {label ?? "Loading"}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "error"; children: ReactNode }) {
  const Icon = tone === "info" ? Info : AlertTriangle;
  return (
    <div
      className={clsx(
        "flex gap-2.5 rounded-lg border px-3 py-2.5 text-[12px] leading-relaxed",
        tone === "info" && "border-line bg-raised text-ink-2",
        tone === "warn" && "border-uncertain/40 bg-uncertain/5 text-ink-2",
        tone === "error" && "border-danger/40 bg-danger/5 text-danger",
      )}
    >
      <Icon className={clsx("mt-0.5 h-3.5 w-3.5 shrink-0", tone === "warn" ? "text-uncertain" : tone === "error" ? "" : "text-muted")} />
      <div>{children}</div>
    </div>
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: "accent" | "danger" }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
      <div
        className={clsx("h-full rounded-full transition-[width] duration-500", tone === "danger" ? "bg-danger" : "bg-accent")}
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}

/** Live progress of a backend job (polls the real job record). */
export function JobProgress({ jobId, onDone }: { jobId: string | null | undefined; onDone?: (status: string) => void }) {
  const { data: job } = useJob(jobId);
  if (!jobId || !job) return null;
  if (onDone && ["succeeded", "failed", "cancelled"].includes(job.status)) {
    queueMicrotask(() => onDone(job.status));
  }
  return (
    <div className="space-y-1.5 rounded-lg border border-line bg-sunken px-3 py-2.5">
      <div className="flex items-center justify-between gap-2 text-[12px]">
        <span className="flex items-center gap-2">
          <StatusBadge status={job.status} />
          <span className="text-ink-2">{job.type}</span>
        </span>
        <span className="num text-muted">{Math.round(job.progress * 100)}%</span>
      </div>
      <ProgressBar value={job.progress} tone={job.status === "failed" ? "danger" : "accent"} />
      <div className="truncate text-[11px] text-muted" title={job.message}>
        {job.message}
      </div>
      {job.status === "failed" && job.error && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-[11px] text-danger">{job.error.split("\n\n")[0]}</pre>
      )}
    </div>
  );
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="divide-y divide-line text-[13px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="flex items-baseline justify-between gap-4 py-1.5">
          <dt className="text-muted">{k}</dt>
          <dd className="text-right text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-sunken p-0.5">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "whitespace-nowrap rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors",
            value === it.value ? "bg-raised text-ink shadow-sm" : "text-muted hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
