# CampusSpot — บริบทโปรเจกต์สำหรับ AI coding agent

อ่านไฟล์นี้ทั้งหมดก่อนเริ่มทุกงาน แล้วอ่าน `PLAYBOOK.md` เพื่อดูว่างานถัดไปคืออะไร

## โปรเจกต์นี้คืออะไร

เว็บช่วยตัดสินใจว่าควรเปิดร้านประเภทไหน ตรงไหน รอบมหาวิทยาลัย
- ผู้ใช้: นักศึกษา ศิษย์เก่า และคนทั่วไปที่อยากเปิดร้านเล็กใกล้มหาวิทยาลัย
- คำถามหลักที่ระบบตอบ: "ย่านนี้ควรมีร้านประเภทนี้กี่ร้าน มีอยู่จริงกี่ร้าน และกำลังโตขึ้นไหม"
- จุดขาย: ใช้ภาพดาวเทียมย้อนหลังดูว่าย่านไหนกำลังมีอาคารใหม่ (ลูกค้าในอนาคต) ซึ่งข้อมูลแผนที่ทั่วไปมองไม่เห็น
- พื้นที่เดโม: มจธ. บางมด (LAT 13.6513, LON 100.4941) รัศมี 1.5 กม.
- ส่งงาน: ก่อน 10 พฤศจิกายน 2026 (feature freeze 5 พ.ย.)

## สถาปัตยกรรม (ห้ามเปลี่ยนโดยไม่ถามคน)

```
pipeline/ (Python)  --สร้างไฟล์ JSON-->  web/public/data/  --อ่านแบบ static-->  web/ (Next.js)  --deploy-->  Vercel
```

- **ไม่มี backend และไม่มีฐานข้อมูล** ทุกอย่างคำนวณล่วงหน้าใน pipeline แล้วส่งออกเป็นไฟล์ static
- pipeline รันบน Colab หรือเครื่องตัวเอง ไม่ต้อง deploy
- เว็บเป็น static site ทั้งหมด

## Tech stack

| ส่วน | ใช้ |
|---|---|
| pipeline | Python 3.11, pandas, geopandas, shapely, h3, overturemaps, requests, lightgbm, shap, earthengine-api |
| web | Next.js (App Router) + TypeScript + Tailwind CSS |
| แผนที่ | maplibre-gl, h3-js |
| กราฟ | recharts |
| แผนที่พื้นหลัง | style ที่ไม่ต้องใช้ API key เช่น OpenFreeMap (ถ้าใช้ไม่ได้ ให้ถามคนก่อนเปลี่ยน) |
| deploy | Vercel |

ห้ามเพิ่ม dependency ใหญ่โดยไม่บอกเหตุผลและถามก่อน

## โครงสร้างโฟลเดอร์

```
CLAUDE.md
PLAYBOOK.md
CHANGELOG.md            # agent เขียนสรุปสั้น ๆ ทุกครั้งที่ทำงานเสร็จ
pipeline/
  config/universities.yaml
  collect.py            # ดึง OSM + Overture + ขอบเขตมหาวิทยาลัย, จัดประเภท, ติดธง (มาจากโน้ตบุ๊ก v2)
  features.py           # สร้างกริด H3 และฟีเจอร์รายช่อง
  satellite.py          # Earth Engine: ค่า built รายปี + ภาพรายปีของพื้นที่เดโม
  model.py              # baseline, LightGBM, การประเมินผล, SHAP
  export.py             # เขียนไฟล์ตาม data contract ด้านล่าง
  data/raw/             # cache ข้อมูลดิบ (ไม่ commit ไฟล์ใหญ่ ใส่ .gitignore)
  data/processed/
web/
  app/                  # หน้าเว็บ
  components/
  lib/                  # type ของ data contract อยู่ที่ lib/types.ts
  public/data/<uni_id>/ # ไฟล์จาก pipeline
  public/sat/<uni_id>/  # ภาพดาวเทียมรายปี
```

## Data contract (ทั้ง pipeline และ web ต้องตรงกันเป๊ะ)

ไฟล์อยู่ที่ `web/public/data/<uni_id>/` ถ้าต้องเปลี่ยน schema ให้หยุดและถามคนก่อน แล้วแก้ทั้ง `pipeline/export.py` และ `web/lib/types.ts` พร้อมกัน

