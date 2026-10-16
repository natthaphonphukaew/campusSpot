"""T0.4 ตรวจว่าทำ backtest ตามเวลาด้วย Overture ได้ไหม

ไฟล์ข้อมูล Overture รุ่นเก่าถูกลบจาก S3/Azure หลัง 60 วัน (เหลือแค่ 2 รุ่นล่าสุด) จึงดึง "รุ่นเก่า" ตรง ๆ ไม่ได้
แต่ changelog ของทุกรุ่นยังอยู่ (id + bbox ของจุดที่ added / removed ในแต่ละรุ่น) ย้อนไปถึง มิ.ย. 2024
สคริปต์นี้ใช้ changelog นับว่ามีร้านที่ "ปรากฏใหม่" ใน Overture รอบมหาวิทยาลัยในช่วง 12 เดือนกี่ร้าน
แล้วเทียบกับข้อมูลรุ่นล่าสุดที่ collect.py แคชไว้ (เพื่อรู้หมวดร้าน)

ข้อควรระวัง: "ปรากฏใหม่ใน Overture" ไม่เท่ากับ "เปิดใหม่จริง" อาจเป็นการดึงแหล่งข้อมูลเพิ่มหรือ id เปลี่ยน
สคริปต์จึงแยกจุดที่ added ใกล้จุดที่ removed ในรุ่นเดียวกัน (น่าจะเป็นจุดเดิมที่ id เปลี่ยน) ออกมาให้เห็น

รัน:
    python backtest_probe.py                    # kmutt_bangmod, ย้อน 12 เดือน
    python backtest_probe.py kmutt_bangmod --months 24
"""
import argparse, math, sys, time
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import yaml

from collect import CONFIG, RAW, bbox_of, classify, dist_m, first, ov_signals

BUCKET = "overturemaps-us-west-2"
REPLACED_M = 25   # added ห่างจาก removed ในรุ่นเดียวกันไม่เกินนี้ = น่าจะเป็นจุดเดิมที่ id เปลี่ยน
TARGET_NEW = 30   # เกณฑ์ใน PLAYBOOK: ร้านเปิดใหม่ ≥ 30 ร้านต่อมหาวิทยาลัย


def list_releases(fs):
    infos = fs.get_file_info(pafs.FileSelector(f"{BUCKET}/changelog"))
    return sorted(i.base_name for i in infos if i.type == pafs.FileType.Directory and "beta" not in i.base_name)


def release_date(r):
    return date.fromisoformat(r.split(".")[0])


def changelog_in_bbox(fs, release, change_type, bbox, cache_dir):
    """id + จุดกลาง bbox ของจุดที่เปลี่ยนในรุ่นนั้น เฉพาะในกรอบพิกัด (แคชไว้ ไม่ดึงซ้ำ)"""
    path = cache_dir / f"{release}_{change_type}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    W, S, E, N = bbox
    d = ds.dataset(f"{BUCKET}/changelog/{release}/theme=places/type=place/change_type={change_type}",
                   filesystem=fs, format="parquet")
    f = ((pc.field("bbox", "xmin") <= E) & (pc.field("bbox", "xmax") >= W)
         & (pc.field("bbox", "ymin") <= N) & (pc.field("bbox", "ymax") >= S))
    t = d.to_table(columns=["id", "bbox"], filter=f).to_pandas()
    out = pd.DataFrame({
        "id": t["id"],
        "lon": [(b["xmin"] + b["xmax"]) / 2 for b in t["bbox"]],
        "lat": [(b["ymin"] + b["ymax"]) / 2 for b in t["bbox"]],
    })
    out.to_parquet(path, index=False)
    return out


