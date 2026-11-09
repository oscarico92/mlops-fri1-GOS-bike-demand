"""Regression tests: recompute the results we recorded, from the frozen data (Lab 6).

Each test names the defect it catches. scripts/regression_can_fail.py injects each
defect into a throwaway copy of the repository and shows that the test turns red.

Expected values come from tests/fixtures/recorded-baseline.json, written by hand from the
recorded runs; `train` never rewrites it (unlike reports/metrics.json), so a changed
result cannot silently become the new expectation.
"""

import json
from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient

from bike_demand import api
from bike_demand.preflight import sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.train import compare_mean, fit_evaluate, load_config
from bike_demand.validate import FEATURES, load_data

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
RECORDED = json.loads((ROOT / "tests/fixtures/recorded-baseline.json").read_text())
DATA = ROOT / "data/raw/hour.csv"
CONFIG = ROOT / "configs/baseline.yaml"

# Measured variation of the recorded values: identical to the last printed digit in
# every run we have (Lab 2 native Windows; Lab 3-5 containers on macOS arm64 and
# Windows x86_64; local runs on Linux). The tolerance only absorbs floating-point
# summation order, and is far below the smallest model change we measured (see
# README, "Regression tests (Lab 6)").
TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def partitions():
    return split_data(load_data(DATA))


@pytest.fixture(scope="module")
def fitted(partitions):
    model, _, mae = fit_evaluate(
        partitions["train"], partitions["validation"], load_config(CONFIG)
    )
    return model, mae


def test_frozen_data_is_the_recorded_snapshot():
    """Defect: the raw data file was edited or replaced."""
    assert sha256(DATA) == RECORDED["data_sha256"]


def test_partitions_match_the_recorded_split(partitions):
    """Defect: a partition window was moved (rows leak between train, validation, test)."""
    assert partition_summary(partitions) == RECORDED["partitions"]


def test_train_mean_comparator_recomputes(partitions):
    """Defect: the comparator is computed on validation labels instead of train labels."""
    mean, mae = compare_mean(
        partitions["train"]["cnt"], partitions["validation"]["cnt"]
    )
    assert mean == pytest.approx(RECORDED["train_mean"], abs=TOLERANCE)
    assert mae == pytest.approx(
        RECORDED["validation_mae"]["naive_train_mean"], abs=TOLERANCE
    )


def test_random_forest_validation_mae_recomputes(fitted):
    """Defect: a model setting changed without review (preset and config edited together)."""
    _, mae = fitted
    assert mae == pytest.approx(
        RECORDED["validation_mae"]["random_forest"], abs=TOLERANCE
    )


def test_served_prediction_for_the_reference_request(fitted, tmp_path, monkeypatch):
    """Defect: the API feeds the model something other than what it was trained on."""
    model, _ = fitted
    joblib.dump(model, tmp_path / "model.joblib")
    metadata = {
        "model_version": "baseline-regression",
        "model_sha256": sha256(tmp_path / "model.joblib"),
        "features": list(FEATURES),
    }
    (tmp_path / "model-metadata.json").write_text(json.dumps(metadata))
    monkeypatch.setenv(api.MODEL_DIR_ENV, str(tmp_path))
    request = RECORDED["reference_request"]
    with TestClient(api.app) as client:
        response = client.post("/predict", json=request)
    assert response.status_code == 200
    assert response.json()["prediction"] == pytest.approx(
        RECORDED["reference_prediction"], abs=TOLERANCE
    )
