# Lab 8 incident record: 503 on every valid prediction (10 November 2026)

Operator: Simon (diagnosis, workloads, evidence). Injector and rollback: Oscar (only team member allowed to change
the service). Reviewer: Gautier. All times are UTC. Every claim below points to a file under `logs/lab-08/`.

## Summary

At 19:57:44 a manual `gcloud run services update` created revision `gos-bike-demand-00011-z46` with the same image
as the healthy revision but with `BIKE_MODEL_DIR=/app/artifacts/v2`, a folder that does not exist in the image; the
traffic switch to it was requested at 19:57:50 and had returned by 19:58:04 (`/health` 503). The service started without a model: `/health` and every valid
`/predict` answered 503, invalid requests were still rejected with 422. The operator saw it at 20:10:31, measured it
at 20:11:27 (0/40 valid requests good), traced it to the configuration boundary, and asked for a rollback.
Traffic went back to `00010-m4d` at 20:17:47; recovery was measured at 20:20:05 (40/40 good, latency within the
baseline). At 20:49:37 the variable was removed from the service template so that the next deployment cannot
inherit it.

Impact: about 20 minutes (traffic on 00011-z46 from 19:57:50-19:58:04 to 20:17:47-20:17:53) during which no valid prediction could succeed. The operator was told by
the injector at 19:58 that the drill had started and looked 13 minutes later; that is the time to look once told,
not a detection time. Nothing watches the service, so without the drill message the fault would have stayed unnoticed
until someone used the service: the real detection time is unknown.

## Timeline

