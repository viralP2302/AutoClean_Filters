#!/usr/bin/env python3
"""Stage 1: stratified sampling of a prepared dataset (README.md#input-schema).

The sampler records the producing filter version and samples prepared data:

  input   parquet shards where every document carries a label column
          (`qf_reason`: the reserved value `kept` for accepted documents, any
          other value = a rejection label) — plus whatever
          other columns exist, which are passed through untouched
  output  a stratified sample: for each distinct label, `--target-default`
          documents (overridable per label with `--target LABEL=COUNT`),
          drawn uniformly within the label across a seeded shard pool

The flow, in the order run() calls it:

  choose_pool     seeded random subset of the manifest (the shard pool)
  plan_columns    which columns the fetch pass will read (probe one shard)
  count_pass      exact per-label counts across the pool (label column only)
  draw            exact global ranks per label, mapped to (shard, local rank)
  fetch_pass      read just the drawn rows + the raw-text mirror
  run             write sample.parquet + meta.json + pool_shards.txt

Signals and verdict columns (viol_*, n_violations, ...) are copied from the
input. Dataset preparation, applying QF, and filter versioning live upstream
of this command. Sampling records the named pack's fingerprint without
executing its code or generating QF columns.
"""

import argparse
import json
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from multiprocessing import Pool, set_start_method
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

from shard_io import count_shard, fetch_shard, initialize_worker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from filter_provenance import describe_pack

LABEL_COLUMN_KEY = "reason_column"
TOOL_VERSION = "0.3.0"


def git_state():
    """Record the producing code revision, including uncommitted changes."""
    cwd = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=cwd,
                                    capture_output=True, text=True).stdout.strip())
        return (commit + "-dirty") if dirty else (commit or None)
    except Exception:
        return None


def parse_targets(target_default, target_overrides):
    """['kept=10000', 'lorem_ipsum=500'] -> {'kept': 10000, 'lorem_ipsum': 500}."""
    overrides = {}
    for entry in target_overrides or []:
        label, _, count = entry.partition("=")
        if not label or not count.isdigit():
            sys.exit(f"--target expects LABEL=COUNT, got {entry!r}")
        overrides[label] = int(count)
    return target_default, overrides


def choose_pool(dataset_config, pool_size, seed):
    """Seeded draw of the shard pool; returns (pool_shards, manifest_size, rng).

    The SAME rng continues into draw(), so one seed determines the entire sample.
    """
    manifest_names = [line.strip() for line in open(dataset_config["manifest"]) if line.strip()]
    rng = random.Random(seed)
    pool_shards = sorted(rng.sample(manifest_names, min(pool_size, len(manifest_names))))
    return pool_shards, len(manifest_names), rng


def plan_columns(dataset_config, probe_shard):
    """Decide which columns the fetch pass reads, probing one shard's schema.

    Hard-errors if the label column or any column named in the yaml mapping is
    missing from the data. Everything not on the known identity/drop list is
    passed through untouched (measurements, pre-existing viol_* columns,
    anything future).
    """
    columns = dataset_config["columns"]
    schema = pq.ParquetFile(Path(dataset_config["qf_root"]) / probe_shard).schema_arrow

    required = {dataset_config[LABEL_COLUMN_KEY]: "the label column (reason_column)",
                columns["id"]: "columns.id", columns["url"]: "columns.url",
                columns["vendor_lang"]: "columns.vendor_lang", "text": "the text column"}
    missing = [f"{name} ({role})" for name, role in required.items()
               if name not in schema.names]
    if missing:
        sys.exit("ERROR: the data does not have columns the dataset yaml promises:\n  "
                 + "\n  ".join(missing)
                 + f"\n(probed {probe_shard}; fix the yaml mapping or the data)")
    skip_columns = {columns["id"], columns["url"], columns["vendor_lang"],
                    dataset_config[LABEL_COLUMN_KEY], "text",
                    "title", "description", "is_best_duplicate", "orig_text_has_dup_lines",
                    "fast_text_lang", "fast_text_lang_score"}
    passthrough_columns = [name for name in schema.names if name not in skip_columns]
    fetch_columns = [columns["id"], columns["url"], columns["vendor_lang"]] \
        + [name for name in ("fast_text_lang", "fast_text_lang_score") if name in schema.names] \
        + [dataset_config[LABEL_COLUMN_KEY]] + passthrough_columns + ["text"]
    return fetch_columns


