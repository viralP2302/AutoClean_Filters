# Dataset input contract — what a corpus must provide

Counterpart of `SAMPLE_OUTPUT.md`: that file defines what sampling produces;
this one defines what a dataset must look like to be sampled at all. Onboarding
a new corpus should never require code changes — only a new
`configs/datasets/<name>.yaml` that satisfies one of the kinds below.

## kind: `qf_output_parquet` — implemented (the fast path)

For corpora that already went through a QF run which recorded per-document
outcomes. Keenable is the reference instance.

Note: the ORIGINAL CC pipeline driver does not produce this — it writes only
high/low-quality splits, drops language-/URL-gate rejects entirely, and keeps
rejection counts as per-file aggregates, not per-document labels. What
satisfies this contract is the keenable-style driver
(`keenable/quality-filtering/qf_keenable.py`: every document written, per-doc
`qf_reason`, signals flattened to parquet columns). A corpus filtered with the
stock CC driver must either be re-run through that driver or wait for the
`raw` kind.

### Required pieces

| yaml key | requirement |
|---|---|
| `manifest` | text file, **one shard file name per line**, fixed and versioned. The pool draw is seeded against this list — never regenerate it in place; a changed manifest is a new dataset version. |
| `qf_root` | directory of parquet shards named exactly as in the manifest. Column requirements below. |
| `raw_root` | mirror directory: **same file names, same row count, same row order** as `qf_root`; its `columns.text_raw` column holds the pre-filter text. Row order is verified per drawn row on the id column; a row-count mismatch automatically falls back to an id-join within the shard (slower, still correct). |
| `reason_column` | which column holds the outcome. The value **`kept`** (literal, reserved — docs/NAMING.md) means accepted; every other value is a rejection label. |
| `columns.{id,url,vendor_lang,text_raw}` | name mapping for the identity columns and the raw-text column. |

### Column contract inside `qf_root` shards

- **id** (`columns.id`): stable, unique string per document.
- **outcome** (`reason_column`): either the reserved literal **`kept`** or the
  FIRST rule/stage that rejected the document (chain semantics). For documents
  that reached the signal stage, the label must be spelled exactly like the
  pack's rule names (`word_count`, `common_ngram`, `alpha_charcter` [sic], …)
  — the annotate invariant "first violation in chain order reproduces the
  stored reason" depends on it and will loudly report any mismatch.
- **measurements**: the shards should carry the numeric quality signals the
  pack's rules read (`word_count`, `fraction_of_duplicate_lines`, …,
  `common_ngram_frac_<n>`, `dup_ngram_frac_<n>`, boolean flags like
  `has_lorem_ipsum`). Signals may be null exactly for documents that never
  reached the signal stage (lang / url / empty / oversize rejects).
- **verdicts are optional input**: per-rule pass/fail (`viol_*`) may already be
  present (ideally written at filter time — see FILTER_AUTHORING). When
  absent, `qf_tuner annotate` derives them on the drawn sample from the
  measurements; when present, they pass through and annotate is skipped.
- **`text`**: the post-filter view of the document (what would enter training
  if kept). May be an empty string.
- **optional**: `url`, vendor language, `fast_text_lang(+_score)` — carried
  through when present, skipped without error when absent.
- **unknown extra columns** are treated as additional signal columns and
  carried into the sample untouched (a small known drop-list — title,
  description, dedup flags — is excluded in code).

### Signal-name coupling (read this before wiring a new corpus)

The fast path assumes the corpus's signal columns use the SAME names and
semantics as the pack rule declarations (rules.yaml, interpreted by `src/qf_tuner/annotate/rules.py`). If a new
corpus computed different signals, or named them differently, do not rename
columns to fake compliance — its measurements may not mean the same thing.
Use the `raw` kind instead and let the pack compute its own signals.

## kind: `raw` — planned, not implemented

Minimum viable dataset: `manifest` + parquet shards with just (**id, text**).
No reasons, no signals. Sampling then requires running the pack over a pool to
tag each document first — this needs the eval stage's run_pack machinery, and
`qf_tuner sample` currently exits with a clear message for this kind.
Everything downstream (sample schema, judge contract, eval) is unchanged.

## Onboarding checklist for a new dataset

1. Write `configs/datasets/<name>.yaml` per the table above.
2. Smoke run on a login node:
   `PYTHONPATH=src python -m qf_tuner sample --dataset configs/datasets/<name>.yaml \
       --out data/samples/<name>_smoke --pool-shards 3 --target-default 3 --target kept=10 --processes 3`
   then `PYTHONPATH=src python -m qf_tuner annotate --sample data/samples/<name>_smoke \
       --pack <the pack recorded in the corpus's FILTER_INFO/provenance>`
3. Check annotate's printed invariants: `kept_with_violations=0` and
   `first_blocking_mismatches=0`. A nonzero count means the corpus's labels or
   signal semantics do not line up with the pack — annotate aborts; stop and
   investigate before drawing a real sample.
4. Check the label table against expectations (labels present? counts
   plausible?), then size `--pool-shards` so the rarest label's expected
   pool count comfortably exceeds `--target-default`.
