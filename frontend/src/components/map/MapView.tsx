import maplibregl, { type LngLatBoundsLike, type Map as MLMap, type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";

export type RasterLayer = {
  id: string;
  kind: "raster";
  tiles: string;
  opacity?: number;
  visible?: boolean;
  attribution?: string;
};

export type VectorLayer = {
  id: string;
  kind: "regions" | "outline" | "draw";
  data: GeoJSON.FeatureCollection | GeoJSON.Feature | null | undefined;
  visible?: boolean;
  color?: string;
  selectedId?: string | null;
};

export type MapLayer = RasterLayer | VectorLayer;

const BLANK_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0e1613" } }],
};
const BASEMAP_URL = "https://tiles.openfreemap.org/styles/dark";

interface Props {
  layers: MapLayer[];
  fitBounds?: [number, number, number, number] | null;
  fitKey?: string | number;
  onFeatureClick?: (f: maplibregl.MapGeoJSONFeature) => void;
  onMapClick?: (lngLat: { lng: number; lat: number }) => void;
  drawMode?: boolean;
  onDraw?: (bbox: [number, number, number, number]) => void;
  onMapReady?: (map: MLMap) => void;
  syncWith?: MLMap | null;
  children?: ReactNode;
  className?: string;
  interactive?: boolean;
  showControls?: boolean;
}

function addOrUpdate(map: MLMap, l: MapLayer, before?: string) {
  const vis = l.visible === false ? "none" : "visible";
  if (l.kind === "raster") {
    const src = map.getSource(l.id) as maplibregl.RasterTileSource | undefined;
    if (src && (src as unknown as { _sylvaTiles?: string })._sylvaTiles !== l.tiles) {
      map.removeLayer(l.id);
      map.removeSource(l.id);
    }
    if (!map.getSource(l.id)) {
      map.addSource(l.id, {
        type: "raster",
        tiles: [l.tiles],
        tileSize: 256,
        attribution: l.attribution ?? "Contains modified Copernicus Sentinel data · ESA WorldCover · Hansen/UMD/Google/USGS/NASA",
        maxzoom: 18,
      });
      (map.getSource(l.id) as unknown as { _sylvaTiles?: string })._sylvaTiles = l.tiles;
      map.addLayer({ id: l.id, type: "raster", source: l.id, paint: { "raster-opacity": l.opacity ?? 1, "raster-fade-duration": 150 } }, before);
    }
    map.setPaintProperty(l.id, "raster-opacity", l.opacity ?? 1);
    map.setLayoutProperty(l.id, "visibility", vis);
    return;
  }
  const data = (l.data ?? { type: "FeatureCollection", features: [] }) as GeoJSON.FeatureCollection;
  const src = map.getSource(l.id) as maplibregl.GeoJSONSource | undefined;
  if (src) src.setData(data);
  else map.addSource(l.id, { type: "geojson", data, promoteId: "id" });
  const fillId = `${l.id}-fill`;
  const lineId = `${l.id}-line`;
  if (l.kind === "regions") {
    if (!map.getLayer(fillId)) {
      map.addLayer({
        id: fillId,
        type: "fill",
        source: l.id,
        paint: {
          "fill-color": ["match", ["get", "change_type"], "potential_gain", "#3ba7d9", "#e4572e"],
          "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.55, 0.28],
        },
      });
      map.addLayer({
        id: lineId,
        type: "line",
        source: l.id,
        paint: {
          "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#ffffff", ["match", ["get", "change_type"], "potential_gain", "#7cc8ec", "#f28a6b"]],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, 1.1],
        },
      });
    }
    map.setLayoutProperty(fillId, "visibility", vis);
    map.setLayoutProperty(lineId, "visibility", vis);
  } else {
    if (!map.getLayer(lineId)) {
      map.addLayer({
        id: lineId,
        type: "line",
        source: l.id,
        paint: {
          "line-color": l.color ?? "#e8ebe9",
          "line-width": l.kind === "draw" ? 2 : 1.4,
          "line-dasharray": l.kind === "outline" ? [3, 2] : [1, 0],
        },
      });
    }
    map.setLayoutProperty(lineId, "visibility", vis);
  }
}

