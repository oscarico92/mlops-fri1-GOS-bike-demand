"""Prediction API: normal, invalid-input and missing-model behaviour."""

import json
import logging

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestRegressor

from bike_demand import api
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

pytestmark = pytest.mark.api

VALID = {
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


def write_model(directory, version="baseline-test0001"):
    """A tiny model saved like train does: model.joblib + model-metadata.json."""
    frame = pd.DataFrame([VALID, {**VALID, "hr": 3}], columns=list(FEATURES))
    model = RandomForestRegressor(n_estimators=2, random_state=0)
    model.fit(frame, [500.0, 20.0])
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, directory / "model.joblib")
    metadata = {
        "model_version": version,
        "model_sha256": sha256(directory / "model.joblib"),
        "features": list(FEATURES),
    }
    (directory / "model-metadata.json").write_text(json.dumps(metadata))
    return directory


@pytest.fixture
def client_for(monkeypatch):
    """Start the app (lifespan included) with the model directory under test."""

    def start(directory):
        monkeypatch.setenv(api.MODEL_DIR_ENV, str(directory))
        return TestClient(api.app)

    return start


def test_health_and_predict_with_model(tmp_path, client_for):
    with client_for(write_model(tmp_path / "model", "baseline-abc123")) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["model_version"] == "baseline-abc123"

        response = client.post("/predict", json=VALID)
        assert response.status_code == 200
        body = response.json()
        assert body["model_version"] == "baseline-abc123"
        assert body["prediction"] >= 0


def test_predict_accepts_integer_for_normalised_bounds(tmp_path, client_for):
    with client_for(write_model(tmp_path / "model")) as client:
        response = client.post("/predict", json={**VALID, "temp": 1, "hum": 0})
        assert response.status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"hr": 24},
        {"season": 0},
        {"weathersit": 5},
        {"temp": 1.0000001},
        {"windspeed": -0.1},
        {"hr": "17"},
        {"hr": 17.5},
        {"holiday": True},
        {"temp": "0.7"},
        {"cnt": 100},
        {"registered": 80},
    ],
    ids=lambda change: next(iter(change)) + "=" + repr(next(iter(change.values()))),
)
def test_invalid_input_is_rejected_before_inference(tmp_path, client_for, change):
    with client_for(write_model(tmp_path / "model")) as client:
        response = client.post("/predict", json={**VALID, **change})
        assert response.status_code == 422


