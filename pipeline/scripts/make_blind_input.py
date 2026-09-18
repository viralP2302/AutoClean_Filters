#!/usr/bin/env python3
"""Adapter: sample.parquet -> blind judge input jsonl.

Emits exactly the schema 02_llm_labeling/run_inference.py consumes:
one line per document, {"id", "text", "coverage"}. `id` is the corpus uid, so
labels join back to the sample (and to qf_full) with no extra mapping. Nothing
else — no qf_reason, no signals — ever enters this file: blinding happens
here, at the interface.

usage: python3 make_blind_input.py SAMPLE_DIR OUT_JSONL
"""
import json
import sys
from pathlib import Path

import pandas as pd

sample_dir = Path(sys.argv[1])
out_path = Path(sys.argv[2])
if out_path.exists():
    sys.exit(f"{out_path} already exists — blind inputs are immutable, pick a new path")

frame = pd.read_parquet(sample_dir / "sample.parquet", columns=["uid", "text"])
if not frame["uid"].is_unique:
    sys.exit("sample uids are not unique")
empty_count = (frame["text"].fillna("").str.strip() == "").sum()
if empty_count:
    sys.exit(f"{empty_count} documents have empty text — refuse to send them to the judge")

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open("x", encoding="utf-8") as handle:
    for uid, text in zip(frame["uid"], frame["text"]):
        handle.write(json.dumps({"id": uid, "text": text, "coverage": "complete"},
                                ensure_ascii=False) + "\n")
print(f"wrote {len(frame):,} blind documents -> {out_path}")
