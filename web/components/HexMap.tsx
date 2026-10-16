"use client";

import { cellToBoundary } from "h3-js";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, LngLatBoundsLike, MapLayerMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { BASEMAP, MAP_COLORS, OPP_RAMP, OPP_STOPS, type Scheme } from "@/lib/scale";
import type { CategoryId, Hex, Meta } from "@/lib/types";

type Props = {
  meta: Meta;
  hexes: Hex[];
  category: CategoryId;
  scheme: Scheme;
};

// worker ของ MapLibre ถูกก๊อปไปไว้ที่ public/ (ดู scripts/copy-maplibre-worker.mjs)
maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

type Hover ={ x: number; y: number; w: number; h3: string };

function hexesToGeoJSON(hexes: Hex[], category: CategoryId): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: hexes.map((h) => ({
      type: "Feature",
      properties: { h3: h.h3, on_campus: h.on_campus, opp: h.scores[category]?.opportunity ?? 0 },
      geometry: { type: "Polygon", coordinates: [cellToBoundary(h.h3, true)] },
    })),
  };
}

function radiusRing(meta: Meta): GeoJSON.Feature {
  const [lat, lon] = meta.center;
  const coords: [number, number][] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    coords.push([
      lon + (meta.radius_m * Math.cos(a)) / (111_320 * Math.cos((lat * Math.PI) / 180)),
      lat + (meta.radius_m * Math.sin(a)) / 111_320,
    ]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } };
}

function ringBounds(ring: GeoJSON.Feature): LngLatBoundsLike {
  const coords = (ring.geometry as GeoJSON.LineString).coordinates;
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

// เว้นที่ให้แผงข้อมูลที่ลอยอยู่ทางซ้ายบนจอใหญ่
const fitPadding = () =>
  window.innerWidth >= 768 ? { top: 48, bottom: 48, left: 400, right: 48 } : { top: 56, bottom: 24, left: 16, right: 16 };

function addLayers(map: maplibregl.Map, data: GeoJSON.FeatureCollection, ring: GeoJSON.Feature, scheme: Scheme) {
  const c = MAP_COLORS[scheme];
  const ramp = OPP_RAMP[scheme];
  // วางชั้นของเราไว้ใต้ชื่อถนนและชื่อสถานที่ของแผนที่พื้นหลัง
  const beforeId = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  // ซ่อนโครงอาคารของ OSM: รอบมหาวิทยาลัยมีไม่ครบ ดูแล้วเข้าใจความหนาแน่นผิด และทำให้ช่องสีรก
  for (const l of map.getStyle().layers) {
    if (l.id.includes("building")) map.setLayoutProperty(l.id, "visibility", "none");
  }

  map.addSource("hexes", { type: "geojson", data, promoteId: "h3" });
  map.addSource("radius", { type: "geojson", data: ring });

  map.addLayer(
    {
      id: "hex-campus",
      type: "fill",
      source: "hexes",
      filter: ["==", ["get", "on_campus"], true],
      paint: { "fill-color": c.onCampus, "fill-opacity": 0.6 },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: "hex-fill",
      type: "fill",
      source: "hexes",
      filter: ["==", ["get", "on_campus"], false],
      paint: {
        "fill-color": ["interpolate", ["linear"], ["get", "opp"], ...OPP_STOPS.flatMap((s, i) => [s, ramp[i]])],
        "fill-opacity": c.fillOpacity,
      },
    },
    beforeId,
  );
  map.addLayer(
    { id: "hex-gap", type: "line", source: "hexes", paint: { "line-color": c.gap, "line-width": 1 } },
    beforeId,
  );
  map.addLayer(
    {
      id: "hex-hover",
      type: "line",
      source: "hexes",
      paint: {
        "line-color": c.hover,
        "line-width": 2,
        "line-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 1, 0],
      },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: "radius",
      type: "line",
      source: "radius",
      paint: { "line-color": c.radius, "line-width": 1.5, "line-dasharray": [3, 3] },
    },
    beforeId,
  );
}

export default function HexMap({ meta, hexes, category, scheme }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const data = useMemo(() => hexesToGeoJSON(hexes, category), [hexes, category]);
  const ring = useMemo(() => radiusRing(meta), [meta]);
  const byId = useMemo(() => new Map(hexes.map((h) => [h.h3, h])), [hexes]);

  // ค่าล่าสุดสำหรับ callback ของ MapLibre ที่ผูกไว้ครั้งเดียว
  const latest = useRef({ data, scheme });
  useEffect(() => {
    latest.current = { data, scheme };
  }, [data, scheme]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const map = new maplibregl.Map({
      container,
      style: BASEMAP[latest.current.scheme],
      bounds: ringBounds(ring),
      fitBoundsOptions: { padding: fitPadding() },
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    // style.load เกิดทุกครั้งที่เปลี่ยนแผนที่พื้นหลัง (สลับโหมดสว่าง/มืด) จึงต้องใส่ชั้นใหม่ทุกครั้ง
    map.on("style.load", () => addLayers(map, latest.current.data, ring, latest.current.scheme));

    let hovered: string | null = null;
    const clearHover = () => {
      if (hovered) map.setFeatureState({ source: "hexes", id: hovered }, { hover: false });
      hovered = null;
      setHover(null);
    };
    const onHex = (e: MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.h3 as string | undefined;
      if (!id) return;
      if (hovered !== id) {
        if (hovered) map.setFeatureState({ source: "hexes", id: hovered }, { hover: false });
        map.setFeatureState({ source: "hexes", id }, { hover: true });
        hovered = id;
      }
      map.getCanvas().style.cursor = "pointer";
      setHover({ x: e.point.x, y: e.point.y, w: map.getContainer().clientWidth, h3: id });
    };
    for (const layer of ["hex-fill", "hex-campus"]) {
      map.on("mousemove", layer, onHex);
      map.on("click", layer, onHex); // มือถือไม่มี hover ใช้แตะแทน
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
        clearHover();
      });
    }
    map.on("movestart", () => {
      if (window.matchMedia("(hover: none)").matches) clearHover();
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [ring]);

  // สลับแผนที่พื้นหลังตามโหมดสว่าง/มืด
  const firstScheme = useRef(scheme);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || scheme === firstScheme.current) return;
    firstScheme.current = scheme;
    map.setStyle(BASEMAP[scheme], { diff: false });
  }, [scheme]);

  // เปลี่ยนหมวดร้าน → อัปเดตสีช่อง
  useEffect(() => {
    (mapRef.current?.getSource("hexes") as GeoJSONSource | undefined)?.setData(data);
  }, [data]);

  const hex = hover ? byId.get(hover.h3) : undefined;
  const score = hex?.scores[category];

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {hover && hex && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-panel"
          style={{
            left: Math.min(hover.x + 14, hover.w - 180),
            top: Math.max(hover.y - 52, 8),
          }}
        >
          {hex.on_campus ? (
            <span className="text-ink-2">ในมหาวิทยาลัย ไม่นับเป็นทำเล</span>
          ) : (
            <>
              <span className="text-ink-2">คะแนนโอกาส </span>
              <span className="font-semibold text-ink">{score?.opportunity ?? "–"}</span>
              <span className="text-ink-3"> / 100</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
