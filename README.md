# Bike Demand (team GOS)

Team repository of Oscar Schwartz, Gautier Deplanque and Simon Gallais for the ECE
MLOps course (session `fri1`). How we work together: [CONTRIBUTING.md](CONTRIBUTING.md)
and [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md). Lab evidence: [reports/](reports/).

## Project scope

- **User:** someone planning bike availability who needs an estimate of total hourly
  rentals for a given hour.
- **Goal:** estimate total hourly rentals (`cnt`) from calendar fields and supplied
  weather conditions, served later as a prediction API that also returns the loaded
  model version.
- **Inputs:** the 12 contract features (`season`, `yr`, `mnth`, `hr`, `holiday`,
  `weekday`, `workingday`, `weathersit`, `temp`, `atemp`, `hum`, `windspeed`) from the
  frozen UCI snapshot `data/raw/hour.csv`.
- **Output:** estimated rentals per hour, with the identity of the model that produced it.
- **Non-goals:** forecasting future weather, station-level demand, using `casual` or
  `registered` (labels) as predictors, computing test metrics before the final release.
- **How success is checked:** validation MAE (rentals/hour) on January to June 2012,
  always compared with the training-mean baseline on the same rows; the data contract,
  split and quality checks pass locally and in CI on the revision being merged.
  July to December 2012 rows are held out until the final evaluation of the release
  candidate.

## Reproduce the Lab 2 baseline in Docker (Lab 3)

The image runs the Lab 2 baseline from the committed `uv.lock`, with the same data
snapshot, config and split as Lab 2. Nothing from your machine is used: no Python,
uv, `.venv`, caches or earlier outputs.

**Requirement:** Docker Desktop (or Docker Engine) running. Check with
`docker run --rm hello-world`.

### 1. Start from a clean clone and record the revision

```bash
git clone https://github.com/oscarico92/mlops-fri1-GOS-bike-demand.git rerun-clean
cd rerun-clean
git rev-parse HEAD          # commit that will be packaged
git hash-object uv.lock     # identity of the lock used by the build
```

### 2. Build the image

```bash
docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t bike-demand:lab3 . 2>&1 | tee build.log
docker image inspect bike-demand:lab3 --format '{{.Id}}'
docker image inspect bike-demand:lab3 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

The first build downloads the base image and the locked dependencies (a few
minutes). `uv sync --locked` stops the build if `uv.lock` is missing or does not
match `pyproject.toml`; never regenerate the lock to make the build pass (see
[reports/lab-03-lock.md](reports/lab-03-lock.md) and `scripts/lock_check_demo.py`).

### 3. Check the setup and run the tests

```bash
docker run --rm --network none bike-demand:lab3 python -m bike_demand.preflight
docker run --rm --network none bike-demand:lab3 pytest -q
```

Expected: `Preflight passed: ...` and `51 passed`.

### 4. Run the baseline and copy the outputs out

Since Lab 4 the default command starts the API, so pass the training command explicitly.
Use a named container so its outputs can be copied before it is removed.
`--network none` shows that nothing is downloaded at run time: everything comes from the image.

```bash
docker run --name bike-rerun --network none bike-demand:lab3 \
  python -m bike_demand.train --config configs/baseline.yaml 2>&1 | tee train.log
