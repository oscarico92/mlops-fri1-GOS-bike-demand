# Runbook: bike demand prediction service

For whoever is on call for the `gos-bike-demand` Cloud Run service (project `mlops-ece-group2`, shared with
other teams, region `europe-west1`). It says what normal looks like, how to find what changed, how to go back to a retained
version, and what to record. Every command below already exists in this repository; nothing here retrains.

**Access needed.** To diagnose: `roles/run.viewer` and `roles/logging.viewer` on the project. To roll back
(`update-traffic`): a role that can update the service, such as `roles/run.developer`. Without them the runbook stops
at section 2: ask someone who has them (see `docs/cloud-run-setup.md`) instead of working around it.

**Last verified:** 11 November 2026, by Oscar (not the author), on revision `00016-rwx`, commit `46af152`, from a fresh
Cloud Shell directory: sections 2, 3 and 5 (rollback rehearsal) worked as written; the seven gaps he found
(`logs/lab-08/runbook-peer-oscar/`) are fixed in this version, which has not been followed again since. Re-verify after
any change to the service, the deploy workflow or the IAM roles.

**Escalation.** In our team only Oscar can change the service (`update-traffic`, `services update`). If your
`update-traffic` is refused, do not try another way: post in the team channel what you saw (first signal, UTC time,
revision), the exact command to run and why, and wait for his "done" before checking recovery.

## 0. Before you start (fresh Cloud Shell or terminal)

```bash
gcloud config set project mlops-ece-group2          # Cloud Shell may remember another project
git clone https://github.com/oscarico92/mlops-fri1-GOS-bike-demand.git
cd mlops-fri1-GOS-bike-demand                       # the scripts below run from here (Python 3, standard library)
```

Then check the deploys: GitHub → **Actions** → "Deploy to Cloud Run". A merge to `main` builds, deploys and moves 100 %
of the traffic to the new revision. If a run is in progress or failed, note its commit and time before acting: the
serving revision may not be the commit of `main`. During an incident, **freeze `main`** (no merge) until recovery is
verified, otherwise a deploy can replace what you are looking at. A deploy that fails on a transient error (e.g.
"Unable to retrieve Identity Pool subject token … connection timeout") may be re-run once with "Re-run failed jobs";
if it fails again, leave the traffic where it is and report it.

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
# Cloud Logging is not instant (lines still arrived after 90 s in our baseline): read, then read again with a
# timestamp window covering the workload before calling any request missing.
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="gos-bike-demand"' \
  --freshness=1h --format=json | python3 scripts/signals.py --label check --sent logs/lab-08/check-sent.jsonl
```

Save every output as it is, with its UTC time. Compare it with the baseline using the same definitions, the same
workload size and the same label scheme; do not compare against numbers measured with other definitions.

## 3. Find what changed, boundary by boundary

| Boundary | Question | Check | A mismatch means |
| --- | --- | --- | --- |
| Service | Which revision serves, since when? | traffic and revision list above | a new revision appeared: compare it with the last good one |
| Image and code | Which commit does it run? | `code_revision` in `/health` and in the log lines; the image digest of the serving revision vs the last good revision (command below) | code changed; `code_revision` alone can be overridden by an env var, the digest cannot |
| Model | Which model answers, are its bytes the reviewed ones? | `model_version` and `model_sha256` from `/health`; identity in `signals.py` | another or a modified model is served |
| Configuration | Which settings does the revision run with? | `gcloud run revisions describe <revision> --region europe-west1` (env vars, image, port) | e.g. a model directory, a revision or a variable that differs from the last good revision |
| Inputs | Did the requests change, or the service's answer to the same requests? | the fixed workload of section 2 (same requests every time); `invalid_accepted`, `eligible_statuses` | same requests answered differently: the service changed, not the traffic |

Where the expected values come from:

```bash
# image (by digest) and env vars of a revision, serving or last good
gcloud run revisions describe <revision> --region europe-west1 \
  --format='yaml(spec.containers[0].image,spec.containers[0].env,status.imageDigest)'
```

- **Expected digest:** the `status.imageDigest` of the last good revision (same command), or the `live-check-*.txt` of
  the deploy run of that commit. That file is a GitHub Actions **artifact**, not a file in the repository: Actions →
  "Deploy to Cloud Run" → the run of that commit → Artifacts. Copies kept in Git exist only for a few deploys
  (`logs/lab-06/deploy-oscar/`, `logs/lab-08/injector-oscar/`).
- **Commit of a revision:** the `code_revision` of its request lines in Cloud Logging
  (`resource.labels.revision_name="<revision>"`), or of `/health` while it serves, or the deploy run that created it.

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

The commit of the last good revision is its `code_revision` (section 3): read `/health` once the traffic is on it,
then pass that value.

A rollback **pins** the traffic on that revision. It stays there until someone moves it: the next deploy from `main`
moves 100 % to the new revision (#29). To go back to the newest revision after a rehearsal, or once the fix is
deployed and checked:

```bash
gcloud run services update-traffic gos-bike-demand --region europe-west1 --to-latest
curl -s "$URL/health"                                   # identity of the newest revision
```

Recovery is verified only when the identity is back (`model_sha256`, `code_revision`, digest) **and** the signals are
back within the baseline. A worked example: `logs/lab-06/deploy-oscar/rollback.txt`.

Rollback is the wrong tool when the cause is outside the release (input data, a dependency, the platform): then keep
the traffic where it is, guard or fix forward through a reviewed pull request.

## 6. Record

Keep one timeline (UTC) with: who did what, each observation and its raw file, each hypothesis and its result, the
rollback, the recovery check. Commit the raw outputs under `logs/lab-08/` and the incident record under `reports/`,
through a reviewed pull request.

Before committing a Cloud Logging export, remove personal data, then say so in the file and change nothing else:

- request logs: `httpRequest.remoteIp` (the client's IP address) is in every entry; replace it with `redacted`;
- audit logs (`gcloud logging read` on `cloudaudit.googleapis.com`): `protoPayload.authenticationInfo.principalEmail`
  and `principalSubject` (who ran the command) and `protoPayload.requestMetadata.callerIp`; replace a team member's e-mail with
  `redacted (team member)` and a person's IP with `redacted`. Addresses of GitHub Actions runners and of the
  service account are not personal data and may stay.

Check before committing: `grep -rE '"(remoteIp|callerIp|principalEmail|principalSubject)"' logs/lab-08/` must show only redacted
values or runner and service-account addresses.

Save the outputs of the first checks too (`curl` of section 2): a check that is not in a file
cannot be quoted as the first signal later.

**Detection is not covered yet.** Nothing watches the service: in the 10 November drill the operator looked only
because the drill was announced, so the real detection time is unknown (`reports/lab-08-incident.md`). Until a
scheduled `workload.py` + `signals.py` run or a Cloud Monitoring alert on the 5xx rate exists, this runbook starts
when someone notices.

**Limits of this runbook.** It checks that the reviewed model answers, not that its predictions are good (model
quality is decided by the Lab 7 gate before release, not here). Cloud Run serves the model baked into the image; it
does not read `registry/`, so `pipeline status` on a laptop says nothing about what is served. It relies on someone
looking (see "Detection" above).

## 7. Never

- touch another team's Cloud Run service;
- modify the accepted bundle (`registry/accepted/`), the raw data or committed evidence;
- retrain as a recovery action;
- call the service recovered from `/health` alone.
