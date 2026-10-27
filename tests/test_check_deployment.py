"""The deployment check passes on the expected service and fails on each mismatch."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import write_model

from bike_demand import api

pytestmark = pytest.mark.deploy

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_deployment.py"
spec = importlib.util.spec_from_file_location("check_deployment", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

REVISION = "a" * 40


def client_fetch(client):
    def fetch(method, path, body=None):
        response = client.request(method, path, json=body)
        return response.status_code, response.json()

    return fetch


@pytest.fixture
def service(tmp_path, monkeypatch):
    directory = write_model(tmp_path / "model", "baseline-deploy01")
    monkeypatch.setenv(api.MODEL_DIR_ENV, str(directory))
    monkeypatch.setenv(api.CODE_REVISION_ENV, REVISION)
    metadata = json.loads((directory / "model-metadata.json").read_text())
    with TestClient(api.app) as client:
        yield client, metadata["model_sha256"]


def failed(rows):
    return [claim for claim, _, _, ok in rows if not ok]


def test_expected_service_passes(service):
    client, sha = service
    assert failed(check.run_checks(client_fetch(client), REVISION, sha)) == []


def test_wrong_code_revision_fails(service):
    client, sha = service
    rows = check.run_checks(client_fetch(client), "b" * 40, sha)
    assert failed(rows) == ["code_revision"]


def test_wrong_model_fails(service):
    client, _ = service
    rows = check.run_checks(client_fetch(client), REVISION, "0" * 64)
    assert failed(rows) == ["model_sha256"]


def test_service_without_model_fails(tmp_path, monkeypatch):
    monkeypatch.setenv(api.MODEL_DIR_ENV, str(tmp_path / "empty"))
    monkeypatch.setenv(api.CODE_REVISION_ENV, REVISION)
    with TestClient(api.app) as client:
        rows = check.run_checks(client_fetch(client), REVISION, "0" * 64)
    assert "ready (/health)" in failed(rows)
    assert "valid /predict" in failed(rows)
    assert "code_revision" not in failed(rows)  # still reported with a 503
