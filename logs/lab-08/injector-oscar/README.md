# Lab 8 injector record (Oscar)

Raw log: [`injector-log.txt`](injector-log.txt), written in Cloud Shell with `tee -a` as each command ran
(downloaded unchanged; it keeps the terminal colour codes gcloud printed, e.g. `\x1b[1m`). SHA-256 of the file: `9de63360…`. All times UTC, 10 November 2026. Revealed after the operator's diagnosis.

## The fault

One configuration change on our own service `gos-bike-demand` (project `mlops-ece-group2`, `europe-west1`):
a new revision with `BIKE_MODEL_DIR=/app/artifacts/v2`, a folder that does not exist in the image, then 100 % of
the traffic moved to it. A plausible release mistake (a model path for a "v2" that was never shipped).

- Same image, same code (`code_revision` `c2fc401…`), same accepted model bundle in the image: nothing rebuilt.
- Expected symptom (Lab 5 design): the service starts, `/health` and valid `/predict` answer `503` with the reason,
  invalid input still `422`.
- Reversible by one traffic change to the retained revision `gos-bike-demand-00010-m4d` (the revision of the
  operator's second baseline, `logs/lab-08/baseline-00010/`).
- Not touched: other teams' services, the image, the registry and accepted bundles, raw data, committed evidence.

## Timeline (from the raw log)

| Time | Event |
| --- | --- |
| 19:57:20 | before: 100 % on `00010-m4d`, `/health` 200 (`c2fc401…`, `d24c050e…`, `baseline-637fa42462b2`) |
| 19:57:43 | inject start: `gcloud run services update --update-env-vars BIKE_MODEL_DIR=/app/artifacts/v2` creates `00011-z46`; traffic stays pinned on `00010-m4d` |
| 19:58:04 | `update-traffic --to-revisions gos-bike-demand-00011-z46=100`; `/health` **503** "model not available: … '/app/artifacts/v2/model-metadata.json'" |
| (operator) | "The drill has started" sent; Simon investigates without the answer, diagnoses a configuration fault on `00011-z46`, names `00010-m4d` as the target and asks for the rollback (he has viewer roles only) |
| 20:15:59 | log line "rollback requested": a mistyped command (a template was pasted); **nothing executed**, recorded on the next line |
| 20:17:53 | rollback done by the injector at the operator's request: 100 % on `00010-m4d`, `/health` **200**, identity identical to the baseline |
| 20:49:37–42 | cleanup at the operator's request: `--remove-env-vars BIKE_MODEL_DIR` creates `00012-zkx` with no env var, **0 %** traffic; 100 % stays on `00010-m4d`, `/health` 200 |

The cleanup is a separate action from the rollback: the rollback moved the traffic back, but the service template
still carried the bad variable, and our deploy workflow (`gcloud run deploy --image`) keeps the service's env vars,
so the next merge on `main` would have redeployed the fault. Found by the operator.

## Notes for the incident record

- Fault active for users from 19:58:04 (traffic switch); `00011-z46` was created between 19:57:43 and 19:58:04 with 0 % traffic.
- gcloud's messages "revision … is serving 100 / 0 percent of traffic" name the wrong revision when traffic is
  pinned; the `Traffic:` lines and `status.traffic` are the reliable source.
- Main was frozen during the drill (GitHub issue), so no deploy interfered.
