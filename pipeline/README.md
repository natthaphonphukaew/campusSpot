# CampusSpot pipeline

ดึงข้อมูล → จัดประเภท → สร้างฟีเจอร์ → โมเดล → ส่งออก JSON ไปที่ `web/public/data/`
ตอนนี้มีแค่ขั้นแรก `collect.py` (T0.2)

## รันในเครื่อง (Windows, Python 3.11)

```bash
# ครั้งแรก: สร้าง venv ที่ root ของ repo
python -m venv .venv
.venv/Scripts/python -m pip install -r pipeline/requirements.txt

# ดึงข้อมูลทุกมหาวิทยาลัยใน pipeline/config/universities.yaml
.venv/Scripts/python pipeline/collect.py

# เฉพาะบางแห่ง / ไม่ใช้แคช
.venv/Scripts/python pipeline/collect.py kmutt_bangmod
.venv/Scripts/python pipeline/collect.py kmutt_bangmod --refresh
```

macOS/Linux ใช้ `.venv/bin/python` แทน `.venv/Scripts/python`

## รันบน Colab

```python
!git clone https://github.com/natthaphonphukaew/campusSpot.git
%cd campusSpot
!pip install -q -r pipeline/requirements.txt
!python pipeline/collect.py
```

- ถ้า repo เป็น private ต้อง clone ด้วย GitHub token หรืออัปโหลดโฟลเดอร์ขึ้นไปเอง
- แคชบน Colab หายเมื่อปิด session ถ้าไม่อยากดึงซ้ำ ให้ก๊อป `pipeline/data/raw/` ไปเก็บใน Google Drive

## collect.py ทำอะไร

| ขั้น | รายละเอียด |
|---|---|
| ดึง | OSM (Overpass) ร้านค้า หอพัก จำนวนอาคาร ขอบเขตมหาวิทยาลัย + Overture places (แหล่งหลัก) |
| แคช | `pipeline/data/raw/<uni_id>/` ถ้ามีไฟล์แล้วจะไม่ดึงซ้ำ (ใช้ `--refresh` เพื่อดึงใหม่) |
| จัดประเภท | dorm_like, cafe, food, laundry, print_stationery, convenience, other (กฎ regex อยู่ในส่วนที่ 3 ของไฟล์) |
| ติดธง | ok, duplicate, false_positive, industrial_print, on_campus, needs_check, unnamed_building — ไม่ลบข้อมูลทิ้ง |
| บันทึก | `pipeline/data/processed/<uni_id>/points.parquet`, `campus.geojson` (ถ้าเจอขอบเขต), `collect_meta.json` |

เพิ่มมหาวิทยาลัยใหม่: เพิ่มรายการใน `pipeline/config/universities.yaml` (uni_id, name_th, lat, lon, radius_m และ on_campus_name ถ้ามี)
