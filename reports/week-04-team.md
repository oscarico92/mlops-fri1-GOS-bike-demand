# Week 4, Labs 7–8: team record

Team GOS: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`).
Raw logs: [`logs/lab-07/`](../logs/lab-07/), [`decisions/`](../decisions/), [`logs/lab-08/`](../logs/lab-08/).
State as of 10 November 2026, 22:10 UTC (`main` at `8c0cc62`; the incident record #38 is under review). All times UTC.

## Lab 7: pipeline, quality gate, accepted-state boundary

### Areas, owners and reviews

| Area | Owner | PR | Reviewer | Main finding and response |
| --- | --- | --- | --- | --- |
| Gate policy and decision function, committed before any candidate is decided | Gautier | #25 | Simon | Ran it merged with #23: 140 passed, shallow-forest rejected. Found that the pipeline marked the tree dirty because of its own decision records (fixed in #23, `43f3fa6`). Merged `140d47d`. |
| Pipeline entry point (`bootstrap`, `run`, `promote`, `status`, `restore`) and accepted-model registry | Simon | #23 | Gautier, Oscar | Gautier's challenge (C1-C4): second run blocked by the pipeline's own output (C2), a gate exception left no decision record (C4); both fixed and re-checked by Gautier. Oscar: bootstrap must register the reviewed bytes (`d24c050e…`, not the native Windows `fd98ceaf…`), evidence on a clean tree. Merged `44a5edd`. |
| Reviewer challenge: predictions before running | Oscar | #35 | Simon | Predictions committed before the run. D (rejected bundle copied with its metadata over `accepted/baseline`) was not detected: `restore` rewrote `current.json` with the rejected SHA and the gate then accepted deep-forest. Merged `e3d0d64`. |
| Fix for the #35 finding | Oscar | #36 | Simon | Accepted bundles are now checked against a record outside the bundle (`configs/expected-model.json` for the baseline, the committed accept decision otherwise); `status` exits 1 when a version is not usable; 3 tests. D now fails closed. Merged `339a1b8`. |

### Gated runs (Simon, macOS 27.2 arm64, commit `244a633`, clean tree, policy of #25)

| Candidate | Validation MAE | Outcome | Reason | Record |
| --- | --- | --- | --- | --- |
| shallow-forest (max_depth 6) | 90.62 | reject, exit 2 | worse than the accepted baseline (86.85) | `decisions/20261110T143923Z-775fcb.json` |
| deep-forest (100 trees, max_depth 20) | 86.11 | reject, exit 2 | 0.73 better, below the 1.0 margin | `decisions/20261110T143925Z-bc9a2f.json` |

Accepted state after both runs: `baseline`, `d24c050e…`, bytes verified ([`gate-run/status.txt`](../logs/lab-07/gate-run/status.txt)).
Nothing qualified, so nothing was promoted and Cloud Run kept serving the accepted baseline; no extra candidate was
run to search for a pass. Disclosure: shallow-forest's MAE was already computed once before the policy existed (the
blocked run `decisions/20261109T182707Z-f3eaf0.json`, kept as history).

### Reviewer challenge (#35, #36)

| # | Prediction | Before the fix (`e7f7202`) | After the fix (`d9f1087`) |
| --- | --- | --- | --- |
| A | reject, state unchanged | holds | holds |
| B | blocked on a dirty tree | holds | holds |
| C | one appended byte fails closed | `restore` exit 1, but `status` exit 0 | `status` exit 1 |
| D | consistent substitution not detected | not detected; deep-forest **accepted** against a rejected incumbent | `status` and `restore` exit 1, `run` blocked |

Evidence: [`logs/lab-07/challenge-oscar/`](../logs/lab-07/challenge-oscar/).

## Lab 8: signals, runbook, incident drill, verified rollback

### Roles and areas

| Area | Owner | PR | Reviewer |
| --- | --- | --- | --- |
| Workload and signal definitions (`scripts/workload.py`, `scripts/signals.py`) | Simon | #30 | Gautier (cases C-F added after his review) |
| Runbook | Gautier | #34 | Simon (project id, access roles, `remoteIp` redaction, read logs again before calling a request missing) |
| Baseline 1 (revision 00009, `6e97194`) | Simon | #33 | — |
| Drill: injector, rollback, template cleanup | Oscar | #37 | Simon |
| Drill: operator, baseline 2, incident and recovery evidence, incident record | Simon | #38 | Gautier, Oscar |

Oscar was the only member who could change the service; Simon (operator) had `run.viewer` and `logging.viewer`.

### Incident (details in [`reports/lab-08-incident.md`](lab-08-incident.md), #38)

- Fault (Oscar, 19:57:44-19:58:04): revision `00011-z46`, same image, `BIKE_MODEL_DIR=/app/artifacts/v2` (folder
  absent), 100 % of the traffic.
- First signal (Simon, 20:10:31): `/health` and `/predict` 503. Workload at 20:11:27: 0/40 valid good (40 × 503),
  10/10 invalid still 422, `model_version` None.
- Diagnosis: image digest unchanged (code ruled out), startup error names the configured path (configuration
  confirmed). Simon's rollback attempt refused by IAM at 20:11:40, as the runbook says; command handed to Oscar.
- Rollback (Oscar, 20:17:47): 100 % on `00010-m4d`. Recovery (Simon, 20:20:05): 40/40 good.
- Cleanup (Oscar, 20:49:37, found by the operator): `BIKE_MODEL_DIR` removed from the service template, otherwise the
  next deploy from `main` would have inherited it.

| Signal (40 valid + 10 invalid) | Baseline 2 | Incident | Recovery |
| --- | --- | --- | --- |
| success rate | 1.0 | 0.0 | 1.0 |
| intentional 422 / invalid accepted | 10 / 0 | 10 / 0 | 10 / 0 |
| latency p50 / p95 (ms) | 12.0 / 13.8 | none | 9.0 / 13.1 |
| identity | c2fc401 / baseline-637fa42462b2 | c2fc401 / None | c2fc401 / baseline-637fa42462b2 |

## Process deviations (recorded, not hidden)

- #33, #34, #35 and #36 were merged within one minute (17:40 UTC) while `main` was meant to stay frozen for the drill;
  the deploy redeployed the service (revision `00010-m4d`, `c2fc401`), so baseline 1 no longer described the live
  revision. Simon recorded a second baseline on `00010-m4d` before the drill (`logs/lab-08/baseline-00010/`).
- #35 and #36 were approved by Simon at 17:37-17:38 and merged two to three minutes later, together with #33, whose
  title said "do not merge until the drill is over".
- #37 asked to be merged together with the incident record; it was merged at 21:08, before #38 was reviewed.
- Personal data: the first Cloud exports of #38 still contained e-mail addresses; the branch was rewritten before
  review so they never reached `main`. The `callerIp` values in the #33 exports are GitHub runner addresses, not
  personal data, so those merged files were left unchanged.
- Simon's rollback attempt at 20:11:40 was made through an AI coding agent; IAM refused it.

## Missing evidence and next actions

| Missing | Owner |
| --- | --- |
| Review and merge of #38 (incident record and evidence) | Gautier, then Simon |
| Runbook followed by a member who did not write it, on a quiet service | Gautier / Oscar |
| Detection: the operator looked because the drill was announced; nothing watches the service, so the real detection time is unknown | team |
| Tag `m4` once #38 and this record are merged | team |

## Assistance

Course slides and starter code. Assistance used by each member is stated in their own PRs. This record was drafted
by Simon with Claude from the merged PRs and logs; every value above comes from a committed log, a decision record or
a GitHub review.
