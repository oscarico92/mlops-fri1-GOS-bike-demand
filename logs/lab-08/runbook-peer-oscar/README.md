# Lab 8: runbook followed by a member who did not write it (Oscar)

`RUNBOOK.md` was written by Gautier (#34). Oscar followed it on the live service, from a fresh directory in Cloud
Shell, on 11 November 2026, 14:54–15:08 UTC, while `main` was `46af152`. The service was healthy: this is a peer
attempt on a quiet service, not a second incident.

Raw log: [`runbook-peer-log.txt`](runbook-peer-log.txt), recorded with `exec > >(tee -a ...)` (it keeps the terminal
control codes of the Cloud Shell prompt). One change only: the personal e-mail shown by `gcloud run revisions list`
in "DEPLOYED BY" of `00011-z46` and `00012-zkx` (manual changes during the drill) is replaced by
"redacted (team member)". Blocking points are the lines starting with `# BLOCKED` or `# NOTE`.

Honesty note: Gautier did not narrate, but Oscar was helped by an AI assistant (Claude) that gave him the order of the
steps and the wrapper commands (`tee`, `echo "# NOTE"`). Each place where the runbook alone was not enough is listed
below rather than hidden.

## What worked as written

| Section | Result |
| --- | --- |
| 2. First look | `/health` 200, traffic and revision list readable; workload `check` (run `145830502a`) + `signals.py`: 50/50 logged, missing 0, success 1.0, 10 intentional 422, p50 10.5 ms, p95 15.5 ms, one identity (`9b88190…`), consistent with the baselines |
| 3. Configuration | serving revision `00016-rwx` runs the image by digest `sha256:55194ac0…` (`image` = `imageDigest`), no environment variables |
| 5. Rollback (rehearsal) | `update-traffic` to `00015-7zq` at 15:07:40: `/health` gave `9b88190…`, `check_deployment.py --expected-revision 9b88190…` **check passed** (7 claims ok); back with `--to-latest`: 100 % on `00016-rwx`, `/health` `46af152…` |

## Where the runbook was not enough (to fix in the runbook)

1. **No step to get the repository** (`# BLOCKED` 14:57:54). Section 2 runs `scripts/workload.py` and
   `scripts/signals.py`; in a fresh Cloud Shell they do not exist. Fix: start section 2 with
   `git clone https://github.com/oscarico92/mlops-fri1-GOS-bike-demand.git && cd mlops-fri1-GOS-bike-demand`.
2. **No project selection** (`# NOTE`). It worked only because Cloud Shell remembered the project from the drill.
   Fix: `gcloud config set project mlops-ece-group2` as the first command.
3. **A deploy can be running or failing while you act** (`# NOTE` 15:00:57, 15:01:32, 15:05:27). `/health` showed
   `9b88190` while `main` was already `46af152`; that deploy then failed at `gcloud run deploy` with a transient
   "Unable to retrieve Identity Pool subject token … connection timeout" and passed on "Re-run failed jobs". Nothing
   in the runbook says to check GitHub Actions before acting, that a merge redeploys and moves 100 % of the traffic
   (freeze `main` during an incident), or what to do with a transient deploy failure. The rollback rehearsal was
   postponed until the deploy was green.
4. **Expected digest not reachable from the runbook** (`# BLOCKED` 15:07:02). Section 3 compares with "the deploy
   run's `live-check-*.txt`", which is a GitHub Actions artifact (Actions → "Deploy to Cloud Run" → run of that
   commit → Artifacts), not a file in the repository; the runbook does not say so. Copies kept in Git exist only for a
   few deploys (`logs/lab-06/deploy-oscar/`, `logs/lab-08/injector-oscar/`).
5. **"Commit of the last good revision" (section 5) is not explained.** It is the `code_revision` returned by
   `/health` once the traffic is on that revision (or the deploy run of that revision); in this attempt the commit was
   supplied by the assistant, not found from the runbook.
6. **No way back after a rehearsal or a rollback.** The runbook does not mention `--to-latest`, nor that a rollback
   pins the traffic and that the next deploy from `main` moves it again (#29).
7. **Missing sections required by the lab**: escalation (who to call when `update-traffic` is refused, how), limits
   (model quality, the registry is not read by Cloud Run, detection needs someone to look), and the "last verified
   context" (this attempt: 11 November 2026, revision `00016-rwx`, commit `46af152`).

Owner of the runbook revision: Gautier, review by Oscar or Simon.
