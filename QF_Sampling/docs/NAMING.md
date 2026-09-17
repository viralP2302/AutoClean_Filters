# Naming contract — columns and labels

Every name below is fixed across the whole pipeline (corpus shards, samples,
annotations, labels). Nothing downstream renames anything upstream; new things
get new names, existing things keep theirs.

## The label column

| name | rule |
|---|---|
| `qf_reason` | the per-document outcome column. Required on any labeled corpus. |
| value `kept` | **reserved**: the document passed the filter. Literal, lowercase, not configurable. |
| any other value | a rejection label: the FIRST rule/stage that rejected the document. Lowercase snake_case, equal to the filter's counter name with `doc_removed_by_` stripped (so labels match the rule names in the pack's rules.yaml — the `alpha_charcter` typo included). Never rename an existing label. |

## Measurement columns (written at filter time)

Named by the filter's `DataAttributes` fields, verbatim (`word_count`,
`mean_word_length`, `fraction_of_duplicate_lines`, …). The two n-gram
measurements are flattened per n as `common_ngram_frac_<n>` and
`dup_ngram_frac_<n>`. Null exactly when the document never reached the signal
stage. Measurements are numbers, never pass/fail verdicts.

## Text columns

| name | rule |
|---|---|
| `text` | the primary text of that dataset stage — post-filter view in QF outputs and samples. The pipeline-wide convention; never aliased. |
| `text_raw` | pre-filter text (from the extraction stage). Only ever ADDED next to `text`, never replacing it. |

Both stay the LAST columns of any file that has them.

## Verdict columns (added by `qf_tuner annotate`, or at filter time)

| name | rule |
|---|---|
| `viol_<rule_name>` | did the document violate this rule, re-evaluated independently (no chain short-circuit). `<rule_name>` = the `name` field in the pack's rules.yaml = the qf_reason label. Nullable: null off-stage. |
| `n_violations` | count of violated rules (null off-stage) |
| `sole_blocker` | the rule name when exactly one rule is violated, else empty |
| `first_blocking` | first violated rule in chain order; must reproduce `qf_reason` |

## Sampler columns (added by `qf_tuner sample`)

| name | rule |
|---|---|
| `strat` | the stratum the row was drawn for; today always == `qf_reason`, may gain other stratum kinds later — group by `strat`, filter by `qf_reason` |
| `shard`, `row_idx` | provenance back to the source shard and row |

## Judge columns (produced by the judge stage — see SAMPLE_OUTPUT.md)

`uid`, `sample`, `text_hash`, `label` (`coherent` | `incoherent`),
`label_source` (`llm` | `triage` | `human`), `judge_model`, `rubric_version`,
`truncated`, `created_at`, `raw_response`.
