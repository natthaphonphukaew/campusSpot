"""โมเดลทำนาย "จำนวนร้านที่ย่านนี้น่าจะรองรับได้" ต่อช่อง H3 และการประเมินผลแบบ leave-one-university-out

แยกโมเดลต่อหมวด (cafe, food, laundry, print_stationery)
    y = actual_<cat>_200m
    X = dorms_200m, condo_200m, dist_gate_m, commerce_ex_<cat>_200m (เรียกว่า commerce_200m ในตาราง),
        built_now, built_change_2019_2025
ตัดช่อง on_campus ออกทั้งตอนเทรนและทดสอบ

เทียบกับ baseline:
    baseline_mean     ค่าเฉลี่ย y ของมหาวิทยาลัยอื่น (ทายเท่ากันทุกช่อง)
    baseline_poisson  Poisson regression ที่ใช้แค่ dorms_200m
โมเดลหลัก: LightGBM objective=poisson ไฮเปอร์พารามิเตอร์ค่าคงที่ด้านล่าง (ไม่ tune บนชุดทดสอบ)

ประเมิน: วนเอาแต่ละมหาวิทยาลัยเป็นชุดทดสอบ เทรนด้วยที่เหลือ รายงาน MAE และ Spearman ต่อหมวด
ผล: data/processed/evaluation.json (ห้ามแก้ตัวเลขด้วยมือ meta.json.evaluation ต้องมาจากไฟล์นี้)

รัน:
    python model.py
"""
import json, sys
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr
from sklearn.linear_model import PoissonRegressor

from collect import CONFIG, PROCESSED, ROOT

CATS = ["cafe", "food", "laundry", "print_stationery"]
FEATURES = ["dorms_200m", "condo_200m", "dist_gate_m", "commerce_200m", "built_now", "built_change_2019_2025"]
LGB_PARAMS = dict(objective="poisson", n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=42, verbose=-1)
METHODS = ["model", "baseline_mean", "baseline_poisson"]


def load_dataset():
    """ช่องนอกมหาวิทยาลัยของทุกแห่ง พร้อมฟีเจอร์จาก features.py และ satellite.py"""
    unis = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["universities"]
    frames = []
    for u in unis:
        d = PROCESSED / u["uni_id"]
        hx = pd.read_parquet(d / "hex_features.parquet")
        sat = pd.read_parquet(d / "hex_satellite.parquet")[["h3", "built_now", "built_change_2019_2025"]]
        frames.append(hx.merge(sat, on="h3", how="left"))
    df = pd.concat(frames, ignore_index=True)
    missing = df[["built_now", "built_change_2019_2025"]].isna().any(axis=1).sum()
    if missing:
        raise ValueError(f"มี {missing} ช่องที่ไม่มีค่าดาวเทียม ให้รัน satellite.py ก่อน")
    return df


def xy(df, cat):
    """X ของหมวด cat: commerce_200m ใช้ค่าที่ไม่นับหมวดนั้น (กันข้อมูลรั่ว)"""
    X = df[["dorms_200m", "condo_200m", "dist_gate_m", f"commerce_ex_{cat}_200m", "built_now", "built_change_2019_2025"]]
    X = X.rename(columns={f"commerce_ex_{cat}_200m": "commerce_200m"})[FEATURES]
    return X, df[f"actual_{cat}_200m"].to_numpy()


def make_model():
    return lgb.LGBMRegressor(**LGB_PARAMS)


def predict_all(train, test, cat):
    Xtr, ytr = xy(train, cat)
    Xte, _ = xy(test, cat)
    model = make_model().fit(Xtr, ytr)
    pois = PoissonRegressor(alpha=0, max_iter=1000).fit(Xtr[["dorms_200m"]], ytr)
    return {
        "model": model.predict(Xte),
        "baseline_mean": np.full(len(Xte), ytr.mean()),
        "baseline_poisson": pois.predict(Xte[["dorms_200m"]]),
    }


