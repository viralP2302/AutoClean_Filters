#!/usr/bin/env python
"""Generate or check a pack's thresholds.yaml from its own rule code.

The yaml duplicates the defaults of DataThreshold in <pack>/rules/threshold.py.
That duplication must never be maintained by hand:

  generate   python scripts/pack_thresholds.py PACK_DIR --write
             (re)writes thresholds.yaml from the code defaults; policy keys
             already in the yaml (e.g. `tunable`) are preserved.
             Use when cutting a new baseline from upstream.

  check      python scripts/pack_thresholds.py PACK_DIR
             lists every key whose yaml value differs from the code default.
             For a BASELINE pack the list must be empty; for a tuned pack the
             list IS the tuning (thresholds.yaml overrides the code at run
             time, so a diff here is intentional and belongs in the CHANGELOG).

threshold.py only imports the stdlib, so this runs anywhere (no QF runtime).
"""
import argparse
import importlib.util
import sys

sys.dont_write_bytecode = True  # keep pack directories free of __pycache__
from dataclasses import fields
from pathlib import Path

import yaml

POLICY_KEYS = ("tunable",)  # qf-tuner policy config living in the same file


def code_defaults(pack):
    spec = importlib.util.spec_from_file_location("pack_threshold", pack / "rules" / "threshold.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    th = mod.DataThreshold()
    out = {}
    for f in fields(th):
        v = getattr(th, f.name)
        if isinstance(v, (tuple, list)):
            v = [list(x) if isinstance(x, (tuple, list)) else x for x in v]
        out[f.name] = v
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    parser.add_argument("--write", action="store_true", help="write thresholds.yaml (default: check)")
    args = parser.parse_args()

    defaults = code_defaults(args.pack)
    yaml_path = args.pack / "thresholds.yaml"
    current = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}

    if args.write:
        merged = dict(defaults)
        for k in POLICY_KEYS:
            merged[k] = current.get(k, [])
        yaml_path.write_text(
            "# GENERATED from rules/threshold.py by scripts/pack_thresholds.py — do not hand-edit\n"
            "# a baseline; in a tuned pack, edited values here override the code at run time.\n"
            + yaml.safe_dump(merged, sort_keys=False))
        print(f"wrote {yaml_path} ({len(defaults)} threshold keys, policy keys preserved)")
        return

    def normalize(value):
        if not isinstance(value, (tuple, list)):
            return value
        return [list(item) if isinstance(item, (tuple, list)) else item for item in value]

    changed = [(name, defaults[name], current.get(name, "<missing>"))
               for name in defaults if normalize(current.get(name)) != defaults[name]]
    unknown = [name for name in current if name not in defaults and name not in POLICY_KEYS]
    for name, code_value, yaml_value in changed:
        print(f"DIFFERS {name}: code={code_value!r} yaml={yaml_value!r}")
    for name in unknown:
        print(f"UNKNOWN key in yaml: {name}")
    if not changed and not unknown:
        print("thresholds.yaml matches the code defaults exactly")
    sys.exit(1 if (changed or unknown) else 0)


if __name__ == "__main__":
    main()
