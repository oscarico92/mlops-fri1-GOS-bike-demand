"""Check from outside which model and code a running service answers with (Lab 5).

Sends real HTTP requests to the service (never imports the app) and compares each
claim with an expected value. One mismatch fails the whole check (exit 1).

    uv run --locked python scripts/check_deployment.py --url http://127.0.0.1:8000

Expected values:
- code revision: --expected-revision, default `git rev-parse HEAD` of this checkout,
  so run the script from the commit the image was built from;
- model: --expected-model-sha256, default from configs/expected-model.json.
"""

import argparse
import json
import math
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXPECTED_MODEL_FILE = Path("configs/expected-model.json")
VALID_REQUEST = {
    "season": 3,
    "yr": 1,
    "mnth": 7,
    "hr": 17,
    "holiday": 0,
    "weekday": 3,
    "workingday": 1,
    "weathersit": 1,
    "temp": 0.7,
    "atemp": 0.65,
    "hum": 0.5,
    "windspeed": 0.2,
}
INVALID_REQUEST = {**VALID_REQUEST, "hr": 24}


def http_fetch(base_url: str, timeout: float):
    """Return fetch(method, path, body) -> (status, json or None) over HTTP."""

    def fetch(method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, None

    return fetch


def run_checks(fetch, expected_revision: str, expected_model_sha256: str) -> list:
    """Return rows (claim, expected, observed, ok)."""
    rows = []
    status, health = fetch("GET", "/health")
    health = health if isinstance(health, dict) else {}
    rows.append(("ready (/health)", "200", str(status), status == 200))
    rows.append(
        (
            "model_sha256",
            expected_model_sha256,
            str(health.get("model_sha256")),
            health.get("model_sha256") == expected_model_sha256,
        )
    )
    rows.append(
        (
            "code_revision",
            expected_revision,
            str(health.get("code_revision")),
            health.get("code_revision") == expected_revision,
        )
    )

    status, answer = fetch("POST", "/predict", VALID_REQUEST)
    answer = answer if isinstance(answer, dict) else {}
    prediction = answer.get("prediction")
    valid = (
        status == 200
        and isinstance(prediction, int | float)
        and math.isfinite(prediction)
        and prediction >= 0
    )
    rows.append(
        ("valid /predict", "200, finite >= 0", f"{status}, {prediction}", valid)
    )
    version = health.get("model_version")
    rows.append(
        (
            "same model_version",
            str(version),
            str(answer.get("model_version")),
            version is not None and answer.get("model_version") == version,
        )
    )

    status, _ = fetch("POST", "/predict", INVALID_REQUEST)
    rows.append(("invalid /predict (hr=24)", "422", str(status), status == 422))
    return rows


LABEL = "org.opencontainers.image.revision"


def container_label(container: str) -> str:
    """Revision label of the image a running container was started from.

    Set at build time (--build-arg GIT_COMMIT); unlike the GIT_COMMIT env var
    read by the service, `docker run -e` cannot change it.
    """
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "unavailable"
    return (json.loads(result.stdout or "null") or {}).get(LABEL, "unavailable")


def label_row(expected_revision: str, label: str) -> tuple:
    return (
        "image label revision",
        expected_revision,
        label,
        label == expected_revision,
    )


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--expected-revision", default=None)
    parser.add_argument("--expected-model-sha256", default=None)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--container",
        default=None,
        help="name of the running container: also compare its image revision label",
    )
    args = parser.parse_args()

    revision = args.expected_revision or git_head()
    model_sha256 = (
        args.expected_model_sha256
        or json.loads(EXPECTED_MODEL_FILE.read_text())["model_sha256"]
    )
    try:
        rows = run_checks(http_fetch(args.url, args.timeout), revision, model_sha256)
    except OSError as error:
        print(f"FAIL: service not reachable at {args.url}: {error}")
        return 1
    if args.container:
        rows.append(label_row(revision, container_label(args.container)))

    width = max(len(row[0]) for row in rows)
    print(f"service {args.url}")
    for claim, expected, observed, ok in rows:
        result = "ok" if ok else "FAIL"
        print(
            f"{claim:<{width}}  {result:<4}  expected {expected}  observed {observed}"
        )
    failed = [row[0] for row in rows if not row[3]]
    if failed:
        print(f"check FAILED: {', '.join(failed)}")
        return 1
    print("check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
