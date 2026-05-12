"""Supabase/PostgREST wrapper for the Migaku vocabulary sink."""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import requests

from .models import CachedRow


DEFAULT_TABLE = "migaku_words"


SUPABASE_SCHEMA_SQL = """
create table if not exists public.migaku_words (
  migaku_key text primary key,
  word text not null,
  pinyin text,
  meaning text,
  example text,
  pinyin_numeric text,
  status text,
  frequency integer,
  fail_rate_pct numeric,
  total_reviews integer,
  failed_reviews integer,
  part_of_speech text,
  language text not null,
  last_synced timestamptz,
  sense_index text,
  archived boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists migaku_words_language_status_active_idx
  on public.migaku_words (language, status)
  where archived = false;

create index if not exists migaku_words_last_synced_idx
  on public.migaku_words (last_synced desc);

create or replace function public.set_migaku_words_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_migaku_words_updated_at on public.migaku_words;
create trigger set_migaku_words_updated_at
before update on public.migaku_words
for each row
execute function public.set_migaku_words_updated_at();

alter table public.migaku_words enable row level security;

grant usage on schema public to service_role;
grant select, insert, update, delete on public.migaku_words to service_role;

drop policy if exists service_role_full_access on public.migaku_words;
create policy service_role_full_access
on public.migaku_words
for all
to service_role
using (true)
with check (true);
""".strip()


class SupabaseClient:
    """Small PostgREST client sized for upserting Migaku words."""

    REQUEST_INTERVAL = 0.1

    def __init__(self, url: str, key: str, table: str = DEFAULT_TABLE) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.table = table
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        self._last_call = 0.0

    @property
    def _table_path(self) -> str:
        return quote(self.table, safe="")

    def _throttle(self) -> None:
        wait = self.REQUEST_INTERVAL - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        self._throttle()
        full_url = f"{self.url}/rest/v1{path}"
        for attempt in range(5):
            try:
                resp = self.session.request(method, full_url, timeout=60, **kw)
            except (requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError):
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 429:
                time.sleep(float(resp.headers.get("Retry-After", "1")))
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if not resp.ok:
                raise RuntimeError(
                    f"Supabase {method} {path} -> {resp.status_code}: {resp.text[:500]}"
                )
            if not resp.text:
                return None
            return resp.json()
        raise RuntimeError(f"Supabase {method} {path} failed after 5 attempts")

    def healthcheck(self) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/{self._table_path}?select=migaku_key&limit=1",
        ) or []

    def query_all_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            page = self._request(
                "GET",
                f"/{self._table_path}?select=*&order=migaku_key.asc&limit={limit}&offset={offset}",
            ) or []
            rows.extend(page)
            if len(page) < limit:
                break
            offset += limit
        return rows

    def upsert_row(self, record: dict[str, Any]) -> dict[str, Any]:
        data = self._request(
            "POST",
            f"/{self._table_path}?on_conflict=migaku_key",
            json=[record],
            headers={**self.session.headers, "Prefer": "resolution=merge-duplicates,return=representation"},
        )
        if not data:
            return {}
        return data[0]

    def update_row(self, migaku_key: str, record: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in record.items() if k != "migaku_key"}
        data = self._request(
            "PATCH",
            f"/{self._table_path}?migaku_key=eq.{quote(migaku_key, safe='')}",
            json=payload,
            headers={**self.session.headers, "Prefer": "return=representation"},
        )
        if not data:
            return {}
        return data[0]

    def archive_row(self, migaku_key: str, last_synced: str | None) -> None:
        body: dict[str, Any] = {"archived": True}
        if last_synced:
            body["last_synced"] = last_synced
        self._request(
            "PATCH",
            f"/{self._table_path}?migaku_key=eq.{quote(migaku_key, safe='')}",
            json=body,
            headers={**self.session.headers, "Prefer": "return=minimal"},
        )


def apply_schema(db_url: str) -> None:
    """Apply the Supabase schema over a direct Postgres connection."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Applying the schema requires psycopg. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(SUPABASE_SCHEMA_SQL)
            conn.commit()
    except psycopg.Error as exc:
        raise RuntimeError(f"Could not apply Supabase schema: {exc}") from exc


def format_parts_of_speech(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (list, tuple, set)):
        items = [str(p).strip() for p in value if p and str(p).strip()]
    else:
        items = [p.strip() for p in str(value).split(",") if p.strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    deduped.sort()
    return ", ".join(deduped)


def build_record(word: Any, *, include_meaning: bool, now_iso: str) -> dict[str, Any]:
    if word.language == "zh":
        pinyin_main = word.pinyin_marks or ""
        pinyin_numeric = word.pinyin_numeric or ""
        sense = word.secondary or ""
    else:
        pinyin_main = word.secondary or ""
        pinyin_numeric = ""
        sense = ""

    record: dict[str, Any] = {
        "migaku_key": word.key,
        "word": word.dict_form,
        "pinyin": pinyin_main or None,
        "pinyin_numeric": pinyin_numeric or None,
        "sense_index": sense or None,
        "status": word.known_status or None,
        "language": word.language,
        "last_synced": now_iso,
        "archived": False,
    }
    if word.fail_rate is not None:
        record["fail_rate_pct"] = round(word.fail_rate, 2)
    if word.total_reviews is not None:
        record["total_reviews"] = word.total_reviews
    if word.failed_reviews is not None:
        record["failed_reviews"] = word.failed_reviews
    pos_text = format_parts_of_speech(word.part_of_speech)
    if pos_text:
        record["part_of_speech"] = pos_text
    freq = getattr(word, "frequency_stars", None)
    if freq is not None:
        record["frequency"] = int(freq)
    example = getattr(word, "example", None)
    if example:
        record["example"] = example
    if include_meaning:
        record["meaning"] = getattr(word, "meaning", None) or None
    return record


def cache_row_from_supabase_record(record: dict[str, Any]) -> CachedRow | None:
    key = record.get("migaku_key") or ""
    if not key:
        return None
    parts = key.split("|", 2)
    if len(parts) != 3:
        return None
    lang, dict_form, secondary = parts
    meaning = record.get("meaning") or None
    return CachedRow(
        migaku_key=key,
        page_id=f"supabase:{key}",
        lang=record.get("language") or lang,
        dict_form=record.get("word") or dict_form,
        secondary=secondary,
        known_status=record.get("status") or None,
        fail_rate=record.get("fail_rate_pct"),
        total_reviews=record.get("total_reviews"),
        failed_reviews=record.get("failed_reviews"),
        part_of_speech=record.get("part_of_speech") or None,
        last_synced=record.get("last_synced"),
        archived=bool(record.get("archived", False)),
        pinyin_marks=record.get("pinyin") or None,
        pinyin_numeric=record.get("pinyin_numeric") or None,
        sense_index=record.get("sense_index") or None,
        meaning=meaning,
        example=record.get("example") or None,
        frequency_stars=record.get("frequency"),
        sink_meaning_was_blank=not meaning,
    )
