# Release v1.0.0: Bike Demand (team GOS)

Hourly bike rental demand (`cnt`) from calendar and weather, served by a FastAPI service on Cloud Run.
Team GOS, session fri1: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).
This file is the source of the text on the GitHub Release page; values marked `TO FILL` are taken after the
final merge and deploy, from the runs named next to them.

## Identities

| What | Value | Source |
| --- | --- | --- |
| Commit (tag `v1.0.0` on `main`) | TO FILL | `git rev-parse v1.0.0^{}` |
| Model version | `baseline` (accepted in Lab 7 registry; `model_version` in the image: TO FILL, per build) | `/version` |
| Model SHA-256 | `d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07` | `configs/expected-model.json`, `/version` |
| Data SHA-256 | `e03de4ee4ef4dc376ac6e04bf829673c6269e8eba5c60fa121640fa2f829504f` | `data/manifest.json` |
| Image | `europe-west1-docker.pkg.dev/mlops-ece-group2/gos-bike-demand/bike-demand:<commit>`, digest TO FILL | deploy run artifact `live-check-<commit>.txt` |
| Cloud Run | service `gos-bike-demand`, region `europe-west1`, revision TO FILL, 100 % of the traffic | same file |

The model SHA-256 is the identity; `model_version` changes with every image build (same bytes).

## Final evaluation (held test, run once)

Plan merged before the run (#41, `configs/final-evaluation.yaml`, SHA-256 `6d0ad4fb…`); one run on 12 November 2026,
19:52 UTC, commit `a9f3cae`, macOS; record `logs/week-05/final-evaluation.json` (PR TO FILL).

| Rows | Window | Test MAE | Naive train-mean MAE | Validation MAE (recomputed) |
| --- | --- | --- | --- | --- |
| 4,376 | 2012-07-01 to 2012-12-31 | **93.74** rentals/hour | 182.21 | 86.85 |

All predictions finite and non-negative. As written in the plan before the run, the test MAE is higher than the
validation MAE (demand in Jul-Dec 2012 is higher than in the 2011 training year). The result was not used to choose:
no model, feature, setting or data change followed. One earlier attempt was refused by the script (untracked file in
the tree) before any evaluation.

## Verification

| Check | Result | Link |
| --- | --- | --- |
| Week 1 checks (lint, tests by marker, regression, pipeline, final) on the tag commit | TO FILL | Actions run TO FILL |
| Container checks (tests in the image without network, label, outside check) | TO FILL | Actions run TO FILL |
| Deploy to Cloud Run + live check (`check passed`) | TO FILL | Actions run TO FILL |
| `GET /version` on Cloud Run | TO FILL (paste the JSON) | `curl -s $URL/version` |
| `GET /health` on Cloud Run | TO FILL | `curl -s $URL/health` |

## What is in the repository at the tag

- `README.md`: how to run, test and deploy; `RUNBOOK.md`: recovery procedure.
- `configs/`: training baseline, Lab 7 candidates and gate policy, expected model, final evaluation plan.
- `src/`, `tests/`, `.github/workflows/`: code, unit / API / container / regression / pipeline tests, CI and deploy.
- `reports/`: team records (weeks 1-4), `lab-08-incident.md`; gate decisions in `decisions/`; raw evidence in `logs/`.

## Assets

- `model-baseline-d24c050e.tar.gz`: `model.joblib` + `metadata.json` of the accepted baseline (`artifacts/` and
  `registry/` are not in Git), and its `.sha256`.
- `final-presentation.pdf`: final presentation slides.

## Known limitations

- **The gate never accepted a candidate.** Both declared candidates were rejected (90.62 and 86.11 vs 86.85 with a
  1.0 margin); the only "accept" we saw came from the Lab 7 challenge on a deliberately corrupted registry, fixed in #36.
  The promotion path is tested, not exercised on a real improvement.
- **No monitoring or alerting.** In the Lab 8 drill the operator looked because the drill was announced; the real
  detection time is unknown. Signals exist (`scripts/workload.py`, `scripts/signals.py`) but nothing runs them on a
  schedule.
- **One person can change the service.** Only Oscar holds a role that can run `update-traffic`; the rollback waited for
  him (about 6 minutes in the drill).
- **Model bytes depend on the platform.** Native Windows trains other bytes (`fd98ceaf…`); the reviewed bytes come from
  macOS, Linux and the image. Bootstrap refuses other bytes.
- **The model is trained once on 2011.** Test error is higher than validation error; no retraining on 2012 data was
  done, by design of the held-test rule.
- **Process deviations** are recorded in `reports/week-03-team.md` and `reports/week-04-team.md` (merges before
  approval or during the drill freeze, `m3` tag moved). #41 was merged after a review written as "Approved" but
  submitted as a comment.

## Assistance

Course slides and starter code. Each member states the AI assistance they used in their own PRs and reports.
