# CampusSpot web

Next.js (App Router) + TypeScript + Tailwind, ส่งออกเป็น static site (`output: "export"`) แล้ว deploy บน Vercel

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # ได้โฟลเดอร์ out/
npm run mock     # สร้างข้อมูลจำลองใหม่ที่ public/data/mock/
```

- ชุดข้อมูลที่ใช้: ตั้ง `NEXT_PUBLIC_DATASET=<uni_id>` (ค่าเริ่มต้น `mock` ซึ่งจะแสดงป้าย "ข้อมูลจำลอง")
- type ของ data contract อยู่ที่ `lib/types.ts` ต้องตรงกับ `pipeline/export.py`
- สีและแผนที่พื้นหลังอยู่ที่ `lib/scale.ts`, สีของหน้าเว็บอยู่ที่ `app/globals.css`
- MapLibre v6 ต้องใช้ไฟล์ worker แยก: `scripts/copy-maplibre-worker.mjs` ก๊อปไปที่ `public/` ให้อัตโนมัติก่อน dev/build
- Vercel: Root Directory = `web`, Framework = Next.js (ค่าอื่นใช้ค่าเริ่มต้น)