| Time (UTC) | Who | Event | Evidence |
| --- | --- | --- | --- |
| 17:44:57 | CI (deploy.yml) | revision 00010-m4d deployed from main c2fc401 | `recovery/revisions.txt` |
| 19:23:19 | Simon | second baseline on 00010-m4d: 40/40 good, p50 12.0 ms, p95 13.8 ms | `baseline-00010/signals.txt` |
| 19:57:36 | 00010-m4d | `model loaded: version=baseline-637fa42462b2 sha256=d24c050e…` | `incident/startup-and-errors.json` |
| 19:57:44 | Oscar (injection) | `gcloud run services update`: new revision 00011-z46, same image digest `sha256:134e4389…` | `incident/audit.json` |
| 19:57:50 | Oscar (injection) | `gcloud run services update-traffic`: 100 % to 00011-z46 (audit time of the request; the command returned at 19:58:04) | `incident/audit.json`, `injector-oscar/injector-log.txt` (#37) |
| 19:57:59 | 00011-z46 | `ERROR model not available: [Errno 2] No such file or directory: '/app/artifacts/v2/model-metadata.json'` | `incident/startup-and-errors.json` |
| 19:58:04 | Oscar | `GET /health` → 503 (curl), "model not available" | `incident/startup-and-errors.json`, `injector-oscar/injector-log.txt` |
| 19:58 | Oscar | message "The drill has started" sent to the operator on Discord (20:58 Paris time), without the cause | Oscar's review of #38, `injector-oscar/README.md` |
| **20:10:31** | Simon | **first signal**: `GET /health` → 503 and `POST /predict` → 503 on 00011-z46 | `incident/startup-and-errors.json` |
| 20:11:27-20:11:31 | Simon | incident workload, run 2011271286: 40 × 503, 10 × 422 | `incident/sent.jsonl`, `incident/signals.txt` |
| 20:11:40 | Simon | rollback attempt (`update-traffic` to 00010-m4d) refused: `run.services.update` denied (operator has `run.viewer`) | `incident/audit.json` |
| before 20:15:59 | Simon | diagnosis sent to Oscar with the rollback command (exact sending time not recorded; Oscar logged the request at 20:15:59) | operator notes below, `injector-oscar/injector-log.txt` |
| 20:17:47 | Oscar | `update-traffic`: 100 % to 00010-m4d (audit time; `/health` 200 checked at 20:17:53) | `incident/audit.json`, `recovery/rollback-oscar.txt`, `injector-oscar/injector-log.txt` |
| 20:18:03 | 00010-m4d | `model loaded: version=baseline-637fa42462b2 sha256=d24c050e…` | `incident/startup-and-errors.json` |
| 20:19:54 | Simon | outside check: `/health` 200, valid `/predict` 200, invalid 422, all on 00010-m4d | `recovery/cloud-logs.json` |
| 20:20:05-20:20:09 | Simon | recovery workload, run 20200467b4: 40 × 200, 10 × 422 | `recovery/sent.jsonl`, `recovery/signals.txt` |
| 20:49:37 | Oscar, at the operator's request | `--remove-env-vars BIKE_MODEL_DIR`: revision 00012-zkx created with no env vars, 0 % traffic; traffic still 100 % on 00010-m4d; `/health` 200 with c2fc401 / d24c050e… | `injector-oscar/injector-log.txt` (#37) |

## First signal

20:10:31, two requests from the operator's check (user agent `Python-urllib`, revision 00011-z46): `GET /health`
503 and `POST /predict` 503. Scope: every valid request; the following workload showed that input validation still
worked (10/10 invalid requests → 422), so the service was up but had no model.

## Operator notes (as written to the team during the incident)

1. Symptom: `/health` and `/predict` answer 503; error `model not available: … '/app/artifacts/v2/model-metadata.json'`;
   proof workload run 2011271286: 40 × 503, 10 × 422.
2. Boundaries: image identical to 00010 (digest `sha256:134e4389…` unchanged); configuration: `BIKE_MODEL_DIR=/app/artifacts/v2`
   on 00011-z46, folder absent from the image.
3. Rollback to 00010-m4d needed; the operator's role (`run.viewer`) cannot run `update-traffic`, as the runbook says,
   so the command was handed to Oscar.

The note says "503 since 19:57": that start time was read afterwards from the revision list and the logs, not
observed live.

## Hypotheses and discriminating checks

| Hypothesis | What it predicts | Check (runbook section 3) | Result |
| --- | --- | --- | --- |
| H1. New code or image | a different image digest or `code_revision` on the serving revision | digest of 00011-z46 vs 00010-m4d; `code_revision` in the log lines | **ruled out**: same digest `sha256:134e4389…`, all 50 incident lines carry `c2fc401…` |
| H2. Configuration of the new revision | a setting differs from the last good revision and the startup log names it | env vars of the revision; startup log | **confirmed**: `BIKE_MODEL_DIR=/app/artifacts/v2` only on the new template; startup error names that exact path |
| H3. Model bytes changed or corrupted | `/health` 503 with a checksum error, or another `model_sha256` | startup log of 00011-z46 | **not the cause**: the error is "No such file or directory", not a checksum mismatch; the model loaded from the default path in the same image is `d24c050e…` before and after |
| H4. Bad input traffic | the same requests answered as before | fixed workload, same ids scheme as the baseline | **ruled out**: identical requests; baseline 40 × 200, incident 40 × 503 |

Boundaries not checked: the platform itself (Cloud Run health of the region) was not checked separately; nothing in
the evidence points to it, since 00010-m4d answered normally before and after.

## Cause

A configuration change released outside the pipeline: a revision whose `BIKE_MODEL_DIR` pointed to a folder absent
from the image received all the traffic without any check. The API behaved as designed (no model → 503, invalid
input → 422, error logged at startup), which is why the cause could be read directly from the logs.

## Rollback and recovery

Rollback moved traffic only (no rebuild, no retrain): 100 % to 00010-m4d at 20:17:47. Recovery is verified on
identity **and** signals:

| Signal (same definitions, 40 valid + 10 invalid) | Baseline 2 (00010-m4d, 19:23) | Incident (00011-z46, 20:11) | Recovery (00010-m4d, 20:20) |
| --- | --- | --- | --- |
| logged / sent, missing | 50/50, 0 | 50/50, 0 | 50/50, 0 |
| success rate (good / eligible) | 1.0 (40/40) | **0.0 (0/40, all 503)** | 1.0 (40/40) |
| intentional 422 / invalid accepted | 10 / 0 | 10 / 0 | 10 / 0 |
| latency p50 / p95 / max (ms, good) | 12.0 / 13.8 / 14.1 | none | 9.0 / 13.1 / 16.2 |
| identity (code / model) | c2fc401 / baseline-637fa42462b2 | c2fc401 / **None** | c2fc401 / baseline-637fa42462b2 |

The first baseline (15:18, revision 00009, 6e97194) gave p50 10.7 ms and p95 14.6 ms with the same definitions; it is
kept for reference only, because merging #33 to #36 redeployed the service before the incident, so baseline 2 is the
one measured on the incident revision.

## What we change

1. **Done**: `BIKE_MODEL_DIR` removed from the service template (20:49:37), otherwise the next `gcloud run deploy` of
   `deploy.yml` would inherit it; its live check would fail and undo, but the deploy would fail.
2. Manual `gcloud run services update` on the shared service only through the runbook, with the change written in the
   team channel first; a configuration change goes through a reviewed pull request like code.
3. Detection: the operator only looked because the injector announced the drill; nothing would have noticed the
   fault on its own, so the real detection time is unknown. A scheduled run of `scripts/workload.py` + `signals.py`,
   or a Cloud Monitoring alert on the 5xx rate of the service, would detect it within minutes without being told.
4. The rollback depended on one person: a second team member with a role that can run `update-traffic` would remove
   that wait (here about 6 minutes between the refused attempt and the rollback; the injector's log also shows one mistyped
   command at 20:15:59 that executed nothing).

## Uncertainties and limits

- The state during the incident is reconstructed from Cloud Logging and audit logs exported after recovery; the
  revision's env vars were read from the service template (`recovery/service.json`), not from a `revisions describe`
  of 00011-z46 taken during the incident.
- The 20:10:31 and 20:19:54 requests are attributed to the operator from their user agent and timing; the outputs of
  those two checks were not saved as files.
- gcloud's "revision … is serving N percent of traffic" messages name the wrong revision when traffic is pinned
  (00010-m4d at injection, 00011-z46 at cleanup); the `Traffic:` lines, `status.traffic` and
  `latestCreatedRevisionName` (00012-zkx) are the source we use.
- Times differ by a few seconds between the audit log (when Cloud Run received a request) and the injector log
  (when the command returned); both are given.
- Personal data: e-mail addresses, `remoteIp` and `callerIp` were replaced or removed in every Cloud export
  (wider than runbook section 6, which only names `remoteIp`); nothing else was changed, and the signals computed
  before and after the redaction are identical. The exports of baseline 1 (#33) are left as merged: their
  `callerIp` values are GitHub runner addresses (checked in Oscar's review of #33), not personal data.
- The rollback attempt at 20:11:40 was made through the operator's AI coding agent; it was refused by IAM, as it
  should be.
