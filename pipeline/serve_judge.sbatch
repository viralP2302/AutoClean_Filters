#!/usr/bin/env bash
#SBATCH --job-name=qf-judge-serve
#SBATCH --account=ifm_us
#SBATCH --qos=ifm_us
#SBATCH --partition=hermes-2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=384G
#SBATCH --gres=gpu:mi210:8
#SBATCH --time=1-00:00:00
#SBATCH --no-requeue
# usage: sbatch [--export=...] serve_judge.sbatch
# All configuration flows through JUDGE_* environment variables
# (run_pipeline.sh sets them; see serve_judge_vllm.sh for the list).
set -Eeuo pipefail
PIPELINE_DIR=${JUDGE_PIPELINE_DIR:?run through run_pipeline.sh, which exports JUDGE_PIPELINE_DIR}
echo "SERVE_START job=$SLURM_JOB_ID node=$SLURM_JOB_NODELIST base_port=${JUDGE_BASE_PORT:-18400}"
exec srun --overlap --kill-on-bad-exit=1 --nodes=1 --ntasks=1 \
     --cpus-per-task=16 --cpu-bind=none --gres=gpu:mi210:8 --label \
     bash "$PIPELINE_DIR/serve_judge_vllm.sh"
