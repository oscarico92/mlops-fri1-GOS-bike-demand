"""Gate policy tests (Lab 7): accept, reject, blocked and integrity, with the committed policy."""

import copy
import json
import math
from pathlib import Path

import pytest
import yaml

from bike_demand.gate import decide
from bike_demand.validate import FEATURES

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "configs/gate-policy.yaml").read_text())
DATA_SHA = "e03de4ee4ef4dc376ac6e04bf829673c6269e8eba5c60fa121640fa2f829504f"
CANDIDATE_SHA = "a" * 64

# Same shape as bike_demand.pipeline.train_candidate produces (PR #23).
EVIDENCE = {
    "candidate_id": "test",
    "validation_rows": 4358,
    "validation_window": {
        "rows": 4358,
        "date_min": "2012-01-01",
        "date_max": "2012-06-30",
    },
    "metric": "MAE, rentals per hour, validation Jan-Jun 2012",
    "candidate": {
        "model_sha256": CANDIDATE_SHA,
        "validation_mae": 85.0,
        "predictions_finite": True,
        "predictions_nonnegative": True,
    },
    "naive_train_mean": {"validation_mae": 154.23179306864967},
    "incumbent": {
        "version": "baseline",
        "model_sha256": "d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07",
        "validation_mae": 86.84685685591091,
        "status": "evaluated",
    },
    "data_sha256": DATA_SHA,
}
METADATA = {
    "model_sha256": CANDIDATE_SHA,
    "features": list(FEATURES),
    "model_settings": {
        "n_estimators": 50,
        "max_depth": 12,
        "random_state": 42,
        "n_jobs": 1,
    },
    "data_sha256": DATA_SHA,
    "training_commit": "b" * 40,
    "working_tree_dirty": False,
}


def run(evidence_changes=(), metadata_changes=(), policy=None):
    evidence, metadata = copy.deepcopy(EVIDENCE), copy.deepcopy(METADATA)
    for change in evidence_changes:
        change(evidence)
    for change in metadata_changes:
        change(metadata)
    return decide(policy if policy is not None else POLICY, evidence, metadata)


def statuses(result):
    return {check["name"]: check["status"] for check in result["checks"]}


def named(result, name):
    return any(reason.startswith(name + ":") for reason in result["reasons"])


def test_accept_only_when_every_check_passes():
    result = run()
    assert result["outcome"] == "accept"
    assert set(statuses(result).values()) == {"pass"}
    families = {check["family"] for check in result["checks"]}
    assert families == {"quality", "operation", "integrity"}


def test_reject_quality_improvement_smaller_than_margin():
    # Better than the accepted model, but by less than 1 rental/hour.
    result = run([lambda e: e["candidate"].update(validation_mae=86.0)])
    assert result["outcome"] == "reject"
    assert named(result, "quality.vs_incumbent")
    assert not named(result, "quality.vs_naive_train_mean")


def test_reject_quality_worse_than_accepted_model():
    result = run([lambda e: e["candidate"].update(validation_mae=90.0)])
    assert result["outcome"] == "reject"
    assert statuses(result)["quality.vs_incumbent"] == "fail"


def test_reject_quality_not_better_than_train_mean():
    result = run(
        [
            lambda e: e["candidate"].update(validation_mae=153.5),
            lambda e: e["incumbent"].update(validation_mae=160.0),
        ]
    )
    assert result["outcome"] == "reject"
    assert statuses(result)["quality.vs_naive_train_mean"] == "fail"
    assert statuses(result)["quality.vs_incumbent"] == "pass"


@pytest.mark.parametrize("field", ["predictions_finite", "predictions_nonnegative"])
def test_reject_operation(field):
    result = run([lambda e: e["candidate"].update({field: False})])
    assert result["outcome"] == "reject"
    assert named(result, f"operation.{field}")


@pytest.mark.parametrize(
    "incumbent",
    [
        {"version": "baseline", "status": "unavailable: model checksum mismatch"},
        None,
    ],
    ids=["incumbent-unreadable", "no-incumbent"],
)
def test_blocked_without_an_evaluated_incumbent_even_with_a_great_mae(incumbent):
    result = run(
        [
            lambda e: e.update(incumbent=incumbent),
            lambda e: e["candidate"].update(validation_mae=40.0),
        ]
    )
    assert result["outcome"] == "blocked"
    assert named(result, "quality.vs_incumbent")
    assert statuses(result)["quality.vs_incumbent"] == "unavailable"


