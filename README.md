# migaku-supabase

Sync your [Migaku](https://migaku.com) vocabulary into a Supabase Postgres table.

This is a local Python CLI. It pulls your Migaku vocabulary with Migaku's HTTP sync API, enriches words with Migaku dictionary/frequency data, writes rows to Supabase, and keeps a local `state.db` cache so later runs only write changed rows.

## What It Does

- Pulls Migaku words directly from `core-server.migaku.com`.
- Supports incremental syncs and `--full-refresh`.
- Writes to `public.migaku_words` in Supabase.
- Keeps user-editable `meaning` safe after the first sync.
- Computes fail rate/review counts locally from Migaku review data.
- Exports the local cache to CSV or XLSX.
- Can run without Supabase using `--no-supabase`.

## Install

```bash
git clone https://github.com/RyanJThompson/migaku-supabase.git
cd migaku-supabase

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python -m migaku_supabase setup
```

Optional editable install:

```bash
pip install -e .
migaku-supabase setup
```

You need:

- Python 3.11+
- A Migaku account
- A Supabase project if you want cloud sync

## Supabase Values You Need

Open your project in the [Supabase dashboard](https://supabase.com/dashboard/projects).

### `SUPABASE_URL`

Where to find it:

1. Open your Supabase project.
2. Go to **Project Settings**.
3. Open **API**.
4. Copy **Project URL**.

It looks like:

```bash
SUPABASE_URL=https://your-project-ref.supabase.co
```

### `SUPABASE_SERVICE_ROLE_KEY`

Where to find it:

1. Open your Supabase project.
2. Go to **Project Settings**.
3. Open **API**.
4. Copy the **service_role** key, not the anon key.

It looks like:

```bash
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

Keep this private. It bypasses Row Level Security and should only be used by this local sync job or a trusted server.

### `SUPABASE_TABLE`

Use the default:

```bash
SUPABASE_TABLE=migaku_words
```

The full table name is:

```text
public.migaku_words
```

### `SUPABASE_DB_URL` Optional

This is only needed if you want the CLI to create/update the table schema for you with `init-db` or during `setup`.

You do not need `SUPABASE_DB_URL` for normal syncing.

Where to find it:

1. Open your Supabase project.
2. Click **Connect** in the top bar.
3. Choose **Session pooler** if your network does not support IPv6.
4. Copy the URI.
5. Replace `[YOUR-PASSWORD]` with your Supabase database password.

For Supabase pooler URLs, the username usually includes your project ref:

```text
postgresql://postgres.YOUR_PROJECT_REF:YOUR_DATABASE_PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres
```

Example:

```text
postgresql://postgres.abcdefghijklmnopqrst:myDatabasePassword123@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
```

Use your database password, not the service-role key.

If your password contains special characters, URL-encode them:

| Character | Encoded |
| --- | --- |
| `@` | `%40` |
| `#` | `%23` |
| `/` | `%2F` |
| `:` | `%3A` |

If you do not know the database password, reset it in **Project Settings** -> **Database**.

## Create The Table

Recommended: use Supabase SQL Editor.

1. Open your Supabase project.
2. Go to **SQL Editor**.
3. Paste the contents of [`supabase/schema.sql`](./supabase/schema.sql).
4. Run it.

Alternative: use the CLI with `SUPABASE_DB_URL`.

```bash
python -m migaku_supabase init-db --db-url "postgresql://postgres.PROJECT_REF:ENCODED_PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres"
```

The schema enables Row Level Security and adds a `service_role` policy so the sync can always read/write with `SUPABASE_SERVICE_ROLE_KEY`.

## Configure

The setup wizard writes `.env`:

```bash
python -m migaku_supabase setup
```

You can also create `.env` manually from `.env.example`:

```bash
cp .env.example .env
```

Minimum cloud-sync config:

```bash
MIGAKU_EMAIL=you@example.com
MIGAKU_REFRESH_TOKEN=...
MIGAKU_DEVICE_ID=...

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_TABLE=migaku_words

SYNC_LANG=zh
SYNC_STATUS=KNOWN,LEARNING
SYNC_DIFFICULT_LIMIT=2000
```

The wizard can derive `MIGAKU_REFRESH_TOKEN` from your Migaku email/password. It does not store your Migaku password by default.

## Run

Check connectivity:

```bash
python -m migaku_supabase status
```

Preview the sync:

```bash
python -m migaku_supabase sync --dry-run
```

Run the sync:

```bash
python -m migaku_supabase sync
```

First run or repair run:

```bash
python -m migaku_supabase sync --full-refresh
```

Sync all statuses:

```bash
python -m migaku_supabase sync --full-refresh --status ALL
```

Local-only mode:

```bash
python -m migaku_supabase sync --no-supabase
```

Archive stale Supabase rows:

```bash
python -m migaku_supabase sync --archive-stale
```

Use `--archive-stale` carefully. It sets `archived=true` for cached rows that no longer appear in Migaku for the selected language/status filter.

## Export

```bash
python -m migaku_supabase export --csv out.csv
python -m migaku_supabase export --xlsx out.xlsx
```

To pull the latest `meaning` values from Supabase during export:

```bash
python -m migaku_supabase export --xlsx out.xlsx --with-meaning
```

## Table Schema

The default table is `public.migaku_words`.

| Column | Type | Notes |
| --- | --- | --- |
| `migaku_key` | text primary key | `<lang>|<dictForm>|<secondary>` |
| `word` | text | Migaku `dictForm` |
| `pinyin` | text | Tone marks for zh, secondary reading for other languages |
| `meaning` | text | Filled only on first sync for blank rows unless `--no-dict-meanings` is used |
| `example` | text | Dictionary/example enrichment |
| `pinyin_numeric` | text | Numeric tones for zh |
| `status` | text | `KNOWN`, `LEARNING`, `UNKNOWN`, `IGNORED`, etc. |
| `frequency` | integer | 1-5 frequency star bucket |
| `fail_rate_pct` | numeric | Local review aggregation from Migaku payload |
| `total_reviews` | integer | Local review aggregation |
| `failed_reviews` | integer | Local review aggregation |
| `part_of_speech` | text | Comma-separated POS values |
| `language` | text | Migaku language code |
| `last_synced` | timestamptz | Last write time |
| `sense_index` | text | zh homonym/sense index |
| `archived` | boolean | Soft archive flag |
| `created_at` | timestamptz | Supabase row creation time |
| `updated_at` | timestamptz | Maintained by trigger |

Indexes are included for active `language/status` filtering and `last_synced` sorting.

## Security

The bundled schema enables RLS:

```sql
alter table public.migaku_words enable row level security;
```

It grants full access only to `service_role`:

```sql
create policy service_role_full_access
on public.migaku_words
for all
to service_role
using (true)
with check (true);
```

This means:

- The local sync can read/write using `SUPABASE_SERVICE_ROLE_KEY`.
- Browser clients using anon/authenticated keys do not get access unless you add separate policies.
- `.env` and `state.db` are ignored by git and should not be committed.

## Troubleshooting

### Sync says no words returned

You may already be at the latest Migaku cursor. Run:

```bash
python -m migaku_supabase sync --full-refresh
```

### Supabase has fewer rows than `state.db`

Run a full refresh. The sync checks actual Supabase destination rows and creates missing rows:

```bash
python -m migaku_supabase sync --full-refresh
```

### Direct Postgres connection fails on IPv6

Use the **Session pooler** connection string from Supabase's **Connect** dialog. The direct database host may require IPv6; the pooler works better on IPv4-only networks.

### Password authentication failed for user `postgres`

For the Session pooler, the username is usually:

```text
postgres.YOUR_PROJECT_REF
```

Use your database password, not your service-role key.

### Service-role key works but `init-db` fails

That is expected if `SUPABASE_DB_URL` is wrong. Normal sync uses `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; schema creation uses a Postgres connection URL. You can skip `init-db` and run [`supabase/schema.sql`](./supabase/schema.sql) manually in SQL Editor.

## Credits

Based on the read-side Migaku API work from [`gfsincere/migaku-notion-v2`](https://github.com/gfsincere/migaku-notion-v2), adapted to Supabase.

## License

MIT
