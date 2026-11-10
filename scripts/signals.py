"""Compute the Lab 8 service signals from the JSON request log lines.

    docker logs bike-api 2>&1 | python scripts/signals.py --label baseline --sent logs/lab-08/baseline-requests.jsonl
    gcloud logging read '<filter>' --format=json | python scripts/signals.py --label baseline --sent <file>

Input: the one-line JSON events written by src/bike_demand/api.py (`"event": "request"`),
either as raw lines (docker logs; uvicorn text lines are skipped) or as a gcloud JSON array
(the event is read from `jsonPayload`, or parsed from `textPayload`). `--sent` is the
per-request file written by scripts/workload.py (`--out`): it says what was sent and what the
client received, so requests that never reached the service still count.

Definitions (the same for baseline, incident and recovery). Intent comes from the request,
never from the response: workload ids are `<label>-valid-<n>` or `<label>-invalid-<n>`.
- eligible attempts: every valid request sent (from --sent), or seen in the logs without --sent;
- good: eligible attempts logged with status 200;
- missing: requests sent but with no log line (never arrived, or answered by the platform); a
  missing valid request is not good;
- success rate = good / eligible; "no data" only when no valid request was sent;
- intentional rejections: invalid requests answered 422; invalid_accepted: invalid requests
  answered anything else (a validation defect);
- latency: server duration_ms of good attempts (p50, p95, max);
- identity: requests per code_revision / model_version;
- client view (with --sent): status the client received, including "no_response";
- unreadable: lines that look like JSON but cannot be read.
"""

import argparse
import json
import math
import sys
from pathlib import Path


def events_from(text: str) -> tuple[list[dict], int]:
    text = text.strip()
    if text.startswith("["):
        try:
            entries = json.loads(text)
        except ValueError:
            return [], 1
        events = []
        for entry in entries:
            payload = entry.get("jsonPayload") if isinstance(entry, dict) else None
            if payload is None and isinstance(entry, dict) and entry.get("textPayload"):
                try:
                    payload = json.loads(entry["textPayload"])
                except ValueError:
                    payload = None
            if isinstance(payload, dict):
                events.append(payload)
        return events, 0
    events, unreadable = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue  # uvicorn and startup lines are plain text
        try:
            events.append(json.loads(line))
        except ValueError:
            unreadable += 1
    return events, unreadable


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def intent(request_id: str, label: str) -> str | None:
    if request_id.startswith(f"{label}-valid-"):
        return "valid"
    if request_id.startswith(f"{label}-invalid-"):
        return "invalid"
    return None


def count(values) -> dict:
    out: dict = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return out


def summarize(
    events: list[dict], label: str, unreadable: int = 0, sent: list[dict] | None = None
) -> dict:
    logged = {}
    for e in events:
        if (
            e.get("event") == "request"
            and e.get("method") == "POST"
            and e.get("path") == "/predict"
            and intent(str(e.get("request_id", "")), label)
        ):
            logged[str(e["request_id"])] = e
    if sent is not None:
        sent_ids = {
            str(r["request_id"]): r
            for r in sent
            if intent(str(r.get("request_id", "")), label)
        }
    else:
        sent_ids = {rid: None for rid in logged}
    valid = [rid for rid in sent_ids if intent(rid, label) == "valid"]
    invalid = [rid for rid in sent_ids if intent(rid, label) == "invalid"]
    good = [rid for rid in valid if logged.get(rid, {}).get("status") == 200]
    missing = [rid for rid in sent_ids if rid not in logged]
    rejected = [rid for rid in invalid if logged.get(rid, {}).get("status") == 422]
    invalid_accepted = [
        rid for rid in invalid if rid in logged and logged[rid].get("status") != 422
    ]
    latencies = [
        float(logged[rid]["duration_ms"])
        for rid in good
        if isinstance(logged[rid].get("duration_ms"), int | float)
    ]
    times = sorted(str(e["ts"]) for e in logged.values() if e.get("ts"))
    result = {
        "label": label,
        "window_utc": [times[0], times[-1]] if times else None,
        "sent": len(sent_ids) if sent is not None else "unknown (no --sent)",
        "logged": len(logged),
        "missing": len(missing),
        "eligible": len(valid),
        "good": len(good),
        "success_rate": round(len(good) / len(valid), 4) if valid else "no data",
        "eligible_statuses": count(
            logged[rid].get("status") if rid in logged else "missing" for rid in valid
        ),
        "intentional_rejections_422": len(rejected),
        "invalid_accepted": len(invalid_accepted),
        "latency_ms_good": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
        "identities": count(
            f"{e.get('code_revision')} / {e.get('model_version')}"
            for e in logged.values()
        ),
        "unreadable_lines": unreadable,
    }
    if sent is not None:
        result["client_statuses"] = count(r.get("status") for r in sent_ids.values())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--label", required=True, help="request_id prefix of the workload"
    )
    parser.add_argument(
        "--sent", type=Path, default=None, help="workload.py --out file"
    )
    args = parser.parse_args()
    events, unreadable = events_from(sys.stdin.read())
    sent = None
    if args.sent:
        sent = [
            json.loads(line)
            for line in args.sent.read_text().splitlines()
            if line.strip()
        ]
    print(json.dumps(summarize(events, args.label, unreadable, sent), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
