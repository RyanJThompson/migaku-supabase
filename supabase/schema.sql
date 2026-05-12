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
  first_learning_at timestamptz,
  first_known_at timestamptz,
  sense_index text,
  archived boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.migaku_words
  add column if not exists first_learning_at timestamptz;

alter table public.migaku_words
  add column if not exists first_known_at timestamptz;

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
