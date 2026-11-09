"""Lab 8 signal definitions: same rules for baseline, incident and recovery."""

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.signals

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "signals.py"
spec = importlib.util.spec_from_file_location("signals", SCRIPT)
signals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signals)


def line(request_id, status, ms=10.0, path="/predict", method="POST", model="m-1"):
    return json.dumps(
        {
            "ts": f"2026-11-10T10:00:{len(request_id):02d}.000+00:00",
            "event": "request",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": ms,
            "model_version": model,
            "code_revision": "abc",
        }
    )


DOCKER_LOGS = "\n".join(
    [
        "INFO:     Started server process [1]",
        "2026-11-10 10:00:00,000 INFO bike_demand.api model loaded: version=m-1",
        line("baseline-valid-0", 200, 10.0),
        line("baseline-valid-1", 200, 30.0),
        line("baseline-valid-2", 503, 1.0, model=None),
        line("baseline-invalid-0", 422, 0.5),
        line("other-valid-0", 200, 5.0),
        json.dumps(
            {"event": "request", "method": "GET", "path": "/health", "status": 200}
        ),
        "{broken json",
    ]
)


def test_rejections_are_not_errors_and_label_filters_the_population():
    events, unreadable = signals.events_from(DOCKER_LOGS)
    result = signals.summarize(events, "baseline", unreadable)
    assert result["population"] == 4
    assert result["intentional_rejections_422"] == 1
    assert (result["eligible"], result["good"]) == (3, 2)
    assert result["success_rate"] == round(2 / 3, 4)
    assert result["eligible_statuses"] == {"200": 2, "503": 1}
    assert result["latency_ms_good"] == {"p50": 10.0, "p95": 30.0, "max": 30.0}
    assert result["unreadable_lines"] == 1
    assert result["identities"] == {"abc / m-1": 3, "abc / None": 1}


def test_no_eligible_attempt_is_no_data_not_100_percent():
    events, _ = signals.events_from(line("baseline-invalid-0", 422))
    assert signals.summarize(events, "baseline")["success_rate"] == "no data"


def test_gcloud_json_array_is_read_from_json_or_text_payload():
    entries = [
        {"jsonPayload": json.loads(line("baseline-valid-0", 200))},
        {"textPayload": line("baseline-valid-1", 500)},
        {"textPayload": "INFO:     Uvicorn running"},
    ]
    events, _ = signals.events_from(json.dumps(entries))
    result = signals.summarize(events, "baseline")
    assert (result["eligible"], result["good"]) == (2, 1)