def spearman(pred, y):
    # ทายค่าคงที่ (baseline_mean) หรือค่าจริงเหมือนกันหมด → ไม่มีความหมาย คืน None
    if np.ptp(np.round(pred, 9)) == 0 or np.ptp(y) == 0:
        return None
    s = spearmanr(pred, y).statistic
    return None if np.isnan(s) else float(s)


def evaluate(df):
    off = df[~df.on_campus].reset_index(drop=True)
    unis = list(dict.fromkeys(off.uni_id))
    result = {}
    for cat in CATS:
        folds = []
        for test_uni in unis:
            train, test = off[off.uni_id != test_uni], off[off.uni_id == test_uni]
            preds = predict_all(train, test, cat)
            y = test[f"actual_{cat}_200m"].to_numpy()
            fold = {"test_uni": test_uni, "n_hexes": len(test), "y_mean": round(float(y.mean()), 3)}
            for m in METHODS:
                fold[f"mae_{m}"] = round(float(np.abs(preds[m] - y).mean()), 4)
                s = spearman(preds[m], y)
                fold[f"spearman_{m}"] = round(s, 4) if s is not None else None
            folds.append(fold)
        f = pd.DataFrame(folds)
        summary = {"n_universities": len(unis), "n_hexes": int(f.n_hexes.sum())}
        for m in METHODS:
            summary[f"mae_{m}"] = round(float(f[f"mae_{m}"].mean()), 4)
            sp = f[f"spearman_{m}"].dropna()
            summary[f"spearman_{m}"] = round(float(sp.mean()), 4) if len(sp) else None
        summary["model_beats_mean_mae"] = int((f.mae_model < f.mae_baseline_mean).sum())
        summary["model_beats_poisson_mae"] = int((f.mae_model < f.mae_baseline_poisson).sum())
        result[cat] = {"summary": summary, "folds": folds}
    return result


def print_report(result):
    rows = []
    for cat, r in result.items():
        s = r["summary"]
        rows.append({"หมวด": cat,
                     "MAE โมเดล": s["mae_model"], "MAE ค่าเฉลี่ย": s["mae_baseline_mean"], "MAE Poisson(หอพัก)": s["mae_baseline_poisson"],
                     "Spearman โมเดล": s["spearman_model"], "Spearman Poisson": s["spearman_baseline_poisson"],
                     "ชนะค่าเฉลี่ย": f"{s['model_beats_mean_mae']}/{s['n_universities']}",
                     "ชนะ Poisson": f"{s['model_beats_poisson_mae']}/{s['n_universities']}"})
    print("\n===== ผลประเมิน leave-one-university-out (เฉลี่ยข้าม 7 รอบ, MAE ต่ำดี, Spearman สูงดี) =====")
    print(pd.DataFrame(rows).to_string(index=False))
    for cat in ["cafe", "food"]:
        print(f"\n--- {cat} รายมหาวิทยาลัย (ชุดทดสอบ) ---")
        f = pd.DataFrame(result[cat]["folds"])
        print(f[["test_uni", "n_hexes", "y_mean", "mae_model", "mae_baseline_mean", "mae_baseline_poisson",
                 "spearman_model", "spearman_baseline_poisson"]].to_string(index=False))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 220)
    df = load_dataset()
    off = df[~df.on_campus]
    print(f"ข้อมูล: {len(df)} ช่อง จาก {df.uni_id.nunique()} มหาวิทยาลัย, ใช้ช่องนอกมหาวิทยาลัย {len(off)} ช่อง")
    result = evaluate(df)
    print_report(result)
    out = {
        "method": "leave_one_university_out",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": FEATURES,
        "lgb_params": LGB_PARAMS,
        "baselines": {"baseline_mean": "ค่าเฉลี่ยของมหาวิทยาลัยอื่น", "baseline_poisson": "Poisson regression ใช้แค่ dorms_200m"},
        "per_category": result,
    }
    path = PROCESSED / "evaluation.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nบันทึก:", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
