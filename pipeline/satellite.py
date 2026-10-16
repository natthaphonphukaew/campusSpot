"""ชั้นดาวเทียม

1) ค่า built (ความน่าจะเป็นว่าเป็นสิ่งปลูกสร้าง 0–1) เฉลี่ยรายปี 2019–2025 จาก Dynamic World (Earth Engine) ต่อช่อง H3
   ทุกมหาวิทยาลัย → data/processed/<uni_id>/hex_satellite.parquet (built_<ปี>, built_now = 2025, built_change_2019_2025)
   ค่านี้ใช้ในโมเดล
2) เฉพาะพื้นที่เดโม: ภาพคมสำหรับไทม์แลปส์บนเว็บจาก Esri World Imagery Wayback (0.3–0.5 ม.)
   เลือกรุ่นที่ภาพตรงจุดกลางมหาวิทยาลัยถ่ายใหม่จริง (ดูวันที่ถ่ายจาก metadata) → web/public/sat/<uni_id>/wayback.json
   ใช้แค่แสดงผล ไม่ได้ใช้ในโมเดล ตามเงื่อนไขของ Esri ห้ามดาวน์โหลดภาพเก็บไว้ เว็บจึงดึงภาพสดจาก Esri

แคช: data/raw/<uni_id>/ee_built_by_year.json, data/raw/<uni_id>/wayback_meta.json (ใช้ --refresh เพื่อดึงใหม่)

ครั้งแรกต้องล็อกอิน Earth Engine: .venv/Scripts/earthengine authenticate --auth_mode=localhost
รัน:
    python satellite.py                                # ทุกแห่ง + ภาพ Wayback ของพื้นที่เดโม
    python satellite.py kmutt_bangmod --refresh
    python satellite.py kmutt_bangmod --wayback-only   # ไม่เรียก Earth Engine
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
IMAGE_MARGIN = 1.6         # ขอบเขตภาพกว้างกว่ารัศมี ซูมออกแล้วยังเห็นภาพรอบ ๆ

WAYBACK_CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
WAYBACK_TILE = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/"
                "MapServer/tile/{id}/{{z}}/{{y}}/{{x}}")
WAYBACK_ATTRIBUTION = "Esri, Vantor, Earthstar Geographics, and the GIS User Community"
WAYBACK_SINCE = "2016-01-01"
WAYBACK_LAYERS = [4, 5, 3, 6]      # metadata ความละเอียด 30 ซม., 60 ซม., 15 ซม., 1.2 ม. (ภาพในไทยส่วนใหญ่อยู่ชั้น 30 ซม.)


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


def capture_at(meta_url, lon, lat):
    """วันที่ถ่ายและความละเอียดของภาพ ณ จุดนั้นในรุ่นนั้น (ลองชั้นละเอียดสุดก่อน)"""
    for layer in WAYBACK_LAYERS:
        params = {"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                  "spatialRel": "esriSpatialRelIntersects", "outFields": "SRC_DATE2,SRC_RES",
                  "returnGeometry": "false", "f": "json"}
        feats = None
        for _ in range(3):
            try:
                feats = requests.get(f"{meta_url}/{layer}/query", params=params, timeout=30).json().get("features", [])
                break
            except (requests.RequestException, ValueError):
                continue
        if feats:
            a = feats[0]["attributes"]
            date = pd.Timestamp(a["SRC_DATE2"], unit="ms").strftime("%Y-%m-%d") if a.get("SRC_DATE2") else None
            return {"captured": date, "resolution_m": a.get("SRC_RES")}
    return None


def wayback_frames(uni, refresh):
    """รุ่นของ Wayback ที่ภาพตรงจุดกลางมหาวิทยาลัยถ่ายใหม่ (เอารุ่นแรกของแต่ละวันที่ถ่าย)

    metadata ของ Esri ตอบช้า (~4 วิ/ครั้ง) จึงไม่ถามทุกรุ่น: วันที่ถ่ายของรุ่นใหม่ไม่เก่ากว่ารุ่นก่อน
    ใช้การแบ่งครึ่งหาจุดที่วันที่ถ่ายเปลี่ยน แล้วแคชผลทีละรุ่นทันที
    """
    cache = RAW / uni["uni_id"] / "wayback_meta.json"
    cached = {} if refresh or not cache.exists() else json.loads(cache.read_text(encoding="utf-8"))
    config = requests.get(WAYBACK_CONFIG, timeout=60).json()
    releases = sorted(({"release_id": int(k), "release_date": v["itemTitle"].split("Wayback ")[1].rstrip(")"),
                        "meta": v["metadataLayerUrl"]} for k, v in config.items()), key=lambda r: r["release_date"])
    releases = [r for r in releases if r["release_date"] >= WAYBACK_SINCE]
    asked = 0

    def cap(i):
        nonlocal asked
        key = str(releases[i]["release_id"])
        if key not in cached:
            asked += 1
            cached[key] = capture_at(releases[i]["meta"], uni["lon"], uni["lat"])
            cache.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        c = cached[key]
        return c["captured"] if c else None

    changes = set()

    def search(lo, hi):
        if hi - lo <= 1:
            if cap(lo) != cap(hi):
                changes.add(hi)
            return
        if cap(lo) == cap(hi):
            return
        mid = (lo + hi) // 2
        search(lo, mid)
        search(mid, hi)

    search(0, len(releases) - 1)
    frames = []
    for i in sorted({0} | changes):
        c = cached.get(str(releases[i]["release_id"]))
        if not c or not c["captured"] or c["captured"] < WAYBACK_SINCE:
            continue
        r = releases[i]
        frames.append({"release_id": r["release_id"], "release_date": r["release_date"], **c,
                       "tile_url": WAYBACK_TILE.format(id=r["release_id"])})
    print(f"  Wayback: {len(releases)} รุ่น ถาม metadata ใหม่ {asked} ครั้ง → ภาพถ่ายต่างวันกัน {len(frames)} ภาพ")
    return frames


def export_wayback(uni, refresh):
    frames = wayback_frames(uni, refresh)
    if not frames:
        raise RuntimeError("ไม่พบภาพ Wayback ของพื้นที่นี้")
    out = WEB_SAT / uni["uni_id"]
    out.mkdir(parents=True, exist_ok=True)
    doc = {"source": "esri_wayback", "attribution": WAYBACK_ATTRIBUTION, "bounds": image_bounds(uni), "frames": frames}
    (out / "wayback.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in frames:
        print(f"    ภาพถ่าย {f['captured']} ({f['resolution_m']} ม.) จากรุ่น {f['release_date']} (id {f['release_id']})")
    print(f"  → {(out / 'wayback.json').relative_to(ROOT.parent)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_ids", nargs="*", help="uni_id ที่จะรัน (ไม่ใส่ = ทุกแห่ง)")
    ap.add_argument("--refresh", action="store_true", help="ไม่ใช้แคช ดึงใหม่")
    ap.add_argument("--wayback-only", action="store_true", help="ทำแค่ wayback.json ของพื้นที่เดโม ไม่เรียก Earth Engine")
    args = ap.parse_args()

    if not args.wayback_only:
        ee.Initialize(project=EE_PROJECT)
    unis = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]
    if args.uni_ids:
        unis = [u for u in unis if u["uni_id"] in args.uni_ids]

    summary = []
    for uni in unis:
        uid = uni["uni_id"]
        print(f"\n===== {uid} ({uni['name_th']}) =====")
        if args.wayback_only:
            if uid in DEMO_UNIS:
                export_wayback(uni, args.refresh)
            continue
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
            export_wayback(uni, args.refresh)

    if summary:
        print("\n===== สรุปค่า built (เฉลี่ยช่องนอกมหาวิทยาลัย) =====")
        print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
