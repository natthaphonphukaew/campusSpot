// MapLibre v6 โหลด worker เป็นไฟล์แยก แต่ตอน bundle ไฟล์นี้ไม่ถูกส่งออกไปด้วย
// จึงก๊อปจาก node_modules ไปไว้ที่ public/ ก่อน dev/build ทุกครั้ง (เวอร์ชันตรงกับแพ็กเกจเสมอ)
import { copyFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const src = join(dirname(require.resolve("maplibre-gl/package.json")), "dist", "maplibre-gl-worker.mjs");
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "maplibre-gl-worker.mjs");
copyFileSync(src, dest);
console.log("copied maplibre worker ->", dest);
