"""`migaku-supabase init-db` — apply the Supabase table schema."""
from __future__ import annotations

import argparse
import logging

from .. import config
from ..supabase_client import apply_schema


log = logging.getLogger("migaku-supabase")


def run(args: argparse.Namespace) -> int:
    db_url = args.db_url or config.supabase_db_url()
    if not db_url:
        log.error("Pass --db-url or set SUPABASE_DB_URL in .env")
        return 2
    try:
        apply_schema(db_url)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info("Supabase schema applied.")
    return 0
