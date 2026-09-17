# pipeline/ — one command from sampling to labels

Drives the two fused components end to end: **`QF_Sampling/`** (the qf-tuner
stratified sampler + annotator, stage 1) feeds **`LLM_Inference_LabelsAsGT/`**
(the LLM judge, used verbatim — nothing in that folder is modified). One
command goes corpus → stratified sample → blind input → judged labels +
statistics:

```bash
PIPELINE_PYTHON=~/miniconda3/envs/keenable/bin/python \
bash pipeline/run_pipeline.sh /path/to/workdir \
    --sample-dir /mnt/vast01/shared/ifm_data/qf_tuner_samples/keenable_judge20k_v0 \
    --model-glob '/path/to/hub/models--Qwen--Qwen3-32B/snapshots/*'
```

Smoke run (20 docs per endpoint, server kept up for iteration):

```bash
... run_pipeline.sh /path/to/smoke --limit 20 --keep-server
```

## Stages (all idempotent — rerun the same command to resume)

| stage | what | skip condition |
|---|---|---|
| sample | `QF_Sampling` (`qf_tuner sample` on one node via sbatch, then `annotate`): stratified draw over the labeled corpus with the allowlist targets in `sample_targets.default` (kept 2,000 + 1,285 per content rule; prefilters excluded by construction) | `sample.parquet` exists in `--sample-dir` |
| blind | `sample.parquet` → `blind_input.jsonl` (`{id: uid, text, coverage:"complete"}`); blinding happens here — qf_reason/signals never leave the parquet | file exists |
| serve | sbatch one 8-GPU node (our account), runs `serve_judge_vllm.sh` (adapted from viral's, env-driven): up to 4× TP=2 vLLM endpoints, GPU-cleanliness preflight, writes `serve/endpoints.txt` | serve job still running |
| judge | pending ids (not yet in any `judge_out/shard_*.jsonl`) split round-robin across endpoints; one `run_inference.py` client per shard, in parallel; repeats rounds until every id has a decision (`--max-rounds`) | nothing pending |
| merge | dedup by id, order of `blind_input.jsonl`, → `labels/raw_llm_responses.jsonl` + `missing_ids.txt` | — |
| stats | join decisions back to the sample → `labels/stats.md` / `stats.json`: per-rule conservative recovery rate, kept-agreement, review share | — |
| teardown | `scancel` the serve job (unless `--keep-server`) | — |

## Interfaces

* **In**: a qf-tuner sample directory (`sample.parquet` with unique `uid`,
  non-empty `text`). Producer: `qf_tuner sample` + `annotate`.
* **Out**: `labels/raw_llm_responses.jsonl` — run_inference.py's own output
  schema, one line per document, `id` = corpus `uid`; everything joins back
  to the sample on it.
* Judge-visible surface: `id`, `text`, `coverage` — nothing else, by
  construction of the blind stage.

## Configuration

`PIPELINE_PYTHON` — python with pandas/pyarrow for the adapters (the judge
client itself is stdlib-only). `JUDGE_*` variables pass through to serving:
`JUDGE_IMAGE` (default: the shared vLLM ROCm sif), `JUDGE_BASE_PORT`
(default 18400 — clear of the 18000/18100/18200 blocks other jobs use),
`JUDGE_MAX_MODEL_LEN`, `JUDGE_MAX_NUM_SEQS`, `JUDGE_SERVED_MODEL`.

Known prerequisite: readable judge-model weights (`--model-glob`). The
Qwen3-32B snapshot used for round 1 currently sits under a private
`~/.cache`; copy it somewhere group-readable and point `--model-glob` at it.