export function MapView({
  layers,
  fitBounds,
  fitKey,
  onFeatureClick,
  onMapClick,
  drawMode,
  onDraw,
  onMapReady,
  syncWith,
  children,
  className,
  interactive = true,
  showControls = true,
}: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [cursor, setCursor] = useState<{ lng: number; lat: number } | null>(null);
  const handlers = useRef({ onFeatureClick, onMapClick, onDraw, drawMode });
  handlers.current = { onFeatureClick, onMapClick, onDraw, drawMode };
  const selectedRef = useRef<Record<string, string | null>>({});

  useEffect(() => {
    if (!el.current) return;
    let cancelled = false;
    let map: MLMap | null = null;
    const init = (style: StyleSpecification) => {
      if (cancelled || !el.current) return;
      map = new maplibregl.Map({
        container: el.current,
        style,
        center: [-55.38, -7.05],
        zoom: 10,
        attributionControl: { compact: true },
        interactive,
        maxPitch: 0,
        dragRotate: false,
      });
      mapRef.current = map;
      setup(map);
      map.on("load", () => {
        setReady(true);
        el.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      });
      map.on("error", (e) => console.warn("map error", e?.error?.message));
    };
    // Load the basemap style first (2.5 s timeout); fall back to a blank style offline.
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 2500);
    fetch(BASEMAP_URL, { signal: ctl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("basemap"))))
      .then((style: StyleSpecification) => init(style))
      .catch(() => init(BLANK_STYLE))
      .finally(() => clearTimeout(timer));
    return () => {
      cancelled = true;
      ctl.abort();
      map?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setup = (map: MLMap) => {
    if (showControls) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    }
    map.on("mousemove", (e) => setCursor(e.lngLat));

    // rectangle drawing
    let start: maplibregl.LngLat | null = null;
    map.on("mousedown", (e) => {
      if (!handlers.current.drawMode) return;
      e.preventDefault();
      map.dragPan.disable();
      start = e.lngLat;
    });
    map.on("mousemove", (e) => {
      if (!start) return;
      const src = map.getSource("__draw") as maplibregl.GeoJSONSource | undefined;
      const b = [Math.min(start.lng, e.lngLat.lng), Math.min(start.lat, e.lngLat.lat), Math.max(start.lng, e.lngLat.lng), Math.max(start.lat, e.lngLat.lat)];
      const poly: GeoJSON.Feature = {
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] },
      };
      if (src) src.setData(poly);
      else {
        map.addSource("__draw", { type: "geojson", data: poly });
        map.addLayer({ id: "__draw-fill", type: "fill", source: "__draw", paint: { "fill-color": "#3faf86", "fill-opacity": 0.15 } });
        map.addLayer({ id: "__draw-line", type: "line", source: "__draw", paint: { "line-color": "#5cc79f", "line-width": 2 } });
      }
    });
    map.on("mouseup", (e) => {
      if (!start) return;
      const b: [number, number, number, number] = [
        Math.min(start.lng, e.lngLat.lng),
        Math.min(start.lat, e.lngLat.lat),
        Math.max(start.lng, e.lngLat.lng),
        Math.max(start.lat, e.lngLat.lat),
      ];
      start = null;
      map.dragPan.enable();
      if (b[2] - b[0] > 1e-4 && b[3] - b[1] > 1e-4) handlers.current.onDraw?.(b);
    });

    map.on("click", (e) => {
      if (handlers.current.drawMode) return;
      const regionLayers = (map.getStyle()?.layers ?? []).filter((l) => l.id.endsWith("-fill") && !l.id.startsWith("__")).map((l) => l.id);
      const feats = regionLayers.length ? map.queryRenderedFeatures(e.point, { layers: regionLayers }) : [];
      if (feats.length && handlers.current.onFeatureClick) handlers.current.onFeatureClick(feats[0]);
      else handlers.current.onMapClick?.(e.lngLat);
    });
    onMapReady?.(map);
  };

  // Sync layers whenever they change (and after the basemap style loads)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const apply = () => {
      const wanted = new Set(layers.map((l) => l.id));
      for (const l of layers) {
        try {
          addOrUpdate(map, l);
        } catch (err) {
          console.warn("layer error", l.id, err);
        }
      }
      // keep vector layers above rasters
      for (const l of layers) {
        if (l.kind !== "raster") {
          [`${l.id}-fill`, `${l.id}-line`].forEach((id) => map.getLayer(id) && map.moveLayer(id));
        }
      }
      ["__draw-fill", "__draw-line"].forEach((id) => map.getLayer(id) && map.moveLayer(id));
      // remove stale sylva layers
      for (const src of Object.keys(map.getStyle().sources)) {
        if (src.startsWith("sylva-") && !wanted.has(src)) {
          [src, `${src}-fill`, `${src}-line`].forEach((id) => map.getLayer(id) && map.removeLayer(id));
          map.removeSource(src);
        }
      }
      // selection state
      for (const l of layers) {
        if (l.kind === "regions") {
          const prev = selectedRef.current[l.id];
          if (prev && prev !== l.selectedId) map.setFeatureState({ source: l.id, id: prev }, { selected: false });
          if (l.selectedId) map.setFeatureState({ source: l.id, id: l.selectedId }, { selected: true });
          selectedRef.current[l.id] = l.selectedId ?? null;
        }
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("idle", apply);
  }, [layers, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !fitBounds) return;
    map.fitBounds(fitBounds as LngLatBoundsLike, { padding: 40, duration: 600, maxZoom: 16 });
  }, [fitKey, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = drawMode ? "crosshair" : "";
    if (!drawMode && map.getLayer("__draw-line")) {
      // keep drawn rectangle visible until next draw
    }
  }, [drawMode]);

  // Synchronise camera with another map (swipe compare)
  useEffect(() => {
    const a = mapRef.current;
    const b = syncWith;
    if (!a || !b) return;
    let lock = false;
    const sync = (from: MLMap, to: MLMap) => () => {
      if (lock) return;
      lock = true;
      to.jumpTo({ center: from.getCenter(), zoom: from.getZoom() });
      lock = false;
    };
    const s1 = sync(a, b);
    const s2 = sync(b, a);
    a.on("move", s1);
    b.on("move", s2);
    return () => {
      a.off("move", s1);
      b.off("move", s2);
    };
  }, [syncWith]);

  return (
    <div className={className ?? "relative h-full w-full"}>
      <div ref={el} style={{ position: "absolute", inset: 0 }} data-testid="map" />
      {showControls && cursor && (
        <div className="num pointer-events-none absolute bottom-2 right-24 rounded bg-canvas/80 px-2 py-0.5 text-[10px] text-ink-2">
          {cursor.lat.toFixed(5)}, {cursor.lng.toFixed(5)}
        </div>
      )}
      {children}
    </div>
  );
}
