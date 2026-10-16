"""คำนวณคะแนนโอกาสของพื้นที่เดโม แล้วเขียนไฟล์ตาม data contract (CLAUDE.md) ไปที่ web/public/data/<uni_id>/

ต่อหมวด (cafe, food, laundry, print_stationery):
    expected     จำนวนร้านที่ย่านนี้น่าจะรองรับได้ = LightGBM ที่เทรนด้วยมหาวิทยาลัยอื่นทั้งหมด (ไม่รวมแห่งที่ส่งออก
                 เพื่อไม่ให้โมเดลจำคำตอบของที่นี่ได้ ช่องว่างระหว่าง expected กับ actual จึงมีความหมาย)
    actual       จำนวนร้านหมวดนั้นจริงในรัศมี 200 ม.
    growth       built_change_2019_2025 ปรับสเกล 0–1 ภายในมหาวิทยาลัย
    raw          (expected - actual) + 0.5 * growth * expected
    opportunity  เปอร์เซ็นไทล์ของ raw ภายในมหาวิทยาลัย 0–100, ช่อง on_campus = 0
    shap_top     4 ฟีเจอร์ที่มีผลมากที่สุด (TreeSHAP จาก LightGBM pred_contrib, หน่วย log ของจำนวนร้าน)

ตรวจ schema ด้วยโค้ดก่อนเขียนไฟล์ ถ้าไม่ตรงจะ error

รัน:
    python export.py                 # kmutt_bangmod
    python export.py kmutt_bangmod
"""
import argparse, json, sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from collect import CONFIG, PROCESSED, ROOT
from model import CATS, FEATURES, load_dataset, make_model, xy

WEB = ROOT.parent / "web" / "public"
GROWTH_WEIGHT = 0.5
SHAP_TOP = 4
FLAGS = {"ok", "duplicate", "false_positive", "industrial_print", "on_campus", "needs_check", "unnamed_building"}
POI_CATS = CATS + ["dorm_like"]

FEATURE_LABELS = {
    "dorms_200m": "หอพักใกล้เคียง",
    "condo_200m": "คอนโดและอาคารที่พักใกล้เคียง",
    "dist_gate_m": "ระยะถึงมหาวิทยาลัย",
    "commerce_200m": "ร้านค้าอื่นรอบ ๆ",
    "built_now": "ความหนาแน่นอาคาร (ดาวเทียม)",
    "built_change_2019_2025": "อาคารเพิ่มขึ้นตั้งแต่ปี 2019",
}
CATEGORY_META = {
    "cafe": {"label_th": "ร้านกาแฟ", "confidence": "high", "note_th": "รวมจาก Overture และ OpenStreetMap"},
    "food": {"label_th": "ร้านอาหาร", "confidence": "high", "note_th": "รวมจาก Overture และ OpenStreetMap"},
    "laundry": {"label_th": "ร้านซักผ้า", "confidence": "low", "note_th": "ข้อมูลน่าจะขาด ยังไม่ได้ตรวจภาคสนาม"},
    "print_stationery": {"label_th": "ร้านปริ้นต์และเครื่องเขียน", "confidence": "low", "note_th": "ข้อมูลน่าจะขาด ยังไม่ได้ตรวจภาคสนาม"},
}
FORMULA = "raw = (expected - actual) + 0.5 * growth * expected; opportunity = เปอร์เซ็นไทล์ของ raw ภายในมหาวิทยาลัย (0–100), ช่องในมหาวิทยาลัย = 0"


def score_category(train, target, cat):
    """expected, actual, growth, opportunity และ SHAP ของหมวด cat สำหรับทุกช่องของ target"""
    Xtr, ytr = xy(train, cat)
    model = make_model().fit(Xtr, ytr)
    Xte, actual = xy(target, cat)
    expected = model.predict(Xte)
    contrib = model.predict(Xte, pred_contrib=True)[:, :-1]   # คอลัมน์สุดท้ายคือ bias

    off = ~target.on_campus.to_numpy()
    ch = target.built_change_2019_2025.to_numpy()
    lo, hi = ch[off].min(), ch[off].max()
    growth = np.clip((ch - lo) / (hi - lo), 0, 1) if hi > lo else np.zeros(len(ch))

    raw = (expected - actual) + GROWTH_WEIGHT * growth * expected
    rank = pd.Series(raw[off]).rank(pct=True).to_numpy()
    opportunity = np.zeros(len(raw), dtype=int)
    opportunity[off] = np.round(rank * 100).astype(int)

    shap_rows = []
    for i in range(len(Xte)):
        order = np.argsort(-np.abs(contrib[i]))[:SHAP_TOP]
        shap_rows.append([{"feature": FEATURES[j], "label_th": FEATURE_LABELS[FEATURES[j]],
                           "value": round(float(Xte.iloc[i, j]), 3), "contribution": round(float(contrib[i, j]), 3)}
                          for j in order])
    return pd.DataFrame({"expected": expected, "actual": actual, "growth": growth, "raw": raw,
                         "opportunity": opportunity, "shap_top": shap_rows}, index=target.index)


