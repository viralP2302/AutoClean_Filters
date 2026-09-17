#!/bin/bash
# Bring a new quality-filter version down from the QF main repo as a new baseline pack.
#
# usage:    scripts/new_baseline.sh PACK_NAME [UPSTREAM_QF_DIR]
# example:  scripts/new_baseline.sh cc_baseline_v2
#
# Copies the rule modules, generates thresholds.yaml from the copied code,
# writes a PROVENANCE pinned to the upstream commit, and runs the consistency
# gates. Fails loudly instead of producing a half-made pack.
set -euo pipefail

PACK_NAME="${1:?usage: scripts/new_baseline.sh PACK_NAME [UPSTREAM_QF_DIR]}"
UPSTREAM="${2:-/mnt/vast01/users/pochun.chang/projects/pipeline/quality_filtering}"
PYTHON="${PYTHON:-/mnt/vast01/users/pochun.chang/miniconda3/envs/keenable/bin/python}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK_DIR="$REPO_ROOT/filter_packs/$PACK_NAME"

# not part of the rule chain: the batch driver and ops tooling stay upstream
EXCLUDED_FILES="quality_filtering.py check_statistics.py"

if [ -e "$PACK_DIR" ]; then
  echo "ERROR: $PACK_DIR already exists — baselines are never overwritten" >&2
  exit 1
fi

UPSTREAM_COMMIT=$(git -C "$UPSTREAM" rev-parse --short HEAD)
if [ -n "$(git -C "$UPSTREAM" status --porcelain -- . 2>/dev/null)" ]; then
  echo "WARNING: upstream working tree has uncommitted changes — the commit pin may not match the copied files"
  UPSTREAM_COMMIT="$UPSTREAM_COMMIT-dirty"
fi

mkdir -p "$PACK_DIR/rules"
copied_count=0
for file in "$UPSTREAM"/*.py; do
  base_name=$(basename "$file")
  case " $EXCLUDED_FILES " in *" $base_name "*) continue ;; esac
  cp "$file" "$PACK_DIR/rules/$base_name"
  copied_count=$((copied_count + 1))
done
touch "$PACK_DIR/rules/__init__.py"
echo "copied $copied_count rule modules from $UPSTREAM @ $UPSTREAM_COMMIT"

# rule-chain declaration: start from the template pack's table; edit it in the
# new pack if this filter version changed the rule structure
RULES_TEMPLATE="${RULES_TEMPLATE:-$REPO_ROOT/filter_packs/cc_baseline/rules.yaml}"
cp "$RULES_TEMPLATE" "$PACK_DIR/rules.yaml"

# gate 1: thresholds must be extractable from the code (DataThreshold contract)
"$PYTHON" "$REPO_ROOT/scripts/pack_thresholds.py" "$PACK_DIR" --write
# gate 2: the fresh yaml must round-trip against the code exactly
"$PYTHON" "$REPO_ROOT/scripts/pack_thresholds.py" "$PACK_DIR"
# gate 3: the copy must match the upstream tree it came from
bash "$REPO_ROOT/scripts/diff_upstream.sh" "$PACK_DIR" "$UPSTREAM"

cat > "$PACK_DIR/PROVENANCE.md" <<EOF
# $PACK_NAME — provenance

Baseline pack created by scripts/new_baseline.sh on $(date -I).
Source: github.com/poch4319/pipeline, quality_filtering/ @ commit $UPSTREAM_COMMIT
(rule modules copied verbatim; empty __init__.py added for importability;
thresholds.yaml generated from rules/threshold.py by scripts/pack_thresholds.py).

Never edit this pack. To tune, copy the whole directory to
filter_packs/<name>/ and keep a CHANGELOG there. The constraints the upstream
code must keep for this onboarding to work: docs/FILTER_AUTHORING.md.
EOF

echo
echo "pack ready: filter_packs/$PACK_NAME"
echo "next: review it, then  git add filter_packs/$PACK_NAME && git commit && git push"
echo "reminder: if this version ADDED/REMOVED/REORDERED rules (not just changed values),"
echo "          edit filter_packs/$PACK_NAME/rules.yaml to match (one line per rule) —"
echo "          the sample invariant (first_blocking must reproduce qf_reason) will"
echo "          block until the table is right."
