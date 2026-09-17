#!/usr/bin/env python3
"""Split a blind input into per-endpoint shards, skipping already-judged ids.

Reads every existing judge output matching WORKDIR/judge_out/shard_*.jsonl
(including earlier resume rounds), collects the ids that already carry a
decision, and splits the remaining documents round-robin into N shard inputs
under WORKDIR/judge_in/round_<R>/shard_<K>.jsonl. Prints the round directory,
or "DONE" when nothing is left.

usage: python3 shard_blind_input.py BLIND_JSONL WORKDIR NUM_SHARDS
"""
import json
import sys
from pathlib import Path

blind_path = Path(sys.argv[1])
work_dir = Path(sys.argv[2])
num_shards = int(sys.argv[3])

judged_ids = set()
for output_path in sorted((work_dir / "judge_out").glob("shard_*.jsonl")):
    for line in open(output_path, encoding="utf-8"):
        if line.strip():
            judged_ids.add(json.loads(line)["id"])

pending_lines = []
for line in open(blind_path, encoding="utf-8"):
    if line.strip() and json.loads(line)["id"] not in judged_ids:
        pending_lines.append(line)

if not pending_lines:
    print("DONE")
    sys.exit(0)

round_number = 0
while (work_dir / "judge_in" / f"round_{round_number}").exists():
    round_number += 1
round_dir = work_dir / "judge_in" / f"round_{round_number}"
round_dir.mkdir(parents=True)

handles = [open(round_dir / f"shard_{shard:02d}.jsonl", "x", encoding="utf-8")
           for shard in range(num_shards)]
for index, line in enumerate(pending_lines):
    handles[index % num_shards].write(line)
for handle in handles:
    handle.close()

print(f"{len(judged_ids):,} already judged, {len(pending_lines):,} pending "
      f"-> {num_shards} shards", file=sys.stderr)
print(round_dir)
