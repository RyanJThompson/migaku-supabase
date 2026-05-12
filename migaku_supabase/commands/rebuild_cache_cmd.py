"""`migaku-supabase rebuild-cache` — recreate state.db from Supabase."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .. import config
from ..supabase_client import SupabaseClient, cache_row_from_supabase_record
from ..state import StateCache


log = logging.getLogger("migaku-supabase")


def run(args: argparse.Namespace) -> int:
    supabase_url = config.supabase_url()
    supabase_key = config.supabase_key()
    if not (supabase_url and supabase_key):
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        return 2

    supabase = SupabaseClient(supabase_url, supabase_key, config.supabase_table())
    log.info("Rebuilding %s from Supabase (read-only — no Supabase writes will occur) ...",
             config.STATE_DB_PATH)

    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(config.STATE_DB_PATH) + suffix)
        if p.exists():
            log.info("  removing %s", p.name)
            p.unlink()

    records = supabase.query_all_rows()
    cache = StateCache(config.STATE_DB_PATH)
    rows = 0
    for record in records:
        row = cache_row_from_supabase_record(record)
        if row is None:
            continue
        cache.upsert(row)
        rows += 1
    cache.close()
    log.info("Rebuilt cache at %s with %d rows.", config.STATE_DB_PATH, rows)
    return 0
