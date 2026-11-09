# First Cloud Run deploy (Lab 6, Oscar)

- Commit deployed: `c893a301928fe305273b60bf8f6278c697bad490` (`main`, after the
  `ENV GIT_COMMIT` fix). Workflow "Deploy to Cloud Run", triggered by the green
  "Container checks" run on the push to `main`; result: success.
- Service: `gos-bike-demand`, project `mlops-ece-group2`, region `europe-west1`,
  URL `https://gos-bike-demand-jdc2acx6uq-ew.a.run.app`.
- `live-check.txt`: output of `scripts/check_deployment.py` run by the workflow against
  the public URL (artifact `live-check-c893a30...`).
- `health.json`, `predict.json`, `revisions.txt`: checked by hand from Cloud Shell after
  the deploy. `/health` reports the deployed commit and the same `model_sha256` as the
  local container (`d24c050e...`).
- `revisions.txt` shows who deployed: `DEPLOYED BY` is the identity of this repository's
  `main` branch through the `gos-github` Workload Identity pool, not a person and not a key.

Before this deploy, "Container checks" failed on `main` after #26 removed
`ENV GIT_COMMIT` from the Dockerfile: `/health` returned `code_revision: unknown` and the
check stopped the pipeline, so nothing was deployed.

## Second deploy and rollback (after #29)

- `live-check-c893a30.txt`, `live-check-1feb672.txt`: deploy records of the first deploy and of the first
  deploy with the #29 workflow (`1feb672`): the revision with 100 % of the traffic runs the digest pushed
  by that run, then the Lab 5 check passes.
- `rollback.txt`: manual rollback from `00004-pb7` (`1feb672`) to `00001-lc9` (`c893a30`) with
  `update-traffic`: `/health` answers the old commit and the same model `d24c050e…`, no rebuild.
- Traffic was left pinned on `00001-lc9`; the deploy triggered by merging this evidence must route
  100 % to its new revision anyway (checked in its live-check record).
