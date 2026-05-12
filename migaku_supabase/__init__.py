"""Migaku -> Supabase sync (direct Migaku API, no Docker, no Go).

Package layout:
    migaku_supabase.cli           CLI argparse dispatch
    migaku_supabase.config        env loading, paths, defaults
    migaku_supabase.models        Word / CachedRow / MigakuEntity dataclasses
    migaku_supabase.state         StateCache (SQLite diff cache)
    migaku_supabase.supabase_client Supabase/PostgREST sink
    migaku_supabase.pinyin        pypinyin wrappers (tone marks + numeric)
    migaku_supabase.export        CSV / XLSX writers
    migaku_supabase.migaku.*      Direct talk to core-server / file-sync / auth
    migaku_supabase.commands.*    One module per CLI subcommand
"""

__version__ = "0.1.0a1"
