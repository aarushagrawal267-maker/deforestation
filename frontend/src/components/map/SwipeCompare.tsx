import type { Map as MLMap } from "maplibre-gl";
import { useRef, useState, type ReactNode } from "react";
import { MapView, type MapLayer } from "./MapView";

/** Two synchronised maps with a draggable vertical divider. */
export function SwipeCompare({
  left,
  right,
  leftLabel,
  rightLabel,
  fitBounds,
  fitKey,
  overlay,
}: {
  left: MapLayer[];
  right: MapLayer[];
  leftLabel: ReactNode;
  rightLabel: ReactNode;
  fitBounds?: [number, number, number, number] | null;
  fitKey?: string | number;
  overlay?: ReactNode;
}) {
  const [pos, setPos] = useState(0.5);
  const [leftMap, setLeftMap] = useState<MLMap | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const drag = (e: React.PointerEvent) => {
    const el = box.current;
    if (!el) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const r = el.getBoundingClientRect();
      setPos(Math.min(0.98, Math.max(0.02, (ev.clientX - r.left) / r.width)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div ref={box} className="relative h-full w-full overflow-hidden">
      <MapView layers={left} fitBounds={fitBounds} fitKey={fitKey} onMapReady={setLeftMap} showControls={false} />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${pos * 100}%)` }}>
        <MapView layers={right} fitBounds={fitBounds} fitKey={fitKey} syncWith={leftMap} />
      </div>
      <div className="pointer-events-none absolute inset-y-0" style={{ left: `${pos * 100}%` }}>
        <div className="h-full w-px bg-white/80" />
      </div>
      <button
        aria-label="Drag to compare"
        onPointerDown={drag}
        className="absolute top-1/2 z-10 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border border-white/70 bg-canvas/90 text-xs text-ink"
        style={{ left: `${pos * 100}%` }}
      >
        ⇆
      </button>
      <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-canvas/85 px-2 py-1 text-[11px] text-ink">{leftLabel}</div>
      <div className="pointer-events-none absolute right-14 top-3 rounded-md bg-canvas/85 px-2 py-1 text-[11px] text-ink">{rightLabel}</div>
      {overlay}
    </div>
  );
}
