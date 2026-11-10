# Lab 7 gated runs (Simon, macOS 27.2 arm64, commit 244a633, clean tree)

Policy: configs/gate-policy.yaml (#25, merged before these runs). Registry outside the repo.

| Candidate | Validation MAE | Outcome | Reason |
| --- | --- | --- | --- |
| shallow-forest (max_depth 6) | 90.62 | reject, exit 2 | quality.vs_incumbent: worse than the accepted baseline (86.85) |
| deep-forest (100 trees, max_depth 20) | 86.11 | reject, exit 2 | quality.vs_incumbent: 0.73 better, below the 1.0 margin |

Accepted state after both runs: baseline (d24c050e...), bytes verified (status.txt). Nothing qualified, so the
accepted model is retained; no further candidate was run to look for a pass.

Disclosure: shallow-forest's MAE (90.62) was already computed once before the policy existed, in the blocked
run decisions/20261109T182707Z-f3eaf0.json (kept as history; that record says working_tree_dirty true because it
was written before 43f3fa6). The earlier blocked-run logs were removed and replaced by these runs.
