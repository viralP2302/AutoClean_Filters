# Quality-filter authoring constraints

What the `quality_filtering/` code in the QF main repo
(github.com/poch4319/pipeline) must keep true so that ANY version of it can be
brought into this repo as a baseline pack with `scripts/new_baseline.sh`.
Break one and the onboarding gates fail loudly — nothing downstream silently
misbehaves.

## Hard constraints

1. **Every threshold number lives in `threshold.py`, as a default of the
   `DataThreshold` dataclass.** No numeric threshold buried inside rule logic.
   Allowed value shapes: scalar (int / float / bool), a `(low, high)` range
   tuple, or a per-n list `[(n, threshold), ...]` for the n-gram rules.
   This is what makes thresholds.yaml generatable and threshold sweeps
   possible without touching code.
2. **`threshold.py` imports the standard library only.** It gets loaded on its
   own, outside the QF runtime (no fasttext/nltk available), by
   `scripts/pack_thresholds.py`.
3. **Flat module layout with bare-name imports** (`from data import ...`).
   The directory must work as a pack's `rules/` via a single path insert — no
   package-relative imports, no nested packages.
4. **Rejection accounting convention.** A rule that rejects a document
   increments exactly one specific `DataStatistics` counter named
   `doc_removed_by_<reason>`; umbrella counters (bumped on entry, reverted on
   pass) stay in the known set. The per-document rejection label IS the
   counter name minus the prefix, so **never rename an existing counter** —
   that renames the reason and breaks every longitudinal comparison.
5. **Measurements are typed fields of `DataAttributes`** (float / int / bool;
   n-gram measurements as lists of `(n, fraction)` aligned with the threshold
   lists). Drivers flatten them into output columns by dataclass
   introspection, so a new measurement = a new typed field, picked up
   automatically — never printed, parsed, or hard-coded downstream.
6. **Rules are per-document, deterministic, and pure**: no I/O, no randomness,
   no global mutable state inside the chain. Heavy assets (blocklists, models)
   load once through the existing loader functions that take explicit paths.

## What each kind of change costs downstream

| change in the main repo | what must happen in qf-tuner |
|---|---|
| threshold value only | nothing — regenerate the pack yaml (new_baseline.sh does it) |
| new measurement (new `DataAttributes` field) | nothing — auto-flattened |
| add / remove / reorder a rule | edit the pack's `rules.yaml` (one declaration per rule: name, kind, signal, threshold key, in chain order); the sample invariant (first_blocking must reproduce qf_reason, 100%) blocks any mismatch |
| a rule with a genuinely new SHAPE (not greater/less/range/flag/any-ngram) | add the new `kind` once to the interpreter `src/qf_tuner/annotate/rules.py`, then declare it in `rules.yaml` |
| rename a reason / counter | don't — see constraint 4 |
| structural rework (no longer a rule chain) | that is a new filter shape: it brings its own pack adapters (DESIGN decision 2, scope note) |

## Onboarding a new version

```bash
scripts/new_baseline.sh cc_baseline_v2        # copy + generate + gate, one command
```

The script copies the rule modules (driver and ops scripts stay upstream),
generates `thresholds.yaml` from the copied code, pins the upstream commit in
`PROVENANCE.md`, and runs three gates: thresholds extractable, yaml
round-trips exactly, copy matches the upstream tree. It refuses to overwrite
an existing pack — versions only ever accumulate.
