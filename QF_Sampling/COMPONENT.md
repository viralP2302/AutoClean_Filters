# QF_Sampling — stage 1 of the pipeline (the sampler)

This is the qf-tuner sampling + annotation stage, fused into this repo from
poch4319/qf-tuner @ 20c1445 (data/ excluded). It produces the stratified,
fully-annotated sample that LLM_Inference_LabelsAsGT judges.

Entry points (PYTHONPATH=QF_Sampling/src):
  python -m qf_tuner sample   --dataset QF_Sampling/configs/datasets/keenable.yaml --out DIR [targets...]
  python -m qf_tuner annotate --sample DIR --pack QF_Sampling/filter_packs/cc_baseline

Contract docs: docs/SAMPLE_OUTPUT.md (output schema), docs/NAMING.md,
docs/DATASET_INPUT.md. Filter packs live in filter_packs/ (byte-pinned to the
QF production repo; see each pack's PROVENANCE.md).

pipeline/run_pipeline.sh runs this stage automatically when the sample
directory does not exist yet.
