#!/usr/bin/env bash
# One command: qf-tuner sample -> blind input -> vLLM serve -> parallel judging
# -> merged labels -> statistics. Wraps LLM_Inference_LabelsAsGT/run_inference.py
# WITHOUT modifying it; every stage is idempotent and resumable (rerun the same
# command after any interruption).
#
# usage:
#   bash pipeline/run_pipeline.sh WORKDIR \
#       --sample-dir /path/to/qf_tuner_sample \
#       --model-glob '/path/to/hub/models--Qwen--Qwen3-32B/snapshots/*' \
#       [--limit N] [--keep-server] [--max-rounds 3]
#
# WORKDIR layout it produces:
#   blind_input.jsonl        the only thing the judge ever sees (id, text, coverage)
#   serve/                   vllm logs, endpoints.txt, jobid
#   judge_in/round_*/        per-round pending shards
#   judge_out/shard_*.jsonl  raw per-shard judge outputs (append-only set)
#   labels/raw_llm_responses.jsonl + stats.md + stats.json
#
# Environment: PIPELINE_PYTHON (python with pandas/pyarrow, for the adapters;
# the judge client itself is stdlib-only), JUDGE_* passthroughs (see
# serve_judge_vllm.sh).
set -Eeuo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$PIPELINE_DIR")"
CLIENT="$REPO_DIR/LLM_Inference_LabelsAsGT/run_inference.py"
PYTHON=${PIPELINE_PYTHON:-python3}

WORKDIR=${1:?usage: run_pipeline.sh WORKDIR [options]}; shift
SAMPLE_DIR=${SAMPLE_DIR:-/mnt/vast01/shared/ifm_data/qf_tuner_samples/keenable_judge20k_v0}
MODEL_GLOB=${JUDGE_MODEL_GLOB:-}
LIMIT=0
KEEP_SERVER=0
MAX_ROUNDS=3
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample-dir)  SAMPLE_DIR=$2; shift 2 ;;
    --model-glob)  MODEL_GLOB=$2; shift 2 ;;
    --limit)       LIMIT=$2; shift 2 ;;
    --keep-server) KEEP_SERVER=1; shift ;;
    --max-rounds)  MAX_ROUNDS=$2; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$WORKDIR"/{serve,judge_out,labels}
WORKDIR="$(cd "$WORKDIR" && pwd)"
echo "== pipeline workdir: $WORKDIR"
echo "== sample:           $SAMPLE_DIR"

# ---- stage 1: blind input --------------------------------------------------
BLIND="$WORKDIR/blind_input.jsonl"
if [[ -s "$BLIND" ]]; then
  echo "== blind input exists ($(wc -l < "$BLIND") docs), skipping"
else
  "$PYTHON" "$PIPELINE_DIR/make_blind_input.py" "$SAMPLE_DIR" "$BLIND"
fi

# ---- stage 2: serve --------------------------------------------------------
ENDPOINTS="$WORKDIR/serve/endpoints.txt"
SERVE_JOB=""
serve_alive() {
  [[ -s "$WORKDIR/serve/jobid" ]] || return 1
  SERVE_JOB=$(cat "$WORKDIR/serve/jobid")
  squeue -j "$SERVE_JOB" -h 2>/dev/null | grep -q .
}
if serve_alive && [[ -s "$ENDPOINTS" ]]; then
  echo "== serve job $SERVE_JOB already running, reusing $(wc -l < "$ENDPOINTS") endpoints"
else
  [[ -n "$MODEL_GLOB" ]] || { echo "need --model-glob (or JUDGE_MODEL_GLOB)" >&2; exit 2; }
  rm -f "$ENDPOINTS"
  export JUDGE_PIPELINE_DIR="$PIPELINE_DIR" JUDGE_MODEL_GLOB="$MODEL_GLOB" \
         JUDGE_LOG_ROOT="$WORKDIR/serve"
  SERVE_JOB=$(sbatch --parsable "$PIPELINE_DIR/serve_judge.sbatch")
  echo "$SERVE_JOB" > "$WORKDIR/serve/jobid"
  echo "== serve job $SERVE_JOB submitted, waiting for endpoints (queue + model load)"
  while [[ ! -s "$ENDPOINTS" ]]; do
    if ! squeue -j "$SERVE_JOB" -h 2>/dev/null | grep -q .; then
      echo "serve job $SERVE_JOB left the queue without endpoints — see $WORKDIR/serve/" >&2
      exit 3
    fi
    sleep 30
  done
