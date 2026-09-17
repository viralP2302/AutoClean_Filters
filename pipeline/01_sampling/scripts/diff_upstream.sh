#!/bin/bash
# Has a pack's rule snapshot drifted from the QF main repo?
# usage: scripts/diff_upstream.sh [PACK_DIR] [UPSTREAM_QF_DIR]
set -euo pipefail
PACK="${1:-filter_packs/cc_baseline}"
UP="${2:-/mnt/vast01/users/pochun.chang/projects/pipeline/quality_filtering}"

echo "upstream: $UP @ $(git -C "$UP" rev-parse --short HEAD 2>/dev/null || echo '?')"
status=0
for f in "$PACK"/rules/*.py; do
  b=$(basename "$f")
  [ "$b" = "__init__.py" ] && continue   # added locally for importability
  if [ ! -f "$UP/$b" ]; then
    echo "MISSING upstream: $b"; status=1
  elif ! cmp -s "$f" "$UP/$b"; then
    echo "DIFFERS: $b"; status=1
  fi
done
[ "$status" -eq 0 ] && echo "pack rules identical to upstream working tree"
exit "$status"
