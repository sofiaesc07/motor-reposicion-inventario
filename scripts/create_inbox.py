"""Build a deterministic, read-only, multi-source simulation from Kaggle files.

The filenames represent *arrival dates*, not necessarily observation dates.
A small number of late-arrival corrections are generated for sales.
"""
import argparse
from pathlib import Path
import pandas as pd

SOURCES = {'oil': 'oil.csv', 'transactions': 'transactions.csv',
           'holidays_events': 'holidays_events.csv'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='data/raw')
    ap.add_argument('--output', default='source_inbox')
    ap.add_argument('--days', type=int, default=35)
    args = ap.parse_args()
    raw, out = Path(args.raw), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(raw / 'train.csv', parse_dates=['date'])
    dates = sorted(pd.to_datetime(train.date.unique()))[-args.days:]
    if not dates:
        raise ValueError('No sales dates found')
    start, end = min(dates), max(dates)
    count = 0
    for date in dates:
        day = date.strftime('%Y-%m-%d')
        part = train.loc[train.date == date]
        target = out / f'sales_{day}.csv'
        if not target.exists():
            part.to_csv(target, index=False)
            count += 1
    # Non-sales sources arrive at different cadences: oil daily (business days),
    # transactions every 2 days, holidays weekly. Never alter the raw sources.
    for source, name in SOURCES.items():
        frame = pd.read_csv(raw / name, parse_dates=['date'])
        cadence = {'oil': 1, 'transactions': 2, 'holidays_events': 7}[source]
        for offset, arrival in enumerate(dates):
            if offset % cadence:
                continue
            last = min(arrival + pd.Timedelta(days=cadence - 1), end)
            selected = frame.loc[frame.date.between(arrival, last)]
            if selected.empty:
                continue
            target = out / f'{source}_{arrival:%Y-%m-%d}.csv'
            if not target.exists():
                selected.to_csv(target, index=False)
                count += 1
    # A revised version of one earlier sales file appears two days later.
    if len(dates) >= 5:
        original = dates[-5]
        arrival = dates[-3]
        part = train.loc[train.date == original].copy()
        target = out / f'sales_{original:%Y-%m-%d}_revision1_arrived_{arrival:%Y-%m-%d}.csv'
        if not target.exists():
            part.to_csv(target, index=False)
            count += 1
    print(f'Created {count} new source files in {out}; input data unchanged')


if __name__ == '__main__':
    main()
