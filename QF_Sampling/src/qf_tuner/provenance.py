"""Repo-state helpers for provenance records (meta.json, FILTER_INFO)."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def git_state():
    """Short commit hash of this repo, with a -dirty suffix for uncommitted changes."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                    capture_output=True, text=True).stdout.strip())
        return (commit + "-dirty") if dirty else (commit or None)
    except Exception:
        return None
