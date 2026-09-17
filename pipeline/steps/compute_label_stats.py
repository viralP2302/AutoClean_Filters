#!/usr/bin/env python3
"""End-of-run statistics: join merged judge output back to the sample.

Emits the run-over-run comparison numbers (the "sanity-check kit" set):
  * decision counts (keep / reject / review)
  * per-rule recovery rate with explicit denominators (review counted as
    NOT recovered — conservative)
  * QF-kept agreement rate (raw and non-review)
  * review share per rule
Writes stats.json + stats.md next to the merged output.

usage: python3 compute_label_stats.py MERGED_JSONL SAMPLE_DIR
"""
import json
import sys
from pathlib import Path

import pandas as pd

merged_path = Path(sys.argv[1])
sample_dir = Path(sys.argv[2])

decisions = []
for line in open(merged_path, encoding="utf-8"):
    if line.strip():
        row = json.loads(line)
        decisions.append((row["id"], row["decision"]))
labels = pd.DataFrame(decisions, columns=["uid", "decision"])
if not labels["uid"].is_unique:
    sys.exit("duplicate ids in merged judge output")

sample = pd.read_parquet(sample_dir / "sample.parquet", columns=["uid", "qf_reason"])
joined = labels.merge(sample, on="uid", how="left", validate="one_to_one")
if joined["qf_reason"].isna().any():
    sys.exit("judge output contains ids not present in the sample")

overall = joined["decision"].value_counts().to_dict()
kept_arm = joined[joined["qf_reason"] == "kept"]["decision"].value_counts().to_dict()
kept_total = sum(kept_arm.values())
kept_decided = kept_arm.get("keep", 0) + kept_arm.get("reject", 0)

per_rule = []
for rule, group in joined[joined["qf_reason"] != "kept"].groupby("qf_reason"):
    counts = group["decision"].value_counts().to_dict()
    total = len(group)
    per_rule.append({
        "rule": rule,
        "keep": counts.get("keep", 0),
        "reject": counts.get("reject", 0),
        "review": counts.get("review", 0),
        "total": total,
        "recovery_rate_conservative": counts.get("keep", 0) / total,
        "review_share": counts.get("review", 0) / total,
    })
per_rule.sort(key=lambda entry: -entry["recovery_rate_conservative"])

stats = {
    "documents": len(joined),
    "decisions": overall,
    "kept_agreement": {
        "counts": kept_arm,
        "keep_rate_raw": kept_arm.get("keep", 0) / kept_total if kept_total else None,
        "keep_rate_non_review": (kept_arm.get("keep", 0) / kept_decided) if kept_decided else None,
    },
    "per_rule": per_rule,
    "note": "recovery_rate_conservative = LLM keep / ALL labeled rejects of the rule "
            "(review counted as not recovered)",
}
stats_json = merged_path.with_name("stats.json")
stats_json.write_text(json.dumps(stats, indent=2))

lines = [
    "# Judge run statistics", "",
    f"Documents: {len(joined):,}  |  decisions: {overall}", "",
    f"QF-kept agreement: raw {stats['kept_agreement']['keep_rate_raw']:.1%}, "
    f"non-review {stats['kept_agreement']['keep_rate_non_review']:.1%} ({kept_arm})", "",
    "| rule | keep | reject | review | total | recovery (conservative) | review share |",
    "|---|---|---|---|---|---|---|",
]
for entry in per_rule:
    lines.append(f"| {entry['rule']} | {entry['keep']} | {entry['reject']} | "
                 f"{entry['review']} | {entry['total']} | "
                 f"{entry['recovery_rate_conservative']:.0%} | {entry['review_share']:.0%} |")
stats_md = merged_path.with_name("stats.md")
stats_md.write_text("\n".join(lines) + "\n")
print(f"wrote {stats_json} and {stats_md}")
