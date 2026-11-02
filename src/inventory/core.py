"""Deterministic point-in-time inventory planning logic; no Airflow dependency."""
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[2]
KEYS = ["store_nbr", "family"]
FEATURES = ["store_nbr", "family_id", "dow", "month", "horizon", "lag7", "lag14", "rolling28", "trend", "city_id", "cluster", "last_promo"]


def settings(path=None):
    with open(path or ROOT / "config/params.yaml", encoding="utf-8") as file:
        return yaml.safe_load(file)


def atomic_csv(df, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, dest)


def atomic_json(obj, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, dest)


def read_sales(raw_dir, cutoff=None):
    """Read sales and never expose future observations past cutoff."""
    path = Path(raw_dir) / "train.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing sales source: {path}")
    df = pd.read_csv(path, parse_dates=["date"], dtype={"store_nbr": "int16", "family": "category", "sales": "float32", "onpromotion": "int16"})
    if df.duplicated(["date", *KEYS]).any():
        raise ValueError("Duplicate sales date/store/family keys")
    if df["sales"].isna().any() or (df["sales"] < 0).any():
        raise ValueError("Invalid sales: null or negative")
    if cutoff is not None:
        df = df.loc[df.date <= pd.Timestamp(cutoff)]
    return df.sort_values([*KEYS, "date"]).reset_index(drop=True)


def read_stores(raw_dir):
    p = Path(raw_dir) / "stores.csv"
    df = pd.read_csv(p)
    if df.store_nbr.duplicated().any():
        raise ValueError("Duplicate store metadata")
    df["city_id"] = pd.factorize(df.city, sort=True)[0]
    return df[["store_nbr", "city_id", "cluster"]]


def load_asof(raw_dir, cutoff):
    """Only historical source records available at logical cutoff are used."""
    sales = read_sales(raw_dir, cutoff)
    stores = read_stores(raw_dir)
    if sales.empty:
        raise ValueError("No sales available at cutoff")
    # Oil, transactions and holidays are optional to the forecast model.
    # The public Kaggle dataset does not expose publication timestamps, so using
    # their contemporaneous/future values would create unverifiable leakage.
    return sales, stores


def make_features(sales, stores, cutoff, horizon=7, min_history=35):
    """Create forecasts for dates strictly AFTER cutoff using only prior sales."""
    cutoff = pd.Timestamp(cutoff)
    historical = sales.loc[sales.date <= cutoff].copy()
    if historical.empty:
        raise ValueError("No data for historical features")
    recent = historical.loc[historical.date > cutoff - pd.Timedelta(days=28)]
    # Use explicit date offsets (not shifts, which fail with missing dates).
    base = historical[KEYS].drop_duplicates().reset_index(drop=True)
    counts = historical.groupby(KEYS, observed=True).size().rename("observed_days").reset_index()
    base = base.merge(counts, on=KEYS, how="left")
    for days, label in [(7, "lag7"), (14, "lag14")]:
        # The last observed matching weekday is from cutoff-(days-1).
        target = cutoff - pd.Timedelta(days=days - 1)
        vals = historical.loc[historical.date == target, KEYS + ["sales"]].rename(columns={"sales": label})
        base = base.merge(vals, on=KEYS, how="left")
    aggregate = recent.groupby(KEYS, observed=True).agg(rolling28=("sales", "mean"), last_promo=("onpromotion", "sum")).reset_index()
    early = recent.loc[recent.date <= cutoff - pd.Timedelta(days=14)].groupby(KEYS, observed=True).sales.mean().rename("first14").reset_index()
    late = recent.loc[recent.date > cutoff - pd.Timedelta(days=14)].groupby(KEYS, observed=True).sales.mean().rename("last14").reset_index()
    base = base.merge(aggregate, on=KEYS, how="left").merge(early, on=KEYS, how="left").merge(late, on=KEYS, how="left")
    base["trend"] = (base.last14 - base.first14).fillna(0)
    base = base.merge(stores, on="store_nbr", how="left")
    base["family"] = base.family.astype(str)
    # Alphabetical labels are stable across retraining and inference.
    replicated = pd.concat([base.assign(horizon=h) for h in range(1, horizon + 1)], ignore_index=True)
    replicated["target_date"] = cutoff + pd.to_timedelta(replicated.horizon, unit="D")
    replicated["dow"] = replicated.target_date.dt.dayofweek
    replicated["month"] = replicated.target_date.dt.month
    replicated["cutoff"] = cutoff
    for name in ["lag7", "lag14", "rolling28", "trend", "last_promo"]:
        replicated[name] = replicated[name].fillna(0).astype(float)
    replicated["baseline"] = (0.5 * replicated.lag7 + 0.25 * replicated.lag14 + 0.25 * replicated.rolling28).clip(lower=0)
    replicated["enough_history"] = replicated.observed_days >= min_history
    return replicated


