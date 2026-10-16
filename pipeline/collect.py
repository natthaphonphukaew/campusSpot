"""ดึงร้านค้าและหอพักรอบมหาวิทยาลัยจาก OpenStreetMap + Overture แล้วจัดประเภทและติดธง

แปลงมาจากโน้ตบุ๊ก kmutt_campusspot_data_check_v2 (ตัดส่วนเดินสำรวจและ Earth Engine ออก)
ไม่ลบข้อมูลทิ้ง ทุกจุดยังอยู่ แต่มีคอลัมน์ flag บอกสถานะ และ reason บอกเหตุผล

รัน:
    python collect.py                      # ทุกแห่งใน config/universities.yaml
    python collect.py kmutt_bangmod        # เฉพาะแห่งที่ระบุ
    python collect.py --refresh            # ไม่ใช้แคช ดึงใหม่ทั้งหมด
"""
import argparse, difflib, json, math, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml
from shapely.affinity import scale
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "universities.yaml"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

CATS = ["dorm_like", "cafe", "food", "laundry", "print_stationery", "convenience"]
FLAGS = ["ok", "duplicate", "false_positive", "industrial_print", "on_campus", "needs_check", "unnamed_building"]


def dist_m(lat, lon, lat0, lon0):
    return math.hypot((lat - lat0) * 111_320, (lon - lon0) * 111_320 * math.cos(math.radians(lat0)))


def radius_circle(uni):
    """วงกลมรัศมีในพิกัด lon/lat (ปรับแกน lon ตาม cos ของละติจูด)"""
    circle = Point(uni["lon"], uni["lat"]).buffer(uni["radius_m"] / 111_320, 64)
    return scale(circle, xfact=1 / math.cos(math.radians(uni["lat"])), yfact=1, origin=(uni["lon"], uni["lat"]))


def bbox_of(uni):
    dlat = uni["radius_m"] / 111_320
    dlon = uni["radius_m"] / (111_320 * math.cos(math.radians(uni["lat"])))
    return (uni["lon"] - dlon, uni["lat"] - dlat, uni["lon"] + dlon, uni["lat"] + dlat)


# ---------------------------------------------------------------- 1) OpenStreetMap

HEADERS = {"User-Agent": "CampusSpot/0.3 (student project)", "Accept": "application/json"}
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def overpass(q, rounds=4):
    """ลองทุกเซิร์ฟเวอร์ วนหลายรอบ รอนานขึ้นเรื่อย ๆ ถ้าเซิร์ฟเวอร์ไม่ว่าง (406/429/502/503/504)"""
    last = None
    for rnd in range(rounds):
        for url in MIRRORS:
            try:
                r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=200)
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except ValueError:
                        last = f"non-JSON from {url}"; print("  ✗", last); continue
                    print("  ✓ ok from", url)
                    return data["elements"]
                last = f"{r.status_code} from {url}"
            except requests.RequestException as e:
                last = f"{type(e).__name__} from {url}"
            print("  ✗", last)
            time.sleep(3)
        wait = 15 * (rnd + 1)
        print(f"รอบ {rnd+1} ไม่สำเร็จ รอ {wait} วินาทีแล้วลองใหม่...")
        time.sleep(wait)
    raise RuntimeError(f"Overpass ทุกเซิร์ฟเวอร์ไม่ว่าง (ล่าสุด: {last}) ลองรันใหม่อีก 10 นาที")


def cached_overpass(path, q, refresh):
    """ใช้ผลที่แคชไว้ถ้ามี ไม่งั้นดึงจาก Overpass แล้วเก็บแคช"""
    if path.exists() and not refresh:
        print("  ใช้แคช", path.relative_to(ROOT))
        return json.loads(path.read_text(encoding="utf-8"))
    els = overpass(q)
    path.write_text(json.dumps(els, ensure_ascii=False), encoding="utf-8")
    return els


