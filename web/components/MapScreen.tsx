"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { IS_MOCK, loadDataset } from "@/lib/data";
import { oppGradientCss, MAP_COLORS, type Scheme } from "@/lib/scale";
import type { CategoryId, Hex, Meta } from "@/lib/types";
import { useColorScheme } from "@/lib/useColorScheme";

// MapLibre ใช้ได้แค่ในเบราว์เซอร์
const HexMap = dynamic(() => import("./HexMap"), { ssr: false });

const CATEGORY: CategoryId = "cafe";

type State = { status: "loading" } | { status: "error" } | { status: "ready"; meta: Meta; hexes: Hex[] };

export default function MapScreen() {
  const scheme = useColorScheme();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    loadDataset()
      .then(({ meta, hexes }) => setState({ status: "ready", meta, hexes }))
      .catch(() => setState({ status: "error" }));
  }, []);

  const meta = state.status === "ready" ? state.meta : null;

  return (
    <main className="relative flex h-dvh flex-col overflow-hidden bg-bg md:block">
      <div className="relative min-h-0 flex-1 md:absolute md:inset-0">
        {state.status === "ready" && (
          <HexMap meta={state.meta} hexes={state.hexes} category={CATEGORY} scheme={scheme} />
        )}
        {state.status === "loading" && <Status text="กำลังโหลดแผนที่…" />}
        {state.status === "error" && <Status text="โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าอีกครั้ง" />}
      </div>

      {IS_MOCK && <MockBadge />}

      <section
        className="relative z-10 border-t border-line bg-surface px-5 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]
                   md:absolute md:top-4 md:left-4 md:w-[340px] md:rounded-xl md:border md:p-5 md:shadow-panel"
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-line md:hidden" aria-hidden />
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[15px] font-semibold tracking-tight text-ink">CampusSpot</p>
          {meta && (
            <p className="text-[13px] text-ink-3">
              {meta.name_th} · รัศมี {(meta.radius_m / 1000).toLocaleString("th-TH")} กม.
            </p>
          )}
        </div>

        <h1 className="mt-3 text-xl leading-snug font-semibold text-ink md:mt-4">
          ทำเลน่าเปิด{meta?.categories[CATEGORY].label_th ?? "ร้านกาแฟ"}
        </h1>
        <p className="mt-1 text-sm leading-relaxed text-ink-2">
          ช่องยิ่งเขียวเข้ม ยิ่งมีโอกาส คือคนรอบ ๆ น่าจะต้องการร้านมากกว่าที่มีอยู่ตอนนี้
        </p>

        <Legend scheme={scheme} />
      </section>
    </main>
  );
}

function Legend({ scheme }: { scheme: Scheme }) {
  return (
    <div className="mt-4" aria-label="คำอธิบายสี">
      <div className="mb-1.5 flex justify-between text-xs text-ink-3">
        <span>โอกาสน้อย</span>
        <span>โอกาสมาก</span>
      </div>
      <div className="h-2.5 rounded-sm" style={{ background: oppGradientCss(scheme) }} />
      <div className="mt-1 flex justify-between text-xs text-ink-3">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
      <div className="mt-3 flex items-center gap-2 text-xs text-ink-2">
        <span
          className="inline-block h-3 w-3 rounded-[3px]"
          style={{ background: MAP_COLORS[scheme].onCampus }}
          aria-hidden
        />
        ในมหาวิทยาลัย ไม่นับเป็นทำเล
      </div>
    </div>
  );
}

function MockBadge() {
  return (
    <div
      role="status"
      className="absolute top-3 right-3 z-20 flex items-center gap-2 rounded-full border border-warn-line bg-warn-bg
                 px-3 py-1.5 text-[13px] font-medium text-warn-ink shadow-panel md:top-4 md:right-4"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
        <path
          d="M8 1.5 15 14H1L8 1.5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 6v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.75" r="0.9" fill="currentColor" />
      </svg>
      ข้อมูลจำลอง
      <span className="hidden font-normal sm:inline">· ตัวเลขยังไม่ใช่ของจริง</span>
    </div>
  );
}

function Status({ text }: { text: string }) {
  return <div className="absolute inset-0 grid place-items-center text-sm text-ink-3">{text}</div>;
}
