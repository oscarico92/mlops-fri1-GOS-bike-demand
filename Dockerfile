# Lab 3: run the Lab 2 baseline and its tests in a clean environment.
FROM python:3.12.12-slim

# uv version allowed by pyproject.toml (>=0.12.19,<0.13)
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /bin/uv

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

# Default: train the baseline (preflight and tests are run with another command)
CMD ["python", "-m", "bike_demand.train", "--config", "configs/baseline.yaml"]
