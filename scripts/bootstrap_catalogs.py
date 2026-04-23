#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from xirang import catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Import local API/LLM catalogs into ~/.xirang/catalogs")
    parser.add_argument("--api-readme", help="Path to public-apis README.md")
    parser.add_argument("--llm-readme", help="Path to free-llm-api-resources README.md")
    args = parser.parse_args()

    home = Path(os.getenv("XIRANG_HOME") or (Path.home() / ".xirang")).expanduser()
    catalogs_dir = home / "catalogs"
    imported = []
    if args.api_readme:
        fp, count = catalog.import_catalog(catalogs_dir, "api", Path(args.api_readme).expanduser())
        imported.append(f"api={count} -> {fp}")
    if args.llm_readme:
        fp, count = catalog.import_catalog(catalogs_dir, "llm", Path(args.llm_readme).expanduser())
        imported.append(f"llm={count} -> {fp}")
    if imported:
        print("\n".join(imported))
    else:
        print("Nothing imported.")


if __name__ == "__main__":
    main()
