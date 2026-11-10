# Runbook: bike demand prediction service

For whoever is on call for the `gos-bike-demand` Cloud Run service (project `mlops-ece-group2-and-group3`,
region `europe-west1`). It says what normal looks like, how to find what changed, how to go back to a retained
version, and what to record. Every command below already exists in this repository; nothing here retrains.

## 1. What "working" means

| Check | Normal | Source |
| --- | --- | --- |
| Readiness | `GET /health` → `200`, with `model_version`, `model_sha256`, `code_revision` | `src/bike_demand/api.py` |
| Prediction | valid `POST /predict` → `200`, finite, ≥ 0, with the same `model_version` as `/health` | idem |
| Rejection | invalid input (e.g. `hr=24`) → `422`; valid input without a usable model → `503` | idem |
| Served model | `model_sha256` = `d24c050e…` | `configs/expected-model.json` |
| Served code | `code_revision` = the commit of the serving revision | `live-check-*.txt` of the deploy run |
| Signals | success rate, missing, invalid accepted, latency p50/p95, identity: as in the recorded baseline | `logs/lab-08/`, README "Service signals (Lab 8)" |

## 2. First look (cheapest checks first)

```bash
URL=$(gcloud run services describe gos-bike-demand --region europe-west1 --format='value(status.url)')
curl -s "$URL/health"                                              # identity and readiness
gcloud run services describe gos-bike-demand --region europe-west1 \
  --format='value(status.traffic)'                                 # which revision has the traffic
gcloud run revisions list --service gos-bike-demand --region europe-west1   # what was deployed, and when
python3 scripts/workload.py --url "$URL" --label check --valid 40 --invalid 10 --out logs/lab-08/check-sent.jsonl
# wait about a minute (Cloud Logging is not instant), then:
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="gos-bike-demand"' \
  --freshness=1h --format=json | python3 scripts/signals.py --label check --sent logs/lab-08/check-sent.jsonl
```

Save every output as it is, with its UTC time. Compare it with the baseline using the same definitions, the same
workload size and the same label scheme; do not compare against numbers measured with other definitions.

## 3. Find what changed, boundary by boundary

| Boundary | Question | Check | A mismatch means |
| --- | --- | --- | --- |
| Service | Which revision serves, since when? | traffic and revision list above | a new revision appeared: compare it with the last good one |
| Image and code | Which commit does it run? | `code_revision` in `/health` and in the log lines; image digest of the revision vs the digest in the deploy run's `live-check-*.txt` | code changed; `code_revision` alone can be overridden by an env var, the digest cannot |
| Model | Which model answers, are its bytes the reviewed ones? | `model_version` and `model_sha256` from `/health`; identity in `signals.py` | another or a modified model is served |
| Configuration | Which settings does the revision run with? | `gcloud run revisions describe <revision> --region europe-west1` (env vars, image, port) | e.g. a model directory, a revision or a variable that differs from the last good revision |
| Inputs | Did the requests change, or the service's answer to the same requests? | the fixed workload of section 2 (same requests every time); `invalid_accepted`, `eligible_statuses` | same requests answered differently: the service changed, not the traffic |

A mismatch is evidence, not yet a cause: say whether it explains the observed symptom. Write down the boundaries
you did not check.

## 4. Diagnose before acting

1. Record the **first signal** that looked wrong: UTC time, affected scope (which requests, which revision), the raw
   output that shows it.
2. Write **at least two hypotheses**, each with the observation it predicts.
3. For each, run one **discriminating check** from section 3 and record the actual result, including the checks that
   ruled a hypothesis out.
4. Only then name the cause, and say what remains uncertain.

Do not edit or delete raw outputs to match the final explanation.

## 5. Go back to a retained version (rollback)

When the cause is a release or an artifact (a new revision, image or model), go back to the last revision that was
verified good. Rollback moves traffic; it does not rebuild, redeploy or retrain.

```bash
gcloud run revisions list --service gos-bike-demand --region europe-west1          # find the last good revision
gcloud run services update-traffic gos-bike-demand --region europe-west1 \
  --to-revisions <last-good-revision>=100
curl -s "$URL/health"                                   # identity must be the last good one again
```

Then rerun the workload and `signals.py` with a **new label** (e.g. `recovery`), and the outside check:

```bash
python3 scripts/check_deployment.py --url "$URL" --expected-revision <commit of the last good revision>
```

Recovery is verified only when the identity is back (`model_sha256`, `code_revision`, digest) **and** the signals are
back within the baseline. A worked example: `logs/lab-06/deploy-oscar/rollback.txt`.

Rollback is the wrong tool when the cause is outside the release (input data, a dependency, the platform): then keep
the traffic where it is, guard or fix forward through a reviewed pull request.

## 6. Record

Keep one timeline (UTC) with: who did what, each observation and its raw file, each hypothesis and its result, the
rollback, the recovery check. Commit the raw outputs under `logs/lab-08/` and the incident record under `reports/`,
through a reviewed pull request.

## 7. Never

- touch another team's Cloud Run service;
- modify the accepted bundle (`registry/accepted/`), the raw data or committed evidence;
- retrain as a recovery action;
- call the service recovered from `/health` alone.
