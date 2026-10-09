# Week 1, Labs 1–2: team evidence

## Team and roles

Team GOS, repository `oscarico92/mlops-fri1-GOS-bike-demand`: Oscar Schwartz (`oscarico92`),
Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).

- Lab 1: Oscar lead author, Gautier reviewer, Oscar evidence recorder. Details in [lab-01.md](lab-01.md).
- Lab 2: Gautier lead author, Oscar reviewer, Simon evidence recorder.

## Repository and pull requests

- Lab 1: PR #1 (`lab-01-workflow`, helper repair + added test), PR #2 (`lab-01-report`, worksheet).
- Lab 2: branch `lab-02-data-baseline`, PR #3 _(link once opened)_.
  - `06093bf` Implement data contract, chronological split and baselines (`validate.py`, `split.py`, `train.py`).
  - `85d3d32` Add Fault B: Feb 29 in a non-leap year is rejected (fixture + test).

## Setup, preflight and quality checks (commands and actual results)

Run by Gautier on Windows 11 Famille 10.0.26200 (64-bit), Python 3.12.15, uv 0.12.23, on `85d3d32`:

| Command | Observed result |
| --- | --- |
| `uv sync --locked` | 97 packages checked, lock unchanged |
| `uv run --locked ruff check .` | All checks passed |
| `uv run --locked ruff format --check .` | 11 files already formatted |
| `uv run --locked pytest -q` | 51 passed, 1 warning (SQLAlchemy deprecation raised inside MLflow) |

CI on the pushed PR revision: _(to record from the PR checks once pushed)_.

## Data identity, validator checks and added test

- Canonical data: `data/raw/hour.csv`, SHA-256 `e03de4ee4ef4dc376ac6e04bf829673c6269e8eba5c60fa121640fa2f829504f`,
  17,379 rows; bytes unchanged after every command (preflight checks the manifest).
- `validate --data data/raw/hour.csv` → `Validated 17379 rows; input bytes unchanged.`
- Rules enforced in `check_domains`: integer categories in their domains (season 1–4, yr/holiday/workingday
  0–1, mnth 1–12, hr 0–23, weekday 0–6, weathersit 1–4); temp/atemp/hum/windspeed finite in [0, 1];
  cnt/casual/registered nonnegative integers; dteday within 2011-01-01..2012-12-31. Each rejection names the
  field; nothing is filled, clipped or dropped.
- Added test: `tests/exercise/test_fault_b.py` (see Fault B below).

## Partition counts, boundaries and held test rows

Sorted by `(dteday, hr, instant)`, inclusive intervals, nonempty/disjoint/complete checked in `split_data`.

| Partition | Interval | Rows | First (dteday, hr, instant) | Last (dteday, hr, instant) |
| --- | --- | --- | --- | --- |
| train | 2011-01-01 – 2011-12-31 | 8,645 | (2011-01-01, 0, 1) | (2011-12-31, 23, 8645) |
| validation | 2012-01-01 – 2012-06-30 | 4,358 | (2012-01-01, 0, 8646) | (2012-06-30, 23, 13003) |
| test (held) | 2012-07-01 – 2012-12-31 | 4,376 | (2012-07-01, 0, 13004) | (2012-12-31, 23, 17379) |

8,645 + 4,358 + 4,376 = 17,379. Test rows are counted only; no test metric is computed.

## Comparator and RF: run IDs, validation MAEs, metadata/readback

`uv run --locked python -m bike_demand.train --config configs/baseline.yaml` on training commit
`85d3d328c988a49d06a662bee4638be3fe0bf75d`, `working_tree_dirty: false`, 2026-10-09T10:24:50Z.

| Predictor | MLflow run ID | Validation MAE (rentals/hour) |
| --- | --- | --- |
| Training-label mean (143.79) | `978122b6e59648e7b48b444128c728d0` | 154.23 |
| Random Forest (50 trees, depth 10, seed 42) | `fdeed96296154828a8dbc5be2299aa7f` | 86.85 |

- Both fitted on the 8,645 train rows only, evaluated on the same 4,358 validation rows.
- The RF lowers validation MAE by about 67 rentals/hour versus the mean; this is one fixed comparison,
  not a tuned or test-set result.
- Model version `baseline-2d1d6f765429`, model SHA-256 `fd98ceaf…c49c304`.
- Readback: reloaded `artifacts/model.joblib` gives MAE 86.85 (delta 0.0), metadata matches the run,
  logged model bytes match the saved file, max prediction delta 0.0.
- Evidence: `reports/metrics.json`, `reports/metrics-history.jsonl` (committed); tracking DB and model stay local.

## Optional stretch, after the core: unchanged-config repeat (new run IDs, history, differences)

Not attempted as a planned stretch. Note: an earlier run (`naive 3a847cce…`, `rf f27c6667…`) was discarded
because it recorded `working_tree_dirty: true`; it gave the same MAEs and the same model SHA-256.

## Fault diagnosis and your own Fault B

- Fault A (worked): `missing-temp.csv` → `Validation failed: Missing required columns: temp`.
- Choice: Fault B breaks the "parseable dates" rule with `2011-02-29` (2011 is not a leap year) in a
  6-row copy (`tests/fixtures/feb-29-non-leap-year.csv`), all columns kept, one value changed.
- Reason: the value has the right `YYYY-MM-DD` shape, so a format-only check would accept a day that does not
  exist; real leap days must stay valid (the canonical CSV has 23 rows on 2012-02-29).
- Result: `Validation failed: dteday: invalid date values`; controls `2011-02-28` and `2012-02-29` pass;
  fixture bytes unchanged. Limitation: the validator does not cross-check `dteday` against `mnth`/`yr`/`weekday`.

## Review observation and author's response

_(Oscar's review observation on PR #3 and Gautier's response, once posted.)_

## Contribution and assistance/recovery acknowledgement

- Gautier: implemented the Lab 2 TODOs and Fault B, ran the checks and training on his machine.
- Oscar: review of PR #3.
- Simon: evidence recording.
- Starter code, tests, tracking helpers and fixtures supplied by the course.
- _(Other assistance: to complete by the team.)_

## Blockers and next action

- Blocker found and fixed: the first training run was marked dirty because a shell redirect created an
  untracked output file before the run; outputs removed and training rerun on a clean tree.
- Local clock was about 10 h behind; corrected before the recorded run.
- Next: Oscar reviews PR #3; merge after approval and green CI; tag `m1`.

## Screenshots

_(pytest, validator output and MLflow runs: to add in `reports/images/`.)_
