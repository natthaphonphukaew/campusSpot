"""ส่งออกร้าน 4 หมวด (กาแฟ อาหาร ซักผ้า ปริ้นต์) ที่ผ่านการคัดแล้ว ให้โปรเจกต์อื่นเอาไปใช้ (ไม่ใช่ส่วนหนึ่งของเว็บ CampusSpot)

ใช้เฉพาะจุดที่ flag = ok จาก collect.py (ตัดร้านซ้ำ จัดหมวดผิด โรงพิมพ์ และร้านในมหาวิทยาลัยออกแล้ว)
แต่ละร้านมีไลเซนส์ของตัวเอง: Overture ตามแหล่งต้นทาง (CDLA-Permissive-2.0 / CC0-1.0 / Apache-2.0), OSM = ODbL-1.0

ผล: data/exports/<uni_id>/shops.geojson, shops.csv, README.md (วิธีใช้กับ MapLibre)

รัน:
    python export_shops.py                       # kmutt_bangmod, รวม OSM
    python export_shops.py --overture-only       # ตัดร้านจาก OSM (ODbL) ออก ไลเซนส์ง่ายกว่า
"""
import argparse, json, sys
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd

from collect import PROCESSED, RAW, ROOT, first

CATS = {"cafe": "ร้านกาแฟ", "food": "ร้านอาหาร", "laundry": "ร้านซักผ้า", "print_stationery": "ร้านปริ้นต์และเครื่องเขียน"}
OSM_LICENSE = "ODbL-1.0"
ATTRIBUTION = {
    "overture": "© Overture Maps Foundation",
    "osm": "© OpenStreetMap contributors",
}


def overture_lookup(uid):
    """(lat, lon, name) → id, ไลเซนส์, confidence ของร้านจาก Overture ที่ collect.py แคชไว้"""
    path = RAW / uid / "overture_places.parquet"
    ov = gpd.read_parquet(path)
    lookup = {}
    for _, r in ov.iterrows():
        sources = r["sources"] if r["sources"] is not None else []
        licenses = sorted({s.get("license") for s in sources if s.get("license")})
        key = (round(r.geometry.y, 7), round(r.geometry.x, 7), first(r["names"], "primary") or "")
        lookup[key] = {"overture_id": r["id"], "license": "; ".join(licenses), "confidence": r.get("confidence")}
    fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
    return lookup, fetched


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_id", nargs="?", default="kmutt_bangmod")
    ap.add_argument("--overture-only", action="store_true", help="ตัดร้านจาก OSM (ODbL) ออก")
    args = ap.parse_args()
    uid = args.uni_id

    pts = pd.read_parquet(PROCESSED / uid / "points.parquet")
    pts = pts[pts.category.isin(CATS) & (pts.flag == "ok")].copy()
    if args.overture_only:
        pts = pts[pts.source == "overture"]

    lookup, ov_fetched = overture_lookup(uid)
    osm_fetched = datetime.fromtimestamp((RAW / uid / "osm_pois.json").stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")

    rows = []
    for _, p in pts.iterrows():
        row = {"name": p["name"] or "", "category": p.category, "category_th": CATS[p.category],
               "lat": round(float(p.lat), 7), "lon": round(float(p.lon), 7), "source": p.source,
               "distance_from_campus_center_m": int(p.dist_m)}
        if p.source == "overture":
            info = lookup.get((round(float(p.lat), 7), round(float(p.lon), 7), p["name"] or ""), {})
            if not info:
                raise ValueError(f"หาร้าน Overture ในแคชไม่เจอ: {p['name']} ({p.lat}, {p.lon})")
            row |= {"license": info["license"], "overture_id": info["overture_id"],
                    "confidence": round(float(info["confidence"]), 3) if pd.notna(info["confidence"]) else None,
                    "data_date": ov_fetched}
        else:
            row |= {"license": OSM_LICENSE, "overture_id": None, "confidence": None, "data_date": osm_fetched}
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(["category", "distance_from_campus_center_m"]).reset_index(drop=True)

    sources = sorted(df.source.unique())
    attribution = ", ".join(ATTRIBUTION[s] for s in sources)
    out = ROOT / "data" / "exports" / uid
    out.mkdir(parents=True, exist_ok=True)

    props = [c for c in df.columns if c not in ("lat", "lon")]
    geo = {
        "type": "FeatureCollection",
        # foreign members ของ GeoJSON — MapLibre ไม่อ่าน แต่บอกที่มาของไฟล์
        "name": f"{uid}_shops",
        "attribution": attribution,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": [{"type": "Feature", "id": i,
                      "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
                      "properties": {k: (None if pd.isna(r[k]) else r[k]) for k in props}}
                     for i, r in df.iterrows()],
    }
    (out / "shops.geojson").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    df.to_csv(out / "shops.csv", index=False, encoding="utf-8-sig")

    print(f"{uid}: {len(df)} ร้าน ({'เฉพาะ Overture' if args.overture_only else 'Overture + OSM'})")
    print(df.groupby(["category", "source"]).size().unstack(fill_value=0).to_string())
    print("\nไลเซนส์:")
    print(df.license.value_counts().to_string())
    print(f"\nเครดิตที่ต้องใส่: {attribution}")
    for f in ["shops.geojson", "shops.csv"]:
        print(f"  {(out / f).relative_to(ROOT.parent)}: {(out / f).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
