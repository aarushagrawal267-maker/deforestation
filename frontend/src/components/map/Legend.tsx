import clsx from "clsx";

export const CHANGE_LEGEND = [
  { key: "potential_loss", label: "Potential forest loss", swatch: "bg-loss" },
  { key: "potential_gain", label: "Potential vegetation gain", swatch: "bg-gain" },
  { key: "uncertain", label: "Uncertain change", swatch: "hatch-uncertain" },
  { key: "stable_forest", label: "Stable forest", swatch: "bg-forest/60" },
  { key: "invalid", label: "Cloud / invalid", swatch: "hatch-invalid" },
];

export function LegendRow({ swatch, label, value }: { swatch: string; label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="flex items-center gap-2 text-ink-2">
        <span className={clsx("inline-block h-3 w-3 rounded-[3px] border border-white/10", swatch)} />
        {label}
      </span>
      {value && <span className="num text-muted">{value}</span>}
    </div>
  );
}

export function ProbabilityRamp({ label = "P(tree cover)" }: { label?: string }) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-ink-2">{label}</div>
      <div className="h-2.5 rounded" style={{ background: "linear-gradient(90deg,#ece2c6 0%,#bec478 40%,#6ea050 60%,#0c4628 100%)" }} />
      <div className="num mt-0.5 flex justify-between text-[10px] text-muted">
        <span>0</span>
        <span>0.4</span>
        <span>0.6</span>
        <span>1</span>
      </div>
    </div>
  );
}

export function DeltaRamp() {
  return (
    <div>
      <div className="mb-1 text-[11px] text-ink-2">Δ P(tree), later − earlier</div>
      <div className="h-2.5 rounded" style={{ background: "linear-gradient(90deg,#b2182b,#ef8a62,#f7f7f7,#67a9cf,#2166ac)" }} />
      <div className="num mt-0.5 flex justify-between text-[10px] text-muted">
        <span>−1</span>
        <span>0</span>
        <span>+1</span>
      </div>
    </div>
  );
}

export function ClassLegend() {
  const items = [
    ["#2f8f5b", "Tree cover"],
    ["#b5c96a", "Other vegetation"],
    ["#c9a27a", "Bare / sparse"],
    ["#3a7bd5", "Water"],
    ["#d1495b", "Built-up"],
  ];
  return (
    <div className="space-y-1">
      {items.map(([c, n]) => (
        <div key={n} className="flex items-center gap-2 text-[11px] text-ink-2">
          <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: c }} />
          {n}
        </div>
      ))}
    </div>
  );
}