def build_hexes(target, scores):
    years = sorted(int(c.split("_")[1]) for c in target.columns if c.startswith("built_") and c.split("_")[1].isdigit())
    rows = []
    for i, h in target.iterrows():
        rows.append({
            "h3": h.h3,
            "on_campus": bool(h.on_campus),
            "features": {"dorms_200m": int(h.dorms_200m), "built_now": round(float(h.built_now), 3),
                         "built_change_2019_2025": round(float(h.built_change_2019_2025), 3),
                         "dist_gate_m": int(h.dist_gate_m), "commerce_200m": int(h.commerce_200m)},
            "built_by_year": {str(y): round(float(h[f"built_{y}"]), 3) for y in years},
            "scores": {cat: {"opportunity": int(s.at[i, "opportunity"]), "expected": round(float(s.at[i, "expected"]), 2),
                             "actual": int(s.at[i, "actual"]), "growth": round(float(s.at[i, "growth"]), 3),
                             "shap_top": s.at[i, "shap_top"]}
                       for cat, s in scores.items()},
        })
    return rows


def build_meta(uni, sat_years):
    ev = json.loads((PROCESSED / "evaluation.json").read_text(encoding="utf-8"))
    per_cat, baselines_used = {}, {}
    for cat in CATS:
        s = ev["per_category"][cat]["summary"]
        # เทียบกับ baseline ที่แข็งที่สุด (MAE ต่ำสุด) ของหมวดนั้น
        name = min(["baseline_mean", "baseline_poisson"], key=lambda b: s[f"mae_{b}"])
        per_cat[cat] = {"mae_model": s["mae_model"], "mae_baseline": s[f"mae_{name}"], "n_universities": s["n_universities"]}
        baselines_used[cat] = name
    return {
        "uni_id": uni["uni_id"],
        "name_th": uni["name_th"],
        "center": [uni["lat"], uni["lon"]],
        "radius_m": uni["radius_m"],
        "h3_res": 10,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": CATEGORY_META,
        "evaluation": {"method": ev["method"], "per_category": per_cat},
        "sat_years": sat_years,
        "scoring": {"formula": FORMULA, "growth_weight": GROWTH_WEIGHT,
                    "expected_from": "LightGBM เทรนด้วยมหาวิทยาลัยอื่นที่ไม่ใช่แห่งนี้",
                    "baseline": baselines_used, "shap_unit": "log ของจำนวนร้าน"},
    }


def build_pois(uid):
    pts = pd.read_parquet(PROCESSED / uid / "points.parquet")
    pts = pts[pts.category.isin(POI_CATS)]
    return [{"name": n or "", "category": c, "flag": f, "lat": round(float(a), 6), "lon": round(float(b), 6), "source": s}
            for n, c, f, a, b, s in zip(pts.name, pts.category, pts.flag, pts.lat, pts.lon, pts.source)]


# ---------------------------------------------------------------- ตรวจ schema

def check(cond, msg):
    if not cond:
        raise ValueError(f"schema ไม่ตรง: {msg}")


