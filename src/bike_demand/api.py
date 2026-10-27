"""Prediction API: serve the saved, evaluated baseline model. Never trains."""

import json
import logging
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

logger = logging.getLogger("bike_demand.api")

# Directory holding model.joblib and model-metadata.json written by train.
MODEL_DIR_ENV = "BIKE_MODEL_DIR"
DEFAULT_MODEL_DIR = "artifacts"
# Commit the image was built from (Dockerfile: ENV GIT_COMMIT from the build arg).
CODE_REVISION_ENV = "GIT_COMMIT"

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    directory = Path(os.environ.get(MODEL_DIR_ENV, DEFAULT_MODEL_DIR))
    try:
        state["loaded"], state["error"] = load_model(directory), None
        logger.info("model loaded: %s", state["loaded"]["model_version"])
    except (OSError, ValueError, KeyError) as error:
        state["loaded"], state["error"] = None, f"model not available: {error}"
        logger.error(state["error"])
    yield
    state["loaded"] = None


app = FastAPI(title="Bike demand prediction", lifespan=lifespan)


def require_model() -> dict:
    if state["loaded"] is None:
        raise HTTPException(status_code=503, detail=state["error"] or "no model")
    return state["loaded"]


@app.get("/health")
def health():
    revision = os.environ.get(CODE_REVISION_ENV, "unknown")
    if state["loaded"] is None:
        # Still say which code is running, so a broken deployment can be identified.
        return JSONResponse(
            status_code=503,
            content={"detail": state["error"] or "no model", "code_revision": revision},
        )
    loaded = state["loaded"]
    return {
        "status": "ok",
        "model_version": loaded["model_version"],
        "model_sha256": loaded["model_sha256"],
        "code_revision": revision,
    }


@app.post("/predict")
def predict(request: PredictRequest) -> PredictResponse:
    loaded = require_model()
    row = pd.DataFrame([request.model_dump()], columns=list(FEATURES))
    prediction = float(loaded["model"].predict(row)[0])
    if not math.isfinite(prediction) or prediction < 0:
        raise HTTPException(status_code=500, detail="model returned an invalid value")
    return PredictResponse(prediction=prediction, model_version=loaded["model_version"])
