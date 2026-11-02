"""Airflow 3 daily orchestration; business logic stays in inventory modules."""
from datetime import datetime, timedelta
from pathlib import Path
import os
import sys

sys.path.insert(0, os.environ.get("INVENTORY_SRC", "/opt/inventory/src"))
from airflow.sdk import dag, task, get_current_context

BASE = Path(os.environ.get("INVENTORY_ROOT", "/opt/inventory"))

@dag(dag_id="inventory_daily", start_date=datetime(2017, 7, 1), schedule="@daily", catchup=False, max_active_runs=1, tags=["inventory", "reproducibility"])
def inventory_daily():
    @task(retries=2, retry_delay=timedelta(minutes=2))
    def ingest_validate():
        from inventory.ingestion import ingest_batches, materialize_auxiliary
        from inventory.core import read_sales
        date = get_current_context()["logical_date"].strftime("%Y-%m-%d")
        raw = BASE / "data" / "snapshots" / f"cutoff={date}"
        raw.mkdir(parents=True, exist_ok=True)
        n = ingest_batches(BASE / "source_inbox", BASE / "data/raw/train.csv", date, raw / "train.csv")
        materialize_auxiliary(BASE / "source_inbox", BASE / "data/raw", date, raw)
        read_sales(raw, date)
        return str(raw)

    @task()
    def prepare(raw):
        from inventory.core import load_asof
        date = get_current_context()["logical_date"].strftime("%Y-%m-%d")
        sales, stores = load_asof(raw, date)
        if len(sales) < 1 or len(stores) < 1:
            raise ValueError("Missing historical data")
        return raw

    @task()
    def train_and_publish(raw):
        from inventory.core import evaluate_and_fit, publish
        date = get_current_context()["logical_date"].strftime("%Y-%m-%d")
        directory = BASE / "models" / f"cutoff={date}"
        package, metrics = evaluate_and_fit(raw, date, output=directory)
        dest = BASE / "data/published" / f"cutoff={date}" / "forecast.csv"
        publish(raw, date, package, dest=dest)
        return str(dest)

    @task()
    def monitor_previous(publication):
        from inventory.core import monitor
        raw = BASE / "data/raw"
        output = BASE / "reports" / (Path(publication).parent.name + ".json")
        return monitor(publication, raw, output)

    monitor_previous(train_and_publish(prepare(ingest_validate())))

inventory_daily()
