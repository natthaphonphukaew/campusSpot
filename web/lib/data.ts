import type { Hex, Meta } from "./types";

// ชุดข้อมูลที่หน้าเว็บใช้ = โฟลเดอร์ใน public/data/
// ตอนนี้ยังไม่มีไฟล์จริงจาก pipeline จึงใช้ mock เป็นค่าเริ่มต้น
export const DATASET = process.env.NEXT_PUBLIC_DATASET ?? "mock";
export const IS_MOCK = DATASET === "mock";

async function getJson<T>(file: string): Promise<T> {
  const res = await fetch(`/data/${DATASET}/${file}`);
  if (!res.ok) throw new Error(`${file}: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function loadDataset(): Promise<{ meta: Meta; hexes: Hex[] }> {
  const [meta, hexes] = await Promise.all([getJson<Meta>("meta.json"), getJson<Hex[]>("hexes.json")]);
  return { meta, hexes };
}
