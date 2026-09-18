"""Record a saved filter version and keep sampling/labeling runs consistent.

Only reads pack files; never imports or executes quality-filter code.
"""

import argparse
import hashlib
import json
from pathlib import Path


PACKS_ROOT = Path(__file__).resolve().parents[1] / "filters" / "packs"


def describe_pack(name):
    """Identify a repository pack by name and a digest of its saved contents."""
    if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("--filter-pack expects a version name from filters/packs/")
    pack = PACKS_ROOT / name
    files = sorted((pack / "rules").rglob("*.py"))
    if not files or not all((pack / filename).is_file()
                            for filename in ("thresholds.yaml", "PROVENANCE.md")):
        raise ValueError(f"Unknown or incomplete filter pack {name!r}; import it into filters/packs/ first")
    files += [pack / "thresholds.yaml", pack / "PROVENANCE.md"]
    hashes = {path.relative_to(pack).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in files}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()
    return {"name": name, "path": f"filters/packs/{name}", "sha256": fingerprint}


def read_json(path):
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read metadata {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def sample_filter(meta_path):
    """Read the sample's declared filter and reject missing or changed versions."""
    record = read_json(meta_path).get("filter_pack")
    if not isinstance(record, dict) or not isinstance(record.get("name"), str):
        raise ValueError(f"{meta_path} has no filter_pack record; create a new sample with --filter-pack")
    if record != describe_pack(record["name"]):
        raise ValueError(f"Filter pack {record['name']!r} differs from {meta_path}; "
                         "restore the saved version or create a new pack and sample")
    return record


def prepare_run(name, sample_dir, workdir):
    """Check sample provenance and bind the work directory before submitting jobs."""
    expected = describe_pack(name)
    sample_dir, workdir = Path(sample_dir).resolve(), Path(workdir).resolve()
    if (sample_dir / "sample.parquet").exists():
        actual = sample_filter(sample_dir / "meta.json")
        if actual != expected:
            raise ValueError(f"Sample filter pack {actual['name']!r} does not match "
                             f"--filter-pack {name!r}; use the matching sample or a new sample directory")

    record = {"filter_pack": expected, "sample_dir": str(sample_dir)}
    meta_path = workdir / "meta.json"
    if meta_path.exists():
        if read_json(meta_path) != record:
            raise ValueError(f"{workdir} belongs to another sample or filter version; use a new workdir")
    else:
        if ((workdir / "blind_input.jsonl").exists()
                or any((workdir / "judge_out").glob("*.jsonl"))
                or any((workdir / "labels").glob("*"))):
            raise ValueError(f"{workdir} has existing results without filter provenance; use a new workdir")
        workdir.mkdir(parents=True, exist_ok=True)
        with meta_path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filter-pack", required=True)
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    try:
        record = prepare_run(args.filter_pack, args.sample_dir, args.workdir)
    except (OSError, ValueError) as error:
        parser.exit(2, f"ERROR: {error}\n")
    print(f"== filter pack: {record['name']} ({record['sha256'][:12]})")


if __name__ == "__main__":
    main()
