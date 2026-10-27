# Lab 3: run the Lab 2 baseline and its tests in a clean environment.
# Lab 4: serve the evaluated baseline model through the prediction API.
FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

# uv version allowed by pyproject.toml (>=0.12.19,<0.13)
COPY --from=ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a /uv /bin/uv

# Use the Python of the base image, never download another one
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# git: training records the commit; without .git in the image it records "unavailable"
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Manifest and lock first: this layer is reused while only the code changes.
# --locked stops the build if uv.lock is missing or out of date.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

# Code, config, frozen data snapshot and the files checked by preflight and tests
COPY README.md ./
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY tests ./tests
COPY reports ./reports
COPY .github ./.github
RUN uv sync --locked

# Produce the evaluated Lab 2 model once, at build time, from the same frozen data,
# config and split: the image then carries one fixed model (artifacts/model.joblib
# + model-metadata.json). The service only loads it; it never trains.
RUN python -m bike_demand.train --config configs/baseline.yaml > /dev/null

# Commit packaged in the image (set with --build-arg GIT_COMMIT=$(git rev-parse HEAD))
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision=$GIT_COMMIT
# Same commit, readable by the running service (/health "code_revision")
ENV GIT_COMMIT=$GIT_COMMIT

# Default: serve the API on port 8000 (preflight, tests and train run with
# another command, see README)
EXPOSE 8000
CMD ["uvicorn", "bike_demand.api:app", "--host", "0.0.0.0", "--port", "8000"]
