# AutoClean_Filters

Collaborative pipeline for LLM-guided quality-filter tuning on the keenable
corpus. The repo is laid out as the pipeline itself — one numbered folder per
stage, plus the orchestration that runs them end to end:

```
pipeline/
├── 01_sampling/       stage 1 — stratified sampling + per-rule annotation
│                      (qf-tuner: pure sampler over the QF-labeled corpus,
│                      filter packs, violation vectors; see COMPONENT.md)
├── 02_llm_labeling/   stage 2 — LLM-as-judge labeling
│                      (vLLM client: blind {id, text, coverage} in,
│                      keep/review/reject decisions out; see its README.md)
├── run_pipeline.sh    ONE COMMAND: corpus → sample → blind input → serve →
│                      judge → merged labels → statistics (idempotent,
│                      resumable; see pipeline/README.md)
└── *.py, *.sbatch     the stage-to-stage glue (blind adapter, sharding,
                       serving, merge, statistics)
```

Quick start:

```bash
PIPELINE_PYTHON=<python with pandas/pyarrow> \
bash pipeline/run_pipeline.sh /path/to/workdir \
    --model-glob '/path/to/judge/model/snapshots/*'
```

Stage contracts:

* 1 → 2: `sample.parquet` (unique `uid`, `text`, labels + signals; schema in
  `01_sampling/docs/SAMPLE_OUTPUT.md`). Only `uid`/`text`/`coverage` cross
  into stage 2 — blinding is enforced by the adapter, not by convention.
* 2 → downstream: `labels/raw_llm_responses.jsonl` (one line per document,
  `id` = corpus uid, `decision` ∈ keep/review/reject) + run statistics.

Future stages (e.g. 03: filter tuning against the labels) slot in as new
numbered folders with the same file-contract style.
