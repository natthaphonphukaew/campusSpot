"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { IS_MOCK, loadDataset, loadWayback } from "@/lib/data";
import type { CategoryId, Hex, Meta, Poi, SatWayback } from "@/lib/types";
import { useColorScheme } from "@/lib/useColorScheme";
import { BuiltLegend, CategoryTabs, ConfidenceNote, Legend, PoiToggle, SatelliteButton, WarnIcon } from "./Controls";
import HexDetail from "./HexDetail";
import type { HexMode, SatView } from "./HexMap";
import Timeline from "./Timeline";

// MapLibre ใช้ได้แค่ในเบราว์เซอร์
const HexMap = dynamic(() => import("./HexMap"), { ssr: false });

type State = { status: "loading" } | { status: "error" } | { status: "ready"; meta: Meta; hexes: Hex[]; pois: Poi[] };

export default function MapScreen() {
  const scheme = useColorScheme();
  const [state, setState] = useState<State>({ status: "loading" });
  const [category, setCategory] = useState<CategoryId>("cafe");
  const [showPois, setShowPois] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  // ไทม์แลปส์ดาวเทียม
  const [satOn, setSatOn] = useState(false);
  const [wayback, setWayback] = useState<SatWayback | null | undefined>(undefined); // undefined = ยังไม่ได้โหลด
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [opacity, setOpacity] = useState(1);
  const [hexMode, setHexMode] = useState<HexMode>("opportunity");

  useEffect(() => {
    loadDataset()
      .then((d) => setState({ status: "ready", ...d }))
      .catch(() => setState({ status: "error" }));
  }, []);

  // กด Esc เพื่อปิดรายละเอียด
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onSelect = useCallback((h3: string | null) => setSelected(h3), []);
  const ready = state.status === "ready" ? state : null;
  const meta = ready?.meta ?? null;
  const frames = useMemo(() => wayback?.frames ?? [], [wayback]);

  // เล่นอัตโนมัติ ภาพละ 1 วินาที หยุดเองเมื่อถึงภาพล่าสุด
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => (frame >= frames.length - 1 ? setPlaying(false) : setFrame(frame + 1)), 1000);
    return () => clearTimeout(t);
  }, [playing, frame, frames.length]);

  const openSatellite = () => {
    if (!meta) return;
    if (wayback === undefined) loadWayback(meta.uni_id).then(setWayback);
    setFrame(0);
    setHexMode("none");
    setSatOn(true);
  };
  const closeSatellite = () => {
    setSatOn(false);
    setPlaying(false);
    setHexMode("opportunity");
  };
  const togglePlay = () => {
    if (!playing && frame >= frames.length - 1) setFrame(0);
    setPlaying(!playing);
  };

  // ค่า built (Dynamic World มีปี 2019–2025) ที่ใช้ระบายช่องในโหมด "อาคาร" = ปีที่ใกล้วันถ่ายภาพที่สุด
  const builtYears = meta?.sat_years ?? [];
  const capturedYear = frames[frame] ? Number(frames[frame].captured.slice(0, 4)) : (builtYears.at(-1) ?? 2025);
  const builtYear = builtYears.length
    ? Math.min(Math.max(capturedYear, builtYears[0]), builtYears[builtYears.length - 1])
    : capturedYear;

  const sat: SatView = useMemo(
    () => ({ on: satOn, frame, opacity, wayback: wayback ?? null, builtYear }),
    [satOn, frame, opacity, wayback, builtYear],
  );
  const hex = ready && selected ? ready.hexes.find((h) => h.h3 === selected) : undefined;
  const label = meta?.categories[category].label_th ?? "ร้านกาแฟ";

  const detail = hex && meta && (
    <HexDetail hex={hex} meta={meta} category={category} onClose={() => setSelected(null)} />
  );

  return (
    <main className="relative flex h-dvh flex-col overflow-hidden bg-bg md:block">
      <div className="relative min-h-0 flex-1 md:absolute md:inset-0">
        {ready && (
          <HexMap
            meta={ready.meta}
            hexes={ready.hexes}
            pois={ready.pois}
            category={category}
            scheme={scheme}
            showPois={showPois}
            selected={selected}
            onSelect={onSelect}
            hexMode={hexMode}
            sat={sat}
          />
        )}
        {state.status === "loading" && <Status text="กำลังโหลดแผนที่…" />}
        {state.status === "error" && <Status text="โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง" />}

        {/* แถบไทม์แลปส์: มือถืออยู่ใต้แถบหมวดด้านบน (ไม่บังเครดิตแผนที่ด้านล่าง) / จอใหญ่อยู่กลางล่าง */}
        {satOn && wayback !== undefined && (
          <div className="absolute top-16 right-3 left-3 z-20 md:top-auto md:right-auto md:bottom-6 md:left-1/2 md:w-[520px] md:-translate-x-1/2">
            <Timeline
              frames={frames}
              frame={frame}
              onFrame={(i) => {
                setPlaying(false);
                setFrame(i);
              }}
              playing={playing}
              onTogglePlay={togglePlay}
              opacity={opacity}
              onOpacity={setOpacity}
              hexMode={hexMode}
              onHexMode={setHexMode}
              attribution={wayback?.attribution ?? null}
              onClose={closeSatellite}
            />
          </div>
        )}

        {/* มือถือ: แถบหมวดลอยอยู่บนแผนที่ */}
        <div className="absolute top-3 right-3 left-3 z-20 md:hidden">
          <CategoryTabs value={category} onChange={setCategory} floating />
        </div>
      </div>

      {IS_MOCK && <MockBadge />}

      {/* แผงซ้าย (จอใหญ่) / แผ่นล่าง (มือถือ) */}
      <section
        className="relative z-10 max-h-[55dvh] overflow-y-auto border-t border-line bg-surface px-5 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]
                   md:absolute md:top-4 md:left-4 md:max-h-[calc(100dvh-2rem)] md:w-[340px] md:rounded-xl md:border md:p-5 md:shadow-panel"
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-line md:hidden" aria-hidden />

        {/* มือถือ: เลือกช่องแล้วแผ่นล่างแสดงรายละเอียดแทน */}
        {detail && <div className="md:hidden">{detail}</div>}

        {/* มือถือ + เปิดดาวเทียม: เหลือแค่แถบสี ให้แผนที่มีที่มากขึ้น */}
        {satOn && !detail && (
          <div className="md:hidden">
            {hexMode === "built" ? <BuiltLegend scheme={scheme} year={builtYear} /> : <Legend scheme={scheme} />}
          </div>
        )}

        <div className={detail || satOn ? "hidden md:block" : ""}>
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[15px] font-semibold tracking-tight text-ink">CampusSpot</p>
            {meta && (
              <p className="text-[13px] text-ink-3">
                {meta.name_th} · รัศมี {(meta.radius_m / 1000).toLocaleString("th-TH")} กม.
              </p>
            )}
          </div>

          <h1 className="mt-3 text-xl leading-snug font-semibold text-ink md:mt-4">ทำเลน่าเปิด{label}</h1>
          <p className="mt-1 text-sm leading-relaxed text-ink-2">
            ช่องยิ่งเขียวเข้ม ยิ่งมีโอกาส คือคนรอบ ๆ น่าจะต้องการร้านมากกว่าที่มีอยู่ตอนนี้ แตะช่องเพื่อดูรายละเอียด
          </p>

          <div className="mt-4 hidden md:block">
            <CategoryTabs value={category} onChange={setCategory} />
          </div>

          {meta && (
            <div className="mt-3">
              <ConfidenceNote meta={meta} category={category} />
            </div>
          )}

          <div className="mt-4">
            {hexMode === "built" ? <BuiltLegend scheme={scheme} year={builtYear} /> : <Legend scheme={scheme} />}
          </div>

          <div className="mt-3 border-t border-line pt-2">
            <PoiToggle checked={showPois} onChange={setShowPois} scheme={scheme} />
          </div>

          {meta && (
            <div className="mt-3">
              <SatelliteButton on={satOn} onClick={satOn ? closeSatellite : openSatellite} />
            </div>
          )}
        </div>
      </section>

      {/* จอใหญ่: รายละเอียดเป็นแผงด้านขวา */}
      {detail && (
        <aside className="absolute top-4 right-4 z-10 hidden max-h-[calc(100dvh-2rem)] w-[340px] overflow-y-auto rounded-xl border border-line bg-surface p-5 shadow-panel md:block">
          {detail}
        </aside>
      )}
    </main>
  );
}

function MockBadge() {
  return (
    <div
      role="status"
      className="absolute top-16 right-3 z-20 flex items-center gap-2 rounded-full border border-warn-line bg-warn-bg
                 px-3 py-1.5 text-[13px] font-medium text-warn-ink shadow-panel md:top-4 md:right-4"
    >
      <WarnIcon className="shrink-0" />
      ข้อมูลจำลอง
      <span className="hidden font-normal sm:inline">· ตัวเลขยังไม่ใช่ของจริง</span>
    </div>
  );
}

function Status({ text }: { text: string }) {
  return <div className="absolute inset-0 grid place-items-center text-sm text-ink-3">{text}</div>;
}
