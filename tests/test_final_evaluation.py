"""Week 5 final evaluation: guards and plan consistency.

These tests never read the real test labels: the evaluation is exercised on a synthetic
frame, and the real data is only used to count rows (allowed in Weeks 1-4).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from bike_demand import final_evaluation as fe
from bike_demand import pipeline
from bike_demand.split import split_data
from bike_demand.validate import FEATURES, load_data

pytestmark = pytest.mark.final

ROOT = Path(__file__).resolve().parents[1]


def plan():
    return yaml.safe_load((ROOT / fe.PLAN).read_text())


def synthetic_frame():
    """One row per day, 2011-2012, values inside the contract ranges."""
    days = pd.date_range("2011-01-01", "2012-12-31", freq="D")
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        {
            "instant": np.arange(1, len(days) + 1),
            "dteday": days,
            "season": 1,
            "yr": (days.year == 2012).astype(int),
            "mnth": days.month,
            "hr": 0,
            "holiday": 0,
            "weekday": days.weekday,
            "workingday": 1,
            "weathersit": 1,
            "temp": 0.5,
            "atemp": 0.5,
            "hum": 0.5,
            "windspeed": 0.2,
            "casual": 0,
            "registered": 0,
        }
    )
    frame["cnt"] = rng.integers(0, 500, len(days))
    return frame


class Constant:
    """A model that predicts 100 everywhere and counts its calls."""

    def __init__(self):
        self.calls = []

    def predict(self, features):
        assert list(features.columns) == list(FEATURES)
        self.calls.append(len(features))
        return np.full(len(features), 100.0)


def synthetic_plan(frame, model_mae=None):
    parts = split_data(frame)
    validation, test = parts["validation"], parts["test"]
    mae = float((validation["cnt"] - 100.0).abs().mean())
    return {
        "checks_before_test": {
            "validation_rows": len(validation),
            "validation_mae": mae if model_mae is None else model_mae,
            "tolerance": 1e-9,
        },
        "data": {
            "test": {
                "rows": len(test),
                "date_min": "2012-07-01",
                "date_max": "2012-12-31",
            }
        },
    }


def test_evaluation_reports_the_declared_numbers():
    frame, model = synthetic_frame(), Constant()
    result = fe.evaluate(frame, model, synthetic_plan(frame))
    test = split_data(frame)["test"]
    assert result["test"]["rows"] == len(test)
    assert result["test"]["mae"] == pytest.approx((test["cnt"] - 100.0).abs().mean())
    assert (
        result["test"]["predictions_finite"]
        and result["test"]["predictions_nonnegative"]
    )
    assert set(result["test"]) == {
        "rows",
        "date_min",
        "date_max",
        "mae",
        "naive_train_mean_mae",
        "predictions_finite",
        "predictions_nonnegative",
    }


def test_a_validation_mismatch_stops_before_the_test_rows():
    frame, model = synthetic_frame(), Constant()
    with pytest.raises(ValueError, match="stopped before using the test rows"):
        fe.evaluate(frame, model, synthetic_plan(frame, model_mae=1.0))
    assert len(model.calls) == 1  # validation only, never the test rows


def test_a_different_test_window_is_refused():
    frame = synthetic_frame()
    wrong = synthetic_plan(frame)
    wrong["data"]["test"]["rows"] += 1
    with pytest.raises(ValueError, match="test partition"):
        fe.evaluate(frame, Constant(), wrong)


def test_preconditions_refuse_a_second_run_and_a_dirty_tree(tmp_path, monkeypatch):
    record = tmp_path / "final-evaluation.json"
    record.write_text("{}")
    monkeypatch.setattr(fe, "RECORD", record)
    monkeypatch.setattr(pipeline, "code_tree_dirty", lambda: True)
    monkeypatch.setattr(pipeline, "read_current", lambda root: {"version": "other"})
    problems = fe.preconditions(plan())
    assert any("already ran" in p for p in problems)
    assert any("not clean" in p for p in problems)
    assert any("plan says baseline" in p for p in problems)


def test_main_never_overwrites_an_existing_record(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    record = tmp_path / "final-evaluation.json"
    record.write_text('{"kept": true}')
    monkeypatch.setattr(fe, "RECORD", record)
    assert fe.main() == 1
    assert json.loads(record.read_text()) == {"kept": True}
    assert "already ran" in capsys.readouterr().err


def test_plan_matches_the_committed_references():
    """Model, data, validation MAE and row counts agree with earlier committed evidence."""
    p = plan()
    expected_model = json.loads((ROOT / "configs/expected-model.json").read_text())
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    recorded = json.loads((ROOT / "tests/fixtures/recorded-baseline.json").read_text())
    assert p["release_candidate"]["model_sha256"] == expected_model["model_sha256"]
    assert p["data"]["sha256"] == manifest["sha256"]
    assert p["checks_before_test"]["validation_mae"] == pytest.approx(
        recorded["validation_mae"]["random_forest"], abs=1e-9
    )
    assert p["data"]["test"] == recorded["partitions"]["test"]
    # Counting the held rows is allowed; their labels are not read here.
    parts = split_data(load_data(ROOT / p["data"]["path"]))
    assert len(parts["validation"]) == p["checks_before_test"]["validation_rows"]
    assert len(parts["test"]) == p["data"]["test"]["rows"]
    assert str(parts["test"]["dteday"].min().date()) == p["data"]["test"]["date_min"]
    assert str(parts["test"]["dteday"].max().date()) == p["data"]["test"]["date_max"]


def test_preconditions_read_origin_main(monkeypatch):
    """A record already on origin/main, or a HEAD outside main, is refused."""

    def fake_git(*args):
        if args[0] == "cat-file":
            return ""  # the record exists on origin/main
        if args[0] == "merge-base":
            return "unavailable"  # HEAD is not an ancestor of origin/main
        return "tracked"

    monkeypatch.setattr(pipeline, "git", fake_git)
    monkeypatch.setattr(pipeline, "code_tree_dirty", lambda: False)
    monkeypatch.setattr(pipeline, "read_current", lambda root: {"version": "baseline"})
    problems = fe.preconditions(plan())
    assert any("already on origin/main" in p for p in problems)
    assert any("not on origin/main" in p for p in problems)
