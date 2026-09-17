"""Annotate stage: add per-rule verdict columns to a drawn sample.

Input: a sample directory (sample.parquet with the label column `qf_reason`
and the filter's measurement columns). Output: the same sample.parquet with 19
columns added —

  viol_<rule> ×N   each declared rule re-evaluated independently on the stored
                   measurements (no chain short-circuiting); null for documents
                   whose measurements were never computed
  n_violations     how many rules the document violates
  sole_blocker     the rule name when exactly one is violated
  first_blocking   first violated rule in declared order

plus the invariant check that makes a wrong --pack impossible to miss: for
every document labeled `kept` there must be zero violations, and for every
signal-stage reject the first violation must reproduce the stored qf_reason.
Mismatches abort the annotation (nothing is written).

`kept` is the reserved label for accepted documents (docs/NAMING.md). Skippable
entirely when the corpus already carries viol_* columns from filter time.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..provenance import git_state
from .pack import Pack

KEPT_LABEL = "kept"
LABEL_COLUMN = "qf_reason"


def add_verdict_columns(frame, pack):
    """The 19 derived columns + invariant counts. Pure; used on any frame."""
    verdicts = pack.verdicts(frame)
    signal_stage_mask = verdicts.iloc[:, 0].notna()

    violation_counts = pd.Series(pd.NA, index=frame.index, dtype="Int32")
    violation_counts[signal_stage_mask] = \
        verdicts.loc[signal_stage_mask].astype(bool).sum(axis=1).astype("int32")

    sole_blockers = pd.Series(pd.NA, index=frame.index, dtype=object)
    single_violation_mask = signal_stage_mask & (violation_counts == 1)
    if single_violation_mask.any():
        sole_blockers[single_violation_mask] = (
            verdicts.loc[single_violation_mask].astype(bool).idxmax(axis=1)
            .str.replace("viol_", "", regex=False))

    first_blocking = pack.first_blocking(verdicts)

    kept_mask = frame[LABEL_COLUMN] == KEPT_LABEL
    kept_with_violations = int((kept_mask & (violation_counts > 0)).sum())
    checked_rejects_mask = signal_stage_mask & ~kept_mask
    mismatch_count = int((first_blocking[checked_rejects_mask]
                          != frame.loc[checked_rejects_mask, LABEL_COLUMN]).sum())

    frame = frame.copy()
    frame["n_violations"] = violation_counts
    frame["sole_blocker"] = sole_blockers
    frame["first_blocking"] = first_blocking
    frame = pd.concat([frame, verdicts], axis=1)
    text_columns = [name for name in ("text", "text_raw") if name in frame.columns]
    frame = frame[[name for name in frame.columns if name not in text_columns] + text_columns]
    invariants = {"kept_with_violations": kept_with_violations,
                  "first_blocking_mismatches": mismatch_count,
                  "stage_rejects_checked": int(checked_rejects_mask.sum())}
    return frame, invariants


def run(args):
    sample_dir = Path(args.sample)
    sample_path = sample_dir / "sample.parquet"
    frame = pd.read_parquet(sample_path)

    already_annotated = [name for name in frame.columns if name.startswith("viol_")]
    if already_annotated:
        sys.exit(f"{sample_path} already carries {len(already_annotated)} viol_* columns — "
                 "nothing to do (annotation is not repeated)")
    if LABEL_COLUMN not in frame.columns:
        sys.exit(f"{sample_path} has no `{LABEL_COLUMN}` column — not a labeled sample")

    pack = Pack(args.pack)
    missing = [name for name in pack.required_columns() if name not in frame.columns]
    if missing:
        sys.exit("this sample lacks measurement columns the pack's rules read: "
                 f"{missing} — the corpus was filtered without storing measurements; "
                 "annotation cannot help (the filter itself must be re-run)")

    frame, invariants = add_verdict_columns(frame, pack)
    print(f"invariants: kept_with_violations={invariants['kept_with_violations']} (expect 0), "
          f"first_blocking_mismatches={invariants['first_blocking_mismatches']}"
          f"/{invariants['stage_rejects_checked']} (expect 0)", flush=True)
    if invariants["kept_with_violations"] or invariants["first_blocking_mismatches"]:
        sys.exit("ABORT: the pack does not reproduce this data's labels — wrong --pack "
                 "for this corpus, or the pack's rules.yaml is out of sync. Nothing written.")

    frame.to_parquet(sample_path, compression="zstd", index=False)

    meta_path = sample_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["annotate"] = {
        "pack": pack.name, "pack_path": str(pack.path.resolve()),
        "qf_tuner_git": git_state(), "invariants": invariants,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"annotated {len(frame):,} docs with {len(pack.rule_names)} rules -> {sample_path}",
          flush=True)
