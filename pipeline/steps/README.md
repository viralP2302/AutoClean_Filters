# steps/ — internal pieces of run_pipeline.sh

Nothing here is run by hand; run_pipeline.sh calls each at its stage:

| file | stage | role |
|---|---|---|
| sample_targets.default | sample | default draw: kept 2,000 + 1,285 per content rule (prefilters excluded) |
| make_blind_input.py | blind | sample.parquet → {id, text, coverage}; the blinding boundary |
| serve_judge_vllm.sh / serve_judge.sbatch | serve | start vLLM endpoints (GPU preflight, endpoints.txt) |
| shard_blind_input.py | judge | split pending (not-yet-judged) ids across endpoints |
| compute_label_stats.py | stats | per-rule recovery rate, kept agreement, review share |
