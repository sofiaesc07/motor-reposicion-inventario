"""Read-only incoming batches, last-arrival-wins revisions, atomic snapshots."""
from pathlib import Path
import pandas as pd
from inventory.core import atomic_csv

REQUIRED = {"date", "store_nbr", "family", "sales", "onpromotion"}

def ingest_batches(inbox, historical, cutoff, destination):
    """Merge valid arrived batches without changing the source directory.

    A batch's filename encodes its observation date. Corrections use suffix
    _revisionN, with highest revision winning. A new batch is available only
    when its filename date is on/before the logical cutoff.
    """
    cutoff = pd.Timestamp(cutoff)
    incoming = []
    for file in sorted(Path(inbox).glob("sales_*.csv")):
        name = file.stem.replace("sales_", "")
        date_str = name.split("_revision")[0]
        observed_date = pd.to_datetime(date_str, errors="coerce")
        if pd.isna(observed_date):
            raise ValueError(f"Invalid batch name: {file.name}")
        if observed_date > cutoff:
            continue
        revision = 0
        if "_revision" in name:
            revised = name.split("_revision", 1)[1]
            revision = int(revised.split("_", 1)[0])
            if "_arrived_" in revised:
                arrival = pd.to_datetime(revised.split("_arrived_", 1)[1], errors="coerce")
                if pd.isna(arrival):
                    raise ValueError(f"Invalid revision arrival: {file.name}")
                if arrival > cutoff:
                    continue
        batch = pd.read_csv(file)
        if not REQUIRED.issubset(batch.columns):
            raise ValueError(f"Invalid source schema {file.name}")
        if batch.duplicated(["date", "store_nbr", "family"]).any() or batch.sales.isna().any() or (batch.sales < 0).any():
            raise ValueError(f"Invalid source records {file.name}")
        if not pd.to_datetime(batch.date).eq(observed_date).all():
            raise ValueError(f"Batch date mismatch in {file.name}")
        batch["_revision"] = revision
        incoming.append(batch)
    existing = pd.read_csv(historical)
    if not REQUIRED.issubset(existing.columns):
        raise ValueError("Invalid initial historic schema")
    existing = existing.loc[pd.to_datetime(existing.date) <= cutoff].copy()
    existing["_revision"] = -1
    merged = pd.concat([existing, *incoming], ignore_index=True)
    merged = merged.sort_values(["date", "store_nbr", "family", "_revision"])
    merged = merged.drop_duplicates(["date", "store_nbr", "family"], keep="last")
    atomic_csv(merged.drop(columns="_revision"), destination)
    return len(merged)


def materialize_auxiliary(inbox, raw_dir, cutoff, destination):
    """Freeze non-sales sources at the cutoff without modifying their inbox.

    Date-only source files have no historical publication times. The public
    initial snapshot is filtered to the cutoff; simulated arrivals are selected
    only when their arrival filename is at or before the cutoff.
    """
    cutoff = pd.Timestamp(cutoff)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("stores", "oil", "transactions", "holidays_events"):
        source = Path(raw_dir) / f"{name}.csv"
        base = pd.read_csv(source)
        if name == "stores":
            atomic_csv(base, destination / source.name)
            continue
        if "date" not in base:
            raise ValueError(f"Missing date in {source}")
        base = base.loc[pd.to_datetime(base.date, errors="coerce") <= cutoff].copy()
        incoming = []
        for path in sorted(Path(inbox).glob(f"{name}_*.csv")):
            arrival = pd.to_datetime(path.stem.removeprefix(f"{name}_"), errors="coerce")
            if pd.isna(arrival):
                raise ValueError(f"Invalid arrival date in {path.name}")
            if arrival > cutoff:
                continue
            chunk = pd.read_csv(path)
            if list(chunk.columns) != list(base.columns):
                raise ValueError(f"Schema mismatch in {path.name}")
            if not pd.to_datetime(chunk.date, errors="coerce").le(cutoff).all():
                continue
            incoming.append(chunk)
        if incoming:
            keys = {"oil": ["date"], "transactions": ["date", "store_nbr"],
                    "holidays_events": ["date", "type", "locale", "locale_name", "description"]}[name]
            base = pd.concat([base, *incoming], ignore_index=True).drop_duplicates(keys, keep="last")
        atomic_csv(base, destination / source.name)
