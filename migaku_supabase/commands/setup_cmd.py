"""`migaku-supabase setup` — interactive first-run wizard."""
from __future__ import annotations

import argparse
import getpass
import logging
from typing import Any

from .. import config
from ..migaku import auth
from ..migaku.dict import MigakuDict
from ..migaku.frequency import MigakuFrequency
from ..supabase_client import (
    DEFAULT_TABLE,
    SUPABASE_SCHEMA_SQL,
    SupabaseClient,
    apply_schema,
)


log = logging.getLogger("migaku-supabase")


def _prompt(label: str, *, current: str | None = None, secret: bool = False,
            allow_blank: bool = False, default: str | None = None) -> str:
    while True:
        suffix = ""
        if current:
            suffix = " (press enter to keep current value)"
        elif default:
            suffix = f" [{default}]"
        if secret:
            value = getpass.getpass(f"  {label}{suffix}: ").strip()
        else:
            value = input(f"  {label}{suffix}: ").strip()
        if not value:
            if current:
                return current
            if default:
                return default
            if allow_blank:
                return ""
            print("    (required - please enter a value)")
            continue
        return value


def _yes_no(label: str, *, default_yes: bool = True) -> bool:
    prompt = " [Y/n]: " if default_yes else " [y/N]: "
    while True:
        try:
            value = input(label + prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if not value:
            return default_yes
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("    (please answer y or n)")


def run(args: argparse.Namespace) -> int:  # noqa: C901
    print()
    print("==============================================================")
    print("  Migaku-Supabase setup wizard")
    print("==============================================================")
    print()
    print("This will walk you through the one-time configuration:")
    print("  1. Migaku login (email/password -> Firebase refresh token)")
    print("  2. Optional Supabase project URL + service-role key")
    print("  3. Optional Supabase table creation through a Postgres URL")
    print("  4. Mint a stable MIGAKU_DEVICE_ID for this install")
    print("  5. Download Migaku's published dictionary + frequency database")
    print()
    print("Existing values in .env are kept unless you pass --force.")
    print()

    existing = config._read_env_file()
    if args.force:
        existing = {}

    print("--- 1. Migaku login (Firebase) ---")
    print("  Your normal Migaku account credentials. The password is used")
    print("  once to get a long-lived refresh token; it is not stored.")
    email = _prompt("Migaku email", current=existing.get("MIGAKU_EMAIL"))
    refresh_token = existing.get("MIGAKU_REFRESH_TOKEN") or ""
    password = ""
    if not refresh_token or args.force:
        password = _prompt("Migaku password", secret=True)
    print()

    print("  Authenticating with Migaku ...")
    try:
        if password:
            session = auth.AuthSession.from_email_password(email, password)
        else:
            session = auth.AuthSession.from_refresh_token(refresh_token)
        refresh_token = session.refresh_token
        print("  Login OK. Refresh token will be persisted to .env.")
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        return 1
    print()

    supabase_enabled = _yes_no("Enable Supabase sync now?", default_yes=True)
    supabase_url = existing.get("SUPABASE_URL", "")
    supabase_key = (
        existing.get("SUPABASE_SERVICE_ROLE_KEY")
        or existing.get("SUPABASE_KEY")
        or ""
    )
    supabase_table = existing.get("SUPABASE_TABLE", DEFAULT_TABLE) or DEFAULT_TABLE
    supabase_db_url = existing.get("SUPABASE_DB_URL", "")

    if supabase_enabled:
        print("--- 2. Supabase connection ---")
        print("  In Supabase, open Project Settings -> API. Paste:")
        print("    - Project URL as SUPABASE_URL")
        print("    - service_role key as SUPABASE_SERVICE_ROLE_KEY")
        print("  Keep the service-role key private; it bypasses RLS.")
        supabase_url = _prompt("Supabase project URL", current=supabase_url)
        supabase_key = _prompt("Supabase service-role key", current=supabase_key, secret=True)
        supabase_table = _prompt("Supabase table name", current=supabase_table, default=DEFAULT_TABLE)
        print()

        print("--- 3. Supabase table schema ---")
        print(f"  The default table is public.{supabase_table}.")
        print("  You can create it by running this file in the Supabase SQL editor:")
        print(f"    {config.PROJECT_ROOT / 'supabase' / 'schema.sql'}")
        if _yes_no("Apply the schema now using a direct Postgres connection URL?", default_yes=False):
            supabase_db_url = _prompt(
                "Supabase Postgres connection URL",
                current=supabase_db_url,
                secret=True,
            )
            try:
                apply_schema(supabase_db_url)
                print("  Schema applied.")
            except RuntimeError as exc:
                print(f"  ERROR: {exc}")
                return 1
        else:
            print("  Skipping schema apply. Make sure the table exists before sync.")
        print()

        print("  Checking Supabase REST access ...")
        try:
            SupabaseClient(supabase_url, supabase_key, supabase_table).healthcheck()
            print("  Supabase OK.")
        except RuntimeError as exc:
            print(f"  WARNING: Supabase check failed ({exc})")
            print("  If the table does not exist yet, apply supabase/schema.sql and rerun status.")
        print()
    else:
        print("--- 2/3. Supabase connection ---")
        print("  Skipping Supabase setup. Sync will run in local-only mode until")
        print("  you add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY later.")
        supabase_url = ""
        supabase_key = ""
        print()

    print("--- 4. Device identity ---")
    device_id = existing.get("MIGAKU_DEVICE_ID") or config.get_or_create_device_id()
    print(f"  MIGAKU_DEVICE_ID = {device_id[:8]}... (32-hex, persisted to .env)")
    print()

    lang_for_dict = existing.get("SYNC_LANG", "zh") or "zh"
    print(f"--- 5. Migaku dictionary + frequency DB (lang={lang_for_dict}) ---")
    try:
        md = MigakuDict(lang_for_dict)
        dict_path = md.ensure_downloaded()
        print(f"  Dict:      {dict_path}")
        mf = MigakuFrequency(lang_for_dict)
        freq_path = mf.ensure_downloaded()
        print(f"  Frequency: {freq_path}")
    except Exception as exc:    # noqa: BLE001
        print(f"  WARNING: dict download failed ({exc}). The sync will still")
        print("  run, but pinyin/meaning/example will fall back to pypinyin")
        print("  and the Frequency column will stay blank. Re-run `setup` to retry.")
    print()

    print("--- 6. Writing .env ---")
    new_env: dict[str, Any] = {
        **existing,
        "MIGAKU_EMAIL": email,
        "MIGAKU_REFRESH_TOKEN": refresh_token,
        "MIGAKU_DEVICE_ID": device_id,
    }
    if supabase_enabled:
        new_env["SUPABASE_URL"] = supabase_url
        new_env["SUPABASE_SERVICE_ROLE_KEY"] = supabase_key
        new_env["SUPABASE_TABLE"] = supabase_table
        if supabase_db_url:
            new_env["SUPABASE_DB_URL"] = supabase_db_url
    else:
        new_env.pop("SUPABASE_URL", None)
        new_env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        new_env.pop("SUPABASE_KEY", None)
        new_env.pop("SUPABASE_TABLE", None)
    new_env.setdefault("SYNC_LANG", "zh")
    new_env.setdefault("SYNC_STATUS", "KNOWN,LEARNING")
    new_env.setdefault("SYNC_DIFFICULT_LIMIT", "2000")
    new_env.pop("MIGAKU_PASSWORD", None)
    config._write_env_file(new_env)
    print(f"  Wrote {config.ENV_PATH}")
    print()

    schema_path = config.PROJECT_ROOT / "supabase" / "schema.sql"
    if not schema_path.exists():
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(SUPABASE_SCHEMA_SQL + "\n", encoding="utf-8")
        print(f"  Wrote {schema_path}")
        print()

    print("==============================================================")
    print("  Setup complete.")
    print("==============================================================")
    print()
    print("Next:")
    print("  1. Verify connectivity:          python -m migaku_supabase status")
    if supabase_enabled:
        print("  2. Preview the sync:             python -m migaku_supabase sync --dry-run")
        print("  3. Run the sync:                 python -m migaku_supabase sync")
    else:
        print("  2. Preview local-only sync:      python -m migaku_supabase sync --dry-run --no-supabase")
        print("  3. Run local-only sync:          python -m migaku_supabase sync --no-supabase")
    print()
    return 0