def validate(meta, hexes, pois):
    for k, t in [("uni_id", str), ("name_th", str), ("center", list), ("radius_m", int), ("h3_res", int),
                 ("generated_at", str), ("categories", dict), ("evaluation", dict), ("sat_years", list)]:
        check(isinstance(meta.get(k), t), f"meta.{k}")
    check(set(meta["categories"]) == set(CATS), "meta.categories")
    for c, m in meta["categories"].items():
        check(set(m) == {"label_th", "confidence", "note_th"} and m["confidence"] in ("high", "low"), f"meta.categories.{c}")
    check(meta["evaluation"]["method"] == "leave_one_university_out", "meta.evaluation.method")
    for c, e in meta["evaluation"]["per_category"].items():
        check(set(e) == {"mae_model", "mae_baseline", "n_universities"}, f"meta.evaluation.per_category.{c}")

    feat_keys = {"dorms_200m", "built_now", "built_change_2019_2025", "dist_gate_m", "commerce_200m"}
    seen = set()
    for h in hexes:
        check(set(h) == {"h3", "on_campus", "features", "built_by_year", "scores"}, f"hex keys {h.get('h3')}")
        check(h["h3"] not in seen, f"h3 ซ้ำ {h['h3']}")
        seen.add(h["h3"])
        check(isinstance(h["on_campus"], bool), "on_campus")
        check(set(h["features"]) == feat_keys, "features")
        check(all(str(y) in h["built_by_year"] for y in meta["sat_years"]), "built_by_year")
        check(set(h["scores"]) == set(CATS), "scores")
        for c, s in h["scores"].items():
            check(set(s) == {"opportunity", "expected", "actual", "growth", "shap_top"}, f"scores.{c}")
            check(isinstance(s["opportunity"], int) and 0 <= s["opportunity"] <= 100, f"opportunity {s['opportunity']}")
            check(not h["on_campus"] or s["opportunity"] == 0, "on_campus ต้องมี opportunity = 0")
            check(len(s["shap_top"]) <= SHAP_TOP, "shap_top เกิน 4")
            mags = [abs(x["contribution"]) for x in s["shap_top"]]
            check(mags == sorted(mags, reverse=True), "shap_top ไม่เรียงตาม contribution")
            for x in s["shap_top"]:
                check(set(x) == {"feature", "label_th", "value", "contribution"}, "shap_top item")
    for p in pois:
        check(set(p) == {"name", "category", "flag", "lat", "lon", "source"}, "poi keys")
        check(p["flag"] in FLAGS, f"poi flag {p['flag']}")


# ---------------------------------------------------------------- รัน

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 220)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uni_id", nargs="?", default="kmutt_bangmod")
    args = ap.parse_args()

    unis = {u["uni_id"]: u for u in yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]}
    uni = unis[args.uni_id]
    df = load_dataset()
    sat = pd.read_parquet(PROCESSED / uni["uni_id"] / "hex_satellite.parquet")
    target = df[df.uni_id == uni["uni_id"]].merge(sat.drop(columns=["built_now", "built_change_2019_2025"]), on="h3")
    target = target.reset_index(drop=True)
    train = df[(df.uni_id != uni["uni_id"]) & ~df.on_campus]
    print(f"{uni['uni_id']}: {len(target)} ช่อง, เทรนด้วย {train.uni_id.nunique()} มหาวิทยาลัยอื่น ({len(train)} ช่อง)")

    scores = {cat: score_category(train, target, cat) for cat in CATS}
    # ปีที่มีค่า built จาก Dynamic World (ภาพไทม์แลปส์บนเว็บอยู่แยกใน sat/<uni_id>/wayback.json)
    sat_years = sorted(int(c.split("_")[1]) for c in sat.columns if c.startswith("built_") and c.split("_")[1].isdigit())

    meta = build_meta(uni, sat_years)
    hexes = build_hexes(target, scores)
    pois = build_pois(uni["uni_id"])
    validate(meta, hexes, pois)

    out = WEB / "data" / uni["uni_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "hexes.json").write_text(json.dumps(hexes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "pois.json").write_text(json.dumps(pois, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for f in ["meta.json", "hexes.json", "pois.json"]:
        print(f"  {(out / f).relative_to(ROOT.parent)}: {(out / f).stat().st_size // 1024} KB")
    print(f"  ตรวจ schema ผ่าน: {len(hexes)} ช่อง, {len(pois)} จุด, sat_years {sat_years}")

    off = ~target.on_campus
    print("\nสรุปต่อหมวด (ช่องนอกมหาวิทยาลัย):")
    print(pd.DataFrame({cat: {"expected รวม": round(s.expected[off].sum()), "actual รวม": int(s.actual[off].sum()),
                              "ช่อง opportunity ≥ 90": int((s.opportunity >= 90).sum())}
                        for cat, s in scores.items()}).T.to_string())

    s = scores["cafe"]
    top = target[["h3", "lat", "lon"]].join(s[["opportunity", "expected", "actual", "growth", "raw"]])
    top = top[off].sort_values("raw", ascending=False).head(5)
    print("\nช่องคะแนนสูงสุด 5 อันดับ หมวด cafe:")
    for i, r in top.iterrows():
        why = ", ".join(f"{x['label_th']} {x['value']:g} ({x['contribution']:+.2f})" for x in s.at[i, "shap_top"])
        print(f"  {r.h3}  ({r.lat:.5f}, {r.lon:.5f})  คะแนน {r.opportunity}  รองรับ {r.expected:.1f} มีอยู่ {r.actual} "
              f"โต {r.growth:.2f}\n      เพราะ: {why}")
        print(f"      https://www.google.com/maps/@{r.lat:.5f},{r.lon:.5f},18z")


if __name__ == "__main__":
    main()
