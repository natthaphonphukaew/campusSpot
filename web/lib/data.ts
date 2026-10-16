import type { Hex, Meta, Poi, SatWayback } from "./types";

// ชุดข้อมูลที่หน้าเว็บใช้ = โฟลเดอร์ใน public/data/ (ตั้ง NEXT_PUBLIC_DATASET=mock เพื่อดูข้อมูลจำลอง)
export const DATASET = process.env.NEXT_PUBLIC_DATASET ?? "kmutt_bangmod";
export const IS_MOCK = DATASET === "mock";

async function getJson<T>(file: string): Promise<T> {
  const res = await fetch(`/data/${DATASET}/${file}`);
  if (!res.ok) throw new Error(`${file}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** รายการภาพดาวเทียมสำหรับไทม์แลปส์ (sat/<uni_id>/wayback.json) หรือ null ถ้ายังไม่มี */
export async function loadWayback(uniId: string): Promise<SatWayback | null> {
  try {
    const res = await fetch(`/sat/${uniId}/wayback.json`);
    if (!res.ok) return null;
    const doc = (await res.json()) as SatWayback;
    return doc.frames?.length ? doc : null;
  } catch {
    return null;
  }
}

export async function loadDataset(): Promise<{ meta: Meta; hexes: Hex[]; pois: Poi[] }> {
  const [meta, hexes, pois] = await Promise.all([
    getJson<Meta>("meta.json"),
    getJson<Hex[]>("hexes.json"),
    getJson<Poi[]>("pois.json"),
  ]);
  return { meta, hexes, pois };
}
