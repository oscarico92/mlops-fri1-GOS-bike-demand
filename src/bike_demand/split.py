"""Chronological partitions; test targets are never evaluated in Week 1."""

import pandas as pd

WINDOWS = {
    "train": ("2011-01-01", "2011-12-31"),
    "validation": ("2012-01-01", "2012-06-30"),
    "test": ("2012-07-01", "2012-12-31"),
}


SORT_KEY = ["dteday", "hr", "instant"]


def split_data(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ordered = frame.sort_values(SORT_KEY, kind="mergesort")
    membership = pd.Series(0, index=ordered.index)
    partitions = {}
    for name, (start, end) in WINDOWS.items():
        # Inclusive intervals: a row dated `end` belongs to this partition.
        mask = ordered["dteday"].between(pd.Timestamp(start), pd.Timestamp(end))
        if not mask.any():
            raise ValueError(f"split: {name} partition must be nonempty")
        partitions[name] = ordered.loc[mask].copy()
        membership += mask.astype(int)
    if (membership > 1).any():
        raise ValueError("split: partitions must be disjoint")
    if (membership == 0).any():
        unassigned = ordered.loc[membership == 0, "instant"].tolist()
        raise ValueError(
            f"split: partitions must be complete; unassigned instant(s) {unassigned}"
        )
    return partitions


def partition_summary(partitions: dict[str, pd.DataFrame]) -> dict:
    return {
        name: {
            "rows": len(part),
            "date_min": str(part["dteday"].min().date()),
            "date_max": str(part["dteday"].max().date()),
        }
        for name, part in partitions.items()
    }
