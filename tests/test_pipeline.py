"""Pipeline and accepted-state boundary (Lab 7).

The gate policy is not under test here: a stand-in gate returns a fixed outcome, so
these tests only check what the pipeline does with each outcome.
"""

import hashlib
import json
import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bike_demand import pipeline

pytestmark = pytest.mark.pipeline

ROOT = Path(__file__).resolve().parents[1]
RECORDED_RF_MAE = 86.84685685591091


def digest_tree(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(folder)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def bootstrapped(tmp_path_factory):
    """One accepted baseline, trained once and copied for each test."""
    registry = tmp_path_factory.mktemp("template") / "registry"
    mp = pytest.MonkeyPatch()
    mp.chdir(ROOT)
    mp.setenv(pipeline.REGISTRY_ENV, str(registry))
    assert pipeline.cmd_bootstrap(SimpleNamespace()) == 0
    mp.undo()
    return registry


@pytest.fixture
def env(tmp_path, monkeypatch, bootstrapped):
    registry = tmp_path / "registry"
    shutil.copytree(bootstrapped, registry)
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv(pipeline.REGISTRY_ENV, str(registry))
    monkeypatch.setattr(pipeline, "DECISIONS", tmp_path / "decisions")
    monkeypatch.setattr(pipeline, "POLICY", tmp_path / "gate-policy.yaml")
    candidate = tmp_path / "small.yaml"
    candidate.write_text(
        yaml.safe_dump(
            {
                "data": pipeline.DATA,
                "features": list(pipeline.FEATURES),
                "model": {"n_estimators": 5, "max_depth": 6},
            }
        )
    )
    return SimpleNamespace(tmp=tmp_path, registry=registry, candidate=candidate)


def use_gate(monkeypatch, env, outcome):
    env_policy = pipeline.POLICY
    env_policy.write_text("stand-in: true\n")
    gate = types.ModuleType("bike_demand.gate")
    gate.decide = lambda policy, evidence, metadata: {
        "outcome": outcome,
        "reasons": [f"stand-in gate: {outcome}"],
    }
    monkeypatch.setitem(sys.modules, "bike_demand.gate", gate)


def run(env):
    return pipeline.cmd_run(SimpleNamespace(candidate=env.candidate))


def only_decision(env):
    (path,) = (env.tmp / "decisions").glob("*.json")
    return json.loads(path.read_text())


def test_bootstrap_reproduces_the_recorded_baseline(env):
    current = pipeline.read_current(env.registry)
    assert current["version"] == "baseline" and current["previous"] is None
    evidence = json.loads(
        (env.registry / "candidates/baseline/evidence.json").read_text()
    )
    assert evidence["candidate"]["validation_mae"] == pytest.approx(
        RECORDED_RF_MAE, abs=1e-9
    )
    assert evidence["validation_rows"] == 4358


def test_without_policy_the_outcome_is_blocked_and_nothing_changes(env):
    before = digest_tree(env.registry / "accepted")
    current = pipeline.read_current(env.registry)
    assert run(env) == pipeline.EXIT["blocked"]
    record = only_decision(env)
    assert record["outcome"] == "blocked"
    assert record["reasons"] == ["no committed gate policy"]
    assert pipeline.read_current(env.registry) == current
    assert digest_tree(env.registry / "accepted") == before


def test_rejection_preserves_the_accepted_state(env, monkeypatch):
    use_gate(monkeypatch, env, "reject")
    before = digest_tree(env.registry / "accepted")
    current = pipeline.read_current(env.registry)
    assert run(env) == pipeline.EXIT["reject"]
    record = only_decision(env)
    assert record["outcome"] == "reject"
    assert record["evidence"]["incumbent"]["version"] == "baseline"
    assert record["evidence"]["incumbent"]["validation_mae"] == pytest.approx(
        RECORDED_RF_MAE, abs=1e-9
    )
    assert pipeline.read_current(env.registry) == current
    assert digest_tree(env.registry / "accepted") == before
    with pytest.raises(ValueError, match="not accept"):
        pipeline.cmd_promote(SimpleNamespace(candidate_id=record["candidate_id"]))


def test_promotion_keeps_the_version_it_replaces_and_can_be_undone(env, monkeypatch):
    use_gate(monkeypatch, env, "accept")
    baseline = digest_tree(env.registry / "accepted/baseline")
    assert run(env) == pipeline.EXIT["accept"]
    candidate_id = only_decision(env)["candidate_id"]
    assert pipeline.cmd_promote(SimpleNamespace(candidate_id=candidate_id)) == 0
    current = pipeline.read_current(env.registry)
    assert (current["version"], current["previous"]) == (candidate_id, "baseline")
    assert digest_tree(env.registry / "accepted/baseline") == baseline
    assert pipeline.cmd_restore(SimpleNamespace(version="baseline")) == 0
    assert pipeline.read_current(env.registry)["version"] == "baseline"


def test_promotion_refused_if_the_incumbent_changed(env, monkeypatch):
    use_gate(monkeypatch, env, "accept")
    run(env)
    candidate_id = only_decision(env)["candidate_id"]
    current = pipeline.read_current(env.registry)
    pipeline.atomic_write_json(
        env.registry / "current.json", {**current, "switched_at": "later"}
    )
    with pytest.raises(ValueError, match="changed since this decision"):
        pipeline.cmd_promote(SimpleNamespace(candidate_id=candidate_id))


def test_tampered_accepted_model_fails_closed(env):
    with (env.registry / "accepted/baseline/model.joblib").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        pipeline.cmd_restore(SimpleNamespace(version="baseline"))
    assert run(env) == pipeline.EXIT["blocked"]
    assert only_decision(env)["evidence"]["incumbent"]["status"].startswith(
        "unavailable"
    )


def test_a_consistent_substitution_of_the_accepted_bundle_fails_closed(
    env, monkeypatch
):
    """Lab 7 challenge (#35): a rejected bundle copied over accepted/baseline, model and
    metadata together, must not be served, restored or used as the incumbent."""
    use_gate(monkeypatch, env, "reject")
    assert run(env) == pipeline.EXIT["reject"]
    rejected = env.registry / "candidates" / only_decision(env)["candidate_id"]
    for name in ("model.joblib", "metadata.json"):
        shutil.copy(rejected / name, env.registry / "accepted/baseline" / name)
    current = pipeline.read_current(env.registry)
    assert pipeline.cmd_status(SimpleNamespace()) == 1
    with pytest.raises(ValueError, match="differs from its committed record"):
        pipeline.cmd_restore(SimpleNamespace(version="baseline"))
    assert pipeline.read_current(env.registry) == current
    for path in (env.tmp / "decisions").glob("*.json"):
        path.unlink()
    run(env)  # the stand-in gate decides; what matters is what it was given
    incumbent = only_decision(env)["evidence"]["incumbent"]
    assert incumbent["status"].startswith("unavailable")
    assert "committed record" in incumbent["status"]


def test_status_fails_when_a_retained_version_is_not_usable(env):
    assert pipeline.cmd_status(SimpleNamespace()) == 0
    with (env.registry / "accepted/baseline/model.joblib").open("ab") as stream:
        stream.write(b"tampered")
    assert pipeline.cmd_status(SimpleNamespace()) == 1


def test_a_promoted_version_without_its_accept_record_fails_closed(env, monkeypatch):
    use_gate(monkeypatch, env, "accept")
    run(env)
    candidate_id = only_decision(env)["candidate_id"]
    assert pipeline.cmd_promote(SimpleNamespace(candidate_id=candidate_id)) == 0
    assert pipeline.cmd_status(SimpleNamespace()) == 0
    (env.tmp / "decisions" / f"{candidate_id}.json").unlink()
    with pytest.raises(ValueError, match="no decision record"):
        pipeline.cmd_restore(SimpleNamespace(version=candidate_id))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"data": "data/raw/other.csv"}, "data must stay"),
        ({"features": ["hr", "temp"]}, "features must stay"),
        ({"model": {"random_state": 7}}, "random_state must stay"),
        ({"model": {"criterion": "poisson"}}, "model settings limited"),
    ],
)
def test_candidates_vary_model_settings_only(tmp_path, change, message):
    config = {
        "data": pipeline.DATA,
        "features": list(pipeline.FEATURES),
        "model": {"n_estimators": 5},
        **change,
    }
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match=message):
        pipeline.load_candidate_config(path)