docker cp bike-rerun:/app/reports/metrics.json ./metrics-rerun.json
docker cp bike-rerun:/app/artifacts ./artifacts-rerun
docker rm bike-rerun
```

### 5. Compare with Lab 2

| Value | Lab 2 (`reports/metrics.json` on `main`) | Expected in the container |
| --- | --- | --- |
| Partitions (train / validation / test rows) | 8,645 / 4,358 / 4,376 | identical |
| Validation MAE, training-mean comparator | 154.23179306864967 | identical |
| Validation MAE, random forest | 86.84685685591091 | identical |
| `readback.reload_mae_delta` | 0.0 | 0.0 |
| `model_sha256` | `fd98ceaf…` (native Windows run) | `d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07` |

Known, explained differences:

- `training_commit` is `unavailable` and `working_tree_dirty` is `null`, because `.git`
  is excluded from the image. The commit is carried by the image label
  `org.opencontainers.image.revision` (step 2); it must match `git rev-parse HEAD` from step 1.
- The image ID changes between machines. `model_sha256` differs from the native Lab 2
  run (Windows, `fd98ceaf…`) but was identical in the container on arm64 (macOS) and
  amd64 (Windows): `d24c050e…`. The MAEs are identical in all three runs.
- New MLflow run IDs and `model_version` on every run.

No test-set metric is computed.

### Windows PowerShell

Replace `tee` with `Tee-Object` (for example `... 2>&1 | Tee-Object build.log`) and use
`--format "{{.Id}}"` with double quotes. The label command above does not work in
Windows PowerShell 5.1: it drops the inner double quotes and Docker answers
`function "org" not defined`. Read the labels as JSON instead:

```powershell
(docker image inspect bike-demand:lab3 --format "{{json .Config.Labels}}" | ConvertFrom-Json).'org.opencontainers.image.revision'
```

Windows PowerShell 5.1 prints Docker's normal
log lines in red as `NativeCommandError` when stderr is redirected; they are not
failures. PowerShell 7 (`pwsh`) does not do this.

## Prediction API (Lab 4)

`src/bike_demand/api.py` serves the evaluated baseline model. It never trains: at
startup it loads `model.joblib` and `model-metadata.json` from `BIKE_MODEL_DIR`
(default `artifacts/`), checks the model SHA-256 against the metadata, and keeps the
result in one model-availability state shared by both endpoints.

| Endpoint | Answer |
| --- | --- |
| `GET /health` | `200` with `status`, `model_version`, `model_sha256` when a usable model is loaded; otherwise `503` with the reason |
| `POST /predict` | `200` with `prediction` (finite, non-negative rentals/hour) and `model_version`; `422` for invalid input; `503` for valid input without a model |

`model_version` is read from `model-metadata.json`, never hard-coded.

**Input contract.** One flat JSON object with the 12 training features, all required:
`season` 1–4, `yr` 0–1, `mnth` 1–12, `hr` 0–23, `holiday` 0–1, `weekday` 0–6,
`workingday` 0–1, `weathersit` 1–4 (integers), and `temp`, `atemp`, `hum`,
`windspeed` (finite numbers in 0–1, normalised as in the UCI data, not Celsius or %).

- Types are strict: `"17"`, `17.5` or `true` for an integer field are rejected (`422`).
- Extra fields are rejected (`422`), so `cnt`, `casual` and `registered` can never be
  sent as inputs. Rejected alternative: silently ignoring them, which would hide a
  client bug.

**Where the model comes from in the image.** The Dockerfile runs the Lab 2 training
once at build time (same frozen data, config and split), so each image carries one
fixed model. The model bytes are the same as in the Lab 3 rerun (`model_sha256`
`d24c050e…`); `model_version` is a new random id for each build, so read it from
`/health`. Rejected alternative: mounting a model from the laptop, which would make
the image depend on host files.

### Run and test the service in Docker

```bash
docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t bike-demand:lab4 . 2>&1 | tee build.log
docker image inspect bike-demand:lab4 --format '{{.Id}}'
docker run --rm --network none bike-demand:lab4 pytest -q            # tests run inside the image
docker run --rm --name bike-api -p 127.0.0.1:8000:8000 bike-demand:lab4
```

In a second terminal:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/predict -H "Content-Type: application/json" --data-binary @examples/predict-valid.json
curl -s -X POST localhost:8000/predict -H "Content-Type: application/json" --data-binary @examples/predict-bad-hr.json
curl -s -X POST localhost:8000/predict -H "Content-Type: application/json" --data-binary @examples/predict-nan-temp.json
docker logs bike-api
```

Expected: `200` with the model version, `200` with a prediction, then `422` naming
`hr`, then `422` naming `temp` (`NaN` is not a valid number here; it used to crash the
error handler and give `500`). `docker logs` shows one startup line
`... INFO bike_demand.api model loaded: version=... sha256=... dir=artifacts`.
To see the missing-model case, start the container with
`-e BIKE_MODEL_DIR=/nowhere`: `/health` and `/predict` answer `503` and the startup
line is `... ERROR bike_demand.api model not available: ...`. The interactive
contract is at http://localhost:8000/docs.

In Windows PowerShell type `curl.exe` (plain `curl` is an alias of
`Invoke-WebRequest`) and keep the body in a file as above: PowerShell 5.1 strips the
double quotes of an inline `-d '{"season":3,...}'` and the API answers `422`
`JSON decode error`. The same commands work with `curl.exe` and no other change.

### Run the tests locally

```bash
uv sync --locked
uv run --locked pytest -q -m api
```

The API tests build a tiny model in a temporary folder, so they do not need a trained
`artifacts/` directory. They cover a valid request, out-of-range values, wrong types,
missing and extra fields, `NaN`/`Infinity` inputs, the startup log line, a missing
model and a tampered model file.

---

The rest of this file is the course starter README, kept unchanged.

## Week 1 starter

Teams of 3–4 use one private GitHub repository throughout the course. Lab 1 is
repository setup, Git workflow and quality checks. Lab 2 adds validated data,
chronological splitting, a baseline comparison and local MLflow tracking.
No Docker, cloud account or MLflow server is needed this week.

## Setup: Lab 1

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`>=0.12.19,<0.13`). Python **3.12** is required; uv can download it. From the
`bike-demand/` root:

```bash
uv python install 3.12
uv sync --locked
uv run --locked python -m bike_demand.preflight
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q -m infra
uv run --locked pytest -q -m lab1
```

First setup requires internet for Python and the locked dependencies, unless
these exact distributions are already cached. The frozen UCI CSV ships here;
preflight does not download/repair it. `uv.lock` is shared across platforms;
that is not evidence that every OS has been tested. macOS setup has been checked;
Windows and Linux remain unverified. Remote CI is unavailable until a permitted
repository is configured and a workflow actually runs on the checked revision.
Do not regenerate the lock just to bypass an installation failure.

## Expected failure and exercise: Lab 1

