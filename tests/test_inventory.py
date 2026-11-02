from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from inventory.core import make_features, quantile_order, predict_rows, read_sales
from inventory.ingestion import ingest_batches


def sample_data():
    dates = pd.date_range("2017-01-01", periods=65)
    sales = pd.DataFrame({"date": dates, "store_nbr": 1, "family": "A", "sales": range(65), "onpromotion": 0})
    stores = pd.DataFrame({"store_nbr": [1], "city_id": [0], "cluster": [1]})
    return sales, stores


def test_asof_prevents_future_leakage():
    sales, stores = sample_data()
    a = make_features(sales, stores, "2017-02-20", 7)
    sales.loc[sales.date > "2017-02-20", "sales"] = 999999
    b = make_features(sales, stores, "2017-02-20", 7)
    pd.testing.assert_frame_equal(a, b)


def test_horizon_and_all_dates():
    sales, stores = sample_data()
    df = make_features(sales, stores, "2017-02-20", 7)
    assert len(df) == 7
    assert df.target_date.min() == pd.Timestamp("2017-02-21")
    assert df.target_date.max() == pd.Timestamp("2017-02-27")


def test_cost_changes_order_without_code_changes():
    rows = pd.DataFrame({"p10": [4], "p50": [10], "p90": [20]})
    low, _ = quantile_order(rows, {"stockout_cost": 1, "overstock_cost": 5})
    high, _ = quantile_order(rows, {"stockout_cost": 5, "overstock_cost": 1})
    assert high[0] > low[0]


def test_idempotent_ingestion_and_revision(tmp_path):
    sales, _ = sample_data()
    historical = tmp_path / "historical.csv"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    output = tmp_path / "out.csv"
    sales.iloc[:40].to_csv(historical, index=False)
    batch = sales.loc[sales.date == "2017-02-09"].copy()
    batch.to_csv(inbox / "sales_2017-02-09.csv", index=False)
    first = ingest_batches(inbox, historical, "2017-02-09", output)
    content = output.read_bytes()
    second = ingest_batches(inbox, historical, "2017-02-09", output)
    assert first == second
    assert content == output.read_bytes()
    batch["sales"] = 500
    batch.to_csv(inbox / "sales_2017-02-09_revision1.csv", index=False)
    ingest_batches(inbox, historical, "2017-02-09", output)
    revised = pd.read_csv(output)
    assert revised.loc[revised.date == "2017-02-09", "sales"].iloc[0] == 500


def test_invalid_batch_stops_pipeline(tmp_path):
    sales, _ = sample_data()
    raw = tmp_path / "historical.csv"
    sales.iloc[:40].to_csv(raw, index=False)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    bad = sales.loc[sales.date == "2017-02-09"].copy()
    bad["sales"] = -1
    bad.to_csv(inbox / "sales_2017-02-09.csv", index=False)
    with pytest.raises(ValueError):
        ingest_batches(inbox, raw, "2017-02-09", tmp_path / "output.csv")
