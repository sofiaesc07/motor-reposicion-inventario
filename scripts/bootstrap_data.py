"""Extract only permitted Kaggle training sources from local ZIP."""
import argparse
import zipfile
from pathlib import Path

NEEDED = {"train.csv", "stores.csv", "holidays_events.csv", "oil.csv", "transactions.csv"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zipfile", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    with zipfile.ZipFile(args.zipfile) as archive:
        available = set(archive.namelist())
        if not NEEDED <= available:
            raise ValueError(f"Missing {NEEDED - available}")
        args.output.mkdir(parents=True, exist_ok=True)
        for name in sorted(NEEDED):
            path = args.output / name
            with archive.open(name) as source, path.open("wb") as destination:
                import shutil
                shutil.copyfileobj(source, destination)
            print(path)

if __name__ == "__main__":
    main()
