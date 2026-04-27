#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xirang.benchmark import run_benchmark
from xirang.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="xirang-bench", description="Run Xirang benchmark tasks")
    parser.add_argument("--dry-run", action="store_true", help="Validate benchmark task definitions without LLM calls")
    parser.add_argument("--provider", help="Override provider")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--out", default="bench_results.json", help="Where to write results JSON")
    args = parser.parse_args()

    cfg = load_config(provider_override=args.provider)
    if args.model:
        cfg.model = args.model
    result = run_benchmark(cfg, dry_run=args.dry_run, out_path=Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
