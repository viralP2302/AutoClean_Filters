# qf-tuner — design

> Archived design from the standalone qf-tuner project. This file includes
> unimplemented proposals and historical paths. Current behavior is documented
> in [the repo README](../../README.md).

Goal: make per-dataset quality-filter tuning a repeatable, automated process.
An LLM judge finds documents the filter wrongly rejected (false positives);
an automated tuner adjusts the filter to retain them without letting garbage
through; every future corpus with a different data profile reuses the same
pipeline with a new dataset config.

Judge rubric (per Yuekai): the judge is NOT asked "is this good for training?"
but "is this text coherent and properly extracted, without repetition or
noise?" — a simpler, more reliable signal.

## Pipeline

```
corpus ──sample──▶ sample.parquet ──annotate──▶ +viol_* columns ──judge──▶ labels.parquet
                                                  │
filter_packs/cc_baseline ────────eval─────────────┤ baseline metrics
                                                  ▼
                     tune (threshold sweep → agent edits, iterate via eval)
                                                  ▼
                     filter_packs/<dataset>_vN + runs/<run_id>/ ledger
                                                  ▼
                                               report (HTML)
                                                  ▼
                     apply (separate, human-triggered: Slurm over the corpus)
```

- **sample** — pure stratified draw over every label (rejection reasons + the
  kept side; both are required: rejected-only labels measure false positives
  but not the garbage a loosened filter would admit). Knows nothing about
  filters — its whole input contract is "a label column plus passthrough
  columns" (docs/NAMING.md).
- **annotate** — adds the per-rule verdict columns (viol_*, n_violations,
  sole_blocker, first_blocking) to a drawn sample by interpreting the pack's
  rules.yaml against the stored measurements, and aborts unless the labels are
  reproduced exactly (the wrong-pack fuse). Skipped when the corpus already
  carries verdicts from filter time.
- **judge** — LLM labels each sampled document against the coherence rubric.
- **eval** — pure function `(pack, labels) → metrics`: confusion matrix,
  precision/recall/F-β, per-rule false-positive breakdown. Seconds, no cluster.
- **tune** — changes the pack to improve eval metrics. Two layers: numeric
  thresholds via deterministic sweep (cheap, reproducible, auditable); rule
  *code* (regexes, new predicates, splitting a rule) via an LLM agent. Every
  iteration is logged (pack diff + metrics) in the run ledger.
- **report** — baseline vs tuned, per-rule analysis, rendered to shareable HTML.
- **apply** — deliberately outside the loop; a human triggers the full-corpus
  Slurm run with the tuned pack. Implementation-wise this generalizes the
  keenable driver (`keenable/quality-filtering/qf_keenable.py`) into
  `qf_tuner apply --dataset X --pack P`: rules come from the named pack
  directory instead of a hard-coded snapshot, column mapping from the dataset
  yaml, and the output directory gets a FILTER_INFO record (decision 8).

## Artifacts

- **Dataset config** (`configs/datasets/*.yaml`) — where the corpus lives and
  what it already has (reason column, signal columns). The only hard
  requirement on a corpus is raw text + a stable document id; everything else
  is recomputable by running the pack (stored columns are just caches).
- **Filter pack** (`filter_packs/<name>/`) — thresholds.yaml + rules/ code.
  The unit of tuning, versioning, and provenance. `cc_baseline` is read-only;
  tuned packs are forks with a CHANGELOG.
- **Label store** (`data/labels/`) — append-only judge labels keyed by
  `(text_hash, rubric_version, judge_model)`; never re-pay for a judgment.
- **Run ledger** (`data/runs/<run_id>/`) — config, per-iteration pack diffs and
  metrics; the audit trail that makes a tuning result explainable and
  repeatable.

## Design decisions

1. **Violation vector, not first-blocking-rule.** The chain short-circuits, so
   the first rule masks the rest; a document is rescued only if ALL rules it
   violates are relaxed. Keenable evidence: 92% of common_ngram rejects also
   violate word_count — fixing common_ngram alone rescues ~8% of that bucket.
   The sample therefore stores the full per-rule vector (no short-circuit),
   plus `sole_blocker` (rescue requires touching exactly one rule) and
   `first_blocking` (kept only to validate against production behaviour).
2. **The pack is the single source of truth.** Rejection reasons and signals
   stored by a corpus are caches; the pack can always recompute them from raw
   text. New datasets plug in with nothing but text.
   *Scope note:* the current pack tooling (the vectorized rule mirror,
   pack_thresholds.py, the tag executor) is CC-chain-specific by design — thin
   adapters, not the skeleton. A structurally different filter (e.g. a
   model-based classifier) brings its own adapters inside its own pack; what
   it must provide, in increasing order of capability: (1) a per-document
   outcome label — enough for sampling, judging, and per-reason FP analysis;
   (2) a way to re-run it on one document — enables eval/tune iteration;
   (3) reusable per-document measurements — enables free threshold sweeps.
   The sampling/judge/eval skeleton and the governance rules are
   filter-shape-agnostic. No abstract filter interface is built until a
   second filter type actually exists; the boundary is the pack directory,
   and the acceptance bar for any new adapter is unchanged: re-running must
   reproduce production labels exactly on a held shard.
