"""สร้างกริด H3 รอบมหาวิทยาลัยและฟีเจอร์รายช่อง จาก points.parquet ของ collect.py

ฟีเจอร์ต่อช่อง (นับจากจุดกลางช่อง ในรัศมี 200 ม.):
    dorms_200m            หอพักมีชื่อ (dorm_like, flag ok)
    condo_200m            อาคารที่พักที่ยังไม่ยืนยันว่าเป็นหอ (dorm_like, flag needs_check/unnamed_building)
    dist_gate_m           ระยะถึงขอบเขตมหาวิทยาลัยที่ใกล้ที่สุด (ช่องในมหาวิทยาลัย = 0, ไม่มีขอบเขต = ระยะถึงจุดกลาง)
    commerce_200m         ร้าน/สถานที่ทุกประเภทที่ไม่ใช่หอพัก (flag ok)
    commerce_ex_<cat>_200m  เหมือน commerce_200m แต่ไม่นับหมวด <cat> ใช้เป็นฟีเจอร์ตอนทำนายหมวดนั้น (กันข้อมูลรั่ว)
    actual_<cat>_200m     ร้านหมวด <cat> (flag ok) = ค่าจริงที่จะทำนาย ไม่ใช่ฟีเจอร์

รัน:
    python features.py                     # ทุกแห่งใน config/universities.yaml
    python features.py kmutt_bangmod
"""
import argparse, json, math, sys
from pathlib import Path

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import yaml
from shapely.affinity import affine_transform
from shapely.geometry import Point

from collect import CONFIG, PROCESSED, ROOT, radius_circle

H3_RES = 10
NEAR_M = 200
TARGET_CATS = ["cafe", "food", "laundry", "print_stationery"]
CONDO_FLAGS = ["needs_check", "unnamed_building"]


def to_local_m(uni):
    """แปลง lon/lat เป็นเมตรรอบจุดกลางมหาวิทยาลัย (พอสำหรับระยะไม่กี่กิโลเมตร)"""
    k = 111_320
    c = math.cos(math.radians(uni["lat"]))
    def xy(lat, lon):
        return (np.asarray(lon) - uni["lon"]) * k * c, (np.asarray(lat) - uni["lat"]) * k
    # สำหรับ shapely: x' = a*x + xoff, y' = e*y + yoff
    geom_matrix = [k * c, 0, 0, k, -uni["lon"] * k * c, -uni["lat"] * k]
    return xy, geom_matrix


def hex_grid(uni):
    circle = radius_circle(uni)
    ring = [(lat, lon) for lon, lat in circle.exterior.coords]
    cells = sorted(h3.polygon_to_cells(h3.LatLngPoly(ring), H3_RES))
    lat, lon = zip(*(h3.cell_to_latlng(c) for c in cells))
    return pd.DataFrame({"h3": cells, "lat": lat, "lon": lon})


def count_within(hx, hy, px, py, radius):
    """จำนวนจุดในรัศมีของแต่ละช่อง (เมทริกซ์ระยะ ช่อง × จุด — ไม่กี่ร้อย × ไม่กี่พัน จึงเร็วพอ)"""
    if len(px) == 0:
        return np.zeros(len(hx), dtype=int)
    d2 = (hx[:, None] - px[None, :]) ** 2 + (hy[:, None] - py[None, :]) ** 2
    return (d2 <= radius ** 2).sum(axis=1)


def build_features(uni):
    uid = uni["uni_id"]
    out_dir = PROCESSED / uid
    pts = pd.read_parquet(out_dir / "points.parquet")
    campus_path = out_dir / "campus.geojson"
    campus = gpd.read_file(campus_path).geometry.union_all() if campus_path.exists() else None

    hexes = hex_grid(uni)
    xy, matrix = to_local_m(uni)
    hx, hy = xy(hexes.lat, hexes.lon)

    if campus is not None:
        campus_m = affine_transform(campus, matrix)
        centers = [Point(x, y) for x, y in zip(hx, hy)]
        hexes["on_campus"] = [campus_m.contains(p) for p in centers]
        hexes["dist_gate_m"] = [0 if inside else round(campus_m.boundary.distance(p))
                                for p, inside in zip(centers, hexes.on_campus)]
    else:
        hexes["on_campus"] = False
        hexes["dist_gate_m"] = np.round(np.hypot(hx, hy)).astype(int)

    def near(mask):
        px, py = xy(pts.lat[mask], pts.lon[mask])
        return count_within(hx, hy, px, py, NEAR_M)

    ok = pts.flag == "ok"
    dorm = pts.category == "dorm_like"
    hexes["dorms_200m"] = near(ok & dorm)
    hexes["condo_200m"] = near(dorm & pts.flag.isin(CONDO_FLAGS))
    hexes["commerce_200m"] = near(ok & ~dorm)
    for cat in TARGET_CATS:
        hexes[f"actual_{cat}_200m"] = near(ok & (pts.category == cat))
        hexes[f"commerce_ex_{cat}_200m"] = hexes.commerce_200m - hexes[f"actual_{cat}_200m"]

    hexes.insert(0, "uni_id", uid)
    hexes.to_parquet(out_dir / "hex_features.parquet", index=False)
    return hexes


