# Clean LLM quality-judge inference

This is a minimal review copy of the inference code used to label the balanced
20,000-document Keenable quality-filter sample with `Qwen/Qwen3-32B` through
an OpenAI-compatible vLLM endpoint.

The historical source, completed outputs, shared corpus and deterministic-QF
labels were not modified. This folder contains only:

```text
LLM_Inference_LabelsAsGT/
├── README.md
├── judge_prompt.txt
└── run_inference.py
```

`run_inference.py` consolidates the historical `judge.py` and
`judge_dynamic_context.py` execution path into one reviewable program. It does
not start vLLM, allocate GPUs, sample data, merge shards, compute a confusion
matrix, or tune the quality filter.

## Actual inference contract

| Property | Value |
|---|---|
| Model used in completed run | `Qwen/Qwen3-32B` |
| Served model alias | `judge` |
| API | OpenAI-compatible `/v1/chat/completions` |
| vLLM context limit | 32,768 tokens, configured at server startup |
| Maximum generated tokens | 768 |
| Temperature | 0 |
| Seed | 0 |
| Qwen thinking | Disabled |
| Input policy | Submit the entire document first |
| Long-document fallback | Recursively split into contiguous halves only after an HTTP 400 context-length error |
| Truncation | None |
| Final label | Model-produced `verdict` |
| Evidence validation | Audit warning only; it cannot replace a valid model verdict |
| Overwrite behavior | Existing output is rejected |

The 20,000-document production run used eight independent instances of this
same client, each pointed at one Qwen/vLLM replica and one disjoint input
shard. Parallel serving and sharding were orchestration choices; the inference
logic for every document was this same program.

## Input schema

The canonical input is JSONL with one unique document per line:

```json
{
  "id": "QFGT00001",
  "text": "Complete extracted document text...",
  "coverage": "complete",
  "text_sha256": "optional upstream digest"
}
```

Only `id`, `text`, and coverage information reach the model. Deterministic-QF
labels, `qf_reason`, URL, source shard, and the expected/reference label are
not included in the model request.

Accepted coverage values are:

- `complete`
- `possibly_truncated`
- `unknown`

If coverage is absent, the program derives it only from explicit truncation
metadata when available; otherwise it uses `unknown`.

## Model request

The system message is the complete contents of `judge_prompt.txt`. The user
message is exactly:

```json
{"coverage": "complete", "text": "...document text..."}
```

No ground-truth or deterministic-QF label is exposed.

## Output schema

Every output row preserves the normalized input fields and adds:

```text
run                 inference configuration and prompt digest
inference_mode      whole_document or fallback_chunked
chunks              offsets, raw model output, token usage and judgment/error
decision            keep, review or reject
decision_basis      why the document-level decision was produced
```

If all successfully processed chunks agree and source coverage is complete,
their model verdict is the document decision. Mixed verdicts, an explicit
model `review`, incomplete source coverage, or an inference/parsing failure
produce `review`.

## Run against one existing endpoint

The endpoint must already be serving the model. No GPU allocation is performed
by this script.

```bash
python3 run_inference.py \
  /absolute/path/input.jsonl \
  /absolute/path/output.jsonl \
  --base-url http://GPU-NODE.core42.hpc:19610/v1 \
  --model judge \
  --max-new-tokens 768 \
  --max-split-depth 12 \
  --timeout-seconds 600
```

For a small review:

```bash
python3 run_inference.py INPUT.jsonl OUTPUT.jsonl \
  --base-url http://GPU-NODE.core42.hpc:19610/v1 \
  --model judge --limit 20
```

The program flushes after every document, so a partial output remains readable
if interrupted. It intentionally does not overwrite or append to an existing
file. Preserve a partial output and resume using a separately constructed
input containing only missing IDs.

## Completed-run provenance

Historical implementation:

```text
/mnt/vast01/users/viral.patel/IFM/LLM_AS_A_Judge/pipeline/judge.py
/mnt/vast01/users/viral.patel/IFM/LLM_AS_A_Judge/pipeline/judge_dynamic_context.py
/mnt/vast01/users/viral.patel/IFM/LLM_AS_A_Judge/pipeline/judge_prompt.txt
```

Canonical blind input:

```text
/mnt/vast01/users/viral.patel/IFM/PubMed_Central_Open_Access_Subset/
keenable_qf_tuner/ground_truth_qf_population_20000_20260914/
sample_20000/input/blind_input_20000.jsonl
```

Completed merged raw responses:

```text
/mnt/vast01/users/viral.patel/IFM/PubMed_Central_Open_Access_Subset/
keenable_qf_tuner/ground_truth_qf_population_20000_20260914/sample_20000/
inference/scaleout_8x_tp2_20260914/raw_llm_responses_20000_merged.jsonl
```

Evidence boundary: these are weak Qwen3-32B quality judgments, not human
ground truth and not evidence that retained documents improve model training.