**meta.json**
```json
{
  "uni_id": "kmutt_bangmod",
  "name_th": "มจธ. บางมด",
  "center": [13.6513, 100.4941],
  "radius_m": 1500,
  "h3_res": 10,
  "generated_at": "2026-10-20T10:00:00Z",
  "categories": {
    "cafe":  {"label_th": "ร้านกาแฟ", "confidence": "high", "note_th": "ข้อมูลหนาแน่น ตรวจแล้ว"},
    "food":  {"label_th": "ร้านอาหาร", "confidence": "high", "note_th": ""},
    "laundry": {"label_th": "ร้านซักผ้า", "confidence": "low", "note_th": "ข้อมูลน่าจะขาด ยังไม่ได้ตรวจภาคสนาม"},
    "print_stationery": {"label_th": "ร้านปริ้นต์และเครื่องเขียน", "confidence": "low", "note_th": ""}
  },
  "evaluation": {
    "method": "leave_one_university_out",
    "per_category": {"cafe": {"mae_model": 0.0, "mae_baseline": 0.0, "n_universities": 0}}
  },
  "sat_years": [2019, 2020, 2021, 2022, 2023, 2024, 2025]
}
```

**hexes.json** — หนึ่งแถวต่อช่อง H3
```json
[
  {
    "h3": "8a65...",
    "on_campus": false,
    "features": {"dorms_200m": 4, "built_now": 0.71, "built_change_2019_2025": 0.18, "dist_gate_m": 420, "commerce_200m": 23},
    "built_by_year": {"2019": 0.52, "2025": 0.71},
    "scores": {
      "cafe": {"opportunity": 0, "expected": 0.0, "actual": 0, "growth": 0.0,
               "shap_top": [{"feature": "dorms_200m", "label_th": "จำนวนหอพักใกล้เคียง", "value": 4, "contribution": 0.42}]}
    }
  }
]
```
- `opportunity` เป็นจำนวนเต็ม 0–100
- `shap_top` มีไม่เกิน 4 รายการ เรียงตามขนาด contribution

**pois.json** — ร้านและหอพักทุกจุด
```json
[{"name": "...", "category": "cafe", "flag": "ok", "lat": 0, "lon": 0, "source": "overture"}]
```
ค่า `flag`: ok, duplicate, false_positive, industrial_print, on_campus, needs_check, unnamed_building

**ภาพดาวเทียม (ไทม์แลปส์บนเว็บ)**: `web/public/sat/<uni_id>/wayback.json` สร้างโดย `pipeline/satellite.py`
```json
{
  "source": "esri_wayback",
  "attribution": "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
  "bounds": [[100.47, 13.63], [100.51, 13.67]],
  "frames": [
    {"release_id": 18820, "release_date": "2018-10-17", "captured": "2017-10-29", "resolution_m": 0.31,
     "tile_url": "https://wayback.maptiles.arcgis.com/.../tile/18820/{z}/{y}/{x}"}
  ]
}
```
- `bounds` = `[[west, south], [east, north]]`, `frames` เรียงตามเวลา หนึ่งภาพต่อวันที่ถ่าย
- ภาพเป็น tile ที่ดึงสดจาก Esri World Imagery Wayback (Esri Master License Agreement) **ห้ามดาวน์โหลด tile เก็บไว้** และต้องแสดงเครดิต `attribution` บนแผนที่เสมอ
- ภาพนี้ใช้แสดงผลเท่านั้น ค่า built ที่ใช้ในโมเดลมาจาก Dynamic World (Sentinel-2) และ `meta.sat_years` คือปีที่มีใน `built_by_year`
- (16 ต.ค. 2026 คนตัดสินใจเปลี่ยนจาก PNG Sentinel-2 รายปี เพราะ 10 ม./พิกเซลไม่คมพอให้เห็นตึกใหม่)

## กฎการเขียนโค้ด

