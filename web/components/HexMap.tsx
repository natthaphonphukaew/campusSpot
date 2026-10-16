"use client";

import { cellToBoundary } from "h3-js";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, LngLatBoundsLike, MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { FLAG_LABEL } from "@/lib/labels";
import { BASEMAP, MAP_COLORS, OPP_RAMP, OPP_STOPS, type Scheme } from "@/lib/scale";
import type { CategoryId, Hex, Meta, Poi } from "@/lib/types";

type Props = {
  meta: Meta;
  hexes: Hex[];
  pois: Poi[];
  category: CategoryId;
  scheme: Scheme;
  showPois: boolean;
  selected: string | null;
  onSelect: (h3: string | null) => void;
};

// worker ของ MapLibre ถูกก๊อปไปไว้ที่ public/ (ดู scripts/copy-maplibre-worker.mjs)
maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

type Hover = { x: number; y: number; w: number } & ({ kind: "hex"; h3: string } | { kind: "poi"; name: string; flag: string });

const HEX_LAYERS = ["hex-fill", "hex-campus"];
const POI_LAYERS = ["poi-ok", "poi-flagged"];

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

function poisToGeoJSON(pois: Poi[], category: CategoryId): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: pois
      .filter((p) => p.category === category)
      .map((p) => ({
        type: "Feature",
        properties: { name: p.name, flag: p.flag },
        geometry: { type: "Point", coordinates: [p.lon, p.lat] },
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

// เว้นที่ให้แผงที่ลอยอยู่บนจอใหญ่ / แถบหมวดด้านบนบนมือถือ
const fitPadding = () =>
  window.innerWidth >= 768 ? { top: 48, bottom: 48, left: 400, right: 48 } : { top: 64, bottom: 16, left: 16, right: 16 };

type Sources = { hexes: GeoJSON.FeatureCollection; pois: GeoJSON.FeatureCollection; ring: GeoJSON.Feature };

function addLayers(map: maplibregl.Map, src: Sources, scheme: Scheme, showPois: boolean) {
  const c = MAP_COLORS[scheme];
  const ramp = OPP_RAMP[scheme];
  // วางช่องสีไว้ใต้ชื่อถนนและชื่อสถานที่ของแผนที่พื้นหลัง ส่วนจุดร้านวางบนสุด
  const beforeId = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  // ซ่อนโครงอาคารของ OSM (รอบมหาวิทยาลัยมีไม่ครบ ดูแล้วเข้าใจความหนาแน่นผิด)
  // และพื้นที่สีเขียว/ย่านที่พักของแผนที่พื้นหลัง (สีโผล่ทะลุช่องโปร่ง ทำให้อ่านสีคะแนนเพี้ยน) — เก็บแหล่งน้ำไว้
  for (const l of map.getStyle().layers) {
    if (/building|^landcover_|^landuse_/.test(l.id)) map.setLayoutProperty(l.id, "visibility", "none");
  }

  map.addSource("hexes", { type: "geojson", data: src.hexes, promoteId: "h3" });
  map.addSource("radius", { type: "geojson", data: src.ring });
  map.addSource("pois", { type: "geojson", data: src.pois });

  const isOn = (flag: boolean): maplibregl.ExpressionSpecification => ["==", ["get", "on_campus"], flag];
  const state = (key: string): maplibregl.ExpressionSpecification => ["boolean", ["feature-state", key], false];

  map.addLayer({ id: "hex-campus", type: "fill", source: "hexes", filter: isOn(true),
    paint: { "fill-color": c.onCampus, "fill-opacity": 0.6 } }, beforeId);
  map.addLayer({ id: "hex-fill", type: "fill", source: "hexes", filter: isOn(false),
    paint: {
      "fill-color": ["interpolate", ["linear"], ["get", "opp"], ...OPP_STOPS.flatMap((s, i) => [s, ramp[i]])],
      "fill-opacity": c.fillOpacity,
    } }, beforeId);
  map.addLayer({ id: "hex-gap", type: "line", source: "hexes",
    paint: { "line-color": c.gap, "line-width": 1 } }, beforeId);
  map.addLayer({ id: "hex-hover", type: "line", source: "hexes",
    paint: { "line-color": c.hover, "line-width": 1.5, "line-opacity": ["case", state("hover"), 0.8, 0] } }, beforeId);
  map.addLayer({ id: "hex-selected", type: "line", source: "hexes",
    paint: { "line-color": c.hover, "line-width": 3, "line-opacity": ["case", state("selected"), 1, 0] } }, beforeId);
  map.addLayer({ id: "radius", type: "line", source: "radius",
    paint: { "line-color": c.radius, "line-width": 1.5, "line-dasharray": [3, 3] } }, beforeId);

  const vis = showPois ? "visible" : "none";
  const radius: maplibregl.ExpressionSpecification = ["interpolate", ["linear"], ["zoom"], 13, 2.5, 16, 5, 18, 7];
  map.addLayer({ id: "poi-flagged", type: "circle", source: "pois", filter: ["!=", ["get", "flag"], "ok"],
    layout: { visibility: vis },
    paint: { "circle-radius": radius, "circle-color": c.poiFlagged, "circle-opacity": 0.45 } });
  map.addLayer({ id: "poi-ok", type: "circle", source: "pois", filter: ["==", ["get", "flag"], "ok"],
    layout: { visibility: vis },
    paint: { "circle-radius": radius, "circle-color": c.poi, "circle-stroke-color": c.poiRing, "circle-stroke-width": 1.5 } });
}

export default function HexMap({ meta, hexes, pois, category, scheme, showPois, selected, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const hexData = useMemo(() => hexesToGeoJSON(hexes, category), [hexes, category]);
  const poiData = useMemo(() => poisToGeoJSON(pois, category), [pois, category]);
  const ring = useMemo(() => radiusRing(meta), [meta]);
  const byId = useMemo(() => new Map(hexes.map((h) => [h.h3, h])), [hexes]);

  // ค่าล่าสุดสำหรับ callback ของ MapLibre ที่ผูกไว้ครั้งเดียว
  const latest = useRef({ hexData, poiData, scheme, showPois, selected, onSelect });
  useEffect(() => {
    latest.current = { hexData, poiData, scheme, showPois, selected, onSelect };
  }, [hexData, poiData, scheme, showPois, selected, onSelect]);

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

    // style.load เกิดทุกครั้งที่เปลี่ยนแผนที่พื้นหลัง (สลับโหมดสว่าง/มืด) จึงต้องใส่ชั้นและสถานะเลือกใหม่ทุกครั้ง
    map.on("style.load", () => {
      const l = latest.current;
      addLayers(map, { hexes: l.hexData, pois: l.poiData, ring }, l.scheme, l.showPois);
      if (l.selected) map.setFeatureState({ source: "hexes", id: l.selected }, { selected: true });
    });

    const canHover = window.matchMedia("(hover: hover)").matches;
    let hovered: string | null = null;
    const setHexHover = (id: string | null) => {
      if (hovered === id) return;
      if (hovered) map.setFeatureState({ source: "hexes", id: hovered }, { hover: false });
      if (id) map.setFeatureState({ source: "hexes", id }, { hover: true });
      hovered = id;
    };
    const layersAt = (e: MapMouseEvent, ids: string[]) =>
      map.queryRenderedFeatures(e.point, { layers: ids.filter((id) => map.getLayer(id)) });

    map.on("mousemove", (e) => {
      if (!canHover || !map.getLayer("hex-fill")) return;
      const w = map.getContainer().clientWidth;
      const poi = layersAt(e, POI_LAYERS)[0];
      const hex = layersAt(e, HEX_LAYERS)[0];
      setHexHover((hex?.properties?.h3 as string) ?? null);
      map.getCanvas().style.cursor = hex ? "pointer" : "";
      if (poi) setHover({ kind: "poi", x: e.point.x, y: e.point.y, w, name: poi.properties.name, flag: poi.properties.flag });
      else if (hex) setHover({ kind: "hex", x: e.point.x, y: e.point.y, w, h3: hex.properties.h3 });
      else setHover(null);
    });
    map.on("mouseout", () => {
      setHexHover(null);
      setHover(null);
    });
    // คลิกช่อง = เลือก, คลิกนอกช่อง = ยกเลิกการเลือก
    map.on("click", (e) => {
      const hex = layersAt(e, HEX_LAYERS)[0];
      latest.current.onSelect((hex?.properties?.h3 as string) ?? null);
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

  // เปลี่ยนหมวดร้าน → อัปเดตสีช่องและจุดร้าน
  useEffect(() => {
    (mapRef.current?.getSource("hexes") as GeoJSONSource | undefined)?.setData(hexData);
  }, [hexData]);
  useEffect(() => {
    (mapRef.current?.getSource("pois") as GeoJSONSource | undefined)?.setData(poiData);
  }, [poiData]);

  // เปิด/ปิดชั้นจุดร้าน
  useEffect(() => {
    const map = mapRef.current;
    for (const id of POI_LAYERS) {
      if (map?.getLayer(id)) map.setLayoutProperty(id, "visibility", showPois ? "visible" : "none");
    }
  }, [showPois]);

  // ไฮไลต์ช่องที่เลือก
  const prevSelected = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("hexes")) return;
    if (prevSelected.current) map.setFeatureState({ source: "hexes", id: prevSelected.current }, { selected: false });
    if (selected) map.setFeatureState({ source: "hexes", id: selected }, { selected: true });
    prevSelected.current = selected;
  }, [selected]);

  const hoverHex = hover?.kind === "hex" ? byId.get(hover.h3) : undefined;

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {hover && (hover.kind === "poi" || hoverHex) && (
        <div
          className="pointer-events-none absolute z-10 max-w-60 rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-panel"
          style={{ left: Math.min(hover.x + 14, hover.w - 250), top: Math.max(hover.y - 56, 8) }}
        >
          {hover.kind === "poi" ? (
            <>
              <p className="font-medium text-ink">{hover.name || "ไม่มีชื่อ"}</p>
              {hover.flag !== "ok" && (
                <p className="text-xs text-ink-3">{FLAG_LABEL[hover.flag as keyof typeof FLAG_LABEL]} · ไม่นับในคะแนน</p>
              )}
            </>
          ) : hoverHex?.on_campus ? (
            <span className="text-ink-2">ในมหาวิทยาลัย ไม่นับเป็นทำเล</span>
          ) : (
            <>
              <span className="text-ink-2">คะแนนโอกาส </span>
              <span className="font-semibold text-ink">{hoverHex?.scores[category]?.opportunity ?? "–"}</span>
              <span className="text-ink-3"> / 100</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
