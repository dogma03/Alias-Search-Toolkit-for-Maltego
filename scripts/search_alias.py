#!/usr/bin/env python3
"""Search an alias with Sherlock/Maigret without starting Maltego.

Usage:
    .venv/bin/python scripts/search_alias.py torvalds
    .venv/bin/python scripts/search_alias.py torvalds --engines sherlock
    .venv/bin/python scripts/search_alias.py torvalds --engines maigret --raw
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from transforms.alias_core import (  # noqa: E402
    AliasSearchError,
    combined_raw_result,
    format_summary_note,
    limit_profiles,
    merge_profiles,
    normalize_alias,
    run_alias_search,
)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Search profiles by alias")
    parser.add_argument("alias", help="username without @")
    parser.add_argument(
        "--engines",
        default=os.getenv("ALIAS_ENGINES", "sherlock,maigret"),
        help="comma-separated engines: sherlock,maigret (default: both)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print raw Sherlock CSV / Maigret JSON after the summary",
    )
    args = parser.parse_args()

    os.environ["ALIAS_ENGINES"] = args.engines
    alias = normalize_alias(args.alias)
    outcomes = await run_alias_search(alias)
    profiles = merge_profiles(outcomes)
    profiles, truncated = limit_profiles(profiles)
    print(format_summary_note(alias, outcomes, profiles, truncated))

    if args.raw:
        raw = combined_raw_result(outcomes)
        if raw:
            print("\n--- RAW RESULTS ---")
            print(raw)

    return 0 if any(not outcome.error for outcome in outcomes) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main()))
    except (AliasSearchError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
