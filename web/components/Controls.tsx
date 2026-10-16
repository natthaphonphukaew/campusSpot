import { CATEGORY_ORDER, CATEGORY_SHORT } from "@/lib/labels";
import { builtGradientCss, MAP_COLORS, oppGradientCss, type Scheme } from "@/lib/scale";
import type { CategoryId, Meta } from "@/lib/types";

export function CategoryTabs({
  value,
  onChange,
  floating = false,
}: {
  value: CategoryId;
  onChange: (c: CategoryId) => void;
  floating?: boolean;
}) {
  return (
    <div
      role="tablist"
      aria-label="หมวดร้าน"
      className={
        floating
          ? "flex gap-1.5 overflow-x-auto rounded-full border border-line bg-surface p-1 shadow-panel [scrollbar-width:none]"
          : "grid grid-cols-4 gap-1 rounded-lg bg-bg p-1"
      }
    >
      {CATEGORY_ORDER.map((c) => {
        const active = c === value;
        return (
          <button
            key={c}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(c)}
            className={`min-h-9 shrink-0 rounded-full px-3.5 text-sm font-medium whitespace-nowrap transition-colors md:rounded-md md:px-2 ${
              active ? "bg-ink text-surface" : "text-ink-2 hover:text-ink"
            }`}
          >
            {CATEGORY_SHORT[c]}
          </button>
        );
      })}
    </div>
  );
}

export function ConfidenceNote({ meta, category }: { meta: Meta; category: CategoryId }) {
  const c = meta.categories[category];
  if (c.confidence === "low") {
    return (
      <div className="flex gap-2.5 rounded-lg border border-warn-line bg-warn-bg px-3 py-2.5 text-warn-ink">
        <WarnIcon />
        <div className="text-[13px] leading-snug">
          <p className="font-semibold">ข้อมูล{c.label_th}ยังบาง ใช้ประกอบการตัดสินใจเท่านั้น</p>
          {c.note_th && <p className="mt-0.5 opacity-90">{c.note_th}</p>}
        </div>
      </div>
    );
  }
  return (
    <p className="flex items-center gap-2 text-[13px] text-ink-3">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
      ข้อมูล{c.label_th}ค่อนข้างครบ{c.note_th ? ` (${c.note_th})` : ""}
    </p>
  );
}

export function Legend({ scheme }: { scheme: Scheme }) {
  return (
    <div aria-label="คำอธิบายสี">
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
        <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: MAP_COLORS[scheme].onCampus }} aria-hidden />
        ในมหาวิทยาลัย ไม่นับเป็นทำเล
      </div>
    </div>
  );
}

export function BuiltLegend({ scheme, year }: { scheme: Scheme; year: number }) {
  return (
    <div aria-label="คำอธิบายสีความหนาแน่นอาคาร">
      <div className="mb-1.5 flex justify-between text-xs text-ink-3">
        <span>อาคารน้อย</span>
        <span>อาคารแน่น</span>
      </div>
      <div className="h-2.5 rounded-sm" style={{ background: builtGradientCss(scheme) }} />
      <p className="mt-1.5 text-xs text-ink-3">ความหนาแน่นอาคารจากดาวเทียม ปี {year}</p>
    </div>
  );
}

export function SatelliteButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className={`flex min-h-10 w-full items-center gap-2.5 rounded-lg border px-3 text-left text-sm font-medium transition-colors ${
        on ? "border-accent bg-accent text-surface" : "border-line text-ink hover:border-ink-3"
      }`}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden className="shrink-0">
        <rect x="5.5" y="5.5" width="5" height="5" rx="1" transform="rotate(45 8 8)" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M1.5 6.5 4 4M12 12l2.5-2.5M4 12l-2.5-2.5M12 4l2.5 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      {on ? "ปิดภาพดาวเทียม" : "ดูอาคารใหม่จากดาวเทียม 2019–2025"}
    </button>
  );
}

export function PoiToggle({ checked, onChange, scheme }: { checked: boolean; onChange: (v: boolean) => void; scheme: Scheme }) {
  const c = MAP_COLORS[scheme];
  return (
    <label className="flex min-h-9 cursor-pointer items-center justify-between gap-3 text-sm text-ink-2">
      <span className="flex items-center gap-2">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c.poi, boxShadow: `0 0 0 1.5px ${c.poiRing}, 0 0 0 2.5px ${c.poiFlagged}` }} aria-hidden />
        แสดงร้านที่มีอยู่แล้ว
      </span>
      <span className="relative inline-flex">
        <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="h-5 w-9 rounded-full bg-line transition-colors peer-checked:bg-accent peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent" />
        <span className="absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-surface shadow transition-transform peer-checked:translate-x-4" />
      </span>
    </label>
  );
}

export function WarnIcon({ className = "mt-0.5 shrink-0" }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden className={className}>
      <path d="M8 1.5 15 14H1L8 1.5Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M8 6v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="11.75" r="0.9" fill="currentColor" />
    </svg>
  );
}
