// สร้างข้อมูลจำลองตาม data contract ไว้ที่ web/public/data/mock/
// ใช้ระหว่างที่ pipeline ยังไม่ส่งออกไฟล์จริง — ตัวเลขทั้งหมดสุ่มขึ้น ไม่ใช่ข้อมูลจริง
// รัน: node scripts/make-mock.mjs

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cellToLatLng, gridDisk, latLngToCell } from "h3-js";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "data", "mock");
const CENTER = [13.6513, 100.4941]; // มจธ. บางมด
const H3_RES = 10;
const RINGS = 10; // 331 ช่อง ≈ ราว 300
const CAMPUS_R_M = 260;
const YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025];
const CATS = ["cafe", "food", "laundry", "print_stationery"];
const LABELS = {
  dorms_200m: "จำนวนหอพักใกล้เคียง",
  built_now: "ความหนาแน่นอาคารตอนนี้",
  built_change_2019_2025: "อาคารเพิ่มขึ้นตั้งแต่ปี 2019",
  dist_gate_m: "ระยะถึงมหาวิทยาลัย",
  commerce_200m: "ร้านค้ารอบ ๆ",
};

// สุ่มแบบกำหนด seed ได้ ไฟล์จะออกมาเหมือนเดิมทุกครั้ง
let seed = 20261016;
const rand = () => {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const round = (x, d = 2) => Math.round(x * 10 ** d) / 10 ** d;
const clamp01 = (x) => Math.min(1, Math.max(0, x));

const distM = ([lat, lon], [lat0, lon0]) =>
  Math.hypot((lat - lat0) * 111_320, (lon - lon0) * 111_320 * Math.cos((lat0 * Math.PI) / 180));

// "ย่าน" จำลองเป็นก้อนเกาส์เซียน ให้แผนที่มีโครงสร้าง ไม่ใช่จุดสุ่มกระจาย
const blob = (p, [lat, lon], r) => Math.exp(-((distM(p, [lat, lon]) / r) ** 2));
const dormField = (p) =>
  blob(p, [13.6475, 100.4985], 450) + 0.8 * blob(p, [13.6555, 100.4895], 380) + 0.5 * blob(p, [13.6440, 100.4900], 300);
const growthField = (p) => blob(p, [13.6585, 100.5005], 500) + 0.7 * blob(p, [13.6430, 100.4880], 420);

const cells = gridDisk(latLngToCell(CENTER[0], CENTER[1], H3_RES), RINGS);

const hexes = cells.map((h3) => {
  const p = cellToLatLng(h3);
  const dist = distM(p, CENTER);
  const onCampus = dist < CAMPUS_R_M;
  const dorm = dormField(p);
  const grow = growthField(p);

  const built2025 = clamp01(0.35 + 0.4 * dorm + 0.15 * grow + 0.1 * rand());
  const change = clamp01(0.05 + 0.25 * grow + 0.04 * rand());
  const built_by_year = Object.fromEntries(
    YEARS.map((y, i) => [String(y), round(clamp01(built2025 - change * (1 - i / (YEARS.length - 1))))]),
  );
  const features = {
    dorms_200m: Math.round(dorm * 7 + rand() * 2),
    built_now: round(built2025),
    built_change_2019_2025: round(change),
    dist_gate_m: Math.max(0, Math.round(dist - CAMPUS_R_M)),
    commerce_200m: Math.round(dorm * 25 + rand() * 6),
  };

  const scores = {};
  for (const [k, cat] of CATS.entries()) {
    const demand = dorm * (k === 1 ? 9 : k === 0 ? 4 : 1.5) + grow * 1.5;
    const expected = round(demand + rand() * 0.5, 1);
    const actual = Math.max(0, Math.round(expected * (0.4 + 1.2 * rand())));
    const raw = expected - actual + 0.5 * grow * expected;
    const contribs = [
      ["dorms_200m", dorm * 0.6 - 0.15],
      ["built_change_2019_2025", grow * 0.4 - 0.05],
      ["commerce_200m", -(actual / Math.max(1, expected)) * 0.3 + 0.1],
      ["dist_gate_m", 0.2 - dist / 6000],
      ["built_now", built2025 * 0.2 - 0.1],
    ]
      .map(([feature, c]) => ({ feature, label_th: LABELS[feature], value: features[feature], contribution: round(c) }))
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
      .slice(0, 4);
    scores[cat] = { raw, expected, actual, growth: round(clamp01(grow)), shap_top: contribs };
  }
  return { h3, on_campus: onCampus, features, built_by_year, scores };
});

// opportunity = เปอร์เซ็นไทล์ของ raw ภายในพื้นที่ แปลงเป็น 0–100, ช่อง on_campus = 0 (ตามสูตรใน PLAYBOOK T2.2)
for (const cat of CATS) {
  const off = hexes.filter((h) => !h.on_campus).map((h) => h.scores[cat].raw).sort((a, b) => a - b);
  for (const h of hexes) {
    const s = h.scores[cat];
    const rank = off.filter((v) => v <= s.raw).length;
    s.opportunity = h.on_campus ? 0 : Math.round((100 * rank) / off.length);
    delete s.raw;
    h.scores[cat] = { opportunity: s.opportunity, expected: s.expected, actual: s.actual, growth: s.growth, shap_top: s.shap_top };
  }
}

const POI_CATS = ["cafe", "cafe", "food", "food", "food", "laundry", "print_stationery", "dorm_like"];
const POI_FLAGS = ["ok", "ok", "ok", "ok", "ok", "ok", "duplicate", "needs_check"];
const pois = Array.from({ length: 50 }, (_, i) => {
  const a = rand() * 2 * Math.PI;
  const r = 150 + rand() * 1250;
  return {
    name: `ร้านจำลอง ${i + 1}`,
    category: POI_CATS[Math.floor(rand() * POI_CATS.length)],
    flag: r < CAMPUS_R_M ? "on_campus" : POI_FLAGS[Math.floor(rand() * POI_FLAGS.length)],
    lat: round(CENTER[0] + (r * Math.sin(a)) / 111_320, 6),
    lon: round(CENTER[1] + (r * Math.cos(a)) / (111_320 * Math.cos((CENTER[0] * Math.PI) / 180)), 6),
    source: "mock",
  };
});

const meta = {
  uni_id: "mock",
  name_th: "มจธ. บางมด",
  center: CENTER,
  radius_m: 1500,
  h3_res: H3_RES,
  generated_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  categories: {
    cafe: { label_th: "ร้านกาแฟ", confidence: "high", note_th: "ข้อมูลจำลอง" },
    food: { label_th: "ร้านอาหาร", confidence: "high", note_th: "ข้อมูลจำลอง" },
    laundry: { label_th: "ร้านซักผ้า", confidence: "low", note_th: "ข้อมูลน่าจะขาด ยังไม่ได้ตรวจภาคสนาม" },
    print_stationery: { label_th: "ร้านปริ้นต์และเครื่องเขียน", confidence: "low", note_th: "ข้อมูลน่าจะขาด ยังไม่ได้ตรวจภาคสนาม" },
  },
  // ข้อมูลจำลองไม่มีผลประเมินจริง ตัวเลขจริงต้องมาจาก pipeline/model.py เท่านั้น
  evaluation: { method: "leave_one_university_out", per_category: {} },
  sat_years: YEARS,
};

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, "meta.json"), JSON.stringify(meta, null, 2));
writeFileSync(join(OUT, "hexes.json"), JSON.stringify(hexes));
writeFileSync(join(OUT, "pois.json"), JSON.stringify(pois));
console.log(`mock: ${hexes.length} hexes (${hexes.filter((h) => h.on_campus).length} on_campus), ${pois.length} pois -> ${OUT}`);
