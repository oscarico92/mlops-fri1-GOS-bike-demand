"""Lab 8 signal definitions: same rules for baseline, incident and recovery.

Intent comes from the request id (`<label>-valid-<n>` / `<label>-invalid-<n>`), never from
the response; requests that were sent but never logged still count (cases from Gautier's
review of #30: C regression to 422, D all valid rejected, E validation broken, F requests
that never arrive).
"""

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.signals

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "signals.py"
spec = importlib.util.spec_from_file_location("signals", SCRIPT)
signals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signals)


def event(rid, status, ms=10.0, model="m-1"):
    return {
        "ts": f"2026-11-10T10:00:00.{len(rid):03d}+00:00",
        "event": "request",
        "request_id": rid,
        "method": "POST",
        "path": "/predict",
        "status": status,
        "duration_ms": ms,
        "model_version": model,
        "code_revision": "abc",
    }


def workload(valid=10, invalid=5, client=200):
    sent = [{"request_id": f"inc-r1-valid-{n}", "status": client} for n in range(valid)]
    sent += [
        {"request_id": f"inc-r1-invalid-{n}", "status": 422} for n in range(invalid)
    ]
    return sent


def logs(valid_status, invalid_status=422, valid=10, invalid=5):
    out = [event(f"inc-r1-valid-{n}", valid_status(n)) for n in range(valid)]
    out += [event(f"inc-r1-invalid-{n}", invalid_status) for n in range(invalid)]
    return out


def test_a_baseline():
    r = signals.summarize(logs(lambda n: 200), "inc", sent=workload())
    assert (r["sent"], r["logged"], r["missing"]) == (15, 15, 0)
    assert (r["eligible"], r["good"], r["success_rate"]) == (10, 10, 1.0)
    assert (r["intentional_rejections_422"], r["invalid_accepted"]) == (5, 0)


def test_c_valid_requests_answered_422_are_failures_not_rejections():
    r = signals.summarize(logs(lambda n: 422 if n < 5 else 200), "inc", sent=workload())
    assert (r["eligible"], r["good"], r["success_rate"]) == (10, 5, 0.5)
    assert r["intentional_rejections_422"] == 5


def test_d_all_valid_rejected_is_zero_not_no_data():
    r = signals.summarize(logs(lambda n: 422), "inc", sent=workload())
    assert r["success_rate"] == 0.0


def test_e_invalid_requests_accepted_are_flagged():
    r = signals.summarize(
        logs(lambda n: 200, invalid_status=200), "inc", sent=workload()
    )
    assert r["invalid_accepted"] == 5
    assert r["success_rate"] == 1.0


def test_f_requests_that_never_arrive_count_as_not_good():
    events = [
        e
        for e in logs(lambda n: 200)
        if e["request_id"] not in {f"inc-r1-valid-{n}" for n in range(4)}
    ]
    r = signals.summarize(events, "inc", sent=workload())
    assert (r["missing"], r["good"], r["success_rate"]) == (4, 6, 0.6)
    assert r["eligible_statuses"] == {"missing": 4, "200": 6}


def test_no_response_is_named_in_the_client_view():
    r = signals.summarize(
        [], "inc", sent=workload(valid=2, invalid=0, client="no_response")
    )
    assert r["client_statuses"] == {"no_response": 2}
    assert (r["missing"], r["success_rate"]) == (2, 0.0)


def test_nothing_sent_is_no_data():
    assert signals.summarize([], "inc", sent=[])["success_rate"] == "no data"


def test_docker_and_gcloud_inputs_are_read():
    text = "\n".join(
        [
            "INFO:     Started server process [1]",
            json.dumps(event("inc-r1-valid-0", 200)),
            "{broken",
        ]
    )
    events, unreadable = signals.events_from(text)
    assert (len(events), unreadable) == (1, 1)
    entries = [
        {"jsonPayload": event("inc-r1-valid-0", 200)},
        {"textPayload": json.dumps(event("inc-r1-valid-1", 500))},
        {"textPayload": "INFO:     Uvicorn running"},
    ]
    events, _ = signals.events_from(json.dumps(entries))
    r = signals.summarize(events, "inc")
    assert (r["eligible"], r["good"]) == (2, 1)


def test_lines_of_an_earlier_run_with_the_same_label_do_not_count():
    old_run = [event(f"inc-r0-valid-{n}", 200) for n in range(10)]
    new_run = [event(f"inc-r1-valid-{n}", 200) for n in range(6)]  # 4 never arrived
    sent = [{"request_id": f"inc-r1-valid-{n}", "status": 200} for n in range(10)]
    r = signals.summarize(old_run + new_run, "inc", sent=sent)
    assert (r["logged"], r["missing"], r["success_rate"]) == (6, 4, 0.6)


def test_a_duplicate_id_counts_its_worst_answer():
    events = [event("inc-r1-valid-0", 503), event("inc-r1-valid-0", 200)]
    sent = [{"request_id": "inc-r1-valid-0", "status": 200}]
    r = signals.summarize(events, "inc", sent=sent)
    assert (r["good"], r["success_rate"], r["duplicate_lines"]) == (0, 0.0, 1)


def test_without_sent_missing_is_unknown():
    r = signals.summarize([event("inc-r1-valid-0", 200)], "inc")
    assert r["missing"] == "unknown (no --sent)"