def test_bootstrap_refuses_bytes_other_than_the_expected_model(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv(pipeline.REGISTRY_ENV, str(tmp_path / "registry"))
    other = tmp_path / "expected-model.json"
    other.write_text(json.dumps({"model_sha256": "f" * 64}))
    monkeypatch.setattr(pipeline, "EXPECTED_MODEL", other)
    with pytest.raises(ValueError, match="nothing was registered"):
        pipeline.cmd_bootstrap(SimpleNamespace())
    assert pipeline.read_current(tmp_path / "registry") is None
    assert not (tmp_path / "registry/accepted/baseline").exists()


def test_output_files_do_not_make_the_tree_dirty(tmp_path, monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        return ""

    monkeypatch.setattr(pipeline, "git", fake_git)
    assert pipeline.code_tree_dirty() is False
    (args,) = calls
    assert ":(exclude)decisions" in args and ":(exclude)logs" in args
    monkeypatch.setattr(pipeline, "git", lambda *a: " M src/bike_demand/api.py")
    assert pipeline.code_tree_dirty() is True
    monkeypatch.setattr(pipeline, "git", lambda *a: "unavailable")
    assert pipeline.code_tree_dirty() is None


def test_a_gate_that_raises_is_recorded_as_blocked(env, monkeypatch):
    pipeline.POLICY.write_text("stand-in: true\n")
    gate = types.ModuleType("bike_demand.gate")

    def broken(policy, evidence, metadata):
        raise TypeError("boom")

    gate.decide = broken
    monkeypatch.setitem(sys.modules, "bike_demand.gate", gate)
    before = digest_tree(env.registry / "accepted")
    assert run(env) == pipeline.EXIT["blocked"]
    record = only_decision(env)
    assert record["outcome"] == "blocked"
    assert record["reasons"] == ["gate could not run: TypeError: boom"]
    assert digest_tree(env.registry / "accepted") == before