def labeled_features(sales, stores, cutoff, horizon, min_history, vocabulary):
    rows = make_features(sales, stores, cutoff, horizon, min_history)
    future = sales.loc[(sales.date > pd.Timestamp(cutoff)) & (sales.date <= pd.Timestamp(cutoff) + pd.Timedelta(days=horizon)), KEYS + ["date", "sales"]]
    rows = rows.merge(future.rename(columns={"date": "target_date", "sales": "actual"}), on=[*KEYS, "target_date"], how="inner")
    return encode(rows, vocabulary)


def encode(rows, vocabulary):
    rows = rows.copy()
    rows["family_id"] = rows.family.map(vocabulary).fillna(-1).astype(int)
    for col in FEATURES:
        rows[col] = pd.to_numeric(rows[col], errors="coerce").fillna(0)
    return rows


def training_rows(sales, stores, cutoff, params):
    cutoff = pd.Timestamp(cutoff)
    horizon = params["horizon_days"]
    weeks = params["training_weeks"]
    first = sales.date.min() + pd.Timedelta(days=params["min_history_days"])
    final = cutoff - pd.Timedelta(days=horizon)
    cutoffs = pd.date_range(max(first, final - pd.Timedelta(weeks=weeks)), final, freq="7D")
    vocabulary = {f: i for i, f in enumerate(sorted(sales.family.astype(str).unique()))}
    frames = [labeled_features(sales, stores, dt, horizon, params["min_history_days"], vocabulary) for dt in cutoffs]
    if not frames:
        raise ValueError("Insufficient historical data to train")
    data = pd.concat(frames, ignore_index=True)
    data = data.loc[data.enough_history & data.actual.notna()]
    if data.empty:
        raise ValueError("No eligible training observations")
    if len(data) > params["max_training_rows"]:
        data = data.sample(n=params["max_training_rows"], random_state=params["seed"]).sort_values(["cutoff", "store_nbr", "family", "horizon"])
    return data, vocabulary


def train_models(data, config):
    models = {}
    for name, alpha in [("p10", 0.1), ("p50", 0.5), ("p90", 0.9)]:
        model = HistGradientBoostingRegressor(loss="quantile", quantile=alpha, random_state=config["seed"], **config["model"])
        model.fit(data[FEATURES], data.actual)
        models[name] = model
    return models


def predict_rows(rows, models, vocabulary, chosen="ml"):
    result = encode(rows, vocabulary)
    if chosen == "ml":
        for name in ["p10", "p50", "p90"]:
            result[name] = np.maximum(0, models[name].predict(result[FEATURES]))
        result[["p10", "p50", "p90"]] = np.sort(result[["p10", "p50", "p90"]].to_numpy(), axis=1)
        no_history = ~result.enough_history
        result.loc[no_history, ["p10", "p50", "p90"]] = np.repeat(result.loc[no_history, "baseline"].to_numpy()[:, None], 3, axis=1)
    else:
        result["p10"] = result.baseline * 0.7
        result["p50"] = result.baseline
        result["p90"] = result.baseline * 1.3
    return result


def quantile_order(rows, costs):
    """Newsvendor critical fractile: Cu/(Cu+Co), piecewise linear quantiles."""
    under = float(costs["stockout_cost"])
    over = float(costs["overstock_cost"])
    if under <= 0 or over <= 0:
        raise ValueError("Both business costs must be positive")
    q = under / (under + over)
    grid = np.array([0.1, 0.5, 0.9])
    levels = rows[["p10", "p50", "p90"]].to_numpy(float)
    # Outside modeled quantiles, clamp, never extrapolate without evidence.
    demand = np.array([np.interp(q, grid, line) for line in levels])
    inventory = float(costs.get("inventory_available", 0))
    if inventory < 0:
        raise ValueError("Available inventory must be nonnegative")
    return np.ceil(np.maximum(0, demand - inventory)).astype(int), q


