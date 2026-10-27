"""Prediction API: serve the saved, evaluated baseline model. Never trains."""

import json
import logging
import math
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

logger = logging.getLogger("bike_demand.api")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
# One JSON line per request, nothing else on that line (see log_request).
access_logger = logging.getLogger("bike_demand.access")
REQUEST_ID_HEADER = "X-Request-ID"
# A client-supplied request id is kept only if it is short and plain; otherwise we make one.
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

# Directory holding model.joblib and model-metadata.json written by train.
MODEL_DIR_ENV = "BIKE_MODEL_DIR"
DEFAULT_MODEL_DIR = "artifacts"

NormalisedValue = Field(ge=0, le=1, allow_inf_nan=False)


class PredictRequest(BaseModel):
    """One hour of calendar and weather fields, as used in training.

    Strict types: "3" is not accepted for an integer field. Extra fields are
    rejected, so labels (cnt, casual, registered) can never be sent as inputs.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    season: int = Field(ge=1, le=4)
    yr: int = Field(ge=0, le=1)
    mnth: int = Field(ge=1, le=12)
    hr: int = Field(ge=0, le=23)
    holiday: int = Field(ge=0, le=1)
    weekday: int = Field(ge=0, le=6)
    workingday: int = Field(ge=0, le=1)
    weathersit: int = Field(ge=1, le=4)
    temp: float = NormalisedValue
    atemp: float = NormalisedValue
    hum: float = NormalisedValue
    windspeed: float = NormalisedValue


class PredictResponse(BaseModel):
    prediction: float
    model_version: str


def load_model(directory: Path) -> dict:
    """Load a locally produced model; raise ValueError/OSError if not usable."""
    metadata = json.loads((directory / "model-metadata.json").read_text())
    model_path = directory / "model.joblib"
    if sha256(model_path) != metadata["model_sha256"]:
        raise ValueError("model.joblib checksum does not match model-metadata.json")
    if list(metadata["features"]) != list(FEATURES):
        raise ValueError("model features do not match the request contract")
    # Only load trusted files produced by our own training run.
    return {
        "model": joblib.load(model_path),
        "model_version": metadata["model_version"],
        "model_sha256": metadata["model_sha256"],
    }


state: dict = {"loaded": None, "error": None}


def configure_logging() -> None:
    """Uvicorn only configures its own loggers; give ours a handler with level and time.

    basicConfig does nothing if the root logger already has handlers (e.g. under pytest).
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logger.setLevel(logging.INFO)
    # Access lines are pure JSON: own handler, no prefix, not repeated by the root logger.
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    if not any(getattr(h, "bike_access", False) for h in access_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.bike_access = True
        access_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    directory = Path(os.environ.get(MODEL_DIR_ENV, DEFAULT_MODEL_DIR))
    try:
        state["loaded"], state["error"] = load_model(directory), None
        logger.info(
            "model loaded: version=%s sha256=%s dir=%s",
            state["loaded"]["model_version"],
            state["loaded"]["model_sha256"],
            directory,
        )
    except (OSError, ValueError, KeyError) as error:
        state["loaded"], state["error"] = None, f"model not available: {error}"
        logger.error(state["error"])
    yield
    state["loaded"] = None


app = FastAPI(title="Bike demand prediction", lifespan=lifespan)


def json_safe(value):
    """Replace NaN/Infinity, which JSON cannot carry, by their text form."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    """Same 422 body as FastAPI's default, but it cannot crash on NaN/Infinity input.

    The default handler echoes the rejected input; json.dumps refuses NaN, so a
    request with "temp": NaN turned into a 500 instead of a 422.
    """
    detail = json_safe(jsonable_encoder(error.errors()))
    # Field names only, never the rejected values, for the access log line.
    request.state.invalid_fields = sorted(
        {
            str(e["loc"][1])
            if len(e["loc"]) > 1 and isinstance(e["loc"][1], str)
            else "body"
            for e in error.errors()
        }
    )
    return JSONResponse(status_code=422, content={"detail": detail})


OUTCOMES = {200: "ok", 422: "invalid_input", 503: "model_unavailable"}


def request_id_for(request: Request) -> str:
    given = request.headers.get(REQUEST_ID_HEADER, "")
    return given if SAFE_REQUEST_ID.fullmatch(given) else uuid.uuid4().hex[:16]


def log_request(request: Request, request_id: str, status: int, started: float) -> None:
    """Write the one access line of this request.

    Enough for an operator to tell what happened and which model answered; never the
    request body, the input values or the client address.
    """
    loaded = state["loaded"]
    line = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "event": "request",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": status,
        "outcome": OUTCOMES.get(
            status, "client_error" if status < 500 else "server_error"
        ),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "model_version": loaded["model_version"] if loaded else None,
    }
    invalid = getattr(request.state, "invalid_fields", None)
    if invalid:
        line["invalid_fields"] = invalid
    access_logger.info(json.dumps(line, separators=(",", ":")))


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    request_id = request_id_for(request)
    try:
        response = await call_next(request)
    except Exception:
        log_request(request, request_id, 500, started)
        raise
    response.headers[REQUEST_ID_HEADER] = request_id
    log_request(request, request_id, response.status_code, started)
    return response


def require_model() -> dict:
    if state["loaded"] is None:
        raise HTTPException(status_code=503, detail=state["error"] or "no model")
    return state["loaded"]


@app.get("/health")
def health() -> dict:
    loaded = require_model()
    return {
        "status": "ok",
        "model_version": loaded["model_version"],
        "model_sha256": loaded["model_sha256"],
    }


@app.post("/predict")
def predict(request: PredictRequest) -> PredictResponse:
    loaded = require_model()
    row = pd.DataFrame([request.model_dump()], columns=list(FEATURES))
    prediction = float(loaded["model"].predict(row)[0])
    if not math.isfinite(prediction) or prediction < 0:
        raise HTTPException(status_code=500, detail="model returned an invalid value")
    return PredictResponse(prediction=prediction, model_version=loaded["model_version"])
