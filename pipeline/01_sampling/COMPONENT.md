# 01_sampling — stage 1 of the pipeline (the sampler)

This is the qf-tuner sampling + annotation stage, fused into this repo from
poch4319/qf-tuner @ 20c1445 (data/ excluded). It produces the stratified,
fully-annotated sample that pipeline/02_llm_labeling judges.

Entry points (PYTHONPATH=pipeline/01_sampling/src):
  python -m qf_tuner sample   --dataset pipeline/01_sampling/configs/datasets/keenable.yaml --out DIR [targets...]
  python -m qf_tuner annotate --sample DIR --pack pipeline/01_sampling/filter_packs/cc_baseline

Contract docs: docs/SAMPLE_OUTPUT.md (output schema), docs/NAMING.md,
docs/DATASET_INPUT.md. Filter packs live in filter_packs/ (byte-pinned to the
QF production repo; see each pack's PROVENANCE.md).

pipeline/run_pipeline.sh runs this stage automatically when the sample
directory does not exist yet.