FEATURE_COLS = ["dorms_200m", "condo_200m", "dist_gate_m", "commerce_200m"]


def print_stats(all_hex):
    cols = FEATURE_COLS + [f"commerce_ex_{c}_200m" for c in TARGET_CATS] + [f"actual_{c}_200m" for c in TARGET_CATS]
    print("\nจำนวนช่องต่อมหาวิทยาลัย:")
    print(all_hex.groupby("uni_id").agg(hexes=("h3", "size"), on_campus=("on_campus", "sum")).to_string())
    off = all_hex[~all_hex.on_campus]
    print(f"\nสถิติฟีเจอร์ (เฉพาะช่องนอกมหาวิทยาลัย {len(off)} ช่อง จากทั้งหมด {len(all_hex)}):")
    print(off[cols].describe().T[["mean", "std", "min", "50%", "max"]].round(2).to_string())
    print("\nค่าเฉลี่ยต่อมหาวิทยาลัย (นอกมหาวิทยาลัย):")
    print(off.groupby("uni_id")[FEATURE_COLS + ["actual_cafe_200m", "actual_food_200m"]].mean().round(1).to_string())


def write_preview_map(uni, hexes, column):
    """หน้า HTML ดูค่าฟีเจอร์บนแผนที่จริง (สำหรับให้คนตรวจด้วยตา ไม่ได้ใช้บนเว็บ)"""
    vmax = max(1, int(hexes[column].max()))
    feats = [{"type": "Feature",
              "properties": {"v": int(v), "on_campus": bool(oc)},
              "geometry": {"type": "Polygon", "coordinates": [[[lng, lat] for lat, lng in h3.cell_to_boundary(c)]
                                                              + [[h3.cell_to_boundary(c)[0][1], h3.cell_to_boundary(c)[0][0]]]]}}
             for c, v, oc in zip(hexes.h3, hexes[column], hexes.on_campus)]
    geo = json.dumps({"type": "FeatureCollection", "features": feats})
    html = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{uni['name_th']} · {column}</title>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>html,body,#m{{margin:0;height:100%}}#l{{position:absolute;top:12px;left:12px;background:#fff;padding:10px 12px;
font:14px system-ui,sans-serif;border:1px solid #ddd;border-radius:8px}}</style></head><body><div id="m"></div>
<div id="l"><b>{uni['name_th']}</b><br>{column} (0–{vmax})<br><span style="color:#888">เทา = ในมหาวิทยาลัย · ชี้ช่องเพื่อดูค่า</span></div>
<script>
const data = {geo};
const map = new maplibregl.Map({{container: "m", style: "https://tiles.openfreemap.org/styles/positron",
  center: [{uni['lon']}, {uni['lat']}], zoom: 14}});
map.on("load", () => {{
  map.addSource("h", {{type: "geojson", data}});
  map.addLayer({{id: "f", type: "fill", source: "h", paint: {{"fill-opacity": 0.7,
    "fill-color": ["case", ["get", "on_campus"], "#cfcac0",
      ["interpolate", ["linear"], ["get", "v"], 0, "#f1edcb", {vmax / 2}, "#6fa56e", {vmax}, "#245c40"]]}}}});
  map.addLayer({{id: "o", type: "line", source: "h", paint: {{"line-color": "#fff", "line-width": 0.5}}}});
  const pop = new maplibregl.Popup({{closeButton: false}});
  map.on("mousemove", "f", e => pop.setLngLat(e.lngLat).setText("{column} = " + e.features[0].properties.v).addTo(map));
  map.on("mouseleave", "f", () => pop.remove());
}});
</script></body></html>"""
    path = PROCESSED / uni["uni_id"] / f"preview_{column}.html"
    path.write_text(html, encoding="utf-8")
    return path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_ids", nargs="*", help="uni_id ที่จะรัน (ไม่ใส่ = ทุกแห่ง)")
    args = ap.parse_args()

    unis = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]
    if args.uni_ids:
        unis = [u for u in unis if u["uni_id"] in args.uni_ids]
    frames = []
    for uni in unis:
        hexes = build_features(uni)
        frames.append(hexes)
        print(f"{uni['uni_id']}: {len(hexes)} ช่อง ({int(hexes.on_campus.sum())} ในมหาวิทยาลัย) -> "
              f"{(PROCESSED / uni['uni_id'] / 'hex_features.parquet').relative_to(ROOT)}")
        if uni["uni_id"] == "kmutt_bangmod":
            print("  แผนที่ตรวจ dorms_200m:", write_preview_map(uni, hexes, "dorms_200m").relative_to(ROOT))
    print_stats(pd.concat(frames, ignore_index=True))


if __name__ == "__main__":
    main()
