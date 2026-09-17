# keenable_shortok_v0 — fork of cc_baseline

2026-09-17, forked from `cc_baseline` (upstream pin unchanged, see PROVENANCE.md).

Single change: `thresholds.yaml` `word_count: [50, 100000]` → `[1, 100000]`
(the 50-word lower bound is disabled; the 100k upper bound stays). Everything
else — rules.yaml, rules/ code, all other thresholds — is byte-identical to
cc_baseline, so thresholds.yaml deliberately diverges from the pinned
threshold.py on this one key.

Purpose: the short-document ablation dataset for Yuan
(`keenable-qf-shortok-120B`): recover documents rejected ONLY for being under
50 words (all other rules still enforced).
