"""ชั้นดาวเทียมจาก Google Earth Engine

1) ค่า built (ความน่าจะเป็นว่าเป็นสิ่งปลูกสร้าง 0–1) เฉลี่ยรายปี 2019–2025 จาก Dynamic World ต่อช่อง H3 ทุกมหาวิทยาลัย
   → data/processed/<uni_id>/hex_satellite.parquet (built_<ปี>, built_now = 2025, built_change_2019_2025)
2) เฉพาะพื้นที่เดโม: ภาพ Sentinel-2 สีจริง median รายปี ช่วงหน้าแล้ง ม.ค.–เม.ย. (ลดเมฆ)
   → web/public/sat/<uni_id>/<ปี>.png + bounds.json = [[west, south], [east, north]]

แคช: ผล reduceRegions เก็บที่ data/raw/<uni_id>/ee_built_by_year.json, ภาพที่มีไฟล์แล้วไม่ดึงซ้ำ (ใช้ --refresh เพื่อดึงใหม่)

ครั้งแรกต้องล็อกอิน: .venv/Scripts/earthengine authenticate --auth_mode=localhost
รัน:
    python satellite.py                    # ทุกแห่ง + ภาพของ มจธ.
    python satellite.py kmutt_bangmod --refresh
"""
import argparse, json, math, sys
from pathlib import Path

import ee
import h3
import pandas as pd
import requests
import yaml

from collect import CONFIG, PROCESSED, RAW, ROOT

EE_PROJECT = "campusspot"
YEARS = list(range(2019, 2026))
DEMO_UNIS = ["kmutt_bangmod"]
WEB_SAT = ROOT.parent / "web" / "public" / "sat"
IMAGE_MARGIN = 1.15        # ภาพกว้างกว่ารัศมีเล็กน้อย ให้ขอบช่อง H3 อยู่ในภาพ
IMAGE_PX = 1024
S2_CLOUD_CLASSES = [3, 8, 9, 10]   # SCL: เงาเมฆ, เมฆปานกลาง, เมฆหนา, เมฆบาง


def hex_collection(hexes):
    feats = []
    for c in hexes.h3:
        ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(c)]
        feats.append(ee.Feature(ee.Geometry.Polygon([ring + [ring[0]]]), {"h3": c}))
    return ee.FeatureCollection(feats)


def built_image(region):
    """ภาพหลายแบนด์ built_2019..built_2025 = ค่าเฉลี่ยความน่าจะเป็น built ของ Dynamic World ทั้งปี"""
    bands = []
    for y in YEARS:
        img = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(region)
               .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("built").mean().rename(f"built_{y}"))
        bands.append(img)
    return ee.Image.cat(bands)


def built_by_hex(uni, hexes, refresh):
    cache = RAW / uni["uni_id"] / "ee_built_by_year.json"
    if cache.exists() and not refresh:
        print("  ใช้แคช", cache.relative_to(ROOT))
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        fc = hex_collection(hexes)
        res = built_image(fc.geometry()).reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
        rows = [f["properties"] for f in res["features"]]
        cache.write_text(json.dumps(rows), encoding="utf-8")
    df = pd.DataFrame(rows)
    cols = [f"built_{y}" for y in YEARS]
    df[cols] = df[cols].astype(float).round(3)
    df["built_now"] = df["built_2025"]
    df["built_change_2019_2025"] = (df["built_2025"] - df["built_2019"]).round(3)
    return df[["h3", *cols, "built_now", "built_change_2019_2025"]]


def image_bounds(uni):
    r = uni["radius_m"] * IMAGE_MARGIN
    dlat = r / 111_320
    dlon = r / (111_320 * math.cos(math.radians(uni["lat"])))
    return [[round(uni["lon"] - dlon, 6), round(uni["lat"] - dlat, 6)], [round(uni["lon"] + dlon, 6), round(uni["lat"] + dlat, 6)]]


def s2_dry_season(region, year):
    def mask(img):
        scl = img.select("SCL")
        bad = scl.eq(S2_CLOUD_CLASSES[0])
        for c in S2_CLOUD_CLASSES[1:]:
            bad = bad.Or(scl.eq(c))
        return img.updateMask(bad.Not())
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
           .filterDate(f"{year}-01-01", f"{year}-05-01")
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(mask))
    return col.median().select(["B4", "B3", "B2"]), col.size()


def export_images(uni, refresh):
    out = WEB_SAT / uni["uni_id"]
    out.mkdir(parents=True, exist_ok=True)
    bounds = image_bounds(uni)
    (out / "bounds.json").write_text(json.dumps(bounds), encoding="utf-8")
    (w, s), (e, n) = bounds
    region = ee.Geometry.Rectangle([w, s, e, n], proj="EPSG:4326", geodesic=False)
    for y in YEARS:
        path = out / f"{y}.png"
        if path.exists() and not refresh:
            print(f"  {y}: ใช้ภาพเดิม ({path.stat().st_size // 1024} KB)")
            continue
        img, n_scenes = s2_dry_season(region, y)
        url = img.getThumbURL({"region": region, "dimensions": IMAGE_PX, "format": "png", "crs": "EPSG:3857",
                               "min": 100, "max": 2600, "gamma": 1.25})
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        path.write_bytes(r.content)
        print(f"  {y}: {n_scenes.getInfo()} ภาพ Sentinel-2 → {path.relative_to(ROOT.parent)} ({len(r.content) // 1024} KB)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_ids", nargs="*", help="uni_id ที่จะรัน (ไม่ใส่ = ทุกแห่ง)")
    ap.add_argument("--refresh", action="store_true", help="ไม่ใช้แคช ดึงจาก Earth Engine ใหม่")
    args = ap.parse_args()

    ee.Initialize(project=EE_PROJECT)
    unis = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]
    if args.uni_ids:
        unis = [u for u in unis if u["uni_id"] in args.uni_ids]

    summary = []
    for uni in unis:
        uid = uni["uni_id"]
        print(f"\n===== {uid} ({uni['name_th']}) =====")
        hexes = pd.read_parquet(PROCESSED / uid / "hex_features.parquet")
        sat = built_by_hex(uni, hexes, args.refresh)
        if sat[["built_2019", "built_2025"]].isna().any(axis=None):
            print("  ⚠ มีช่องที่ไม่มีค่า built:", int(sat.built_2025.isna().sum()))
        sat.to_parquet(PROCESSED / uid / "hex_satellite.parquet", index=False)
        off = sat[~sat.h3.isin(hexes.h3[hexes.on_campus])]
        summary.append({"uni_id": uid, "hexes": len(sat),
                        **{f"built_{y}": round(off[f"built_{y}"].mean(), 3) for y in (2019, 2022, 2025)},
                        "change_mean": round(off.built_change_2019_2025.mean(), 3),
                        "hexes_change_gt_0.15": int((off.built_change_2019_2025 > 0.15).sum())})
        print(f"  บันทึก {(PROCESSED / uid / 'hex_satellite.parquet').relative_to(ROOT)}")
        if uid in DEMO_UNIS:
            export_images(uni, args.refresh)

    print("\n===== สรุปค่า built (เฉลี่ยช่องนอกมหาวิทยาลัย) =====")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
