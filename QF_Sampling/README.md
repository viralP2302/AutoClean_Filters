# qf-tuner

LLM-judge-driven tuning of quality-filter rule chains.

The idea (task brief, 2026-09): sample documents the current quality filter
rejected, ask an LLM judge a deliberately narrow question — *"is this text
coherent and properly extracted, without repetition or noise?"* (not "is it
good for training") — call judge-coherent-but-rejected documents false
positives, then let an automated tuner adjust the filter (thresholds by
deterministic sweep, rule code by an LLM agent) to retain them, hill-climbing
a precision/recall trade-off.

Born from the keenable QF round (`../keenable`), but dataset-agnostic by
design: onboarding a new corpus means writing one YAML under
`configs/datasets/`, not touching code. See `docs/DESIGN.md` for the full
design and its rationale.

## Status

| stage | command | state |
|---|---|---|
| 1. sample | `qf_tuner sample` | **implemented** |
| 1b. annotate | `qf_tuner annotate` | **implemented** |
| 2. judge | `qf_tuner judge` | planned |
| 3. eval | `qf_tuner eval` | planned |
| 4. tune | `qf_tuner tune` | planned |
| 5. report / apply | `qf_tuner report` | planned |

## Layout

```
configs/datasets/        one YAML per corpus (paths, column mapping)
filter_packs/
  cc_baseline/           the CC/TxT360 rule chain — READ-ONLY baseline
    thresholds.yaml      authoritative thresholds (+ `tunable:` policy list)
    rules/               executable rule chain, byte-pinned to the QF main
                         repo (poch4319/pipeline @ eb1a468 — see PROVENANCE)
src/qf_tuner/
  sampler/               pure stratified sampling (pipeline.py, shard_io.py)
  annotate/              verdict columns for a sample (pipeline.py; pack.py +
                         rules.py = pack loading and the rules.yaml interpreter)
  provenance.py          20 lines: which commit produced an output (for meta)
  cli.py                 command line (future stages sit alongside: judge/, ...)
scripts/                 sbatch wrappers, bad-node excludes, pack tooling:
                           new_baseline.sh    onboard a new filter version (one command)
                           pack_thresholds.py generate/check thresholds.yaml from rule code
                           diff_upstream.sh   detect drift vs the QF main repo
data/                    outputs (gitignored): samples/, labels/, runs/
```

## Running stage 1 (sample)

Uses the `keenable` conda env (pyarrow/pandas/pyyaml only — no container).

```bash
# smoke test on the login node (~1 min)
PYTHONPATH=src python -m qf_tuner sample --dataset configs/datasets/keenable.yaml \
    --out data/samples/smoke --pool-shards 3 --target-default 3 --target kept=10

# real run, one node via Slurm (defaults: pool 1200 shards, 1500 per label, kept=10000)
sbatch --exclude=$(grep -v '^#' scripts/bad_nodes.txt | paste -sd,) \
    scripts/run_sample.sbatch configs/datasets/keenable.yaml data/samples/keenable_v0

# then add the per-rule verdict columns (pack = the one in the corpus's provenance)
PYTHONPATH=src python -m qf_tuner annotate --sample data/samples/keenable_v0 \
    --pack filter_packs/cc_baseline
```

Samples are immutable: the command refuses to overwrite an existing `--out`.
Re-running with the same seed and pool reproduces the same draw.

Building the judge stage against a sample? The output contract (columns,
guarantees, and the labels format the judge must produce) is
**`docs/SAMPLE_OUTPUT.md`** — code internals may change, that file is the
interface. Onboarding a new corpus? The input-side contract (what a dataset
must provide, column semantics, onboarding checklist) is
**`docs/DATASET_INPUT.md`**.

### Output

`<out>/sample.parquet` — one row per sampled document:

- `uid, shard, row_idx, url, language, fast_text_lang(+_score)` — identity
- `qf_reason` — production outcome (first rule that rejected it, or `kept`);
  `strat` — the stratum it was drawn for (currently == qf_reason)
- all quality-signal columns (word_count, ngram fractions, …)
- added by `qf_tuner annotate` (or present from filter time): `viol_<rule>` —
  each rule re-evaluated independently, **without** chain short-circuiting;
  null for documents rejected before the signal stage (lang / url / empty /
  oversize) — plus `n_violations`, `sole_blocker` (the rule, when exactly one
  is violated), `first_blocking` (chain-order derivation; must reproduce
  `qf_reason`). A sample without these prints a loud warning.
- `text` (what the filter saw/kept: line-filtered + ftfy + PII-scrubbed —
  the same `text` column as everywhere else in the pipeline),
  `text_raw` (pre-QF text — what the pack re-runs on in later stages)

`<out>/meta.json` — full reproducibility record: seed, pool, per-stratum
target/available/achieved, invariant checks (kept docs violate nothing;
first_blocking reproduces qf_reason), shard errors. `pool_shards.txt` — the pool.

## Conventions

- Slurm: single-node jobs on `--qos=test` (4 h cap, highest priority); always
  exclude `scripts/bad_nodes.txt`; logs land in `logs/`.
- `filter_packs/cc_baseline/` is never edited. Tuning forks the pack directory
  and logs every change in the fork's `CHANGELOG.md`.
- New upstream filter version: `scripts/new_baseline.sh <pack_name>` — the
  constraints the upstream code must keep are in `docs/FILTER_AUTHORING.md`.
- Data outputs live under `data/` and are gitignored; code and configs are
  committed.
