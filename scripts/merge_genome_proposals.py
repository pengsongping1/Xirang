#!/usr/bin/env python3
"""Review and merge Xirang genome proposals into a community genome pack.

This is intentionally offline. It never pulls, pushes, or talks to a network.
Maintainers run it on submitted *.xirang.json files, inspect the generated
community genome and `genome_pack.json`, then decide what to commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xirang import bundle


def _expand_inputs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            out.extend(sorted(path.glob("*.xirang.json")))
            out.extend(sorted(path.glob("*.json")))
        else:
            out.append(path)
    return [path for path in out if path.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline-review and merge Xirang genome proposals."
    )
    parser.add_argument("inputs", nargs="+", help="Genome proposal files or directories")
    parser.add_argument(
        "--out-dir",
        default="community/reviewed",
        help="Output directory for sanitized community genome and genome_pack.json",
    )
    args = parser.parse_args()

    inputs = _expand_inputs(args.inputs)
    if not inputs:
        raise SystemExit("no genome proposal bundles found")
    result = bundle.merge_genome_proposals(inputs, Path(args.out_dir))
    print(f"merged_skilllets={result['merged_skilllets']}")
    print(f"accepted_total={result['accepted_total']}")
    print(f"rejected_total={result['rejected_total']}")
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
