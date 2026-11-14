import clsx from "clsx";

export const BANDS = [
  { name: "B2", nm: 490, res: 10, label: "Blue" },
  { name: "B3", nm: 560, res: 10, label: "Green" },
  { name: "B4", nm: 665, res: 10, label: "Red" },
  { name: "B5", nm: 705, res: 20, label: "Red edge 1" },
  { name: "B6", nm: 740, res: 20, label: "Red edge 2" },
  { name: "B7", nm: 783, res: 20, label: "Red edge 3" },
  { name: "B8", nm: 842, res: 10, label: "NIR" },
  { name: "B8A", nm: 865, res: 20, label: "NIR narrow" },
  { name: "B11", nm: 1610, res: 20, label: "SWIR 1" },
  { name: "B12", nm: 2190, res: 20, label: "SWIR 2" },
];

const COLOR: Record<string, string> = {
  B2: "#4f7bd9",
  B3: "#4fb36b",
  B4: "#d9534f",
  B5: "#b3473f",
  B6: "#93413a",
  B7: "#7a3d3a",
  B8: "#8a6d5a",
  B8A: "#7d6a5c",
  B11: "#7b6f87",
  B12: "#6a6280",
};

/** Wavelength-ordered band selector; 20 m bands are visibly distinguished (hatched). */
export function SpectralStrip({
  selected,
  onToggle,
  multi = false,
  values,
}: {
  selected: string[];
  onToggle?: (band: string) => void;
  multi?: boolean;
  values?: Record<string, number | null>;
}) {
  // evenly spaced in wavelength order (VNIR | SWIR gap), wavelength shown per band
  const pos = (i: number) => (i < 8 ? 4 + i * 9.6 : 4 + 7 * 9.6 + 14 + (i - 8) * 9.6);
  return (
    <div>
      <div className="relative h-[72px] rounded-lg border border-line bg-sunken">
        <div className="absolute bottom-2 top-5 w-px bg-line-strong" style={{ left: `${(pos(7) + pos(8)) / 2}%` }} />
        {BANDS.map((b, i) => {
          const on = selected.includes(b.name);
          const v = values?.[b.name];
          return (
            <button
              key={b.name}
              type="button"
              title={`${b.name} · ${b.label} · ${b.nm} nm · native ${b.res} m${b.res === 20 ? " (resampled to 10 m grid)" : ""}`}
              onClick={() => onToggle?.(b.name)}
              disabled={!onToggle}
              className={clsx(
                "absolute bottom-[6px] flex w-[30px] -translate-x-1/2 flex-col items-center gap-1 disabled:cursor-default",
              )}
              style={{ left: `${pos(i)}%` }}
            >
              <span
                className={clsx("block w-[14px] rounded-sm border transition-all", on ? "border-white/80" : "border-transparent opacity-45")}
                style={{
                  height: v !== undefined && v !== null ? `${Math.max(4, Math.min(34, v * 70))}px` : "22px",
                  background:
                    b.res === 20
                      ? `repeating-linear-gradient(45deg, ${COLOR[b.name]} 0 3px, ${COLOR[b.name]}99 3px 5px)`
                      : COLOR[b.name],
                }}
              />
              <span className={clsx("num text-[9.5px] leading-none", on ? "text-ink" : "text-faint")}>{b.name}</span>
              <span className="num text-[8px] leading-none text-faint">{b.nm}</span>
            </button>
          );
        })}
        <div className="num absolute right-2 top-1 text-[9px] text-faint">{multi ? "click to toggle · " : ""}VNIR │ SWIR</div>
      </div>
      <div className="mt-1.5 flex gap-4 text-[10px] text-faint">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#8a6d5a]" /> native 10 m
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "repeating-linear-gradient(45deg,#8a6d5a 0 2px,#8a6d5a88 2px 4px)" }} />
          native 20 m, resampled to 10 m (no new detail)
        </span>
      </div>
    </div>
  );
}