def score(rows, predicted, costs):
    out = {"mae": float(mean_absolute_error(rows.actual, predicted.p50)), "n": int(len(rows))}
    orders, _ = quantile_order(predicted, costs)
    actual = rows.actual.to_numpy()
    out["business_cost"] = float((np.maximum(actual - orders, 0) * costs["stockout_cost"] + np.maximum(orders - actual, 0) * costs["overstock_cost"]).mean())
    out["pinball_p50"] = float(np.maximum(0.5 * (actual - predicted.p50), -0.5 * (actual - predicted.p50)).mean())
    return out


def evaluate_and_fit(raw_dir, cutoff, params=None, output=None):
    params = params or settings()
    cutoff = pd.Timestamp(cutoff)
    sales, stores = load_asof(raw_dir, cutoff)
    validation_days = params["validation_days"]
    split = cutoff - pd.Timedelta(days=validation_days)
    train_sales = sales.loc[sales.date <= split]
    train_data, vocabulary = training_rows(train_sales, stores, split, params)
    models_val = train_models(train_data, params)
    val_cutoffs = pd.date_range(split, cutoff - pd.Timedelta(days=params["horizon_days"]), freq="7D")
    val_frames = [labeled_features(sales, stores, dt, params["horizon_days"], params["min_history_days"], vocabulary) for dt in val_cutoffs]
    val = pd.concat(val_frames, ignore_index=True)
    val = val.loc[val.enough_history]
    if val.empty:
        raise ValueError("No validation observations")
    base = predict_rows(val, None, vocabulary, "baseline")
    ml = predict_rows(val, models_val, vocabulary, "ml")
    baseline_metrics = score(val, base, params["business"])
    ml_metrics = score(val, ml, params["business"])
    # Production selection must improve MAE and business cost, not cherry-pick one.
    chosen = "ml" if (ml_metrics["mae"] < baseline_metrics["mae"] and ml_metrics["business_cost"] < baseline_metrics["business_cost"]) else "baseline"
    final_training, vocabulary = training_rows(sales, stores, cutoff, params)
    final_models = train_models(final_training, params) if chosen == "ml" else {}
    package = {"models": final_models, "vocabulary": vocabulary, "selected": chosen, "trained_asof": str(cutoff.date())}
    metrics = {"asof": str(cutoff.date()), "baseline": baseline_metrics, "ml": ml_metrics, "selected": chosen, "training_rows": len(final_training), "validation_start": str(split.date())}
    if output:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        joblib.dump(package, output / "model.joblib")
        atomic_json(metrics, output / "model_metrics.json")
    return package, metrics


def publish(raw_dir, cutoff, package, params=None, dest=None):
    params = params or settings()
    sales, stores = load_asof(raw_dir, cutoff)
    rows = make_features(sales, stores, cutoff, params["horizon_days"], params["min_history_days"])
    preds = predict_rows(rows, package["models"], package["vocabulary"], package["selected"])
    orders, q = quantile_order(preds, params["business"])
    cols = ["cutoff", "target_date", "store_nbr", "family", "p10", "p50", "p90"]
    result = preds[cols].copy()
    result["suggested_order"] = orders
    result["critical_fractile"] = q
    result["model_type"] = package["selected"]
    if dest:
        atomic_csv(result, dest)
        manifest = {"cutoff": str(pd.Timestamp(cutoff).date()), "row_count": len(result), "model_type": package["selected"], "costs": params["business"], "source_sha256": hashlib.sha256((Path(raw_dir)/"train.csv").read_bytes()).hexdigest()}
        atomic_json(manifest, str(dest) + ".manifest.json")
    return result


def monitor(publication_file, raw_dir, dest):
    published = pd.read_csv(publication_file, parse_dates=["target_date"])
    actual = read_sales(raw_dir)[["date", *KEYS, "sales"]]
    matched = published.merge(actual, left_on=["target_date", *KEYS], right_on=["date", *KEYS], how="inner")
    result = {"publication": Path(publication_file).name, "matched": len(matched), "total": len(published), "mae": float(np.abs(matched.sales - matched.p50).mean()) if len(matched) else None, "coverage_10_90": float(((matched.sales >= matched.p10) & (matched.sales <= matched.p90)).mean()) if len(matched) else None}
    atomic_json(result, dest)
    return result
