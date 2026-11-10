#!/usr/bin/env bash
# Lab 7 reviewer challenge (Oscar). Runs inside the project image; the checkout is mounted
# read-only at /work and copied, so nothing in the real checkout or registry changes.
# Results are written to /out (logs/lab-07/challenge-oscar/ on the host).
set -u
OUT=/out
cp -a /work /tmp/w && cd /tmp/w
git config --global --add safe.directory '*'
git config --global core.autocrlf true        # Windows checkout: CRLF in the working tree
export PYTHONPATH=/tmp/w/src BIKE_REGISTRY=/tmp/registry
P="python -m bike_demand.pipeline"
hashes() { (cd "$BIKE_REGISTRY" && find accepted current.json -type f -print0 | sort -z | xargs -0 sha256sum); }
step() { echo; echo "### $*"; }
ls decisions > /tmp/decisions-before.txt
{
  echo "commit $(git rev-parse HEAD)"
  echo "dirty before start: '$(git status --porcelain -- . ':(exclude)logs' ':(exclude)decisions')'"
  echo "date $(date -u +%FT%TZ)  $(uname -m)  $(python --version)"

  step "A1 bootstrap"; $P bootstrap; echo "exit=$?"
  hashes > /tmp/before.txt; cat /tmp/before.txt
  step "A2 run shallow-forest (expected: reject, exit 2)"; $P run --candidate configs/candidates/shallow-forest.yaml; echo "exit=$?"
  hashes > /tmp/after.txt
  step "A3 accepted state after the rejection"; cat /tmp/after.txt
  if cmp -s /tmp/before.txt /tmp/after.txt; then echo "A RESULT: accepted bytes and current.json unchanged"; else echo "A RESULT: CHANGED"; diff /tmp/before.txt /tmp/after.txt; fi

  step "B dirty tree: edit a tracked config, then run (expected: blocked, exit 3)"
  echo "# challenge edit, not committed" >> configs/candidates/deep-forest.yaml
  $P run --candidate configs/candidates/deep-forest.yaml; echo "exit=$?"
  git checkout -- configs/candidates/deep-forest.yaml
  hashes | cmp -s /tmp/before.txt - && echo "B RESULT: accepted state unchanged" || echo "B RESULT: accepted state CHANGED"

  step "C inconsistent tamper: append one byte to accepted/baseline/model.joblib"
  cp "$BIKE_REGISTRY/accepted/baseline/model.joblib" /tmp/model.backup
  printf 'x' >> "$BIKE_REGISTRY/accepted/baseline/model.joblib"
  $P status; echo "status exit=$?"
  $P restore baseline; echo "restore exit=$?"
  cp /tmp/model.backup "$BIKE_REGISTRY/accepted/baseline/model.joblib"
  $P status; echo "status after putting the bytes back exit=$?"

  step "D consistent substitution: rejected candidate bundle copied over accepted/baseline"
  REJ=$(ls -d "$BIKE_REGISTRY"/candidates/*/ | grep -v '\.tmp/$' | head -1)
  echo "rejected candidate folder: $REJ"
  grep -h model_sha256 "$REJ/metadata.json" "$BIKE_REGISTRY/accepted/baseline/metadata.json"
  cp "$REJ/model.joblib" "$REJ/metadata.json" "$BIKE_REGISTRY/accepted/baseline/"
  echo "current.json still says:"; cat "$BIKE_REGISTRY/current.json"; echo
  $P status; echo "status exit=$?"
  $P restore baseline; echo "restore exit=$?"
  $P run --candidate configs/candidates/deep-forest.yaml; echo "run exit=$?"
  LAST=$(ls -t decisions/*.json | head -1)
  echo "incumbent evidence in $LAST:"
  python - "$LAST" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print(json.dumps({"incumbent": r["evidence"].get("incumbent"), "outcome": r["outcome"], "reasons": r.get("reasons")}, indent=2))
PY
} 2>&1 | tee "$OUT/run.txt"
# keep only the decision records written by this challenge
for f in decisions/*.json; do grep -qx "$(basename "$f")" /tmp/decisions-before.txt || cp "$f" "$OUT/decision-$(basename "$f")"; done
