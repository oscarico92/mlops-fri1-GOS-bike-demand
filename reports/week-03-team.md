# Week 3, Labs 5–6: team record

Team GOS: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).
Raw logs: [`logs/lab-05/`](../logs/lab-05/), [`logs/lab-06/`](../logs/lab-06/). State as of 9 November 2026.

## Lab 5: service deployment, structured logs, model-version checks

### Areas, owners and reviews

| Area | Owner | PR | Reviewer | Main finding and response |
| --- | --- | --- | --- | --- |
| Check from outside (model and code) | Simon | #14 (replaced #13) | Oscar | Evidence from a commit outside the PR, `code_revision` can be faked with `docker run -e`, README did not say which commit to check from. Rebuilt and reran on `2f9b97a`, added the image label comparison (`--container`). |
| One JSON log line per request | Gautier | #16 | Simon | No code identity in the log line, README conflict with #14. `code_revision` added to every line, merged after #14. |
| README "Deploy": definition, ten questions, break it once | Oscar | #19 | Simon | Described the #16 logs before #16 was on `main`, no evidence of its own for the failure, empty description. Merged `main`, added `logs/lab-05/deploy-oscar/`. |

Merge order: #14 (`0b70e87`), #16 (`2a1d97f`), #19 (`38f296d`). Also merged: #17 (CONTRIBUTING forbids
rewriting `main`, after the history rewrite of #12's commits).

### What "deployed" means

From the README: a container started from an image built from a known commit of `main`, answering on
`127.0.0.1:8000`, for which `scripts/check_deployment.py --container bike-api` exits `0` when run from a
checkout of that same commit. The final check is run by a member who did not write the change.

### Commit → image → run

| Run | Machine | Commit | Image | Result | Log |
| --- | --- | --- | --- | --- | --- |
| Check (Simon) | macOS arm64 | `2f9b97a` | `sha256:0db4844e…` | 7/7 `ok`, exit 0; wrong revision, `-e GIT_COMMIT` override and no model all fail on the right claim | [`check-*.txt`](../logs/lab-05/) |
| Logs (Gautier) | Windows x86_64 | `79a81a9` | `sha256:7e5106aa…` | 99 passed in the image; one JSON line per request, no input values, no client address | [`logging/`](../logs/lab-05/logging/) |
| Deploy section (Oscar, README only) | Windows x86_64 | `b9bfdb2` | `sha256:e5dd254a…` | normal start: check exit 0; break it once: check exit 1 | [`deploy-oscar/`](../logs/lab-05/deploy-oscar/) |

The served model is `d24c050e…` in every run (same bytes on macOS arm64 and Windows x86_64 containers),
and the code revision reported by `/health` and by the image label equals the commit.

### Break it once

Failure caused: the same image started with `-e BIKE_MODEL_DIR=/nowhere`. Observed (Oscar's run):
`/health` answers `503` with the reason and still reports `code_revision`; the check exits `1` and fails on
ready, `model_sha256`, valid `/predict` and `model_version` while revision and label still match, so the
failure points to the model, not the code; `docker logs` shows the startup `ERROR … model not available`
line and one `"outcome":"model_unavailable"` line per request. What it leaves behind: a running container
answering `503` (no crash), nothing written to the image or the host; it is removed with `docker rm -f`.

## Lab 6: CI checks, regression tests, delivery

### Areas, owners and reviews

| Area | Owner | PR | Reviewer | State on 9 November |
| --- | --- | --- | --- | --- |
| Container job + README "CI" | Simon | #18 | Gautier | Merged (`e88797a`). Red then green on the same PR, see below. |
| Regression tests that recompute the recorded baseline | Gautier | #22 | Oscar | Open. CI green; review asks for the runs behind the tolerance numbers and a note on the test map. |
| Cloud Run deploy workflow | Oscar | #21 | Simon | Open. Adapted to the shared project `mlops-ece-group2-and-group3` (`gos-` prefix, direct Workload Identity Federation). No deploy run yet; review asks to restore LF line endings in the README and to fix the gate race, the Cloud Run identity check and the undo target. |

### Red to green on PR #18 (runner evidence)

| Run | Commit | Result |
| --- | --- | --- |
| 1 | `85fc8b5` (workflow only) | red at "Tests inside the image, without network": `FileNotFoundError: /app/scripts/check_deployment.py`, exit 2 ([`run1-red.txt`](../logs/lab-06/run1-red.txt)) |
| 2 | `8e43930` (`COPY scripts ./scripts`) | green |
| 3 | `eb70da7` (merged with `main`) | green, `check passed` 7/7 |

Cause: #14 added a test that loads `scripts/check_deployment.py`, but the Dockerfile never copied
`scripts/`. The first workflow runs the tests on the runner, where the folder exists, so it stayed green;
only a test run inside the image could see it. Gautier found the same bug independently in #16. The cause
was fixed; no test was skipped or muted.

Both workflows are green on `main` after each merge (`e88797a`, `d597309`). These are runner facts for
those commits; local MLflow runs and laptop models are not CI evidence.

## Process deviations (recorded, not hidden)

- #14 was merged by its reviewer (Oscar) after a "Comment" review written before the fixes, not an
  approval; our rule is that the author merges after approval.
- #18: the only approval on it describes #19 (Gautier's review was posted on the wrong PR), so the container
  workflow itself was not reviewed; it was merged about 12 seconds before the container job on its last
  commit finished (it finished green).
- `main` was rewritten after #12 to remove two commit trailers; #13 was closed and replayed as #14. #17 now
  forbids rewriting `main`.

## Missing evidence and next actions

| Missing | Owner |
| --- | --- |
| Deliberate-defect PR by a reviewer (a check must turn red) | Gautier |
| Regression tests merged (#22) | Gautier, review by Oscar |
| First deploy run and `live-check.txt` from Cloud Run (#21) | Oscar, review by Simon |
| Tag `m3` once the three items above are merged | team |

## Assistance

Course slides and starter code. Each member used Claude (AI assistant) for parts of their work, as stated in
their PRs. This record was drafted by Simon with Claude from the merged PRs and logs; every value above comes
from a committed log or a GitHub run.
