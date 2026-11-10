# Week 3, Labs 5–6: team record

Team GOS: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).
Raw logs: [`logs/lab-05/`](../logs/lab-05/), [`logs/lab-06/`](../logs/lab-06/). State as of 9 November 2026, after the merges of that evening (`main` at `46ff046`).

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

| Area | Owner | PR | Reviewer | State |
| --- | --- | --- | --- | --- |
| Container job + README "CI" | Simon | #18 | Gautier | Merged (`e88797a`); red then green on the same PR, see below. |
| Regression tests that recompute the recorded baseline | Gautier | #22 | Oscar | Merged (`f4d5a47`). Tolerance runs committed (`logs/lab-06/regression/tolerance-runs.txt`); `scripts/regression_can_fail.py` shows each test turning red. |
| Cloud Run deploy workflow | Oscar | #21 | Simon | Merged (`e76551f`), first deploy in #28. Review points on the gate race, the Cloud Run identity check and the undo target were not addressed before merge; follow-up PR #29. |
| Deliberate-defect PR (reviewer challenge of #18) | Gautier | #26 | Simon | Prediction written before CI: only the container job turns red. Observed: "Week 1 checks" green, "Container checks" red on `code_revision` (`unknown`). Merged by mistake, see below. |

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

### Red to green on `main` after #26 (runner evidence)

| Commit | Result |
| --- | --- |
| `edc863a` (#26 merged, `ENV GIT_COMMIT` removed) | "Container checks" red at "Check model and code from outside the container": `code_revision` expected `edc863a…`, observed `unknown`, image label ok. Deploy did not run (gated on green). |
| `c893a30` (#27 restores `ENV GIT_COMMIT`) | push run: first attempt red, re-run green with no change. **Cause not identified: open question, not counted as green.** |

Cause of the red on `edc863a`: the image label is only visible from outside the container; `/health` reads
the `GIT_COMMIT` environment variable, which #26 removed.

### First Cloud Run deploy (#28, Oscar)

- Project `mlops-ece-group2`, region `europe-west1`, service `gos-bike-demand`; deployed commit
  `c893a30`, revision `gos-bike-demand-00001-lc9`.
- "Deploy to Cloud Run" on `c893a30`: success, live check passed (artifact `live-check-c893a30…`).
- `/health` on Cloud Run: `code_revision` `c893a30…`, `model_sha256` `d24c050e…`, the same model as every container.
- Deployed by this repository's `main` identity through the `gos-github` Workload Identity pool: no key, no person.
- Evidence: [`logs/lab-06/deploy-oscar/`](../logs/lab-06/deploy-oscar/).

Both workflows were green on `main` after the merges of 27 October (`e88797a`) and 5 November (`d597309`). These are runner facts for
those commits; local MLflow runs and laptop models are not CI evidence.

## Process deviations (recorded, not hidden)

- #14 was merged by its reviewer (Oscar) after a "Comment" review written before the fixes, not an
  approval; our rule is that the author merges after approval.
- #18: the only approval on it describes #19 (Gautier's review was posted on the wrong PR), so the container
  workflow itself was not reviewed; it was merged about 12 seconds before the container job on its last
  commit finished (it finished green).
- `main` was rewritten after #12 to remove two commit trailers; #13 was closed and replayed as #14. #17 now
  forbids rewriting `main`.
- #21, #22 and #26 were merged by Oscar within one minute; #26 was the deliberate-defect PR ("do not merge")
  and was merged without waiting for its container check, which left `main` red until #27. The check itself
  worked: nothing was deployed from the red commit.
- My review of #21 was not addressed before merge (only the line endings); follow-up in #29.
- Creating the Workload Identity pool was denied with our roles; Oscar added
  `roles/iam.workloadIdentityPoolAdmin` to his own account (binding added, nothing removed), recorded in
  `docs/cloud-run-setup.md`.

## Missing evidence and next actions

| Missing | Owner |
| --- | --- |
| Rollback on Cloud Run not exercised yet (needs a second revision) | Oscar |
| `live-check.txt` committed under `logs/lab-06/deploy-oscar/` | Oscar |
| Follow-up of the #21 review (gate race, Cloud Run identity, undo target): PR #29 | Oscar, review by Simon |
| Cause of the first red attempt on `c893a30` | Oscar |
| Tag `m3` once the above is merged | team |

## Assistance

Course slides and starter code. Assistance used by each member is stated in their own PRs. This record was drafted by Simon with Claude from the merged PRs and logs; every value above comes
from a committed log or a GitHub run.
