# Lab 7 reviewer challenge (Oscar): observed results and explanation

Predictions: [`PREDICTION.md`](PREDICTION.md), committed in `e7f7202` **before** the run.
Run: commit `e7f7202`, project image built from it, Linux x86_64, Python 3.12.12, 2026-11-10 15:41 UTC,
`run.sh` on a throwaway copy of the checkout (repo mounted read-only, registry in `/tmp`).
Raw output: [`run.txt`](run.txt). Decision records written by the challenge: `decision-*.json`
(kept here, not in `decisions/`, because the last one comes from a deliberately corrupted registry).

| # | Predicted | Observed | Claim |
| --- | --- | --- | --- |
| A | reject, accepted state unchanged | `shallow-forest` rejected (90.62 vs 86.85), exit `2`; the four files of `accepted/` and `current.json` have identical SHA-256 before and after | **holds** |
| B | blocked on a dirty tree | exit `3`, `integrity.provenance: unavailable (... working_tree_dirty: True)`; accepted state unchanged | **holds** |
| C | one appended byte fails closed | `status`: "NOT usable: model checksum mismatch"; `restore baseline` exit `1` | **holds**, with one gap: `status` still exits `0` |
| D | consistent substitution not detected | **not detected, and worse than predicted** (below) | **does not hold** |

## D: a rejected model replaced the accepted one

1. The rejected `shallow-forest` bundle (`model_sha256` `978b87f3…`, MAE 90.62) was copied, `model.joblib`
   **and** `metadata.json`, over `accepted/baseline/`. `current.json` still said `d24c050e…`.
2. `status`: "baseline (bytes verified)", exit `0`.
3. `restore baseline`: exit `0`, and it **rewrote `current.json` with the rejected model's SHA** (`978b87f3…`):
   the only record that still disagreed was overwritten, so the substitution is now invisible.
4. `run deep-forest`: the incumbent was evaluated as "baseline" with MAE **90.62**, and `deep-forest`
   (86.11) was **accepted**, "all checks passed". The same candidate was rejected against the real
   baseline (86.85) in Simon's run and in scenario B.

So yes: a rejected model can become the accepted one, and then make the gate accept a model that the
committed policy rejects.

## Explanation

`load_accepted` (`src/bike_demand/pipeline.py`) checks `model.joblib` against `model_sha256` from
`metadata.json` in **the same folder**: both can be replaced together. Nothing compares the bundle with
a record kept outside it. `restore` trusts that check and then writes the bundle's own SHA into
`current.json`. The test "tampered bundle fails closed" only covers an inconsistent bundle (case C).

## After the fix (`d9f1087`)

Same `run.sh`, same image recipe, built from the fix commit: [`after-fix/run.txt`](after-fix/run.txt).
`pytest -q -m pipeline` in that image: 16 passed (13 existing + 3 new).

| # | Before the fix (`e7f7202`) | After the fix (`d9f1087`) |
| --- | --- | --- |
| A | reject, state unchanged | reject, state unchanged |
| B | blocked (dirty tree) | blocked (dirty tree) |
| C | NOT usable, `restore` exit 1, but `status` exit 0 | NOT usable, `restore` exit 1, `status` exit **1** |
| D | "bytes verified", `restore` rewrote `current.json` with the rejected SHA, `deep-forest` **accepted** | `status`: "differs from its committed record", exit 1; `restore` exit 1, `current.json` untouched; `run` **blocked** (incumbent unavailable) |

## Proposed fix (implemented in `d9f1087`, under review)

- Keep the SHA of every accepted version where the registry cannot rewrite it: written at promotion in a
  committed record (e.g. the `accept` decision in `decisions/`, or an accepted index in Git), and
  `configs/expected-model.json` for `baseline`.
- `load_accepted` and `restore` check the bundle against that record, not against the bundle's metadata;
  `restore` never derives the SHA it writes from the bundle itself.
- `status` exits non-zero when a version is NOT usable, so CI and a runbook can see it.
- A test for case D: substitute a consistent bundle, then `status`, `restore` and `run` must fail closed.

## What the challenge does not show

- It needs write access to `registry/`; on our setup that is only a local folder. It shows what the
  integrity check can and cannot detect, not who could do this.
- Cloud Run does not read the registry: the image trains and serves its own `d24c050e…` at build time.
  The served model is equal to the accepted baseline by bytes, but a promotion would not change what
  Cloud Run serves. That link is a separate gap for Lab 7 ("Cloud Run serves the accepted version").