def fetch_osm(uni, raw_dir, refresh):
    lat, lon, radius = uni["lat"], uni["lon"], uni["radius_m"]
    A = f"(around:{radius},{lat},{lon})"
    osm_els = cached_overpass(raw_dir / "osm_pois.json", f'''[out:json][timeout:120];
(
  nwr{A}["amenity"~"cafe|restaurant|fast_food|food_court|ice_cream|internet_cafe|dormitory"];
  nwr{A}["shop"];
  nwr{A}["building"~"dormitory|apartments"];
  nwr{A}["tourism"~"guest_house|hostel|apartment"];
  nwr{A}["name"~"หอพัก|อพาร์ท|แมนชั่น|Apartment|Mansion|Residence|Dorm",i];
);
out center tags;''', refresh)
    print("  OSM elements:", len(osm_els))

    count_els = cached_overpass(raw_dir / "osm_building_count.json",
                                f'[out:json][timeout:120];way{A}["building"];out count;', refresh)
    building_count = int(count_els[0]["tags"]["ways"])
    print("  OSM building footprints:", building_count)

    campus_els = cached_overpass(raw_dir / "osm_campus.json", f'''[out:json][timeout:60];
(way(around:800,{lat},{lon})["amenity"="university"];
 relation(around:800,{lat},{lon})["amenity"="university"];);
out geom;''', refresh)
    return osm_els, building_count, campus_els


def build_polys(els):
    polys = []
    for e in els:
        if e["type"] == "way" and "geometry" in e:
            pts = [(p["lon"], p["lat"]) for p in e["geometry"]]
            if len(pts) >= 4:
                polys.append(Polygon(pts))
        elif e["type"] == "relation":
            lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                     for m in e.get("members", []) if m.get("role") == "outer" and "geometry" in m]
            polys += list(polygonize(unary_union(lines)))
    return polys


def campus_polygon(uni, campus_els):
    # รวมทุกชิ้นของ element เดียวกันก่อน (relation อาจมีหลายชิ้น เช่น สจล. มี 4 ชิ้น)
    cands = [unary_union([p.buffer(0) for p in polys]) for polys in (build_polys([e]) for e in campus_els) if polys]
    center = Point(uni["lon"], uni["lat"])
    poly = max(cands, key=lambda p: (p.contains(center), p.area)) if cands else None
    if poly is None:
        print("  ไม่พบขอบเขตมหาวิทยาลัยใน OSM: จะใช้แค่ชื่อร้านในการแยกร้านในมหาวิทยาลัย")
        return None, None
    km2 = poly.area * (111.32 ** 2) * math.cos(math.radians(uni["lat"]))
    print(f"  campus polygon: ~{km2:.2f} ตร.กม., contains center = {poly.contains(center)}")
    return poly, km2


# ---------------------------------------------------------------- 2) Overture (แหล่งหลัก)

def fetch_overture(uni, raw_dir, refresh):
    path = raw_dir / "overture_places.parquet"
    if path.exists() and not refresh:
        print("  ใช้แคช", path.relative_to(ROOT))
        ov = gpd.read_parquet(path)
    else:
        from overturemaps import core
        ov = core.geodataframe("place", bbox=bbox_of(uni))
        ov.to_parquet(path)
    print("  Overture places in bbox:", len(ov))
    return ov


# ---------------------------------------------------------------- 3) จัดประเภท
# ถ้าเจอร้านที่จัดผิด ให้แก้ regex ตรงนี้แล้วรันใหม่ (ใช้แคช ไม่ต้องดึงซ้ำ)

