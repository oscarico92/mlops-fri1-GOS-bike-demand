# Lab 7 reviewer challenge (Oscar): predictions, written before running

I did not write the pipeline (#23) or the gate (#25). Claim challenged, from the README:
"a rejection leaves the accepted bytes unchanged" and "a checksum mismatch fails closed"
(`load_accepted`: "Load an accepted bundle; a checksum mismatch fails closed").
Exit check of Lab 7: *could a rejected model replace the accepted one?*

Reading `src/bike_demand/pipeline.py` at the commit under test, `load_accepted` compares
`accepted/<version>/model.joblib` with `model_sha256` from `accepted/<version>/metadata.json`,
i.e. two files of the same folder. It does not compare with `current.json` (which also records
`model_sha256`) nor with any record kept outside the registry.

| # | Action (in a throwaway copy of the checkout, inside the image) | Predicted result |
| --- | --- | --- |
| A | `bootstrap`, then `run` the rejected `shallow-forest` candidate | exit `2` (reject); accepted files and `current.json` byte-identical before and after |
| B | edit a tracked config without committing, then `run` | exit `3` (blocked: dirty tree), nothing accepted changes |
| C | append one byte to `accepted/baseline/model.joblib`, then `status` and `restore baseline` | `status` says NOT usable, `restore` exits `1`: fails closed |
| D | copy the **rejected** candidate's `model.joblib` **and** `metadata.json` over `accepted/baseline/`, then `status`, `restore baseline` and `run deep-forest` | **not detected**: `status` says "bytes verified", `restore` succeeds, and the next run uses the rejected model as incumbent (its MAE ≈ 90.62 instead of 86.85). This would be a gap: a consistent substitution of the bundle is not caught. |

If D is detected, my reading of the code is wrong and the claim holds. If D is not detected,
the gap is recorded here and the cause goes to a reviewed fix, not to edited evidence.
The challenge only uses our own trusted artifacts (the rejected candidate was produced by the
pipeline itself); no unknown model is loaded.
