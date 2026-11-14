import type { Product } from "../api/types";
import { fmtDate, fmtPct } from "../lib/format";
import { Select } from "./ui";

export function ObservationSelect({
  products,
  value,
  onChange,
  placeholder = "Select observation",
  ...rest
}: {
  products: Product[] | undefined;
  value: string;
  onChange: (id: string) => void;
  placeholder?: string;
  "aria-label"?: string;
}) {
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} aria-label={rest["aria-label"]}>
      <option value="">{placeholder}</option>
      {products?.map((p) => (
        <option key={p.id} value={p.id}>
          {fmtDate(p.acquired)} · {p.kind === "composite" ? `composite (${p.acquired_list.length})` : p.platform ?? "S2"} · valid{" "}
          {fmtPct(p.valid_fraction, 0)}
        </option>
      ))}
    </Select>
  );
}
