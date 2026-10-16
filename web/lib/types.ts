// Data contract ระหว่าง pipeline/export.py กับเว็บ (ดู CLAUDE.md หัวข้อ "Data contract")
// ถ้าต้องเปลี่ยน schema ให้ถามคนก่อน แล้วแก้ทั้งไฟล์นี้และ pipeline/export.py พร้อมกัน

export type CategoryId = "cafe" | "food" | "laundry" | "print_stationery";

export type Confidence = "high" | "low";

export type PoiFlag =
  | "ok"
  | "duplicate"
  | "false_positive"
  | "industrial_print"
  | "on_campus"
  | "needs_check"
  | "unnamed_building";

// ---------------------------------------------------------------- meta.json

export interface CategoryMeta {
  label_th: string;
  confidence: Confidence;
  note_th: string;
}

export interface CategoryEvaluation {
  mae_model: number;
  mae_baseline: number;
  n_universities: number;
}

export interface Meta {
  uni_id: string;
  name_th: string;
  /** [lat, lon] */
  center: [number, number];
  radius_m: number;
  h3_res: number;
  /** ISO 8601 UTC */
  generated_at: string;
  categories: Record<CategoryId, CategoryMeta>;
  evaluation: {
    method: "leave_one_university_out";
    per_category: Partial<Record<CategoryId, CategoryEvaluation>>;
  };
  sat_years: number[];
}

// ---------------------------------------------------------------- hexes.json

export interface HexFeatures {
  dorms_200m: number;
  built_now: number;
  built_change_2019_2025: number;
  dist_gate_m: number;
  commerce_200m: number;
}

export interface ShapItem {
  feature: string;
  label_th: string;
  value: number;
  contribution: number;
}

export interface CategoryScore {
  /** จำนวนเต็ม 0–100 */
  opportunity: number;
  expected: number;
  actual: number;
  growth: number;
  /** ไม่เกิน 4 รายการ เรียงตามขนาด contribution */
  shap_top: ShapItem[];
}

export interface Hex {
  h3: string;
  on_campus: boolean;
  features: HexFeatures;
  /** key = ปี ค.ศ. เป็นสตริง เช่น "2019" */
  built_by_year: Record<string, number>;
  scores: Partial<Record<CategoryId, CategoryScore>>;
}

// ---------------------------------------------------------------- pois.json

export interface Poi {
  name: string;
  /** หมวดร้านหรือ dorm_like (หอพัก) */
  category: string;
  flag: PoiFlag;
  lat: number;
  lon: number;
  source: string;
}

// ---------------------------------------------------------------- ภาพดาวเทียม

/** web/public/sat/<uni_id>/bounds.json = [[west, south], [east, north]] */
export type SatBounds = [[number, number], [number, number]];
