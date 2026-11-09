"""Training pipeline and accepted-model registry (Lab 7).

One entry point produces a decided candidate from declared inputs:

    python -m bike_demand.pipeline bootstrap                    # first accepted model
    python -m bike_demand.pipeline run --candidate configs/candidates/<name>.yaml
    python -m bike_demand.pipeline promote <candidate_id>       # reviewed, manual
    python -m bike_demand.pipeline status
    python -m bike_demand.pipeline restore <version>            # no retraining

Accepted-state boundary:
- a candidate only writes under registry/candidates/<id>/ (written to a temporary
  folder, renamed when complete, so an interrupted run leaves no half candidate);
- registry/accepted/<version>/ is never modified once written;
- registry/current.json names the serving version and the one it replaced; it is
  switched in one atomic rename, and only by `promote`, `bootstrap` or `restore`;
- every `run` writes a decision record under decisions/ (committed to Git).

The decision rule itself (the gate policy) is not defined here: `run` loads it from
configs/gate-policy.yaml and bike_demand.gate. If either is missing, the outcome is
"blocked": an unavailable check is never a passed check.

Exit codes for CI: 0 accept, 2 reject, 3 blocked, 1 error.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.metrics import mean_absolute_error

from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.train import compare_mean, fit_evaluate, select_features
from bike_demand.validate import FEATURES, load_data

REGISTRY_ENV = "BIKE_REGISTRY"
DEFAULT_REGISTRY = "registry"
DECISIONS = Path("decisions")
POLICY = Path("configs/gate-policy.yaml")
BASELINE_CONFIG = Path("configs/baseline.yaml")
EXPECTED_MODEL = Path("configs/expected-model.json")
DATA = "data/raw/hour.csv"

# Candidates vary model settings only; data, features and split stay the contract.
ALLOWED_MODEL_KEYS = {
    "n_estimators",
    "max_depth",
    "min_samples_leaf",
    "max_features",
    "random_state",
    "n_jobs",
}
FIXED_MODEL_SETTINGS = {"random_state": 42, "n_jobs": 1}

EXIT = {"accept": 0, "reject": 2, "blocked": 3}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def registry_root() -> Path:
    return Path(os.environ.get(REGISTRY_ENV, DEFAULT_REGISTRY))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def atomic_write_json(path: Path, value: dict) -> None:
    """Write next to the target, then rename: readers see the old or the new file."""
    tmp = path.with_name(path.name + ".tmp")
    write_json(tmp, value)
    os.replace(tmp, path)


def load_candidate_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or set(config) != {"data", "features", "model"}:
        raise ValueError("candidate: require data, features and model")
    if config["data"] != DATA:
        raise ValueError(f"candidate: data must stay {DATA}")
    if config["features"] != list(FEATURES):
        raise ValueError("candidate: features must stay the 12 contract predictors")
    model = config["model"]
    if not isinstance(model, dict) or not set(model) <= ALLOWED_MODEL_KEYS:
        raise ValueError(
            f"candidate: model settings limited to {sorted(ALLOWED_MODEL_KEYS)}"
        )
    for key, value in FIXED_MODEL_SETTINGS.items():
        if model.get(key, value) != value:
            raise ValueError(f"candidate: {key} must stay {value}")
    config["model"] = {**model, **FIXED_MODEL_SETTINGS}
    return config


# --- accepted state -------------------------------------------------------------


def read_current(root: Path) -> dict | None:
    path = root / "current.json"
    return json.loads(path.read_text()) if path.is_file() else None


def load_accepted(root: Path, version: str) -> tuple[object, dict]:
    """Load an accepted bundle; a checksum mismatch fails closed."""
    folder = root / "accepted" / version
    metadata = json.loads((folder / "metadata.json").read_text())
    if sha256(folder / "model.joblib") != metadata["model_sha256"]:
        raise ValueError(f"accepted {version}: model checksum mismatch")
    # Only trusted files written by this pipeline are loaded.
    return joblib.load(folder / "model.joblib"), metadata


def switch_current(root: Path, version: str, metadata: dict, reason: str) -> dict:
    previous = read_current(root)
    current = {
        "version": version,
        "model_sha256": metadata["model_sha256"],
        "previous": previous["version"] if previous else None,
        "switched_at": now(),
        "reason": reason,
    }
    atomic_write_json(root / "current.json", current)
    return current


def store_accepted(root: Path, version: str, source: Path) -> dict:
    target = root / "accepted" / version
    if target.exists():
        raise ValueError(
            f"accepted {version} already exists; accepted bundles are immutable"
        )
    staging = target.with_name(version + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(source, staging)
    metadata = json.loads((staging / "metadata.json").read_text())
    if sha256(staging / "model.joblib") != metadata["model_sha256"]:
        shutil.rmtree(staging)
        raise ValueError("candidate bytes changed since evaluation; not accepted")
    os.replace(staging, target)
    return metadata


# --- candidate ------------------------------------------------------------------


def train_candidate(root: Path, config: dict, candidate_id: str) -> dict:
    """Fit on train, evaluate candidate, naive and incumbent on the same validation rows."""
    frame = load_data(Path(config["data"]))
    snapshot = check_snapshot(Path("."))
    partitions = split_data(frame)
    train, validation = partitions["train"], partitions["validation"]
    # The test partition is counted, never evaluated.
    _, naive_mae = compare_mean(train["cnt"], validation["cnt"])
    model, predictions, candidate_mae = fit_evaluate(train, validation, config)

    staging = root / "candidates" / (candidate_id + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    joblib.dump(model, staging / "model.joblib")
    metadata = {
        "candidate_id": candidate_id,
        "model_version": f"candidate-{candidate_id}",
        "model_sha256": sha256(staging / "model.joblib"),
        "features": list(FEATURES),
        "model_settings": config["model"],
        "data_sha256": snapshot["sha256"],
        "training_commit": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "created_at": now(),
    }
    write_json(staging / "metadata.json", metadata)

    incumbent = None
    current = read_current(root)
    if current:
        try:
            accepted, accepted_meta = load_accepted(root, current["version"])
            accepted_predictions = accepted.predict(
                select_features(validation, list(FEATURES))
            )
            incumbent = {
                "version": current["version"],
                "model_sha256": accepted_meta["model_sha256"],
                "validation_mae": float(
                    mean_absolute_error(validation["cnt"], accepted_predictions)
                ),
                "status": "evaluated",
            }
        except (OSError, ValueError, KeyError) as error:
            incumbent = {
                "version": current["version"],
                "status": f"unavailable: {error}",
            }

    evidence = {
        "candidate_id": candidate_id,
        "validation_rows": len(validation),
        "validation_window": partition_summary(partitions)["validation"],
        "metric": "MAE, rentals per hour, validation Jan-Jun 2012",
        "candidate": {
            "model_sha256": metadata["model_sha256"],
            "validation_mae": candidate_mae,
            "predictions_finite": bool(np.isfinite(predictions).all()),
            "predictions_nonnegative": bool((predictions >= 0).all()),
        },
        "naive_train_mean": {"validation_mae": naive_mae},
        "incumbent": incumbent,
        "data_sha256": snapshot["sha256"],
    }
    write_json(staging / "evidence.json", evidence)
    final = root / "candidates" / candidate_id
    os.replace(staging, final)
    return {"metadata": metadata, "evidence": evidence, "path": final}


def decide(evidence: dict, metadata: dict) -> dict:
    """Ask the committed gate policy; missing policy or gate code means blocked."""
    policy_file = {
        "path": str(POLICY),
        "sha256": file_sha256(POLICY),
        "last_commit": git("log", "-1", "--format=%H %cI", "--", str(POLICY)) or None,
    }
    if policy_file["sha256"] is None:
        return {
            "outcome": "blocked",
            "reasons": ["no committed gate policy"],
            "policy": policy_file,
        }
    try:
        gate = import_module("bike_demand.gate")
    except ImportError:
        return {
            "outcome": "blocked",
            "reasons": ["gate code not available"],
            "policy": policy_file,
        }
    policy = yaml.safe_load(POLICY.read_text())
    result = gate.decide(policy, evidence, metadata)
    if result.get("outcome") not in EXIT:
        return {
            "outcome": "blocked",
            "reasons": ["gate returned no valid outcome"],
            "policy": policy_file,
        }
    return {**result, "policy": policy_file}


# --- commands -------------------------------------------------------------------


def cmd_run(args) -> int:
    root = registry_root()
    config = load_candidate_config(Path(args.candidate))
    candidate_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    )
    before = read_current(root)
    produced = train_candidate(root, config, candidate_id)
    decision = decide(produced["evidence"], produced["metadata"])
    record = {
        "candidate_id": candidate_id,
        "decided_at": now(),
        "candidate_config": str(args.candidate),
        "candidate": produced["metadata"],
        "evidence": produced["evidence"],
        "incumbent_at_decision": before,
        **decision,
    }
    write_json(DECISIONS / f"{candidate_id}.json", record)
    after = read_current(root)
    if after != before:
        raise RuntimeError("accepted state changed during run; this must never happen")
    print(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "outcome": record["outcome"],
                "reasons": record.get("reasons", []),
            },
            indent=2,
        )
    )
    print(f"decision record: {DECISIONS / (candidate_id + '.json')}")
    return EXIT[record["outcome"]]


def cmd_promote(args) -> int:
    root = registry_root()
    record = json.loads((DECISIONS / f"{args.candidate_id}.json").read_text())
    if record["outcome"] != "accept":
        raise ValueError(
            f"decision is {record['outcome']!r}, not accept; nothing promoted"
        )
    if read_current(root) != record["incumbent_at_decision"]:
        raise ValueError(
            "the accepted model changed since this decision; run the candidate again"
        )
    metadata = store_accepted(
        root, args.candidate_id, root / "candidates" / args.candidate_id
    )
    if metadata["model_sha256"] != record["candidate"]["model_sha256"]:
        raise ValueError("candidate bytes differ from the decided bytes")
    current = switch_current(
        root,
        args.candidate_id,
        metadata,
        f"promoted after {record['decided_at']} decision",
    )
    print(json.dumps(current, indent=2))
    return 0


def cmd_bootstrap(args) -> int:
    """Register the reviewed Lab 2 baseline as the first accepted version."""
    root = registry_root()
    if read_current(root):
        raise ValueError("an accepted model already exists; bootstrap only runs once")
    config = yaml.safe_load(BASELINE_CONFIG.read_text())
    produced = train_candidate(root, config, "baseline")
    # The baseline must be the same bytes the service and the Lab 5 check expect.
    # Native Windows produces other bytes (fd98ceaf...); refuse rather than register them.
    expected = json.loads(EXPECTED_MODEL.read_text())["model_sha256"]
    if produced["metadata"]["model_sha256"] != expected:
        shutil.rmtree(produced["path"], ignore_errors=True)
        raise ValueError(
            f"bootstrap produced model {produced['metadata']['model_sha256'][:12]}..., "
            f"expected {expected[:12]}... ({EXPECTED_MODEL}); run it in the image or on "
            "macOS/Linux, nothing was registered"
        )
    metadata = store_accepted(root, "baseline", produced["path"])
    current = switch_current(
        root, "baseline", metadata, "Lab 2 baseline, reviewed in PR #4"
    )
    print(
        json.dumps(
            {
                **current,
                "validation_mae": produced["evidence"]["candidate"]["validation_mae"],
            },
            indent=2,
        )
    )
    return 0


def cmd_status(args) -> int:
    root = registry_root()
    current = read_current(root)
    if not current:
        print("no accepted model yet: run `python -m bike_demand.pipeline bootstrap`")
        return 1
    for label in ("version", "previous"):
        version = current.get(label)
        if version:
            try:
                load_accepted(root, version)
                state = "bytes verified"
            except (OSError, ValueError, KeyError) as error:
                state = f"NOT usable: {error}"
            print(f"{label:<8} {version}  ({state})")
    print(f"switched {current['switched_at']}  reason: {current['reason']}")
    return 0


def cmd_restore(args) -> int:
    """Point current back to a retained accepted version, without retraining."""
    root = registry_root()
    _, metadata = load_accepted(root, args.version)
    current = switch_current(root, args.version, metadata, f"restored {args.version}")
    print(json.dumps(current, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="train, evaluate and decide one candidate")
    run.add_argument("--candidate", required=True, type=Path)
    promote = sub.add_parser(
        "promote", help="accept a candidate whose decision is accept"
    )
    promote.add_argument("candidate_id")
    sub.add_parser(
        "bootstrap", help="register the Lab 2 baseline as first accepted model"
    )
    sub.add_parser("status", help="show and verify the accepted versions")
    restore = sub.add_parser("restore", help="serve a retained accepted version again")
    restore.add_argument("version")
    args = parser.parse_args()
    commands = {
        "run": cmd_run,
        "promote": cmd_promote,
        "bootstrap": cmd_bootstrap,
        "status": cmd_status,
        "restore": cmd_restore,
    }
    try:
        return commands[args.command](args)
    except (ValueError, OSError, KeyError) as error:
        print(f"pipeline {args.command} failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
