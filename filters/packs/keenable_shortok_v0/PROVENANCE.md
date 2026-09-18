# cc_baseline — provenance and the link to the QF main repo

The upstream ("QF main") repository is **github.com/poch4319/pipeline**; its
`quality_filtering/` directory is the production CC rule chain.

This pack pins that code:

- `rules/` — the 10 rule modules, **byte-identical to pipeline commit
  `eb1a468`** (verified 2026-09-08), plus an empty `__init__.py` added here
  for importability. The same code (via the intermediate snapshot
  `keenable/quality-filtering/cc_qf/`, copied 2026-08-31) produced
  `qf_full-20260708`, so this pack is the exact filter behind all delivered
  keenable data.
- `thresholds.yaml` — duplicates `rules/threshold.py` (`DataThreshold`
  defaults) value for value. The YAML is what qf-tuner reads; in derived packs
  it is the authoritative override applied onto the code defaults. It is never
  maintained by hand: `scripts/pack_thresholds.py PACK --write` generates it
  from the pack's own code, and the check mode (no flag) verifies a baseline's
  yaml matches its code exactly (verified for this pack, 2026-09-08).

## How the two repos connect

- **Upstream → here (adopting changes).** An upstream rule change never edits
  this pack. To adopt one, cut a NEW baseline (`filter_packs/cc_baseline_v2/`)
  pinned to the new commit; old baselines stay frozen so the provenance of
  already-filtered data survives. Run `scripts/diff_upstream.sh` to see
  whether upstream has drifted from a pack.
- **Here → upstream (contributing a tuned pack).** A validated tuned pack goes
  back as a normal PR to `poch4319/pipeline`: the diff is the pack's rules +
  thresholds vs `cc_baseline`, and the PR description is the pack's CHANGELOG
  plus its eval report. Alternatively, production can run a pack directly via
  the future `qf_tuner apply` without touching the main repo — either way the
  output data carries a FILTER_INFO record naming the exact pack and commit.

## Rules of this directory

- **Never edit this pack** — it is the fixed baseline every tuning run starts
  from and is compared against.
- To tune, copy the whole pack to a new directory
  (e.g. `filter_packs/keenable_v1/`), edit the copy, and record every change
  in that pack's `CHANGELOG.md`.