DORM_STRONG = r"หอพัก|หอใน|หอชาย|หอหญิง|อพาร์ท|อพาร์ต|แมนชั่น|apartment|mansion|residence|dorm"
DORM_WEAK   = r"เพลส|place|living|เรสซิเดนซ์|คอนโด|condo|^หอ(?!ม|สมุด|ประชุม|การค้า)"
DORM_FP     = r"หอสมุด|library(?!.*condo)|โรงอาหาร|market ?place|fitness|เอ็กเพลส|express|หอมสนิท|บาร์|\bbar\b|หมู่บ้าน|village|ร้านอาหาร|cafe|coffee"
INTERNET    = r"internet|อินเทอร์เน็ต|อินเตอร์เน็ต|เกมส์|game"
LAUNDRY     = r"ซัก|laundr|laundromat|wash ?(&|and)? ?dry|wash express|dwash|dry ?clean"
NOT_LAUNDRY = r"car|ล้างรถ|detailing|pet|สุนัข"
PRINT       = r"ถ่ายเอกสาร|copy|ปริ้น|พริ้น|print|เครื่องเขียน|stationar|stationer|เข้าเล่ม|ทำเล่ม"
PRINT_STUDENT = r"ถ่ายเอกสาร|copy|ปริ้นสี|เข้าเล่ม|ทำเล่ม|digital|เครื่องเขียน|stationar|stationer|postshop|overprint"
PRINT_INDUSTRIAL = r"co\.|ltd|จำกัด|บริษัท|โรงพิมพ์|import|อิมปอร์ต|ป้าย|สกรีน|ฉลาก|สติ๊กเกอร์|packag|label|การพิมพ์|printing|พริ้นติ้ง|พริ้นท์ติ้ง"


def has(p, s): return bool(re.search(p, s or "", re.I))


def classify(name, signals):
    s = (signals or "").lower()
    n = name or ""
    if has(INTERNET, n) or "internet" in s: return "other"
    if has(LAUNDRY, n) or "laundr" in s or "dry_clean" in s:
        return "other" if has(NOT_LAUNDRY, n) else "laundry"
    if has(PRINT, n) or "print" in s or "copy" in s or "stationer" in s: return "print_stationery"
    if any(k in s for k in ["coffee", "cafe", "tea_room", "bubble_tea"]): return "cafe"
    if any(k in s for k in ["restaurant", "fast_food", "food_court", "food", "ice_cream", "noodle", "bakery"]): return "food"
    if any(k in s for k in ["convenience", "supermarket"]): return "convenience"
    if has(DORM_STRONG, n) or any(k in s for k in ["dormitor", "apartment", "hostel", "guest_house"]): return "dorm_like"
    if has(DORM_WEAK, n) and not any(k in s for k in ["shop", "store", "restaurant", "cafe", "service"]): return "dorm_like"
    return "other"


def osm_signals(t):
    keys = ["amenity", "shop", "building", "tourism", "cuisine"]
    s = " ".join(f"{k}={t.get(k, '')}" for k in keys if t.get(k))
    if t.get("amenity") == "cafe" or t.get("shop") == "coffee": s += " coffee"
    if t.get("amenity") in ("restaurant", "fast_food", "food_court", "ice_cream"): s += " restaurant"
    if t.get("shop") in ("laundry", "dry_cleaning"): s += " laundry"
    if t.get("shop") in ("copyshop", "stationery"): s += " print stationer"
    if t.get("shop") in ("convenience", "supermarket"): s += " convenience"
    if t.get("amenity") == "internet_cafe": s += " internet"
    if t.get("amenity") == "dormitory" or t.get("building") in ("dormitory", "apartments") \
       or t.get("tourism") in ("guest_house", "hostel", "apartment"): s += " apartment"
    return s


def first(x, key):
    if isinstance(x, dict): return x.get(key)
    return None


def ov_signals(cat, basic=None):
    parts = [str(basic)] if isinstance(basic, str) and basic else []
    if isinstance(cat, dict):
        alt = cat.get("alternate")
        alt = list(alt) if alt is not None else []
        parts += [str(cat.get("primary") or "")] + [str(a) for a in alt]
    return " ".join(parts)


