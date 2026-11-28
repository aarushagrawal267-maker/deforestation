import clsx from "clsx";
import type { Scene } from "../api/types";

/** Horizontal timeline of acquisitions; tick height/colour encodes scene cloud cover. */
export function AcquisitionTimeline({
  scenes,
  start,
  end,
  selected,
  onSelect,
}: {
  scenes: Scene[];
  start: string;
  end: string;
  selected: string[];
  onSelect: (s: Scene) => void;
}) {
  const t0 = new Date(start).getTime();
  const t1 = new Date(end).getTime();
  const span = Math.max(1, t1 - t0);
  const months: { label: string; x: number }[] = [];
  const d = new Date(start);
  d.setDate(1);
  while (d.getTime() <= t1) {
    const x = ((d.getTime() - t0) / span) * 100;
    if (x >= 0) months.push({ label: d.toLocaleDateString(undefined, { month: "short", year: "2-digit" }), x });
    d.setMonth(d.getMonth() + 1);
  }
  const step = Math.ceil(months.length / 12);
  return (
    <div className="relative h-24 rounded-lg border border-line bg-sunken px-3 pt-3" data-testid="timeline">
      <div className="relative h-14">
        {[0, 25, 50, 75, 100].map((c) => (
          <div key={c} className="absolute inset-x-0 border-t border-dashed border-line/60" style={{ bottom: `${(100 - c) * 0.56}px` }} />
        ))}
        {scenes.map((s) => {
          const x = ((new Date(s.datetime).getTime() - t0) / span) * 100;
          const cc = s.cloud_cover ?? 100;
          const on = selected.includes(s.id);
          return (
            <button
              key={s.id}
              onClick={() => onSelect(s)}
              title={`${s.date} · ${s.platform} · ${s.mgrs_tile} · cloud ${cc.toFixed(1)}%`}
              className={clsx(
                "absolute bottom-0 w-[5px] -translate-x-1/2 rounded-t-sm transition-opacity duration-150 hover:opacity-75",
                on ? "bg-white ring-2 ring-accent" : "",
              )}
              style={{
                left: `${x}%`,
                height: `${8 + (100 - cc) * 0.48}px`,
                background: on ? undefined : `hsl(${150 - cc * 1.2} ${cc < 20 ? 55 : 25}% ${cc < 20 ? 52 : 45}%)`,
              }}
            />
          );
        })}
      </div>
      <div className="relative mt-1 h-4">
        {months
          .filter((_, i) => i % step === 0)
          .map((m) => (
            <span key={m.label + m.x} className="num absolute -translate-x-1/2 text-[11px] text-faint" style={{ left: `${m.x}%` }}>
              {m.label}
            </span>
          ))}
      </div>
      <div className="absolute right-2 top-1.5 text-[11px] text-faint">taller = clearer scene</div>
    </div>
  );
}
