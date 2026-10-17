# ร้านรอบ มจธ. บางมด (กาแฟ อาหาร ซักผ้า ปริ้นต์)

ข้อมูลจากโปรเจกต์ CampusSpot สร้างด้วย `pipeline/export_shops.py`
รัศมี 1.5 กม. จากจุดกลาง มจธ. บางมด (13.6513, 100.4941) เฉพาะร้านที่ผ่านการคัดแล้ว
(ตัดร้านซ้ำระหว่าง Overture กับ OSM, ร้านที่จัดหมวดผิด, โรงพิมพ์ และร้านในมหาวิทยาลัยออก)

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `shops.geojson` | ใส่ MapLibre / Leaflet / Mapbox ได้เลย (พิกัด WGS84, `[lon, lat]`) |
| `shops.csv` | เปิดใน Excel / Google Sheets หรือนำเข้าฐานข้อมูล (UTF-8 มี BOM ภาษาไทยไม่เพี้ยน) |

## ฟิลด์

| ฟิลด์ | ความหมาย |
|---|---|
| `name` | ชื่อร้าน (บางร้านเป็นภาษาอังกฤษตามแหล่งข้อมูล) |
| `category` | `cafe`, `food`, `laundry`, `print_stationery` |
| `category_th` | ชื่อหมวดภาษาไทย |
| `source` | `overture` หรือ `osm` |
| `license` | ไลเซนส์ของร้านนั้น (ดูด้านล่าง) |
| `overture_id` | id ของ Overture (GERS) ใช้อัปเดตข้อมูลรุ่นใหม่ได้ (ร้านจาก OSM เป็นค่าว่าง) |
| `confidence` | ความมั่นใจของ Overture ว่าร้านมีอยู่จริง 0–1 (OSM เป็นค่าว่าง) |
| `distance_from_campus_center_m` | ระยะจากจุดกลาง มจธ. (เมตร) |
| `data_date` | วันที่ดึงข้อมูล ร้านที่เปิด/ปิดหลังวันนี้จะไม่อยู่ในไฟล์ |

## ข้อควรรู้

- **ร้านซักผ้า (7) และร้านปริ้นต์ (5) ข้อมูลบาง** ของจริงน่าจะมีมากกว่านี้ ควรบอกผู้ใช้ว่าข้อมูลหมวดนี้ยังไม่ครบ
- **ไลเซนส์และเครดิต** ต้องแสดงบนแผนที่ที่เปิดให้คนอื่นใช้:
  - Overture (CDLA-Permissive-2.0 / CC0-1.0 / Apache-2.0): ใส่ `© Overture Maps Foundation`
  - OSM (ODbL-1.0, 17 ร้าน): ใส่ `© OpenStreetMap contributors` และถ้าแจกฐานข้อมูลที่รวมกับข้อมูลอื่น ต้องแจกภายใต้ ODbL ด้วย
  - ถ้าไม่อยากมีเงื่อนไข ODbL ให้สร้างไฟล์ใหม่ด้วย `python export_shops.py --overture-only` (ตัด 17 ร้านจาก OSM ออก)

## ใช้กับ MapLibre

ก๊อป `shops.geojson` ไปไว้ในโฟลเดอร์ไฟล์ static ของโปรเจกต์ (เช่น `public/data/`) แล้ว:

```js
map.on("load", () => {
  map.addSource("shops", {
    type: "geojson",
    data: "/data/shops.geojson",
    attribution: "© Overture Maps Foundation · © OpenStreetMap contributors",
  });

  map.addLayer({
    id: "shops",
    type: "circle",
    source: "shops",
    // แสดงเฉพาะบางหมวด: ["==", ["get", "category"], "cafe"]
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 13, 3, 17, 7],
      "circle-color": [
        "match", ["get", "category"],
        "cafe", "#9a5418",
        "food", "#b42318",
        "laundry", "#2f6f9f",
        "print_stationery", "#5b5f97",
        "#777777",
      ],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
    },
  });

  // คลิกจุดเพื่อดูชื่อร้าน
  map.on("click", "shops", (e) => {
    const p = e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat).setText(`${p.name || "ไม่มีชื่อ"} · ${p.category_th}`).addTo(map);
  });
  map.on("mouseenter", "shops", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "shops", () => (map.getCanvas().style.cursor = ""));
});
```

กรองหมวดภายหลังได้ด้วย `map.setFilter("shops", ["==", ["get", "category"], "food"])` หรือ `map.setFilter("shops", null)` เพื่อแสดงทั้งหมด

## สร้างไฟล์ใหม่ (เมื่ออยากได้ข้อมูลล่าสุด)

```bash
cd pipeline
python collect.py kmutt_bangmod --refresh   # ดึง Overture + OSM ใหม่
python export_shops.py                      # เขียน shops.geojson / shops.csv ใหม่
```