`pytest -m infra` must pass immediately. `pytest -m lab1` has **one intentional
behavior failure** in `src/bike_demand/team.py`: the helper
`normalize_team_slug` does not yet meet the contract in `tests/lab1/test_team.py`
(trim, lowercase, join whitespace with hyphens, reject blank names with
`ValueError`). Read the assertion, diagnose the cause, make a small repair and add
one useful test of your own. Do not weaken assertions, skip tests or disable
checks. Sync or import errors, or failures outside `lab1`, are setup problems:
diagnose them separately.

Fill in `WORKING-AGREEMENT.md`. Use a task branch, open a pull request, and get a
review from another member before merging. Rotate driver/reviewer roles and the
main PR author between labs. Keep actual evidence in `reports/lab-01.md` and
`reports/week-01-team.md`; templates contain no pre-filled results.

## Expected failures: Lab 2

The student export has bounded TODOs in `src/bike_demand/`:

| File | Your task |
| --- | --- |
| `validate.py` | Categorical domains, finite normalised ranges, nonnegative counts, date windows |
| `split.py` | Chronological nonempty/disjoint/complete partitions; sort `(dteday, hr, instant)` |
| `train.py` | Ordered predictors, train-mean comparator, RF fit and validation MAE |

`NotImplementedError("TODO(Week 1, Lab 2): ...")` and failing exercise tests are
**expected before implementation**, not environment failures. Infra must pass
immediately. Do not skip/mute exercise tests or fabricate metrics to get green.
Tracking, metadata/history, configuration and input parsing are already supplied.
Read the failing test, inspect the contract, implement one TODO, and rerun:

```bash
uv run --locked pytest -q -m exercise
uv run --locked python -m bike_demand.validate --data data/raw/hour.csv
uv run --locked python -m bike_demand.train --config configs/baseline.yaml
uv run --locked pytest -q
```

Keep `data/raw/hour.csv` unchanged; use copies and `tests/fixtures/` for deliberate
faults. `missing-temp.csv` is the worked Fault A; design your own Fault B by
breaking exactly one contract rule or split boundary on a tiny copy, with a valid
control and a test of your own. The supplied `hum-out-of-range.csv` is another
worked example, not your Fault B. Missing hours are valid. Features and splits are fixed in the config and
code. Fit only on 2011 training rows; compare both predictors on the same
2012 January–June validation rows. Hold July–December 2012 test rows throughout
Weeks 1–4; do not compute test metrics. MAE is rentals/hour, not accuracy, and
RF is not required to beat the comparator. The task uses supplied weather;
it does not forecast future weather or station-level demand.

## Outputs and readback

Each successful train execution creates two separate MLflow runs, a saved
`artifacts/model.joblib` and `model-metadata.json`, latest `reports/metrics.json`,
and one appended `reports/metrics-history.jsonl` line. Metadata records feature
order, data identity, model version and run ID. A commit is recorded when Git is
available; `working_tree_dirty` prevents uncommitted code being mistaken for a
committed revision. Train reloads the trusted local model and verifies validation
MAE/metadata and logged artifact bytes. Never load untrusted joblib files.
Optional stretch, only after the core is complete and reviewed: run train again
unchanged and compare both run IDs and observed MAEs/history. Do not promise
byte-identical models across systems/library versions.

Viewer is optional; training does not depend on it:

```bash
uv run --locked mlflow server --backend-store-uri sqlite:///tracking/mlflow.db --default-artifact-root tracking/artifacts --no-serve-artifacts --host 127.0.0.1 --port 5000 --workers 1
```

`artifacts/`, `tracking/` and `.venv/` are ignored by Git. Team metrics may be
committed as evidence; never commit credentials or individual private reports.
CI currently checks only infrastructure/quality; expand it in Week 3.

## Support and individual reports

If setup remains blocked after five minutes, contact the instructor using the
support route recorded in your working agreement. Do not spend the whole lab
repairing a laptop. Ask for an approved recovery function only if coding remains
blocked; acknowledge the supplied code and assistance in your report. Recovery
is instructor-controlled, not bundled here.

## Names, reports and screenshots

Repository names (lowercase, hyphens, the same for the whole course):

- Team repository: `mlops-<session>-<team-name>-bike-demand`, for example
  `mlops-thu1-sparrows-bike-demand`. Sessions: `thu1`, `thu2`, `fri1`, `fri2`
  (1 = morning, 2 = afternoon).
- Your private report repository: `mlops-<session>-<github-username>`, for example
  `mlops-thu1-minhtc`. You create it and invite the instructor (`minhtc-uca`). Start from the
  [report template](../report-template/README.md) and commit to `main`; no report
  pull request or CI is used.

Reports mix writing and images. Save screenshots in `reports/images/` and embed
them in the report (see the template). A screenshot supports, but does not replace,
the command, revision and your explanation. Never show tokens, passwords or
personal data. Team evidence goes in `reports/lab-01.md` and
`reports/week-01-team.md`, with team screenshots in `reports/images/`.
Each weekly report is due Sunday 23:59 of the same week (published time zone).
Assessment policy comes from the instructor, not this repository.
See `BACKLOG.md` for later labs.
