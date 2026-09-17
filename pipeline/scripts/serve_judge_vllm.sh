#!/usr/bin/env bash
# Serve the judge model as OpenAI-compatible vLLM endpoints (TP=2 each) on one
# 8-GPU node. Adapted from viral.patel's battle-tested serve_judge_vllm.sh
# (IFM/LLM_AS_A_Judge/pipeline/) — same preflight/readiness logic; only the
# defaults are parameterized for pipeline use. Everything overridable via
# JUDGE_* environment variables.
#   JUDGE_MODEL_GLOB   snapshot dir (glob ok)  — REQUIRED, no default
#   JUDGE_IMAGE        vLLM ROCm apptainer image
#   JUDGE_BASE_PORT    first port (default 18400, clear of 18000/18100/18200 blocks)
#   JUDGE_LOG_ROOT     where vllm-*.log and endpoints.txt go — REQUIRED
set -Eeuo pipefail

MODEL_GLOB=${JUDGE_MODEL_GLOB:?set JUDGE_MODEL_GLOB to the model snapshot path}
SERVED_MODEL=${JUDGE_SERVED_MODEL:-judge}
IMAGE=${JUDGE_IMAGE:-/mnt/vast01/users/viral.patel/containers/vllm-openai-rocm-v0.26.0.sif}
MAX_MODEL_LEN=${JUDGE_MAX_MODEL_LEN:-32768}
MAX_NUM_SEQS=${JUDGE_MAX_NUM_SEQS:-16}
BASE_PORT=${JUDGE_BASE_PORT:-18400}
LOG_ROOT=${JUDGE_LOG_ROOT:?set JUDGE_LOG_ROOT}

MODEL=$(compgen -G "$MODEL_GLOB" | head -1)
[[ -n "$MODEL" && -d "$MODEL" ]] || { echo "Missing model snapshot: $MODEL_GLOB" >&2; exit 2; }
[[ -s "$IMAGE" ]] || { echo "Missing vLLM image: $IMAGE" >&2; exit 2; }
mkdir -p "$LOG_ROOT"

pids=()
cleanup() { trap - EXIT INT TERM; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
            wait "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

start_endpoint() {
  local pair=$1 port=$2
  env -u CUDA_VISIBLE_DEVICES -u ROCR_VISIBLE_DEVICES \
      HIP_VISIBLE_DEVICES="$pair" TOKENIZERS_PARALLELISM=false \
    apptainer exec --rocm "$IMAGE" \
      vllm serve "$MODEL" \
        --host 0.0.0.0 --port "$port" \
        --served-model-name "$SERVED_MODEL" \
        --dtype bfloat16 \
        --tensor-parallel-size 2 \
        --distributed-executor-backend mp \
        --max-model-len "$MAX_MODEL_LEN" \
        --max-num-seqs "$MAX_NUM_SEQS" \
        --gpu-memory-utilization 0.88 \
        --generation-config auto \
        --seed 0 \
        --enforce-eager \
        >"$LOG_ROOT/vllm-$port.log" 2>&1 &
  pids+=("$!")
  echo "STARTED port=$port gpus=$pair pid=$! log=$LOG_ROOT/vllm-$port.log"
}

# Pre-flight: launch ONLY on GPU pairs that are genuinely empty (<=2 GiB used).
# Slurm "idle" is not proof — a foreign process can be squatting on a GPU.
CLEAN_PAIRS=$(env -u CUDA_VISIBLE_DEVICES -u ROCR_VISIBLE_DEVICES HIP_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
  apptainer exec --rocm "$IMAGE" python3 -c '
import sys, torch
lim = 2 * 1024**3
used = []
for i in range(torch.cuda.device_count()):
    free, total = torch.cuda.mem_get_info(i)
    used.append(total - free)
    print(f"GPU{i} used={(total-free)/1024**3:.2f}GiB", file=sys.stderr, flush=True)
pairs = []
for island in (range(0, 4), range(4, 8)):
    clean = [g for g in island if g < len(used) and used[g] <= lim]
    pairs += [f"{clean[k]},{clean[k+1]}" for k in range(0, len(clean) - 1, 2)]
print(" ".join(pairs))
')
echo "CLEAN_PAIRS=[${CLEAN_PAIRS}]"
[[ -n "$CLEAN_PAIRS" ]] || { echo "NO_CLEAN_GPU_PAIRS on $(hostname) -- refusing to start" >&2; exit 4; }

PORTS=()
i=0
for pair in $CLEAN_PAIRS; do
  port=$((BASE_PORT + i)); PORTS+=("$port")
  start_endpoint "$pair" "$port"
  i=$((i + 1))
done

echo "MODEL=$MODEL"
# Resilient readiness: one failed pair must not take down the healthy ones.
deadline=$((SECONDS + 2400))
declare -A dead=()
ready=()
while (( ${#ready[@]} + ${#dead[@]} < ${#PORTS[@]} )); do
  for idx in "${!PORTS[@]}"; do
    port=${PORTS[$idx]}
    [[ " ${ready[*]} " == *" $port "* || -n "${dead[$port]:-}" ]] && continue
    if curl --noproxy '*' -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      ready+=("$port"); echo "READY http://$(hostname):$port/v1"
    elif ! kill -0 "${pids[$idx]}" 2>/dev/null; then
      dead[$port]=1; echo "DEAD port=$port (see $LOG_ROOT/vllm-$port.log)" >&2
    fi
  done
  (( SECONDS < deadline )) || { echo "TIMEOUT: ready=${ready[*]:-none}" >&2; break; }
  sleep 10
done
(( ${#ready[@]} > 0 )) || { echo "NO_ENDPOINTS_READY" >&2; exit 3; }
: > "$LOG_ROOT/endpoints.txt.tmp"
for port in "${ready[@]}"; do echo "http://$(hostname):$port/v1" >> "$LOG_ROOT/endpoints.txt.tmp"; done
mv "$LOG_ROOT/endpoints.txt.tmp" "$LOG_ROOT/endpoints.txt"
cat "$LOG_ROOT/endpoints.txt"
echo "ALL_READY count=${#ready[@]}/${#PORTS[@]} endpoints=$LOG_ROOT/endpoints.txt"
wait
