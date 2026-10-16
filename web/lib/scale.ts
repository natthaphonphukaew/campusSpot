// สีบนแผนที่ (MapLibre อ่าน CSS variable ไม่ได้ จึงต้องเป็นค่า hex ตรงนี้)
// คะแนนโอกาสใช้สีเขียวไล่ระดับสีเดียว: โหมดสว่างอ่อน→เข้ม, โหมดมืดกลับด้าน (มืด→สว่าง)
// ตรวจแล้วว่าความสว่าง (OKLab L) ไล่ขึ้นลงต่อเนื่องทั้งสองโหมด

export type Scheme = "light" | "dark";

export const OPP_STOPS = [0, 20, 40, 60, 80, 100] as const;

export const OPP_RAMP: Record<Scheme, readonly string[]> = {
  light: ["#f1edcb", "#d3dfa3", "#a3c785", "#6fa56e", "#447f57", "#245c40"],
  dark: ["#2e3a2c", "#3e5a3a", "#55804f", "#7aa66a", "#a8c98a", "#dce9b4"],
};

type MapColors = {
  onCampus: string;
  gap: string;
  hover: string;
  radius: string;
  fillOpacity: number;
  /** จุดร้านที่ใช้ได้ (flag ok): จุดทึบสีหมึก มีวงขอบสีพื้น ให้เด่นบนช่องสีเขียว */
  poi: string;
  poiRing: string;
  /** จุดที่ถูกติดธงอื่น: เทาโปร่ง */
  poiFlagged: string;
};

export const MAP_COLORS: Record<Scheme, MapColors> = {
  light: {
    onCampus: "#d9d5cc", gap: "#faf8f5", hover: "#1f1e1b", radius: "#75726a", fillOpacity: 0.72,
    poi: "#1f1e1b", poiRing: "#ffffff", poiFlagged: "#8a877f",
  },
  dark: {
    onCampus: "#3a3934", gap: "#161614", hover: "#edeae3", radius: "#8f8b82", fillOpacity: 0.8,
    poi: "#f4f1ea", poiRing: "#161614", poiFlagged: "#8f8b82",
  },
};

// แผนที่พื้นหลังจาก OpenFreeMap ไม่ต้องใช้ API key
export const BASEMAP: Record<Scheme, string> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

// ความหนาแน่นอาคารจากดาวเทียม (built) ใช้สีอำพันไล่ระดับสีเดียว แยกจากสีเขียวของคะแนนโอกาส
// ค่าจริงส่วนใหญ่อยู่ราว 0.3–0.85 จึงใช้ช่วง 0.2–0.9 ให้เห็นความต่างระหว่างปีชัดขึ้น
export const BUILT_STOPS = [0.2, 0.34, 0.48, 0.62, 0.76, 0.9] as const;

export const BUILT_RAMP: Record<Scheme, readonly string[]> = {
  light: ["#fbeedd", "#f3cf9f", "#e5a660", "#c97a2e", "#9a5418", "#6b3a12"],
  dark: ["#3a2a1a", "#5c3f20", "#8a5a2a", "#b9803d", "#deaa66", "#f4d6a8"],
};

function gradientCss(ramp: readonly string[], stops: readonly number[]): string {
  const lo = stops[0];
  const hi = stops[stops.length - 1];
  return `linear-gradient(to right, ${ramp.map((c, i) => `${c} ${((stops[i] - lo) / (hi - lo)) * 100}%`).join(", ")})`;
}

export const oppGradientCss = (scheme: Scheme) => gradientCss(OPP_RAMP[scheme], OPP_STOPS);
export const builtGradientCss = (scheme: Scheme) => gradientCss(BUILT_RAMP[scheme], BUILT_STOPS);
