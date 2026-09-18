"""Shard-level I/O for the sampler: the two multiprocessing passes.

count pass  read only the reason column of a shard, tally rows per stratum.
fetch pass  read just the drawn rows of a shard (row-group pruned), plus the
            matching pre-QF text from the mirror shard in raw_root — same file
            name, same row order, verified per row on the id column, with an
            id-join fallback if the mirror assumption ever breaks.

Workers inherit WORKER_STATE via fork; initialize_worker fills it before the
pool starts.
"""

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

WORKER_STATE = {}


def initialize_worker(dataset_config, fetch_columns):
    WORKER_STATE["dataset_config"] = dataset_config
    WORKER_STATE["fetch_columns"] = fetch_columns


def read_reason_column(parquet_file, reason_column):
    values = parquet_file.read(columns=[reason_column]).column(0).to_pylist()
    return np.array(values, dtype=object)


def count_shard(shard_name):
    """Count pass worker: exact per-reason row counts of one shard."""
    dataset_config = WORKER_STATE["dataset_config"]
    try:
        parquet_file = pq.ParquetFile(Path(dataset_config["qf_root"]) / shard_name)
        reasons = read_reason_column(parquet_file, dataset_config["reason_column"])
        values, counts = np.unique(reasons, return_counts=True)
        return shard_name, {str(v): int(c) for v, c in zip(values, counts)}, None
    except Exception as error:
        return shard_name, None, repr(error)


def row_group_bounds(metadata):
    """Cumulative row offsets of each row group: [0, end_of_rg0, end_of_rg1, ...]."""
    return np.cumsum([0] + [metadata.row_group(i).num_rows
                            for i in range(metadata.num_row_groups)])


def read_rows(parquet_file, row_indices, columns):
    """Read only the row groups containing `row_indices` (sorted), take within."""
    bounds = row_group_bounds(parquet_file.metadata)
    pieces = []
    for group_index in range(len(bounds) - 1):
        in_group = row_indices[(row_indices >= bounds[group_index])
                               & (row_indices < bounds[group_index + 1])]
        if len(in_group):
            table = parquet_file.read_row_group(group_index, columns=columns)
            pieces.append(table.take(in_group - bounds[group_index]))
    return pa.concat_tables(pieces)


def fetch_shard(job):
    """Fetch pass worker: pull the wanted rows of one shard (+ raw text mirror)."""
    shard_name, wanted_ranks_by_stratum = job
    dataset_config = WORKER_STATE["dataset_config"]
    try:
        qf_file = pq.ParquetFile(Path(dataset_config["qf_root"]) / shard_name)
        reasons = read_reason_column(qf_file, dataset_config["reason_column"])
        picked_indices = []
        for stratum, ranks in wanted_ranks_by_stratum.items():
            stratum_rows = np.flatnonzero(reasons == stratum)
            assert ranks.max() < len(stratum_rows), \
                f"rank out of range for {stratum} in {shard_name}"
            picked_indices.append(stratum_rows[ranks])
        row_indices = np.unique(np.concatenate(picked_indices))

        frame = read_rows(qf_file, row_indices, WORKER_STATE["fetch_columns"]).to_pandas()
        frame["shard"] = shard_name
        frame["row_idx"] = row_indices

        raw_file = pq.ParquetFile(Path(dataset_config["raw_root"]) / shard_name)
        id_column = dataset_config["columns"]["id"]
        raw_text_column = dataset_config["columns"]["text_raw"]
        used_fallback = False
        if raw_file.metadata.num_rows == qf_file.metadata.num_rows:
            raw_table = read_rows(raw_file, row_indices, [id_column, raw_text_column])
            if raw_table.column(0).to_pylist() == frame[id_column].tolist():
                frame["text_raw"] = raw_table.column(1).to_pylist()
            else:
                used_fallback = True
        else:
            used_fallback = True
        if used_fallback:  # mirror assumption broke: join on the id column instead
            wanted_ids = set(frame[id_column])
            text_by_id = {}
            for batch in raw_file.iter_batches(columns=[id_column, raw_text_column]):
                for document_id, text in zip(batch.column(0).to_pylist(),
                                             batch.column(1).to_pylist()):
                    if document_id in wanted_ids:
                        text_by_id[document_id] = text
            frame["text_raw"] = frame[id_column].map(text_by_id)
        return shard_name, frame, used_fallback, None
    except Exception as error:
        return shard_name, None, False, repr(error)
