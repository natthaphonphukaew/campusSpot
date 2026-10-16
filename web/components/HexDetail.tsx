import { growthLabel } from "@/lib/labels";
import type { CategoryId, Hex, Meta } from "@/lib/types";

function oppLabel(opp: number) {
  if (opp >= 80) return "โอกาสสูง";
  if (opp >= 50) return "พอมีโอกาส";
  return "โอกาสน้อย";
}

const fmt = (n: number) => n.toLocaleString("th-TH", { maximumFractionDigits: 1 });

export default function HexDetail({ hex, meta, category, onClose }: { hex: Hex; meta: Meta; category: CategoryId; onClose: () => void }) {
  const s = hex.scores[category];
  const label = meta.categories[category].label_th;

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] text-ink-3">ช่องที่เลือก · {label}</p>
        <button
          onClick={onClose}
          aria-label="ปิดรายละเอียด"
          className="-mt-1.5 -mr-1.5 grid h-9 w-9 place-items-center rounded-md text-ink-3 hover:bg-bg hover:text-ink"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <path d="M2 2l10 10M12 2 2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {hex.on_campus || !s ? (
        <p className="mt-2 text-[15px] leading-relaxed text-ink-2">
          ช่องนี้อยู่ในมหาวิทยาลัย ร้านในนี้ไม่นับเป็นคู่แข่งโดยตรง และเราไม่แนะนำเป็นทำเล
        </p>
      ) : (
        <>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-5xl leading-none font-semibold tracking-tight text-ink">{s.opportunity}</span>
            <span className="text-sm text-ink-3">/ 100</span>
            <span className="ml-auto rounded-full bg-bg px-2.5 py-1 text-[13px] font-medium text-ink-2">{oppLabel(s.opportunity)}</span>
          </div>
          <p className="mt-1 text-[13px] text-ink-3">คะแนนโอกาส เทียบกับช่องอื่นรอบ {meta.name_th}</p>

          <dl className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-line px-3 py-2.5">
              <dt className="text-xs text-ink-3">ย่านนี้น่าจะรองรับได้</dt>
              <dd className="mt-0.5 text-xl font-semibold text-ink">
                {fmt(s.expected)} <span className="text-sm font-normal text-ink-2">ร้าน</span>
              </dd>
            </div>
            <div className="rounded-lg border border-line px-3 py-2.5">
              <dt className="text-xs text-ink-3">มีอยู่จริง</dt>
              <dd className="mt-0.5 text-xl font-semibold text-ink">
                {s.actual} <span className="text-sm font-normal text-ink-2">ร้าน</span>
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-ink-3">นับ{label}ในรัศมี 200 ม. จากกลางช่อง</p>

          <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-sm">
            <span className="text-ink-2">อาคารรอบนี้ 2019–2025 (ดาวเทียม)</span>
            <span className="font-medium text-ink">{growthLabel(s.growth)}</span>
          </div>
        </>
      )}
    </div>
  );
}
