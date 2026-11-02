import pandas as pd

from inventory.ingestion import ingest_batches


def test_late_revision_and_idempotency(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    historical = tmp_path / "train.csv"
    original = pd.DataFrame([{
        "date": "2017-08-11",
        "store_nbr": 1,
        "family": "AUTOMOTIVE",
        "sales": 10.0,
        "onpromotion": 0,
    }])
    original.to_csv(historical, index=False)

    revision = original.copy()
    revision["sales"] = 25.0
    revision.to_csv(
        inbox / "sales_2017-08-11_revision1_arrived_2017-08-13.csv",
        index=False,
    )

    before = tmp_path / "before.csv"
    after = tmp_path / "after.csv"
    repeat = tmp_path / "repeat.csv"

    ingest_batches(inbox, historical, "2017-08-12", before)
    ingest_batches(inbox, historical, "2017-08-13", after)
    ingest_batches(inbox, historical, "2017-08-13", repeat)

    assert pd.read_csv(before).loc[0, "sales"] == 10.0
    assert pd.read_csv(after).loc[0, "sales"] == 25.0
    assert after.read_bytes() == repeat.read_bytes()
