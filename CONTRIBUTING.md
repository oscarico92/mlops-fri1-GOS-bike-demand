# Contributing

Rules the team agreed for every change to this repository. Roles and support route:
[WORKING-AGREEMENT.md](WORKING-AGREEMENT.md).

## Branches and commits

- Never push directly to `main`; every change, including docs, goes through a pull request.
- Never rewrite the history of `main` (no `git push --force`, no rebase or amend of merged
  commits). It breaks every clone and open branch, and orphans the commits that logs, labels and
  reviews point to. A mistake on `main` is fixed by a new commit through a pull request.
  (Added after the rewrite of 27 October, recorded in `reports/week-02-team.md`.)
- One branch per task, named `lab-<NN>-<short-topic>` (for example `lab-02-data-baseline`)
  or `<topic>-<short-description>` for work outside a lab.
- Small commits with an imperative message describing the behavior change
  (for example "Normalize team labels on any whitespace").
- When two members work on one machine, add
  `Co-authored-by: Name <id+username@users.noreply.github.com>` to the commit message.

## Local checks before pushing

From the repository root:

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
```

Do not regenerate `uv.lock`, skip tests or weaken assertions to get a green result.
Never commit `.venv/`, `artifacts/`, `tracking/`, credentials or individual reports.
If you run `train`, only commit `reports/metrics*.json*` when the run is the recorded
evidence (clean tree, `working_tree_dirty: false`).

## Pull requests and review

- Fill in the pull request template: change and owner, actual commands and results,
  checked revision, assistance used.
- A different member reviews the diff, reruns the checks on the latest commit and leaves
  at least one actionable observation.
- The author answers each observation in the pull request (change pushed, or reason
  for not changing) and records it in the lab worksheet.

## Merging

- Merge only after the reviewer approves and CI is green on the latest pushed commit.
- The author merges after approval. Any exception is written in the lab worksheet.
- The lead author rotates every lab; the reviewer is never the lead author.
