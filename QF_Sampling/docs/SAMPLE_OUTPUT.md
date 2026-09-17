# Sample output — the contract between stage 1 (sample) and stage 2 (judge)

Stage 1 produces a stratified sample of documents (`qf_tuner sample`, then
`qf_tuner annotate` adds the per-rule verdict columns); stage 2 (judge) labels
each one against the coherence rubric. This file is the interface: what a
sample directory guarantees, and what the judge stage must produce so the eval
stage can consume it. Build against this contract, not against the current
code — stage-1 internals will keep changing. Column-name rules: docs/NAMING.md.

## Where samples live

`data/samples/<name>/` (cluster-side, gitignored) — **immutable once written**;
the tool refuses to overwrite, new draws get new names. Files:

- `sample.parquet` — one row per sampled document (all you normally need)
- `meta.json` — seed, pool, per-stratum target/available/achieved counts,
  invariant-check results, shard errors, tool git version
- `pool_shards.txt` — the shard pool the draw came from

Current reference sample: `data/samples/keenable_v0/` — 38,500 rows, 98 MB
(19 rejection reasons × 1,500 + 10,000 kept). The group-readable delivery for
the judge work is split by side under
`/mnt/vast01/shared/ifm_data/qf_tuner_samples/`:

- `keenable_rejection_v0/` — the 28,500 rejected rows of this draw (schema
  identical to this contract);
- `keenable_accept_v0/` — a 10,000-doc kept control set copied from
  `qf_kept_subset_120B` (its 40-column schema plus `strat`; the same `text`
  column as everywhere else in the pipeline — judge it).

Each folder carries its own SCHEMA/README and meta.json.

## sample.parquet columns

| group | columns | notes |
|---|---|---|
| identity | `uid`, `shard`, `row_idx`, `url` | `uid` is the stable per-document id; `shard`+`row_idx` trace back to the QF output file |
| language | `language`, `fast_text_lang`, `fast_text_lang_score` | `language` = vendor label (unreliable for the Chinese family); `fast_text_*` = our fastText lid.176 |
| stratification | `qf_reason`, `strat` | `qf_reason` = production outcome (first rule that rejected, or `kept`). `strat` = stratum the row was drawn for; today `strat == qf_reason`, later it may gain values like `near_threshold:<rule>` — group by `strat`, filter by `qf_reason` |
| diagnosis (added by `qf_tuner annotate`) | `viol_<rule>` (16 nullable bools), `n_violations`, `sole_blocker`, `first_blocking` | violations under the baseline pack, evaluated **without** chain short-circuiting; **null ⇔ the document never reached the signal stage** (lang / url / empty / oversize rejects). `sole_blocker` = the rule name when exactly one is violated |
| signals | `word_count`, `mean_word_length`, …, `common_ngram_frac_*`, `dup_ngram_frac_*`, `url_score`, … | numeric quality signals copied from the QF output; null off-stage |
| text | `text`, `text_raw` | see below |

**Judge input = `text`** — the document as the filter saw/kept it
(line-filtered + ftfy NFC + PII-scrubbed for signal-stage documents; untouched
input text for lang/url rejects; may be `""` in the `empty_text` stratum).
Rationale: a rescued document would enter training in this form, so coherence
is judged on it. `text_raw` (pre-QF md-strip text) exists for later line-rule
analyses and for re-running the rule chain — the judge ignores it.

## Guarantees (checked at build time, results in meta.json)

- `kept` rows violate no rule (`n_violations == 0`).
- For rejects that reached the signal stage, `first_blocking == qf_reason`
  (keenable_v0: 21,000/21,000 exact).
- `text_raw` fetched by verified row-order mirror (per-row uid check; uid-join
  fallback counted in meta — keenable_v0: 0 fallbacks).
- Per-stratum achieved counts are exact and listed in `meta.strata`.

## Stability promise (for the judge author)

Column names and semantics above are **stable**; future changes are additive
(new columns, new `strat` values). Select columns by name, never by position,
and don't assume a closed column set. Anything not listed here may change
without notice.

## What the judge stage must produce

`data/labels/<label_set>/labels.parquet`, one row per judgment, append-only:

| column | meaning |
|---|---|
| `uid` | from the sample row |
| `sample` | sample directory name (e.g. `keenable_v0`) |
| `text_hash` | sha256 hex of UTF-8 `text` — the cache-key basis |
| `label` | `coherent` \| `incoherent` (v1 is binary) |
| `label_source` | `llm` \| `triage` \| `human` |
| `judge_model` | exact model id (empty for triage/human) |
| `rubric_version` | e.g. `v1` |
| `truncated` | prompt used truncated text (hash is still over the full `text`) |
| `created_at` | ISO timestamp |
| `raw_response` | optional: the model's verbatim answer/score |

Rules:

- **Cache**: never re-query a `(text_hash, rubric_version, judge_model)` that
  already has a row; labels are never deleted or rewritten.
- **Triage tier**: hopeless documents — empty, fewer than ~5 words, or with
  essentially no alphanumeric content — are labeled `incoherent` with
  `label_source = "triage"`, no LLM call. Triage thresholds are versioned with
  the rubric and must stay far below any value the tuner could plausibly set
  (do NOT triage at e.g. 30 words: the 30–49-word band is exactly where
  word_count false positives live).
- **Rubric v1** (per Yuekai): *"is this text coherent and properly extracted,
  without repetition or noise?"* — explicitly NOT "is this good for training".
  Judge every stratum, coherence is language-agnostic — the `lang` stratum is
  how we detect fastText false kills.
- **Calibration**: before scaling to the full sample, run ~100 documents and
  compare against human judgment; disagreements go into the rubric's next
  version.
