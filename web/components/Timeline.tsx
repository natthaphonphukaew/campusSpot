import type { SatFrame } from "@/lib/types";
import { WarnIcon } from "./Controls";
import type { HexMode } from "./HexMap";

const MODES: { id: HexMode; label: string }[] = [
  { id: "none", label: "ภาพล้วน" },
  { id: "built", label: "อาคาร" },
  { id: "opportunity", label: "โอกาส" },
];

// เดือนย่อภาษาไทย ปี ค.ศ. ให้ตรงกับปีอื่นบนหน้า
const monthYear = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("th-TH-u-ca-gregory", { month: "short", year: "numeric" });

type Props = {
  frames: SatFrame[];
  frame: number;
  onFrame: (i: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  opacity: number;
  onOpacity: (v: number) => void;
  hexMode: HexMode;
  onHexMode: (m: HexMode) => void;
  attribution: string | null;
  onClose: () => void;
};

export default function Timeline(p: Props) {
  const f = p.frames[p.frame];

  return (
    <div className="rounded-xl border border-line bg-surface p-3 shadow-panel md:p-4">
      <div className="flex items-center gap-3">
        <button
          onClick={p.onTogglePlay}
          disabled={p.frames.length < 2}
          aria-label={p.playing ? "หยุด" : "เล่นไทม์แลปส์"}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-surface hover:opacity-90 disabled:opacity-40"
        >
          {p.playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
              <rect x="2.5" y="2" width="3" height="10" rx="1" fill="currentColor" />
              <rect x="8.5" y="2" width="3" height="10" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
              <path d="M4 2.2v9.6a.6.6 0 0 0 .9.5l7.6-4.8a.6.6 0 0 0 0-1L4.9 1.7a.6.6 0 0 0-.9.5Z" fill="currentColor" />
            </svg>
          )}
        </button>

        <div className="w-[5.5rem] shrink-0 leading-tight" aria-live="polite">
          <span className="block text-[11px] text-ink-3">ภาพถ่าย</span>
          <span className="block text-lg font-semibold tracking-tight text-ink tabular-nums">{f ? monthYear(f.captured) : "–"}</span>
        </div>

        <div className="min-w-0 flex-1">
          <input
            type="range"
            min={0}
            max={Math.max(0, p.frames.length - 1)}
            step={1}
            value={p.frame}
            onChange={(e) => p.onFrame(Number(e.target.value))}
            aria-label="เลือกช่วงเวลาของภาพดาวเทียม"
            aria-valuetext={f ? monthYear(f.captured) : undefined}
            className="h-6 w-full cursor-pointer accent-accent"
          />
          <div className="flex justify-between px-0.5 text-[11px] text-ink-3 tabular-nums">
            {p.frames.map((fr, i) => (
              <span key={fr.release_id} className={i === p.frame ? "font-semibold text-ink" : ""}>
                {fr.captured.slice(2, 4)}
              </span>
            ))}
          </div>
        </div>

        <button
          onClick={p.onClose}
          aria-label="ปิดภาพดาวเทียม"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-3 hover:bg-bg hover:text-ink"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <path d="M2 2l10 10M12 2 2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line pt-2 md:mt-3 md:pt-3">
        <label className="flex items-center gap-2 text-[13px] text-ink-2">
          ความชัดภาพ
          <input
            type="range"
            min={0.2}
            max={1}
            step={0.05}
            value={p.opacity}
            onChange={(e) => p.onOpacity(Number(e.target.value))}
            className="h-5 w-24 cursor-pointer accent-accent"
          />
        </label>
        <div role="radiogroup" aria-label="ช่องสีบนภาพ" className="flex gap-1 rounded-lg bg-bg p-1">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="radio"
              aria-checked={p.hexMode === m.id}
              onClick={() => p.onHexMode(m.id)}
              className={`min-h-8 rounded-md px-2.5 text-[13px] font-medium ${
                p.hexMode === m.id ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {p.attribution ? (
        <p className="mt-2 text-[11px] leading-snug text-ink-3">
          {f && `ความละเอียด ${f.resolution_m} ม. · `}ภาพจาก Esri World Imagery Wayback © {p.attribution}
        </p>
      ) : (
        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-warn-ink">
          <WarnIcon className="shrink-0" /> รอภาพดาวเทียม ตอนนี้แสดงพื้นสีแทน
        </p>
      )}
    </div>
  );
}