1. ทำทีละ task ใน PLAYBOOK เท่านั้น อย่าทำเกินขอบเขต ถ้าเห็นสิ่งที่ควรแก้นอก task ให้จดไว้ใน CHANGELOG ภายใต้หัวข้อ "ข้อเสนอ"
2. **ห้ามสร้างข้อมูลปลอมแล้วทำเหมือนเป็นข้อมูลจริง** ข้อมูล mock ให้อยู่ใน `web/public/data/mock/` เท่านั้น และหน้าเว็บต้องแสดงป้าย "ข้อมูลจำลอง" เมื่อใช้ mock
3. ห้ามแก้ตัวเลขผลประเมินด้วยมือ ตัวเลขใน `meta.json.evaluation` ต้องมาจาก `pipeline/model.py` เท่านั้น
4. ข้อความบนหน้าเว็บเป็นภาษาไทย เขียนแบบเป็นกันเอง ไม่ใช้ศัพท์เทคนิคโดยไม่จำเป็น
5. ทุก task ฝั่งเว็บต้องผ่าน `npm run build` ก่อนบอกว่าเสร็จ ทุก task ฝั่ง pipeline ต้องรันจบโดยไม่ error และพิมพ์สรุปจำนวนแถวหรือค่าที่สำคัญ
6. เมื่อเสร็จแต่ละ task ให้ (ก) เขียนสรุป 2–4 บรรทัดใน CHANGELOG (ข) บอกคนว่าต้องตรวจอะไรด้วยตา (ค) เสนอข้อความ commit
7. ถ้าติดปัญหาเกิน 2 รอบ ให้หยุด อธิบายสาเหตุเป็นภาษาง่าย ๆ และเสนอทางเลือก 2 ทางให้คนเลือก
8. แคชข้อมูลดิบทุกครั้งที่ดึงจากอินเทอร์เน็ต (Overpass, Overture, Earth Engine) เพื่อไม่ต้องดึงซ้ำ
9. สีบนแผนที่ต้องอ่านได้ทั้งโหมดสว่างและมืด และหน้าเว็บต้องใช้ได้บนมือถือ

## แนวทาง UX/UI (ใช้กับทุก task ฝั่งเว็บ)

เป้าหมายคือหน้าเว็บต้องดูเหมือนนักออกแบบ UX/UI มืออาชีพทำ ทั้งฟอนต์ สี และเลย์เอาต์ และ **ต้องไม่ดูออกตั้งแต่แวบแรกว่า AI ทำ**

- ก่อนออกแบบ ให้เลือกเว็บหรือแอปจริง 1–3 ตัวเป็นต้นแบบ เช่น แอปแผนที่ แอปอสังหาฯ หรือแอปรีวิวร้านอาหาร บอกคนว่าเลือกตัวไหนและเอาอะไรมาใช้ แล้วอิงเลย์เอาต์ ขนาดตัวอักษร และสีจากต้นแบบนั้น
- ใช้ UI kit หรือ component จากภายนอกได้ แต่ถ้าเป็น dependency ใหญ่ต้องบอกเหตุผลและถามก่อน
- เลือกฟอนต์ไทยคู่กับฟอนต์อังกฤษให้ตั้งใจ เช่น IBM Plex Sans Thai, Anuphan หรือ Noto Sans Thai ห้ามปล่อยเป็นค่าเริ่มต้น
- ทำชุดสีของโปรเจกต์เองให้ไม่ฉูดฉาด กำหนดเป็นตัวแปรสีไว้ที่เดียว ห้ามใช้สีเริ่มต้นของ Tailwind ตรง ๆ
- เลี่ยงลุคแม่แบบ AI: ไล่สีม่วงหรือคราม, กระจกฝ้า (glassmorphism), อีโมจิแทนไอคอน, การ์ดมุมมนมีเงาเรียงเป็นตารางหน้าตาเหมือนกันหมด, hero กลางจอกับสโลแกนลอย ๆ

## ความรู้เฉพาะโดเมนที่ agent ต้องรู้

- OpenStreetMap รอบ มจธ. มีโครงอาคารแค่ราว 291 หลังในรัศมี 1.5 กม. จึง **ห้ามใช้จำนวนอาคาร OSM เป็นตัวแทนความหนาแน่น** ให้ใช้ค่า built จากดาวเทียม (Dynamic World) แทน
- อาคารไม่มีชื่อที่ติดแท็ก apartments ใน OSM รอบ มจธ. ส่วนใหญ่เป็นโครงการคอนโดย่านหมู่บ้านสวนธน ไม่ใช่หอพัก ให้ติดธง `unnamed_building`
- Overture ครบกว่า OSM มากสำหรับร้านค้า ใช้ Overture เป็นแหล่งหลัก
- ร้านซักผ้าและร้านปริ้นต์ข้อมูลบาง ต้องแสดง confidence ต่ำบนหน้าเว็บเสมอ
- ร้านที่อยู่ในมหาวิทยาลัย (`on_campus`) ไม่นับเป็นคู่แข่งโดยตรง และไม่แนะนำช่องในมหาวิทยาลัยเป็นทำเล
