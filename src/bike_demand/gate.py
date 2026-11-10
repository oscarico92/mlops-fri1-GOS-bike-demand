"""Quality gate for Lab 7: decide a candidate from its evidence and the committed policy.

    decide(policy, evidence, metadata) -> {"outcome", "reasons", "checks"}

`bike_demand.pipeline` collects the evidence and calls this function; the rule lives in
configs/gate-policy.yaml. Every check ends in one of three states:

- "pass": the evidence is present, valid and satisfies the rule;
- "fail": the evidence is present and valid and breaks the rule (a measured failure);
- "unavailable": the evidence is missing, invalid (NaN, wrong type) or cannot be
  attributed to the candidate (no commit, uncommitted changes).

Outcome: "blocked" if any check is unavailable, else "reject" if any check fails, else
"accept". An unavailable check is never a pass: a much better MAE does not make up for
missing evidence.
"""

import math
import re

PASS, FAIL, UNAVAILABLE = "pass", "fail", "unavailable"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


def _number(value) -> float | None:
    """A finite real number, or None (bool is not a number here)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _get(source, *path):
    for key in path:
        if not isinstance(source, dict) or key not in source:
            return None
        source = source[key]
    return source


def _check(family, name, status, rule, observed):
    return {
        "family": family,
        "name": f"{family}.{name}",
        "status": status,
        "rule": rule,
        "observed": observed,
    }


def _quality(policy, evidence) -> list[dict]:
    margin = _number(_get(policy, "quality", "margin_rentals_per_hour"))
    candidate = _number(_get(evidence, "candidate", "validation_mae"))
    checks = []
    references = {
        "vs_naive_train_mean": (
            _number(_get(evidence, "naive_train_mean", "validation_mae")),
            "train-mean baseline",
            None,
        ),
    }
    incumbent = _get(evidence, "incumbent")
    if not isinstance(incumbent, dict):
        references["vs_incumbent"] = (None, "accepted model", "no accepted model")
    elif incumbent.get("status") != "evaluated":
        references["vs_incumbent"] = (
            None,
            "accepted model",
            f"accepted model {incumbent.get('version')} {incumbent.get('status')}",
        )
    else:
        references["vs_incumbent"] = (
            _number(incumbent.get("validation_mae")),
            f"accepted model {incumbent.get('version')}",
            None,
        )
    for name, (reference, label, why_missing) in references.items():
        rule = f"candidate MAE <= {label} MAE - margin"
        observed = {
            "candidate_mae": candidate,
            "reference_mae": reference,
            "margin": margin,
        }
        if why_missing:
            checks.append(_check("quality", name, UNAVAILABLE, rule, why_missing))
        elif None in (candidate, reference, margin) or margin < 0:
            checks.append(_check("quality", name, UNAVAILABLE, rule, observed))
        else:
            ok = candidate <= reference - margin
            checks.append(_check("quality", name, PASS if ok else FAIL, rule, observed))
    return checks


def _operation(policy, evidence) -> list[dict]:
    checks = []
    for name in ("predictions_finite", "predictions_nonnegative"):
        required = _get(policy, "operation", name)
        observed = _get(evidence, "candidate", name)
        rule = f"{name} is true on every validation prediction"
        if required is not True or not isinstance(observed, bool):
            status = UNAVAILABLE
        else:
            status = PASS if observed else FAIL
        checks.append(_check("operation", name, status, rule, observed))
    return checks


def _integrity(policy, evidence, metadata) -> list[dict]:
    expected = _get(policy, "integrity") or {}
    checks = []

    data = (_get(evidence, "data_sha256"), _get(metadata, "data_sha256"))
    rule = "evidence and candidate data SHA-256 equal the frozen snapshot"
    if not isinstance(expected.get("data_sha256"), str) or not all(
        isinstance(v, str) and SHA256.fullmatch(v) for v in data
    ):
        status = UNAVAILABLE
    else:
        status = PASS if data[0] == data[1] == expected["data_sha256"] else FAIL
    checks.append(_check("integrity", "data_sha256", status, rule, list(data)))

    features = _get(metadata, "features")
    rule = "candidate trained on the 12 contract features, in order"
    if not isinstance(expected.get("features"), list) or not isinstance(features, list):
        status = UNAVAILABLE
    else:
        status = PASS if features == expected["features"] else FAIL
    checks.append(_check("integrity", "features", status, rule, features))

    window = _get(evidence, "validation_window")
    rows = _get(evidence, "validation_rows")
    wanted = expected.get("validation")
    observed = {"rows": rows, "window": window}
    rule = "evaluated on the validation rows of the contract"
    if (
        not isinstance(wanted, dict)
        or not isinstance(window, dict)
        or isinstance(rows, bool)
        or not isinstance(rows, int)
    ):
        status = UNAVAILABLE
    else:
        same = (
            rows == window.get("rows") == wanted.get("rows")
            and window.get("date_min") == wanted.get("date_min")
            and window.get("date_max") == wanted.get("date_max")
        )
        status = PASS if same else FAIL
    checks.append(_check("integrity", "validation_rows", status, rule, observed))

    sha = (_get(metadata, "model_sha256"), _get(evidence, "candidate", "model_sha256"))
    rule = "the evaluated bytes are the candidate's recorded bytes"
    if not all(isinstance(v, str) and SHA256.fullmatch(v) for v in sha):
        status = UNAVAILABLE
    else:
        status = PASS if sha[0] == sha[1] else FAIL
    checks.append(_check("integrity", "candidate_bytes", status, rule, list(sha)))

    commit = _get(metadata, "training_commit")
    dirty = _get(metadata, "working_tree_dirty")
    rule = "trained from a recorded commit with no uncommitted change"
    if expected.get("require_training_commit") is not True or (
        expected.get("require_clean_tree") is not True
    ):
        status = UNAVAILABLE
    elif (
        not (isinstance(commit, str) and COMMIT.fullmatch(commit)) or dirty is not False
    ):
        # Bytes that cannot be tied to committed code are unattributable, not a measured fail.
        status = UNAVAILABLE
    else:
        status = PASS
    checks.append(
        _check(
            "integrity",
            "provenance",
            status,
            rule,
            {"training_commit": commit, "working_tree_dirty": dirty},
        )
    )
    return checks


def decide(policy: dict, evidence: dict, metadata: dict) -> dict:
    checks = (
        _quality(policy, evidence)
        + _operation(policy, evidence)
        + _integrity(policy, evidence, metadata)
    )
    unavailable = [c for c in checks if c["status"] == UNAVAILABLE]
    failed = [c for c in checks if c["status"] == FAIL]
    if unavailable:
        outcome = "blocked"
    elif failed:
        outcome = "reject"
    else:
        outcome = "accept"
    reasons = [
        f"{c['name']}: {c['status']} ({c['rule']}; observed {c['observed']})"
        for c in unavailable + failed
    ] or ["all checks passed"]
    return {"outcome": outcome, "reasons": reasons, "checks": checks}
