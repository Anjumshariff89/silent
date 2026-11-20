# Database

Two dialects, identical tables and constraints:

| File | Use |
|---|---|
| `backend/database/schema.sql` | SQLite (SIMULATED/default, `DATABASE_URL=sqlite:///./local.db`). Applied automatically at backend start. |
| `backend/database/schema_postgres.sql` | PostgreSQL / Supabase (REAL). Also applied automatically at start (idempotent), or run it by hand. |
| `backend/database/roles_postgres.sql` | Restricted `log_writer` role: INSERT + SELECT on `security_logs` only. Postgres only. |

## Running it in Supabase

1. Supabase Dashboard → your project → **SQL Editor** → **New query**.
2. Paste `schema_postgres.sql` → **Run**. Then check **Table Editor**: 8 tables.
3. New query → paste `roles_postgres.sql`, replace `CHANGE_ME_IN_SQL_EDITOR` *in the editor only* → **Run**.
4. **Project Settings → Database → Connection string (URI)** → put it in `.env` as `DATABASE_URL=postgresql://...`
   yourself. Never paste it into chat or commit it.

## Tables

| Table | Purpose | Key constraints |
|---|---|---|
| `agents` | Registered log agents | PK `agent_id` |
| `security_logs` | Append-only security events | PK `id`, **UNIQUE `seq_id`**, FK `agent_id → agents`, FK `merkle_batch_id → merkle_batches` |
| `hash_chain` | `prev_hash` / `curr_hash` per log | PK+FK `seq_id → security_logs.seq_id`, UNIQUE `curr_hash` |
| `heartbeats` | Agent liveness pings | FK `agent_id → agents` |
| `merkle_batches` | Merkle roots + tree levels per batch | PK `batch_id` |
| `blockchain_anchors` | Anchoring tx per batch | UNIQUE FK `batch_id → merkle_batches` |
| `verification_results` | Every chain/proof verification run | FK `batch_id` |
| `incidents` | Tamper / timeout incidents | `seq_id` deliberately has **no FK** (a "missing" log no longer exists) |

Indexes cover agent, event_id, event_time, batch, heartbeat (agent,time), incident (status,time).

## Restricted role (verified in Step 2 on Postgres 16)

`log_writer` can `INSERT` and `SELECT` on `security_logs`. `UPDATE`, `DELETE`, `TRUNCATE` and any access to
other tables give `permission denied`. Note: the backend itself also writes `hash_chain`, heartbeats, etc., so
the backend connects with a fuller role. `log_writer` is meant for a minimal ingest path or for auditors.

## Upgrading an existing database

`CREATE TABLE IF NOT EXISTS` never changes a table that already exists, so columns added in later versions
are applied by `apply_schema()` at backend start (`MIGRATIONS` in `backend/database/db.py`). Currently:
`blockchain_anchors.onchain_batch_id` (+ unique index). It is idempotent and verified on SQLite and Postgres 16.
For Supabase you can also run it by hand in the SQL Editor:

```sql
ALTER TABLE blockchain_anchors ADD COLUMN IF NOT EXISTS onchain_batch_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_anchors_onchain_batch_id ON blockchain_anchors(onchain_batch_id);
```

Quai anchors fit the existing columns: `chain_id` = 15000, `tx_hash` and the zone-specific
`contract_address` are stored as `TEXT`, and `explorer_url` points to `https://orchard.quaiscan.io`.