def count_pass(pool_shards, dataset_config, fetch_columns, processes):
    """Exact per-label counts for every pool shard (reads one column per shard)."""
    started = time.perf_counter()
    counts_by_shard, errors = {}, []
    with Pool(processes, initializer=initialize_worker,
              initargs=(dataset_config, fetch_columns)) as worker_pool:
        results = worker_pool.imap_unordered(count_shard, pool_shards, chunksize=4)
        for finished, (shard_name, shard_counts, error) in enumerate(results, 1):
            if error:
                errors.append((shard_name, error))
            else:
                counts_by_shard[shard_name] = shard_counts
            if finished % 200 == 0 or finished == len(pool_shards):
                print(f"  count pass {finished}/{len(pool_shards)}", flush=True)
    usable_shards = [name for name in pool_shards if name in counts_by_shard]
    label_totals = Counter()
    for shard_name in usable_shards:
        label_totals.update(counts_by_shard[shard_name])
    print(f"count pass done in {time.perf_counter() - started:.0f}s: "
          f"{len(usable_shards)} usable shards, {sum(label_totals.values()):,} docs, "
          f"{len(label_totals)} labels ({len(errors)} shard errors)", flush=True)
    return counts_by_shard, usable_shards, label_totals, errors


def draw(rng, usable_shards, counts_by_shard, label_totals, target_default, target_overrides):
    """Exact global ranks per label, mapped to (shard, rank within that shard).

    Within one label, imagine its documents laid out shard by shard in pool
    order; drawing k global positions uniformly and mapping them back via
    cumulative counts gives every document of the label an equal chance.
    """
    targets = {label: target_overrides.get(label, target_default) for label in label_totals}
    wanted_by_shard = {name: {} for name in usable_shards}
    for label in sorted(label_totals):
        draw_count = min(targets[label], label_totals[label])
        if draw_count == 0:
            continue
        global_ranks = np.sort(rng.sample(range(label_totals[label]), draw_count))
        per_shard_counts = np.array([counts_by_shard[name].get(label, 0)
                                     for name in usable_shards])
        cumulative_ends = np.cumsum(per_shard_counts)
        shard_of_rank = np.searchsorted(cumulative_ends, global_ranks, side="right")
        local_ranks = global_ranks - (cumulative_ends - per_shard_counts)[shard_of_rank]
        for shard_index in np.unique(shard_of_rank):
            wanted_by_shard[usable_shards[shard_index]][label] = \
                local_ranks[shard_of_rank == shard_index]
    return {name: wanted for name, wanted in wanted_by_shard.items() if wanted}, targets


def fetch_pass(wanted_by_shard, dataset_config, fetch_columns, processes):
    """Pull the drawn rows out of every shard that had a hit."""
    started = time.perf_counter()
    jobs = list(wanted_by_shard.items())
    shard_frames, errors, fallback_count = [], [], 0
    with Pool(processes, initializer=initialize_worker,
              initargs=(dataset_config, fetch_columns)) as worker_pool:
        results = worker_pool.imap_unordered(fetch_shard, jobs, chunksize=2)
        for finished, (shard_name, frame, used_fallback, error) in enumerate(results, 1):
            if error:
                errors.append((shard_name, error))
            else:
                shard_frames.append(frame)
            fallback_count += bool(used_fallback)
            if finished % 100 == 0 or finished == len(jobs):
                print(f"  fetch pass {finished}/{len(jobs)}", flush=True)
    sample_frame = pd.concat(shard_frames, ignore_index=True)
    print(f"fetch pass done in {time.perf_counter() - started:.0f}s: "
          f"{len(sample_frame):,} docs from {len(shard_frames)} shards "
          f"({len(errors)} shard errors, {fallback_count} id-join fallbacks)", flush=True)
    return sample_frame, errors, fallback_count


def order_columns(sample_frame, dataset_config):
    columns = dataset_config["columns"]
    leading = [columns["id"], "shard", "row_idx", columns["url"], columns["vendor_lang"],
               "fast_text_lang", "fast_text_lang_score", dataset_config[LABEL_COLUMN_KEY],
               "strat"]
    leading = [name for name in leading if name in sample_frame.columns]
    trailing = ["text", "text_raw"]
    middle = [name for name in sample_frame.columns if name not in leading + trailing]
    return sample_frame[leading + middle + trailing]


