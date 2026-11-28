import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { EpochRow } from "../../api/types";
import { CLASS_COLORS, CLASS_NAMES } from "../../lib/format";

const axis = { stroke: "#858c88", fontSize: 11, tickLine: false };
const grid = <CartesianGrid stroke="#2a2d2b" strokeDasharray="3 3" vertical={false} />;
const tooltipStyle = {
  contentStyle: { background: "#181a19", border: "1px solid #3b3f3d", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#b6bcb8" },
};

export function LossCurves({ epochs }: { epochs: EpochRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={epochs} margin={{ left: -10, right: 10, top: 8 }}>
        {grid}
        <XAxis dataKey="epoch" {...axis} />
        <YAxis {...axis} domain={[0, "auto"]} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => v?.toFixed(4)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="train_loss" name="Train loss (CE+Dice)" stroke="#3faf86" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="val_loss" name="Validation loss (CE)" stroke="#d9a441" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function MiouCurve({ epochs }: { epochs: EpochRow[] }) {
  const rows = epochs.map((e) => {
    const r: Record<string, number | null> = { epoch: e.epoch, miou: e.val_miou };
    e.val_per_class_iou.forEach((v, i) => (r[`c${i}`] = v));
    return r;
  });
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={rows} margin={{ left: -10, right: 10, top: 8 }}>
        {grid}
        <XAxis dataKey="epoch" {...axis} />
        <YAxis {...axis} domain={[0, 1]} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => v?.toFixed(3)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line dataKey="miou" name="Validation mIoU" stroke="#e8ebe9" strokeWidth={2.4} dot={false} isAnimationActive={false} />
        {CLASS_NAMES.map((n, i) => (
          <Line key={n} dataKey={`c${i}`} name={n} stroke={CLASS_COLORS[i]} strokeWidth={1.2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ConfusionMatrix({ cm, names = CLASS_NAMES }: { cm: number[][]; names?: string[] }) {
  const rowSums = cm.map((r) => r.reduce((a, b) => a + b, 0));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0.5 text-[11px]" data-testid="confusion-matrix">
        <thead>
          <tr>
            <th className="p-1 text-left font-normal text-faint">reference ↓ / predicted →</th>
            {names.map((n) => (
              <th key={n} className="p-1 text-center font-medium text-muted">
                {n}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cm.map((row, i) => (
            <tr key={i}>
              <th className="p-1 pr-2 text-left font-medium text-muted">{names[i]}</th>
              {row.map((v, j) => {
                const f = rowSums[i] ? v / rowSums[i] : 0;
                return (
                  <td
                    key={j}
                    title={`${v.toLocaleString()} px`}
                    className="num rounded p-1.5 text-center"
                    style={{
                      background: i === j ? `rgba(63,175,134,${0.12 + f * 0.75})` : `rgba(228,87,46,${f * 0.9})`,
                      color: f > 0.45 ? "#121413" : "#e8ebe9",
                    }}
                  >
                    {(f * 100).toFixed(1)}%
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1 text-[10px] text-faint">Row-normalised (recall per reference class). Hover a cell for pixel counts.</div>
    </div>
  );
}

export function Reliability({ bins }: { bins: { confidence: number; accuracy: number; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ left: -10, right: 10, top: 8 }}>
        {grid}
        <XAxis type="number" dataKey="confidence" name="Confidence" domain={[0, 1]} {...axis} />
        <YAxis type="number" dataKey="accuracy" name="Accuracy" domain={[0, 1]} {...axis} />
        <ZAxis type="number" dataKey="count" range={[30, 260]} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#858c88" strokeDasharray="4 4" />
        <Tooltip {...tooltipStyle} formatter={(v: number) => (v > 1 ? v.toLocaleString() : v.toFixed(3))} />
        <Scatter data={bins} fill="#3faf86" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
