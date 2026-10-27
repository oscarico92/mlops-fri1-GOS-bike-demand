# Week 2, Labs 3–4: team record

Team GOS: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).
Lab 3 lead: Simon. Raw logs: [`logs/lab-03/`](../logs/lab-03/), [`logs/lab-04/`](../logs/lab-04/).

## Lab 3: same code, clean environment

### Areas, owners and reviews

| Area | Owner | PR | Reviewer | Main finding and response |
| --- | --- | --- | --- | --- |
| Lock | Gautier | #8 | Simon | Logs in two places, `.gitattributes` needs a re-checkout on old clones, container case missing. Fixed in `296a14d`. |
| Dockerfile + `.dockerignore` | Simon | #9 | Gautier | Model SHA-256 explanation wrong, no commit in the image, bases not pinned. Fixed in `c95e9f0` (digests + `org.opencontainers.image.revision` label), rerun in `6132c6a`. |
| README (build and rerun) | Oscar | #10 | Gautier | Wrong statement on `model_sha256`, missing `--network none`, merge order. Fixed in `75176c9`; build-arg added in #9. |

Merge order: #8 (`883a387`), #10 (`0bdfe53`), #9 (`236773e`).

### Locked

- Every install uses `uv sync --locked`; CI runs `uv lock --check` first.
- Missing and stale lock both fail (`scripts/lock_check_demo.py`, 7/7 cases on Windows and macOS,
  [`lock-demo.txt`](../logs/lab-03/lock-demo.txt)). `uv sync --frozen` passes a stale lock silently,
  which is why it is never used.
- In the container: a stale `pyproject.toml` stops `docker build` at `uv sync --locked` with
  "The lockfile at `uv.lock` needs to be updated" ([`stale-lock.log`](../logs/lab-03/stale-lock.log)).
- `uv.lock` SHA-256 `8598f1f2…` on Windows, macOS and Linux after `.gitattributes` (`uv.lock -text`).

### Packaged and rerun

Commit `c95e9f0` → image `sha256:0adc2f05…` (macOS arm64, label = commit) → run with `--network none`.

| Value | Lab 2 (native Windows) | Container, macOS arm64 (Simon) | Container, Windows x86_64 (Gautier, `b6faef1`) |
| --- | --- | --- | --- |
| Preflight / tests | passed / 51 passed | passed / 51 passed | passed / 51 passed |
| MAE, train mean | 154.23 | 154.23 | 154.23 |
| MAE, random forest | 86.85 | 86.85 | 86.85 |
| `model_sha256` | `fd98ceaf…` | `d24c050e…` | `d24c050e…` |

Explained differences: `training_commit` is `unavailable` because `.git` is not in the image (the image label
carries the commit); the model bytes differ from native Windows but are identical in the container on two
hosts and two architectures; run IDs and `model_version` are new on every run.

Missing evidence: the final rerun from `main` by a non-author, following only the README, is not recorded
yet. Owner: Oscar.

## Lab 4: prediction API

Branch `lab-04-api`, code commit `b3a019c`. See the README section "Prediction API (Lab 4)" for the contract.

### Design decisions

- **Serve, never train.** The service loads `model.joblib` + `model-metadata.json` at startup and checks the
  SHA-256 from the metadata. The image produces the Lab 2 model once at build time, so each image carries one
  fixed model; `model_version` comes from the metadata.
- **One model state.** `/health` and `/predict` read the same state: `200` only with a usable model,
  otherwise `503` with the reason. A tampered model file is not served.
- **Validation before inference.** Pydantic, strict types, ranges from the data contract, finite values.
  Extra fields are rejected (`422`), so `cnt`, `casual` and `registered` cannot be sent. Invalid input still
  gets `422` when no model is loaded: the client error is reported first.

### Verify (in the container)

macOS 27.0.1 arm64, fresh clone of `lab-04-api` at `b3a019c`, image `sha256:df6fb4db…`.

| Check | Result | Log |
| --- | --- | --- |
| Tests in the image (`--network none`) | 79 passed (28 API tests) | [`pytest-in-image.log`](../logs/lab-04/pytest-in-image.log) |
| `GET /health` | `200`, `model_version` `baseline-0f688045396d`, `model_sha256` `d24c050e…` | [`http.txt`](../logs/lab-04/http.txt) |
| `POST /predict`, valid | `200`, prediction 519.49 | [`http.txt`](../logs/lab-04/http.txt) |
| `POST /predict`, `hr=24` | `422`, field `hr` named | [`http.txt`](../logs/lab-04/http.txt) |
| No model (`BIKE_MODEL_DIR=/nowhere`) | `503` on `/health` and on a valid `/predict` | [`http-no-model.txt`](../logs/lab-04/http-no-model.txt) |

The model served has the same SHA-256 as the Lab 3 container rerun (`d24c050e…`). No test-set metric is
computed. Local test runs and CI are separate claims: CI runs `pytest -m api` on the PR, not in the image.

Pending: review of the Lab 4 PR (one bad request and one missing-model case by each reviewer), merge, tag `m2`.

## Assistance

Course starter code and slides. Claude (AI assistant) was used by Simon to draft the Dockerfile, the API, its
tests and this record; every result above comes from commands run on our machines.
