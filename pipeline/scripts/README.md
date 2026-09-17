# scripts/ — internal helpers of run_pipeline.sh

Nothing here is run by hand; run_pipeline.sh calls each at its stage:

| file | stage | role |
|---|---|---|
| make_blind_input.py | blind | sample.parquet → {id, text, coverage}; the blinding boundary |
| serve_judge_vllm.sh / serve_judge.sbatch | serve | start vLLM endpoints (GPU preflight, endpoints.txt) |
| shard_blind_input.py | judge | split pending (not-yet-judged) ids across endpoints |

Stage-owned pieces live with their stages: the default sampling targets are
`configs/judge_round_targets.conf`; the post-labeling statistics
tool is `02_llm_labeling/compute_label_stats.py`.
