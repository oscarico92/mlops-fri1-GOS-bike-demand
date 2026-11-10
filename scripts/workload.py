"""Send a fixed, reproducible workload to the service (Lab 8 baseline and incident).

    python scripts/workload.py --url https://<service> --label baseline --valid 40 --invalid 10

Every request carries `X-Request-ID: <label>-<kind>-<n>`, so its JSON log line can be found
and counted later (scripts/signals.py). Valid requests vary the hour over 0-23 so the
workload is not one cached input; invalid requests send hr=24 (an intentional 422).
Prints one summary line and writes the per-request results as JSON lines to --out.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/predict-valid.json").read_text()
)


def send(url: str, body: dict, request_id: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url.rstrip("/") + "/predict",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except OSError as error:
        status, raw = None, str(error).encode()
    try:
        answer = json.loads(raw)
    except ValueError:
        answer = None
    return {
        "request_id": request_id,
        # no HTTP answer at all (timeout, connection refused): named, never dropped
        "status": status if status is not None else "no_response",
        "client_ms": round((time.perf_counter() - started) * 1000, 1),
        "model_version": answer.get("model_version")
        if isinstance(answer, dict)
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--label", required=True, help="e.g. baseline, incident, recovery"
    )
    parser.add_argument("--valid", type=int, default=40)
    parser.add_argument("--invalid", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    results = []
    for n in range(args.valid):
        body = {**BASE, "hr": n % 24}
        results.append(send(args.url, body, f"{args.label}-valid-{n}", args.timeout))
    for n in range(args.invalid):
        body = {**BASE, "hr": 24}
        results.append(send(args.url, body, f"{args.label}-invalid-{n}", args.timeout))
    ended_at = datetime.now(UTC).isoformat(timespec="seconds")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(r) + "\n" for r in results))
    statuses: dict = {}
    for r in results:
        statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1
    versions = sorted({r["model_version"] for r in results if r["model_version"]})
    print(
        json.dumps(
            {
                "label": args.label,
                "url": args.url,
                "window_utc": [started_at, ended_at],
                "sent": len(results),
                "statuses": statuses,
                "model_versions": versions,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
