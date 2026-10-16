"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { IS_MOCK, loadDataset } from "@/lib/data";
import type { CategoryId, Hex, Meta, Poi } from "@/lib/types";
import { useColorScheme } from "@/lib/useColorScheme";
import { CategoryTabs, ConfidenceNote, Legend, PoiToggle, WarnIcon } from "./Controls";
import HexDetail from "./HexDetail";

// MapLibre ใช้ได้แค่ในเบราว์เซอร์
const HexMap = dynamic(() => import("./HexMap"), { ssr: false });

type State = { status: "loading" } | { status: "error" } | { status: "ready"; meta: Meta; hexes: Hex[]; pois: Poi[] };

export default function MapScreen() {
  const scheme = useColorScheme();
  const [state, setState] = useState<State>({ status: "loading" });
  const [category, setCategory] = useState<CategoryId>("cafe");
  const [showPois, setShowPois] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

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
          />
        )}
        {state.status === "loading" && <Status text="กำลังโหลดแผนที่…" />}
        {state.status === "error" && <Status text="โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง" />}

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

        <div className={detail ? "hidden md:block" : ""}>
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
            <Legend scheme={scheme} />
          </div>

          <div className="mt-3 border-t border-line pt-2">
            <PoiToggle checked={showPois} onChange={setShowPois} scheme={scheme} />
          </div>
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