def near_any(df, other, radius_m):
    """แต่ละแถวใน df มีจุดใน other อยู่ใกล้ไม่เกิน radius_m ไหม"""
    if other.empty or df.empty:
        return pd.Series(False, index=df.index)
    cell = radius_m / 111_320
    grid = {}
    for lat, lon in zip(other.lat, other.lon):
        grid.setdefault((int(lat // cell), int(lon // cell)), []).append((lat, lon))
    res = []
    for lat, lon in zip(df.lat, df.lon):
        gy, gx = int(lat // cell), int(lon // cell)
        hit = any(dist_m(lat, lon, a, b) <= radius_m
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1) for a, b in grid.get((gy + dy, gx + dx), []))
        res.append(hit)
    return pd.Series(res, index=df.index)


def current_places(uni):
    """ข้อมูล Overture รุ่นล่าสุดที่ collect.py แคชไว้ พร้อมหมวดร้านตามกฎเดียวกับ collect.py"""
    path = RAW / uni["uni_id"] / "overture_places.parquet"
    if not path.exists():
        sys.exit(f"ไม่พบ {path} ให้รัน collect.py {uni['uni_id']} ก่อน")
    ov = gpd.read_parquet(path)
    cur = pd.DataFrame({
        "id": ov["id"],
        "name": [first(n, "primary") or "" for n in ov["names"]],
        "lat": ov.geometry.y, "lon": ov.geometry.x,
    })
    none = pd.Series([None] * len(ov), index=ov.index)
    # ใช้กฎเดียวกับ collect.py (Overture รุ่นใหม่ไม่มีคอลัมน์ categories แล้ว จะเหลือแค่ basic_category)
    cur["category"] = [classify(n, ov_signals(c, b)) for n, c, b in
                       zip(cur.name, ov.get("categories", none), ov.get("basic_category", none))]
    cur["dist_m"] = [dist_m(a, b, uni["lat"], uni["lon"]) for a, b in zip(cur.lat, cur.lon)]
    return cur[cur.dist_m <= uni["radius_m"]].reset_index(drop=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 200)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_id", nargs="?", default="kmutt_bangmod")
    ap.add_argument("--months", type=int, default=12, help="ย้อนหลังกี่เดือน (ค่าเริ่มต้น 12)")
    args = ap.parse_args()

    unis = {u["uni_id"]: u for u in yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]}
    uni = unis[args.uni_id]
    fs = pafs.S3FileSystem(anonymous=True, region="us-west-2")
    cache_dir = RAW / uni["uni_id"] / "overture_changelog"
    cache_dir.mkdir(parents=True, exist_ok=True)

    releases = list_releases(fs)
    latest = releases[-1]
    d_latest = release_date(latest)
    cutoff = (pd.Timestamp(d_latest) - pd.DateOffset(months=args.months)).date()
    # รุ่นฐาน = รุ่นแรกที่ออกหลังวันตัด ใช้แทน "ข้อมูลรุ่นเก่า" ส่วน changelog ของรุ่นถัด ๆ ไปคือสิ่งที่เปลี่ยนหลังจากนั้น
    base = next(r for r in releases if release_date(r) >= cutoff)
    window = [r for r in releases if release_date(r) > release_date(base)]
    print(f"changelog ทั้งหมด {len(releases)} รุ่น ({releases[0]} ถึง {latest})")
    print(f"รุ่นฐาน {base} (ย้อน {args.months} เดือน) → ดูการเปลี่ยนแปลง {len(window)} รุ่น ({window[0]} ถึง {window[-1]})\n")

    bbox = bbox_of(uni)
    cur = current_places(uni)
    cur_ids = set(cur.id)

    rows, added_all = [], []
    for r in window:
        t = time.time()
        add = changelog_in_bbox(fs, r, "added", bbox, cache_dir)
        rem = changelog_in_bbox(fs, r, "removed", bbox, cache_dir)
        add = add[[dist_m(a, b, uni["lat"], uni["lon"]) <= uni["radius_m"] for a, b in zip(add.lat, add.lon)]]
        rem = rem[[dist_m(a, b, uni["lat"], uni["lon"]) <= uni["radius_m"] for a, b in zip(rem.lat, rem.lon)]]
        replaced = near_any(add, rem, REPLACED_M)
        add = add.assign(release=r, replaced=replaced.values)
        added_all.append(add)
        rows.append({"release": r, "added": len(add), "removed": len(rem), "added_near_removed": int(replaced.sum()),
                     "added_still_present": int(add.id.isin(cur_ids).sum()), "secs": round(time.time() - t, 1)})
        print(f"  {r}: added {len(add)}, removed {len(rem)} ({rows[-1]['secs']} วิ)")

    per_rel = pd.DataFrame(rows).set_index("release")
    print("\nต่อรุ่น (ในรัศมี", uni["radius_m"], "ม.):")
    print(per_rel.drop(columns="secs").to_string())

    added = pd.concat(added_all).drop_duplicates("id", keep="first")
    new = cur[cur.id.isin(added.id)].merge(added[["id", "release", "replaced"]], on="id")
    print(f"\nจุดใน Overture รุ่นล่าสุด ({latest}) ในรัศมี: {len(cur)}")
    print(f"ในนั้นเป็นจุดที่ added ในช่วงนี้: {len(new)} ({len(new) / max(1, len(cur)):.0%})")

    summary = pd.DataFrame({
        "new_all": new.groupby("category").size(),
        "new_not_near_removed": new[~new.replaced].groupby("category").size(),
        "current_total": cur.groupby("category").size(),
    }).fillna(0).astype(int).reindex(["cafe", "food", "laundry", "print_stationery", "dorm_like", "convenience", "other"]).fillna(0).astype(int)
    print("\nร้านที่ปรากฏใหม่ในช่วงนี้และยังอยู่ในรุ่นล่าสุด ต่อหมวด:")
    print(summary.to_string())

    for cat in ["cafe", "food"]:
        sample = new[(new.category == cat) & ~new.replaced].head(12)
        print(f"\nตัวอย่างชื่อ {cat} ที่ปรากฏใหม่ (ให้คนดูว่าเป็นร้านเปิดใหม่จริงไหม):")
        for _, s in sample.iterrows():
            print(f"  [{s.release}] {s['name']}")

    n_core = int(summary.loc[["cafe", "food"], "new_not_near_removed"].sum())
    print(f"\nร้านกาแฟ+ร้านอาหารที่ปรากฏใหม่ (ไม่นับจุดที่น่าจะแค่เปลี่ยน id): {n_core} (เกณฑ์ ≥ {TARGET_NEW})")
    big = per_rel[per_rel.added > 3 * per_rel.added.median()]
    if len(big):
        print("รุ่นที่ added สูงผิดปกติ (น่าจะเป็นการดึงแหล่งข้อมูลใหม่ ไม่ใช่ร้านเปิดจริง):", ", ".join(big.index))


if __name__ == "__main__":
    main()
