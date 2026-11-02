"""CLI entry point invoked by operators and orchestrators."""
import argparse
import json
from pathlib import Path
import joblib
from inventory.core import ROOT, evaluate_and_fit, publish, monitor, read_sales, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["validate", "train", "publish", "monitor"])
    parser.add_argument("--asof", default=None)
    parser.add_argument("--raw", default=str(ROOT / "data/raw"))
    parser.add_argument("--model", default=str(ROOT / "models/model.joblib"))
    parser.add_argument("--publication", default=None)
    args = parser.parse_args()
    if args.action == "validate":
        sales = read_sales(args.raw, args.asof)
        print(json.dumps({"rows": len(sales), "max_date": str(sales.date.max().date())}))
    elif args.action == "train":
        cutoff = args.asof or str(read_sales(args.raw).date.max().date())
        _, metrics = evaluate_and_fit(args.raw, cutoff, output=ROOT / "models")
        print(json.dumps(metrics, indent=2))
    elif args.action == "publish":
        cutoff = args.asof or str(read_sales(args.raw).date.max().date())
        package = joblib.load(args.model)
        if package["trained_asof"] > cutoff:
            raise ValueError("Model was trained on data after forecast cutoff")
        destination = ROOT / f"data/published/cutoff={cutoff}/forecast.csv"
        result = publish(args.raw, cutoff, package, dest=destination)
        print(f"Published {len(result)} forecasts: {destination}")
    else:
        if not args.publication:
            raise ValueError("--publication is mandatory for monitoring")
        output = ROOT / "reports" / (Path(args.publication).parent.name + ".json")
        print(json.dumps(monitor(args.publication, args.raw, output), indent=2))


if __name__ == "__main__":
    main()