3. **The sample is a faithful snapshot; junk triage happens at judge time.**
   Obviously-hopeless documents (empty, a few words, pure symbol soup) are NOT
   dropped at sampling — dropping them there would silently condition every
   false-positive rate on an unversioned pre-filter, hiding exactly the class
   of mistakes this project exists to find. Instead the judge stage runs a
   conservative heuristic *triage tier* that auto-labels them incoherent
   without an LLM call (bounds far below any plausible tuned threshold, e.g.
   <5 words; versioned with the rubric; excluded docs counted per stratum and
   spot-checkable). Denominators stay complete; judge tokens are spent only on
   the ambiguous middle.
4. **Judge labels are versioned, cached, and calibrated.** Prompt/rubric
   carries a version; cache key `(text_hash, rubric_version, model)`; before
   trusting a backend at scale, compare it with human labels on ~100 documents.
   Backends are pluggable (API model first; a local open model on the GPU
   nodes when volume justifies the setup; human labels use the same interface).
5. **Two-layer tuner; the agent only gets the sandbox.** Numeric thresholds
   never need an LLM — sweeps over the labeled sample's stored signals are
   deterministic and free. The agent handles structural edits only, works on a
   copy of the pack + the labeled tune split, and never touches the cluster or
   the full corpus. Iteration cap, bounded diff surface (rules/ +
   thresholds.yaml), every step in the ledger.
6. **Tune/holdout split is enforced in eval.** Final metrics come from the
   holdout, which the agent never sees — thresholds tuned on 30k documents
   overfit like any other model.
7. **Apply is human-gated with corpus-level guardrails.** Before a tuned pack
   touches the corpus: estimate the kept-volume delta (from cached full-corpus
   signals where available, else a large random sample) and re-judge a fresh
   sample of the docs that flip status; a tuning result that changes kept
   volume by an order of magnitude is a red flag, not a win.
8. **Pack governance: one home, one lineage, data points at filters.** Filter
   versions will multiply (per dataset, per tuning round, per upstream
   update); sprawl is prevented by three rules. (a) Packs live ONLY in this
   repo's `filter_packs/` — other projects consume a pack at a pinned commit,
   never by copying directories around; the git history is the family tree,
   and each pack's CHANGELOG names its parent pack and what changed. (b) Every
   filtered data artifact carries a FILTER_INFO record (pack name + qf-tuner
   commit + date) — sample meta.json already does; apply outputs must. The
   reverse index ("which data did pack X filter") is derivable, never
   maintained. (c) An upstream rule change in the team pipeline becomes a NEW
   baseline snapshot (`cc_baseline_v2`), never an in-place edit — overwriting
   a baseline would orphan the provenance of everything filtered before it.
   The `keenable/quality-filtering/cc_qf` snapshot stays frozen as the
   historical record of qf_full-20260708. (d) The QF main repo
   (`poch4319/pipeline`, `quality_filtering/`) is where baselines come from —
   each baseline pack is byte-pinned to a named commit
   (`scripts/diff_upstream.sh` detects drift) — and where validated tuned
   packs go back to, as a PR whose diff is pack-vs-baseline with the pack's
   CHANGELOG and eval report as the description.
9. **Which rules may be tuned is config, not architecture.** Each pack carries
   a `tunable:` list; the tuner refuses to run while it is empty. Whether
   value-laden rules like word_count are in scope is a policy decision
   (deliberately deferred) — flipping it edits one line in a pack, not the
   system. Judging the sample before deciding gives the discussion data:
   per-rule false-positive mass will show what loosening each rule would buy.

## Stage 1 (sample) — implemented

Two-pass exact stratified sampling, one node, no container:

- count pass reads the reason column of a seeded random pool of shards (default
  1200 of 786k for keenable) → exact per-stratum counts;
- exact global ranks are drawn per stratum (default 1500/reason, 10000 kept)
  and mapped to (shard, local rank) via prefix sums;
- fetch pass fetches only the row groups containing drawn rows: ids + signals +
  QF-view text from the QF shard, raw text from the mirror shard (row-order
  mirroring verified per row on the id column; uid-join fallback otherwise);
- the violation vector is evaluated from stored signals under the pack's
  thresholds.yaml; invariants (kept ⇒ no violations; first violation in chain
  order ⇒ stored reason) are checked and written to meta.json.

Limits, by design: documents rejected before the signal stage (lang / url /
empty / oversize) carry null vectors — re-judging *those* against the doc-level
rules requires the eval stage's run_pack on raw text. Raw corpora
(`kind != qf_output_parquet`) wait for the same machinery. Near-threshold
oversampling (enriching docs just outside a threshold) is a planned refinement
of the draw, not needed for the first judge round.

## Open questions

- Tunable-rule policy (decision 9): decide after the first judge round, with
  per-rule FP numbers on the table. The word_count tension in particular:
  under a coherence-only rubric, short-but-coherent documents are "false
  positives" by definition, yet retaining them is a training-value question,
  not a coherence question.
- Judge backend and budget: first round ~37k docs ≈ tens of USD on a small API
  model; local vLLM on MI210 worth it only for routine per-dataset reruns.
- Para-rules (fraction_of_duplicate_paragraphs etc.) fire on nothing (both
  extractors emit no `\n\n`) — candidates for pruning in a tuned pack, or for
  fixing if paragraph structure is ever restored upstream.
