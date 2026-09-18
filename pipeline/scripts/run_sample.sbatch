#!/bin/bash
#SBATCH --job-name=qft_sample
#SBATCH --account=ifm_us
#SBATCH --qos=test
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

# Stage-1 stratified sampling of a prepared dataset on one node.
#
# Usage:
#   mkdir -p logs
#   sbatch pipeline/scripts/run_sample.sbatch \
#       pipeline/configs/datasets/keenable.yaml /path/to/sample \
#       --filter-pack cc_baseline [extra flags]
#
# The job is idempotent per --out: it refuses to overwrite an existing sample.

set -euo pipefail
umask 0007

# Submit from the repo root, or set QF_SAMPLING_ROOT explicitly. Slurm copies
# this script into its spool, so its own filename cannot locate sample.py.
ROOT=${QF_SAMPLING_ROOT:-$SLURM_SUBMIT_DIR/pipeline/01_sampling}
PY=${PIPELINE_PYTHON:-python3}

DATASET="$1"
OUT="$2"
shift 2

exec "$PY" -u "$ROOT/sample.py" \
    --dataset "$DATASET" \
    --out "$OUT" \
    --processes "$SLURM_CPUS_PER_TASK" \
    "$@"
