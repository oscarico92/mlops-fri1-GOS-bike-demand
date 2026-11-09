"""Measure how much small model-setting changes move the validation MAE (Lab 6).

The README tolerance for the regression tests (1e-9) and the Lab 7 gate margin quote these
numbers; this script is how they were measured, so anyone can rerun it:

    uv run --locked python scripts/measure_tolerance.py

It refits the Lab 2 model on the frozen train partition with one setting changed at a time
and prints the validation MAE and its difference from the recorded value. It writes
nothing: no model, no metrics file, no MLflow run.
"""

import json
import platform
import subprocess
import sys
from pathlib import Path

import sklearn

from bike_demand.split import split_data
from bike_demand.train import fit_evaluate, load_config
from bike_demand.validate import load_data

ROOT = Path(__file__).resolve().parents[1]
RECORDED = json.loads((ROOT / "tests/fixtures/recorded-baseline.json").read_text())
REFERENCE = RECORDED["validation_mae"]["random_forest"]

VARIANTS = [
    ("baseline (recorded settings)", {}),
    ("random_state 42 -> 43", {"random_state": 43}),
    ("n_estimators 50 -> 49", {"n_estimators": 49}),
    ("max_depth 10 -> 11", {"max_depth": 11}),
    ("max_depth 10 -> 9", {"max_depth": 9}),
]


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> int:
    print(f"commit       {git('rev-parse', 'HEAD')}")
    print(f"dirty        {bool(git('status', '--porcelain'))}")
    print(f"platform     {platform.platform()} {platform.machine()}")
    print(f"python       {sys.version.split()[0]}  scikit-learn {sklearn.__version__}")
    print("command      uv run --locked python scripts/measure_tolerance.py")
    print(f"reference    recorded RF validation MAE {REFERENCE!r}")
    print()
    partitions = split_data(load_data(ROOT / "data/raw/hour.csv"))
    base = load_config(ROOT / "configs/baseline.yaml")
    for name, change in VARIANTS:
        config = {**base, "model": {**base["model"], **change}}
        _, _, mae = fit_evaluate(partitions["train"], partitions["validation"], config)
        print(f"{name:30s} mae={mae!r:22s} delta={mae - REFERENCE:+.3e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
