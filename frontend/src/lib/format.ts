export const fmtNum = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtHa = (v: number | null | undefined) => {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) >= 1000) return `${(v / 100).toLocaleString(undefined, { maximumFractionDigits: 1 })} km²`;
  return `${fmtNum(v, v < 10 ? 2 : 1)} ha`;
};

export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
};

export const fmtDateTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

export const fmtCoord = (lon: number, lat: number) =>
  `${Math.abs(lat).toFixed(5)}°${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(5)}°${lon >= 0 ? "E" : "W"}`;

export const fmtBytes = (b: number) =>
  b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} kB`;

export const signed = (v: number | null | undefined, digits = 3) =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

export const EVIDENCE: Record<string, { label: string; tone: string; rank: number }> = {
  potential: { label: "Model only", tone: "text-ink-2 border-line-strong", rank: 1 },
  spectrally_supported: { label: "Spectrally supported", tone: "text-uncertain border-uncertain/50", rank: 2 },
  corroborated_hansen: { label: "Corroborated · Hansen GFC", tone: "text-loss border-loss/60", rank: 3 },
};

export const CLASS_COLORS = ["#2f8f5b", "#b5c96a", "#c9a27a", "#3a7bd5", "#d1495b"];
export const CLASS_NAMES = ["Tree cover", "Other vegetation", "Bare / sparse", "Water", "Built-up"];
