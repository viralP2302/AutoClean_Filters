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

# Stage-1 stratified sampling on one node (no container needed: pyarrow-only).
#
# Usage:
#   sbatch --exclude=$(grep -v '^#' scripts/bad_nodes.txt | paste -sd,) \
#       scripts/run_sample.sbatch configs/datasets/keenable.yaml data/samples/keenable_v0 [extra flags]
#
# The job is idempotent per --out: it refuses to overwrite an existing sample.

set -euo pipefail
umask 0007

# Fused-repo layout: the component root comes from the pipeline driver (or
# defaults to QF_Sampling under the submit directory for manual submits).
ROOT=${QF_SAMPLING_ROOT:-$SLURM_SUBMIT_DIR/QF_Sampling}
PY=${PIPELINE_PYTHON:-/mnt/vast01/users/pochun.chang/miniconda3/envs/keenable/bin/python}
cd "$ROOT"

DATASET="$1"
OUT="$2"
shift 2

PYTHONPATH="$ROOT/src" exec "$PY" -u -m qf_tuner sample \
    --dataset "$DATASET" \
    --out "$OUT" \
    --processes "$SLURM_CPUS_PER_TASK" \
    "$@"