fi
mapfile -t ENDPOINT_LIST < "$ENDPOINTS"
echo "== ${#ENDPOINT_LIST[@]} endpoints ready"

# ---- stage 3: judge (rounds until every id has a decision) -----------------
for (( round=0; round<MAX_ROUNDS; round++ )); do
  ROUND_DIR=$("$PYTHON" "$PIPELINE_DIR/shard_blind_input.py" "$BLIND" "$WORKDIR" "${#ENDPOINT_LIST[@]}")
  if [[ "$ROUND_DIR" == "DONE" ]]; then echo "== judging complete"; break; fi
  echo "== judge round: $ROUND_DIR"
  pids=()
  shard_index=0
  for shard_file in "$ROUND_DIR"/shard_*.jsonl; do
    endpoint=${ENDPOINT_LIST[$(( shard_index % ${#ENDPOINT_LIST[@]} ))]}
    out_file="$WORKDIR/judge_out/shard_$(basename "$ROUND_DIR")_$(basename "$shard_file" .jsonl).jsonl"
    limit_args=(); [[ "$LIMIT" -gt 0 ]] && limit_args=(--limit "$LIMIT")
    python3 "$CLIENT" "$shard_file" "$out_file" --base-url "$endpoint" --model judge \
        "${limit_args[@]}" > "$WORKDIR/judge_out/$(basename "$out_file" .jsonl).log" 2>&1 &
    pids+=("$!")
    shard_index=$((shard_index + 1))
  done
  failures=0
  for pid in "${pids[@]}"; do wait "$pid" || failures=$((failures + 1)); done
  echo "== round done ($failures shard clients exited nonzero)"
  [[ "$LIMIT" -gt 0 ]] && break   # smoke mode: one round is the point
done

# ---- stage 4: merge --------------------------------------------------------
MERGED="$WORKDIR/labels/raw_llm_responses.jsonl"
"$PYTHON" - "$BLIND" "$WORKDIR/judge_out" "$MERGED" <<'EOF'
import json, sys
from pathlib import Path
blind_path, out_dir, merged_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
expected = [json.loads(l)["id"] for l in open(blind_path, encoding="utf-8") if l.strip()]
rows = {}
for shard_output in sorted(out_dir.glob("shard_*.jsonl")):
    for line in open(shard_output, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            rows.setdefault(row["id"], line)
with open(merged_path, "w", encoding="utf-8") as handle:
    for doc_id in expected:
        if doc_id in rows:
            handle.write(rows[doc_id])
missing = [doc_id for doc_id in expected if doc_id not in rows]
Path(merged_path).with_name("missing_ids.txt").write_text("\n".join(missing))
print(f"merged {len(rows):,}/{len(expected):,} documents -> {merged_path} "
      f"({len(missing)} missing)")
EOF

# ---- stage 5: statistics ---------------------------------------------------
if [[ -s "$MERGED" ]]; then
  "$PYTHON" "$PIPELINE_DIR/compute_label_stats.py" "$MERGED" "$SAMPLE_DIR" || true
fi

# ---- stage 6: teardown -----------------------------------------------------
if [[ "$KEEP_SERVER" -eq 0 && -n "$SERVE_JOB" ]] && squeue -j "$SERVE_JOB" -h 2>/dev/null | grep -q .; then
  scancel "$SERVE_JOB" && echo "== serve job $SERVE_JOB cancelled"
else
  echo "== serve job left running (--keep-server or already gone)"
fi
echo "== pipeline finished: $WORKDIR/labels/"
