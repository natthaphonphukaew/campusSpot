import type { CategoryId, PoiFlag } from "./types";

export const CATEGORY_ORDER: CategoryId[] = ["cafe", "food", "laundry", "print_stationery"];

/** ชื่อสั้นสำหรับแท็บ (ชื่อเต็มมาจาก meta.categories[cat].label_th) */
export const CATEGORY_SHORT: Record<CategoryId, string> = {
  cafe: "กาแฟ",
  food: "อาหาร",
  laundry: "ซักผ้า",
  print_stationery: "ปริ้นต์",
};

export const FLAG_LABEL: Record<PoiFlag, string> = {
  ok: "",
  duplicate: "น่าจะซ้ำกับร้านอื่น",
  false_positive: "ไม่น่าใช่ร้านหมวดนี้",
  industrial_print: "โรงพิมพ์ ไม่ใช่ร้านสำหรับนักศึกษา",
  on_campus: "อยู่ในมหาวิทยาลัย",
  needs_check: "ยังไม่ได้ตรวจ",
  unnamed_building: "อาคารไม่มีชื่อ",
};

export function growthLabel(growth: number): string {
  if (growth >= 0.6) return "โตเร็ว";
  if (growth >= 0.3) return "โตปานกลาง";
  return "ค่อนข้างคงที่";
}
