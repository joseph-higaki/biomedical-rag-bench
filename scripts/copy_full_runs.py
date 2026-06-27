"""Copy only full eval runs (58 questions attempted) to an analytics destination.

Usage:
    uv run python scripts/copy_full_runs.py <src_dir> <dst_dir>

src_dir  — directory containing .jsonl + .manifest.json pairs (e.g. eval/results/)
dst_dir  — destination root; files land in <dst_dir>/<copy_ts>/

A run is "full" when its .jsonl has exactly 58 lines. Both the .jsonl and
.manifest.json are copied. Runs with fewer lines are logged but skipped.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FULL_COUNT = 58


def count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src", type=Path, help="Source results directory")
    parser.add_argument("dst", type=Path, help="Destination root (a timestamped subdirectory is created)")
    args = parser.parse_args()

    src: Path = args.src.resolve()
    if not src.is_dir():
        sys.exit(f"error: source directory not found: {src}")

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst: Path = args.dst.resolve() / ts
    dst.mkdir(parents=True, exist_ok=True)

    manifests = sorted(src.glob("*.manifest.json"))
    if not manifests:
        sys.exit(f"error: no .manifest.json files found in {src}")

    copied: list[tuple[str, int]] = []
    skipped: list[tuple[str, int]] = []
    missing: list[str] = []

    for manifest in manifests:
        stem = manifest.name[: -len(".manifest.json")]
        jsonl = src / f"{stem}.jsonl"

        if not jsonl.exists():
            missing.append(stem)
            continue

        n = count_lines(jsonl)
        if n == FULL_COUNT:
            shutil.copy2(jsonl, dst / jsonl.name)
            shutil.copy2(manifest, dst / manifest.name)
            copied.append((stem, n))
        else:
            skipped.append((stem, n))

    # --- report ---------------------------------------------------------------
    print(f"\nSource : {src}")
    print(f"Dest   : {dst}")
    print(f"Copied : {len(copied)}   Skipped : {len(skipped)}   Missing JSONL : {len(missing)}")

    if copied:
        print(f"\n{'COPIED':=<60}")
        for stem, n in copied:
            print(f"  {n:>3} q  {stem}")

    if skipped:
        print(f"\n{'SKIPPED (incomplete)':=<60}")
        for stem, n in skipped:
            print(f"  {n:>3} q  {stem}")

    if missing:
        print(f"\n{'MISSING JSONL (manifest only)':=<60}")
        for stem in missing:
            print(f"       {stem}")

    print()


if __name__ == "__main__":
    main()
