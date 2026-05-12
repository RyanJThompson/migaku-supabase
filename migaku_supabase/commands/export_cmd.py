"""`migaku-supabase export` — write state.db rows to CSV / XLSX."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .. import config
from ..export import (
    export_csv,
    export_xlsx,
    fetch_meanings_from_supabase,
    filter_rows,
)
from ..supabase_client import SupabaseClient
from ..state import StateCache


log = logging.getLogger("migaku-supabase")


def run(args: argparse.Namespace) -> int:
    if not (args.csv or args.xlsx):
        log.error("Pass at least one of --csv PATH or --xlsx PATH.")
        return 2

    if not config.STATE_DB_PATH.exists():
        log.error("Local cache (%s) not initialised. Run `python -m migaku_supabase sync` "
                  "or `python -m migaku_supabase rebuild-cache` first.",
                  config.STATE_DB_PATH.name)
        return 1

    with StateCache(config.STATE_DB_PATH) as cache:
        all_rows = list(cache.load_all().values())

    statuses = [s.strip().upper() for s in (args.status or "").split(",") if s.strip()] or None
    if statuses == ["ALL"]:
        statuses = None
    rows = filter_rows(all_rows, args.lang or None, statuses, args.include_archived)
    log.info("Exporting %d rows (filtered from %d cached, lang=%s, status=%s, archived=%s)",
             len(rows), len(all_rows), args.lang or "ALL",
             ",".join(statuses) if statuses else "ALL", args.include_archived)

    meanings: dict[str, str] | None = None
    if args.with_meaning:
        supabase_url = config.supabase_url()
        supabase_key = config.supabase_key()
        if not (supabase_url and supabase_key):
            log.error("--with-meaning requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
            return 2
        supabase = SupabaseClient(supabase_url, supabase_key, config.supabase_table())
        meanings = fetch_meanings_from_supabase(supabase)

    if args.csv:
        export_csv(Path(args.csv), rows, meanings)
    if args.xlsx:
        export_xlsx(Path(args.xlsx), rows, meanings)

    return 0