def run(args):
    try:
        filter_pack = describe_pack(args.filter_pack)
    except (OSError, ValueError) as error:
        sys.exit(f"ERROR: {error}")
    try:
        set_start_method("fork")  # python>=3.14 defaults to forkserver; workers need our globals
    except RuntimeError:
        pass

    dataset_config = yaml.safe_load(Path(args.dataset).read_text())
    if dataset_config.get("kind") != "qf_output_parquet":
        sys.exit("sampling requires kind: qf_output_parquet with QF results already "
                 "prepared upstream (see README.md#input-schema)")
    if (dataset_config.get(LABEL_COLUMN_KEY) != "qf_reason"
            or dataset_config.get("columns", {}).get("id") != "uid"):
        sys.exit("the pipeline input contract requires reason_column: qf_reason and "
                 "columns.id: uid; prepare these columns upstream")
    target_default, target_overrides = parse_targets(args.target_default, args.target)
    output_dir = Path(args.out)
    if (output_dir / "sample.parquet").exists():
        sys.exit(f"{output_dir / 'sample.parquet'} already exists — pick a new --out "
                 "(samples are immutable)")
    output_dir.mkdir(parents=True, exist_ok=True)

    pool_shards, manifest_size, rng = choose_pool(dataset_config, args.pool_shards, args.seed)
    if not pool_shards:
        sys.exit("the dataset manifest contains no shards")
    print(f"dataset={dataset_config['name']} pool={len(pool_shards)}/{manifest_size} shards "
          f"seed={args.seed} processes={args.processes}", flush=True)

    fetch_columns = plan_columns(dataset_config, pool_shards[0])
    counts_by_shard, usable_shards, label_totals, count_errors = \
        count_pass(pool_shards, dataset_config, fetch_columns, args.processes)
    wanted_by_shard, targets = draw(rng, usable_shards, counts_by_shard, label_totals,
                                    target_default, target_overrides)
    sample_frame, fetch_errors, fallback_count = \
        fetch_pass(wanted_by_shard, dataset_config, fetch_columns, args.processes)

    sample_frame["strat"] = sample_frame[dataset_config[LABEL_COLUMN_KEY]]
    sample_frame = order_columns(sample_frame, dataset_config)
    has_verdicts = any(name.startswith("viol_") for name in sample_frame.columns)

    achieved = sample_frame["strat"].value_counts().to_dict()
    (output_dir / "pool_shards.txt").write_text("".join(name + "\n" for name in usable_shards))
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": {"version": TOOL_VERSION, "git": git_state()},
        "filter_pack": filter_pack,
        "dataset": {"name": dataset_config["name"], "config": str(Path(args.dataset).resolve()),
                    "qf_root": dataset_config["qf_root"], "raw_root": dataset_config["raw_root"]},
        "seed": args.seed,
        "pool": {"requested": args.pool_shards, "usable": len(usable_shards),
                 "manifest_total": manifest_size},
        "targets": {"default": target_default, "overrides": target_overrides},
        "strata": {label: {"target": min(targets[label], label_totals[label]),
                           "in_pool": int(label_totals[label]),
                           "achieved": int(achieved.get(label, 0))}
                   for label in sorted(label_totals)},
        "fetch": {"raw_join_fallbacks": fallback_count},
        "verdicts_present": has_verdicts,
        "errors": {"count_pass": count_errors[:20], "fetch_pass": fetch_errors[:20],
                   "count_pass_total": len(count_errors), "fetch_pass_total": len(fetch_errors)},
        "rows": len(sample_frame),
    }
    sample_frame.to_parquet(output_dir / "sample.parquet", compression="zstd", index=False)
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    name_width = max(len(label) for label in label_totals)
    print(f"\n{'label'.ljust(name_width)}  in_pool      achieved")
    for label in sorted(label_totals, key=label_totals.get, reverse=True):
        print(f"{label.ljust(name_width)}  {label_totals[label]:>11,}  "
              f"{achieved.get(label, 0):>8,}")
    print(f"\nwrote {len(sample_frame):,} docs -> {output_dir / 'sample.parquet'}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Stratified sampling of prepared QF-labeled Parquet shards.",
        epilog="Input contract: README.md#input-schema. "
               "Existing QF columns are copied; no filter is applied.")
    parser.add_argument("--dataset", required=True, help="prepared-dataset YAML")
    parser.add_argument("--filter-pack", required=True,
                        help="saved version name in filters/packs/ that produced the dataset")
    parser.add_argument("--out", required=True, help="new sample directory")
    parser.add_argument("--pool-shards", type=int, default=1200)
    parser.add_argument("--target-default", type=int, default=1500,
                        help="documents per qf_reason, unless overridden")
    parser.add_argument("--target", action="append", metavar="LABEL=COUNT",
                        default=["kept=10000"],
                        help="repeatable per-label target (includes kept=10000 by default)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--processes", type=int, default=32)
    args = parser.parse_args()
    if args.pool_shards <= 0 or args.processes <= 0 or args.target_default < 0:
        parser.error("pool-shards/processes must be positive; target-default must be non-negative")
    return args


if __name__ == "__main__":
    run(parse_args())
