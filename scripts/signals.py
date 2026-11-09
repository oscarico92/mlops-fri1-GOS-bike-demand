"""Compute the Lab 8 service signals from the JSON request log lines.

    docker logs bike-api 2>&1 | python scripts/signals.py --label baseline
    gcloud logging read '<filter>' --format=json | python scripts/signals.py --label baseline

Input: the one-line JSON events written by src/bike_demand/api.py (`"event": "request"`),
either as raw lines (docker logs, uvicorn text lines are skipped) or as a gcloud JSON array
(the event is read from `jsonPayload`, or parsed from `textPayload`).

Definitions (the same for baseline, incident and recovery):
- population: POST /predict events whose request_id starts with --label (the workload's
  own requests), inside the window of their timestamps;
- intentional rejections: status 422 (invalid input); counted, never an error;
- eligible attempts: the other /predict events (valid input);
- good: eligible attempts answered 200;
- success rate = good / eligible; error rate = 1 - success rate;
- latency: server duration_ms of good attempts (p50, p95, max);
- identity: each (code_revision, model_version) seen, with its count;
- missing: lines that look like JSON but cannot be read, and an eligible count of 0
  (reported as "no data", never as 100 %).
"""

import argparse
import json
import math
import sys


def events_from(text: str) -> tuple[list[dict], int]:
    text = text.strip()
    unreadable = 0
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
        return events, unreadable
    events = []
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
    rank = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[rank]


def summarize(events: list[dict], label: str | None, unreadable: int = 0) -> dict:
    population = [
        e
        for e in events
        if e.get("event") == "request"
        and e.get("method") == "POST"
        and e.get("path") == "/predict"
        and (label is None or str(e.get("request_id", "")).startswith(f"{label}-"))
    ]
    rejected = [e for e in population if e.get("status") == 422]
    eligible = [e for e in population if e.get("status") != 422]
    good = [e for e in eligible if e.get("status") == 200]
    latencies = [
        float(e["duration_ms"])
        for e in good
        if isinstance(e.get("duration_ms"), int | float)
    ]
    identities: dict = {}
    for e in population:
        key = f"{e.get('code_revision')} / {e.get('model_version')}"
        identities[key] = identities.get(key, 0) + 1
    statuses: dict = {}
    for e in eligible:
        statuses[str(e.get("status"))] = statuses.get(str(e.get("status")), 0) + 1
    times = sorted(str(e["ts"]) for e in population if e.get("ts"))
    return {
        "label": label,
        "window_utc": [times[0], times[-1]] if times else None,
        "population": len(population),
        "intentional_rejections_422": len(rejected),
        "eligible": len(eligible),
        "good": len(good),
        "success_rate": round(len(good) / len(eligible), 4) if eligible else "no data",
        "eligible_statuses": statuses,
        "latency_ms_good": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
        "identities": identities,
        "unreadable_lines": unreadable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--label", default=None, help="request_id prefix of the workload"
    )
    args = parser.parse_args()
    events, unreadable = events_from(sys.stdin.read())
    print(json.dumps(summarize(events, args.label, unreadable), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
