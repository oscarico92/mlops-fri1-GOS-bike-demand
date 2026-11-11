"""Single final evaluation of the release candidate on the held test rows (Week 5).

    BIKE_REGISTRY=/tmp/final-registry uv run --locked python -m bike_demand.pipeline bootstrap
    BIKE_REGISTRY=/tmp/final-registry uv run --locked python -m bike_demand.final_evaluation

The plan (configs/final-evaluation.yaml) is merged before the run. The script:
1. refuses if the record already exists, if the code tree or the plan is not committed, or if
   the accepted model, the data or the plan's release candidate do not match;
2. recomputes the validation MAE and stops if it differs from the plan, before any test label
   is read;
3. evaluates the test rows once and writes the record with an exclusive create, then prints it.

Nothing is printed about the test rows unless the record was written. Exit 0 done, 1 refused.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import mean_absolute_error

from bike_demand import pipeline
from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.train import compare_mean, select_features
from bike_demand.validate import FEATURES, load_data

PLAN = Path("configs/final-evaluation.yaml")
RECORD = Path("logs/week-05/final-evaluation.json")
COMMITTED = (PLAN, Path("src/bike_demand/final_evaluation.py"))


def evaluate(frame: pd.DataFrame, model, plan: dict) -> dict:
    """Validation check first; the test labels are only read if it reproduces."""
    partitions = split_data(frame)
    summary = partition_summary(partitions)
    train, validation, test = (partitions[n] for n in ("train", "validation", "test"))
    checks = plan["checks_before_test"]

    if len(validation) != checks["validation_rows"]:
        raise ValueError(
            f"validation has {len(validation)} rows, plan says {checks['validation_rows']}"
        )
    validation_mae = float(
        mean_absolute_error(
            validation["cnt"],
            model.predict(select_features(validation, list(FEATURES))),
        )
    )
    if abs(validation_mae - checks["validation_mae"]) > checks["tolerance"]:
        raise ValueError(
            f"validation MAE {validation_mae!r} does not reproduce the plan's "
            f"{checks['validation_mae']!r}: stopped before reading the test rows"
        )
    expected_test = plan["data"]["test"]
    if summary["test"] != {
        "rows": expected_test["rows"],
        "date_min": expected_test["date_min"],
        "date_max": expected_test["date_max"],
    }:
        raise ValueError(f"test partition {summary['test']} differs from the plan")

    # From here on the test labels are used, once.
    predictions = model.predict(select_features(test, list(FEATURES)))
    _, naive_test_mae = compare_mean(train["cnt"], test["cnt"])
    return {
        "validation_mae_recomputed": validation_mae,
        "test": {
            **summary["test"],
            "mae": float(mean_absolute_error(test["cnt"], predictions)),
            "naive_train_mean_mae": naive_test_mae,
            "predictions_finite": bool(np.isfinite(predictions).all()),
            "predictions_nonnegative": bool((predictions >= 0).all()),
        },
    }


def preconditions(plan: dict) -> list[str]:
    """Everything that must hold before the model is even loaded."""
    problems = []
    if RECORD.exists():
        problems.append(f"{RECORD} exists: the final evaluation already ran")
    dirty = pipeline.code_tree_dirty()
    if dirty is not False:
        problems.append(f"code tree not clean (dirty={dirty}): commit first")
    for path in COMMITTED:
        if pipeline.git("ls-files", "--", str(path)) in ("", "unavailable"):
            problems.append(f"{path} is not committed")
    current = pipeline.read_current(pipeline.registry_root())
    candidate = plan["release_candidate"]
    if not current or current.get("version") != candidate["version"]:
        problems.append(
            f"accepted version is {current and current.get('version')}, "
            f"plan says {candidate['version']}"
        )
    return problems


def main() -> int:
    plan = yaml.safe_load(PLAN.read_text())
    problems = preconditions(plan)
    if problems:
        print("final evaluation refused:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    try:
        snapshot = check_snapshot(Path("."))
        if snapshot["sha256"] != plan["data"]["sha256"]:
            raise ValueError("data snapshot differs from the plan")
        version = plan["release_candidate"]["version"]
        model, metadata = pipeline.load_accepted(pipeline.registry_root(), version)
        if metadata["model_sha256"] != plan["release_candidate"]["model_sha256"]:
            raise ValueError("accepted model differs from the plan's release candidate")
        result = evaluate(load_data(Path(plan["data"]["path"])), model, plan)
    except (OSError, ValueError, KeyError) as error:
        print(f"final evaluation stopped, nothing recorded: {error}", file=sys.stderr)
        return 1

    record = {
        "plan": str(PLAN),
        "plan_sha256": sha256(PLAN),
        "commit": pipeline.git("rev-parse", "HEAD"),
        "evaluated_at": pipeline.now(),
        "release_candidate": {
            "version": version,
            "model_sha256": metadata["model_sha256"],
        },
        "data_sha256": snapshot["sha256"],
        **result,
    }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("x") as stream:  # exclusive: a second run cannot overwrite it
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