def build_points(uni, osm_els, ov):
    rows = []
    for e in osm_els:
        t = e.get("tags", {})
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None: continue
        rows.append({"source": "osm", "name": t.get("name", ""), "signals": osm_signals(t), "confidence": None,
                     "lat": lat, "lon": lon})
    for _, r in (ov.iterrows() if ov is not None else []):
        rows.append({"source": "overture", "name": first(r.get("names"), "primary") or "",
                     "signals": ov_signals(r.get("categories"), r.get("basic_category")),
                     "confidence": r.get("confidence"),
                     "lat": r.geometry.y, "lon": r.geometry.x})
    pts = pd.DataFrame(rows)
    pts["confidence"] = pd.to_numeric(pts["confidence"], errors="coerce")
    pts["dist_m"] = [round(dist_m(a, b, uni["lat"], uni["lon"])) for a, b in zip(pts.lat, pts.lon)]
    pts = pts[pts.dist_m <= uni["radius_m"]].reset_index(drop=True)
    pts["category"] = [classify(n, s) for n, s in zip(pts.name, pts.signals)]
    return pts


# ---------------------------------------------------------------- 4) ติดธง: จับผิด, โรงพิมพ์, ในมหาวิทยาลัย, รายการซ้ำ

ALIAS = {"cosmo": "คอสโม", "thonburisport": "ธนบุรีสปอร์ต", "siri": "สิริ", "alisha": "อลิชา",
         "dhammaraksa": "ธรรมรักษา", "7eleven": "เซเว่น", "lotus": "โลตัส", "amazon": "อเมซอน",
         "kruajeleng": "เจ๊เล้ง"}   # เพิ่มคู่ชื่อไทย-อังกฤษที่เจอได้เรื่อย ๆ
GENERIC = r"^(หอพักหญิง|หอพักชาย|หอพัก|บ้าน|ร้าน|ก๋วยเตี๋ยว|ข้าว|ครัว|คาเฟ่|cafe|coffee|the)+"
DUP_RADIUS_M = 60   # ร้านชื่อคล้ายกันในระยะนี้ถือว่าซ้ำ (ร้านเชนสาขาต่างกันมักห่างกว่านี้)


def key(s):
    s = re.sub(r"[^a-z0-9ก-๙]", "", str(s).lower())
    for en, th in ALIAS.items():
        s = s.replace(en, th)
    return re.sub(GENERIC, "", s)


def trailing_num(s):
    m = re.search(r"(\d+)\D*$", str(s))
    return m.group(1) if m else None


def similar(ka, kb):
    if min(len(ka), len(kb)) < 4: return False
    if ka in kb or kb in ka: return True
    if len(ka) >= 8 and ka[:8] == kb[:8]: return True
    return difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.8