@pytest.mark.parametrize(
    ("label", "change"),
    [
        (
            "operation.predictions_finite",
            lambda e: e["candidate"].pop("predictions_finite"),
        ),
        (
            "operation.predictions_nonnegative",
            lambda e: e["candidate"].update(predictions_nonnegative="yes"),
        ),
        (
            "quality.vs_incumbent",
            lambda e: e["candidate"].update(validation_mae=math.nan),
        ),
        ("quality.vs_naive_train_mean", lambda e: e.pop("naive_train_mean")),
        ("integrity.validation_rows", lambda e: e.pop("validation_window")),
        ("integrity.data_sha256", lambda e: e.pop("data_sha256")),
    ],
)
def test_blocked_when_evidence_is_missing_or_invalid(label, change):
    result = run([change])
    assert result["outcome"] == "blocked"
    assert named(result, label)


def test_missing_evidence_wins_over_a_measured_failure():
    # Incomplete evaluation is reported as such, with the measured failure kept in reasons.
    result = run(
        [
            lambda e: e["candidate"].pop("predictions_finite"),
            lambda e: e["candidate"].update(validation_mae=95.0),
        ]
    )
    assert result["outcome"] == "blocked"
    assert named(result, "operation.predictions_finite")
    assert named(result, "quality.vs_incumbent")


@pytest.mark.parametrize(
    ("label", "evidence_change", "metadata_change"),
    [
        ("integrity.data_sha256", None, lambda m: m.update(data_sha256="c" * 64)),
        (
            "integrity.data_sha256",
            lambda e: e.update(data_sha256="c" * 64),
            lambda m: m.update(data_sha256="c" * 64),
        ),
        (
            "integrity.features",
            None,
            lambda m: m.update(features=list(reversed(FEATURES))),
        ),
        ("integrity.features", None, lambda m: m.update(features=list(FEATURES)[:-1])),
        ("integrity.validation_rows", lambda e: e.update(validation_rows=4357), None),
        (
            "integrity.validation_rows",
            lambda e: e["validation_window"].update(date_max="2012-06-29"),
            None,
        ),
        (
            "integrity.candidate_bytes",
            lambda e: e["candidate"].update(model_sha256="d" * 64),
            None,
        ),
    ],
)
def test_reject_integrity_mismatch(label, evidence_change, metadata_change):
    result = run(
        [evidence_change] if evidence_change else [],
        [metadata_change] if metadata_change else [],
    )
    assert result["outcome"] == "reject"
    assert named(result, label)


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m.update(working_tree_dirty=True),
        lambda m: m.update(working_tree_dirty=None),
        lambda m: m.update(training_commit="unavailable"),
    ],
    ids=["dirty-tree", "dirty-unknown", "no-commit"],
)
def test_blocked_when_bytes_cannot_be_tied_to_committed_code(change):
    result = run(metadata_changes=[change])
    assert result["outcome"] == "blocked"
    assert named(result, "integrity.provenance")


@pytest.mark.parametrize("section", ["quality", "operation", "integrity"])
def test_blocked_when_a_policy_section_is_missing(section):
    policy = {key: value for key, value in POLICY.items() if key != section}
    result = run(policy=policy)
    assert result["outcome"] == "blocked"
    assert any(reason.startswith(section + ".") for reason in result["reasons"])


def test_every_reason_names_its_check():
    result = run(
        [lambda e: e["candidate"].update(validation_mae=90.0, predictions_finite=False)]
    )
    assert result["outcome"] == "reject"
    names = {check["name"] for check in result["checks"]}
    assert all(reason.split(":")[0] in names for reason in result["reasons"])


def test_policy_matches_the_project_contract():
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    metrics = json.loads((ROOT / "reports/metrics.json").read_text())
    validation = metrics["partitions"]["validation"]
    integrity = POLICY["integrity"]
    assert integrity["data_sha256"] == manifest["sha256"]
    assert integrity["features"] == list(FEATURES)
    assert integrity["validation"] == {
        "rows": validation["rows"],
        "date_min": validation["date_min"],
        "date_max": validation["date_max"],
    }
    assert POLICY["quality"]["margin_rentals_per_hour"] == 1.0