@pytest.mark.parametrize("field", FEATURES)
def test_missing_field_is_rejected(tmp_path, client_for, field):
    payload = {key: value for key, value in VALID.items() if key != field}
    with client_for(write_model(tmp_path / "model")) as client:
        assert client.post("/predict", json=payload).status_code == 422


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("with_model", [True, False], ids=["model", "no-model"])
def test_non_finite_json_number_is_422_not_500(tmp_path, client_for, raw, with_model):
    """Python clients send NaN/Infinity by default (json.dumps allow_nan=True)."""
    directory = write_model(tmp_path / "model") if with_model else tmp_path / "empty"
    body = json.dumps(VALID).replace('"temp": 0.7', f'"temp": {raw}')
    assert raw in body
    with client_for(directory) as client:
        response = client.post(
            "/predict", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail[0]["loc"] == ["body", "temp"]


def test_startup_logs_the_loaded_model(tmp_path, client_for, caplog):
    caplog.set_level("INFO", logger="bike_demand.api")
    with client_for(write_model(tmp_path / "model", "baseline-log0001")):
        pass
    assert "model loaded: version=baseline-log0001 sha256=" in caplog.text


def test_startup_logs_a_missing_model_as_error(tmp_path, client_for, caplog):
    caplog.set_level("INFO", logger="bike_demand.api")
    with client_for(tmp_path / "empty"):
        pass
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errors and "model not available" in errors[0].getMessage()


def test_missing_model_gives_503(tmp_path, client_for):
    with client_for(tmp_path / "empty") as client:
        assert client.get("/health").status_code == 503
        assert client.post("/predict", json=VALID).status_code == 503


def test_invalid_input_without_model_is_still_422(tmp_path, client_for):
    with client_for(tmp_path / "empty") as client:
        response = client.post("/predict", json={**VALID, "hr": 24})
        assert response.status_code == 422


def test_tampered_model_is_not_served(tmp_path, client_for):
    directory = write_model(tmp_path / "model")
    with (directory / "model.joblib").open("ab") as stream:
        stream.write(b"tampered")
    with client_for(directory) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/predict", json=VALID).status_code == 503


@pytest.fixture
def access_lines():
    """Collect the JSON access lines (the access logger does not propagate to caplog)."""
    lines = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    handler = Collect()
    access = logging.getLogger("bike_demand.access")
    access.addHandler(handler)
    yield lines
    access.removeHandler(handler)


def test_one_json_line_per_request(tmp_path, client_for, access_lines, monkeypatch):
    monkeypatch.setenv(api.CODE_REVISION_ENV, "abc1234")
    with client_for(write_model(tmp_path / "model", "baseline-log0002")) as client:
        response = client.post("/predict", json=VALID)
        assert response.status_code == 200
        client.get("/health")
    assert len(access_lines) == 2
    line = json.loads(access_lines[0])
    assert line["event"] == "request"
    assert (line["method"], line["path"], line["status"]) == ("POST", "/predict", 200)
    assert line["outcome"] == "ok"
    assert line["model_version"] == "baseline-log0002"
    assert line["code_revision"] == "abc1234"
    assert isinstance(line["duration_ms"], float) and line["duration_ms"] >= 0
    assert line["request_id"] == response.headers["X-Request-ID"]
    assert json.loads(access_lines[1])["path"] == "/health"


def test_invalid_request_logs_field_names_not_values(
    tmp_path, client_for, access_lines
):
    body = json.dumps({**VALID, "hum": 0.123456}).replace('"temp": 0.7', '"temp": NaN')
    with client_for(write_model(tmp_path / "model")) as client:
        response = client.post(
            "/predict", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    (raw,) = access_lines
    line = json.loads(raw)
    assert (line["status"], line["outcome"]) == (422, "invalid_input")
    assert line["invalid_fields"] == ["temp"]
    for value in ("NaN", "nan", "0.123456", "0.65"):
        assert value not in raw


def test_missing_model_request_is_logged_as_unavailable(
    tmp_path, client_for, access_lines
):
    with client_for(tmp_path / "empty") as client:
        assert client.post("/predict", json=VALID).status_code == 503
    line = json.loads(access_lines[0])
    assert (line["status"], line["outcome"], line["model_version"]) == (
        503,
        "model_unavailable",
        None,
    )
    assert (
        "code_revision" in line
    )  # still says which code runs when the model is missing


@pytest.mark.parametrize(
    ("given", "kept"),
    [("trace-42", True), ("bad id with spaces", False), ("x" * 65, False)],
)
def test_request_id_header(tmp_path, client_for, access_lines, given, kept):
    with client_for(write_model(tmp_path / "model")) as client:
        response = client.get("/health", headers={"X-Request-ID": given})
    returned = response.headers["X-Request-ID"]
    assert (returned == given) is kept
    assert json.loads(access_lines[0])["request_id"] == returned


def test_unhandled_error_is_logged_as_500(
    tmp_path, client_for, access_lines, monkeypatch
):
    with client_for(write_model(tmp_path / "model")):
        broken = {
            **api.state["loaded"],
            "model": None,
        }  # .predict raises AttributeError
        monkeypatch.setitem(api.state, "loaded", broken)
        client_no_raise = TestClient(api.app, raise_server_exceptions=False)
        assert client_no_raise.post("/predict", json=VALID).status_code == 500
    line = json.loads(access_lines[-1])
    assert (line["status"], line["outcome"]) == (500, "server_error")