def apply_flags(pts, uni, campus_poly):
    pts["flag"], pts["reason"] = "ok", ""

    def setf(mask, flag, reason):
        m = mask & (pts.flag == "ok")
        pts.loc[m, "flag"], pts.loc[m, "reason"] = flag, reason

    nm = pts.name.fillna("")
    dorm = pts.category == "dorm_like"
    setf(dorm & nm.str.contains(DORM_FP, case=False, regex=True), "false_positive", "ชื่อไม่ใช่หอพัก")
    # อาคารที่พักไม่มีชื่อ รอบ มจธ. ส่วนใหญ่เป็นคอนโด ไม่ใช่หอพัก
    setf(dorm & nm.str.strip().eq(""), "unnamed_building", "อาคารที่พักไม่มีชื่อ ส่วนใหญ่เป็นคอนโด ไม่ใช่หอพัก")
    setf(dorm & nm.str.fullmatch(r"\s*[A-Za-z0-9]?\s*"), "needs_check", "ชื่อสั้นเกินไป")
    setf(dorm & ~nm.str.contains(DORM_STRONG, case=False, regex=True)
         & ~pts.signals.str.contains("apartment|dormitor|hostel|guest_house", case=False), "needs_check", "มีแค่คำอ่อน เช่น Place")
    setf((pts.category == "print_stationery") & nm.str.contains(PRINT_INDUSTRIAL, case=False, regex=True)
         & ~nm.str.contains(PRINT_STUDENT, case=False, regex=True), "industrial_print", "โรงพิมพ์หรือบริษัท ไม่ใช่ร้านสำหรับนักศึกษา")

    if campus_poly is not None:
        inside = [campus_poly.contains(Point(b, a)) for a, b in zip(pts.lat, pts.lon)]
        setf(pd.Series(inside, index=pts.index), "on_campus", "อยู่ในขอบเขตมหาวิทยาลัย")
    if uni.get("on_campus_name"):
        setf(nm.str.contains(uni["on_campus_name"], case=False, regex=True) & (pts.dist_m < 600),
             "on_campus", "ชื่อบอกว่าอยู่ในมหาวิทยาลัย")

    pts["_k"] = pts.name.map(key)
    order = pts.sort_values(["source", "confidence"], ascending=[False, False]).index  # overture ก่อน
    recs = pts.to_dict("index")
    grid = {}   # (category, ช่องกริด) -> รายการจุดที่เก็บไว้แล้ว
    cell = lambda lat, lon: (int(lat * 111_320 // DUP_RADIUS_M), int(lon * 108_000 // DUP_RADIUS_M))
    for i in order:
        a = recs[i]
        if a["flag"] == "false_positive": continue
        gx, gy = cell(a["lat"], a["lon"])
        dup_of = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((a["category"], gx + dx, gy + dy), []):
                    b = recs[j]
                    if dist_m(a["lat"], a["lon"], b["lat"], b["lon"]) > DUP_RADIUS_M: continue
                    na, nb = trailing_num(a["name"]), trailing_num(b["name"])
                    if na and nb and na != nb: continue
                    if similar(a["_k"], b["_k"]):
                        dup_of = j; break
                if dup_of is not None: break
            if dup_of is not None: break
        if dup_of is None:
            grid.setdefault((a["category"], gx, gy), []).append(i)
        elif a["flag"] == "ok":
            pts.at[i, "flag"], pts.at[i, "reason"] = "duplicate", f"ซ้ำกับ: {recs[dup_of]['name']}"
    return pts.drop(columns="_k")


# ---------------------------------------------------------------- 5) รันและบันทึก

def collect(uni, refresh=False):
    uid = uni["uni_id"]
    print(f"\n===== {uid} ({uni['name_th']}) =====")
    raw_dir, out_dir = RAW / uid, PROCESSED / uid
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    osm_els, building_count, campus_els = fetch_osm(uni, raw_dir, refresh)
    campus_poly, campus_km2 = campus_polygon(uni, campus_els)
    ov = fetch_overture(uni, raw_dir, refresh)

    pts = build_points(uni, osm_els, ov)
    pts = apply_flags(pts, uni, campus_poly)
    pts = pts.sort_values(["category", "flag", "dist_m"]).reset_index(drop=True)
    pts.to_parquet(out_dir / "points.parquet", index=False)
    if campus_poly is not None:
        gpd.GeoSeries([campus_poly], crs="EPSG:4326").to_file(out_dir / "campus.geojson", driver="GeoJSON")

    target = pts[pts.category.isin(CATS)]
    table = (target.groupby(["category", "flag"]).size().unstack(fill_value=0)
             .reindex(index=CATS, columns=FLAGS, fill_value=0))
    table["total"] = table.sum(axis=1)
    named_dorms = int(((pts.category == "dorm_like") & (pts.flag == "ok")).sum())
    # ขอบเขตมหาวิทยาลัยกินพื้นที่ในรัศมีกี่ % (ถ้าสูงมาก ช่องที่เป็นทำเลได้จะเหลือน้อย)
    circle = radius_circle(uni)
    campus_share = campus_poly.intersection(circle).area / circle.area if campus_poly is not None else None

    meta = {"uni_id": uid, "center": [uni["lat"], uni["lon"]], "radius_m": uni["radius_m"],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "osm_building_count": building_count, "campus_polygon_found": campus_poly is not None,
            "campus_km2": round(campus_km2, 3) if campus_km2 else None,
            "campus_share_of_radius": round(campus_share, 3) if campus_share is not None else None,
            "n_points": len(pts), "usable_by_category": {c: int(table.loc[c, "ok"]) for c in CATS}}
    (out_dir / "collect_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nจำนวนจุดต่อหมวดต่อ flag ({uid}) — ทั้งหมด {len(pts)} จุด ในรัศมี {uni['radius_m']} ม.")
    print(table.to_string())
    print(f"\nใช้ได้ (ok): ร้านกาแฟ {table.loc['cafe', 'ok']}, ร้านอาหาร {table.loc['food', 'ok']}, "
          f"หอพักมีชื่อ {named_dorms}")
    print("บันทึก:", (out_dir / "points.parquet").relative_to(ROOT))
    return pts


REPORT_COLS = ["cafe", "food", "laundry", "print_stationery", "dorm_like", "convenience"]


def write_report(unis):
    """สรุปทุกแห่งจาก collect_meta.json ลง data/processed/collect_report.csv"""
    rows = []
    for uni in unis:
        path = PROCESSED / uni["uni_id"] / "collect_meta.json"
        if not path.exists():
            rows.append({"uni_id": uni["uni_id"], "name_th": uni["name_th"], "note": "ยังไม่ได้รัน"})
            continue
        m = json.loads(path.read_text(encoding="utf-8"))
        notes = []
        if not m["campus_polygon_found"]: notes.append("หาขอบเขตมหาวิทยาลัยไม่เจอ")
        if (m.get("campus_share_of_radius") or 0) > 0.4: notes.append("มหาวิทยาลัยกินพื้นที่เกิน 40% ของรัศมี")
        if m["usable_by_category"]["cafe"] < 20: notes.append("ร้านกาแฟน้อยผิดปกติ ตรวจพิกัด")
        rows.append({"uni_id": m["uni_id"], "name_th": uni["name_th"],
                     "campus_polygon_found": m["campus_polygon_found"], "campus_km2": m["campus_km2"],
                     "campus_share_of_radius": m.get("campus_share_of_radius"),
                     "osm_building_count": m["osm_building_count"], "n_points": m["n_points"],
                     **{c: m["usable_by_category"][c] for c in REPORT_COLS}, "note": "; ".join(notes)})
    report = pd.DataFrame(rows)
    report.to_csv(PROCESSED / "collect_report.csv", index=False, encoding="utf-8-sig")
    print("\n===== สรุปทุกมหาวิทยาลัย (จำนวน ok ต่อหมวด) =====")
    print(report.drop(columns="name_th").to_string(index=False))
    print("บันทึก:", (PROCESSED / "collect_report.csv").relative_to(ROOT))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_ids", nargs="*", help="uni_id ที่จะรัน (ไม่ใส่ = ทุกแห่ง)")
    ap.add_argument("--refresh", action="store_true", help="ไม่ใช้แคช ดึงข้อมูลใหม่ทั้งหมด")
    args = ap.parse_args()

    all_unis = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]
    unis = all_unis
    if args.uni_ids:
        unknown = set(args.uni_ids) - {u["uni_id"] for u in unis}
        if unknown:
            sys.exit(f"ไม่พบ uni_id ใน config: {', '.join(sorted(unknown))}")
        unis = [u for u in unis if u["uni_id"] in args.uni_ids]
    for uni in unis:
        collect(uni, refresh=args.refresh)
    write_report(all_unis)


if __name__ == "__main__":
    main()
