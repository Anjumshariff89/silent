-- =====================================================================
-- Logs the Attacker Can't Erase — schema (SQLite dialect)
-- Postgres / Supabase version: schema_postgres.sql (same tables & constraints)
-- Foreign keys require `PRAGMA foreign_keys = ON` per connection (the app sets it).
-- =====================================================================

CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,
    hostname        TEXT NOT NULL,
    agent_version   TEXT NOT NULL DEFAULT '0.0.0',
    collector_mode  TEXT NOT NULL DEFAULT 'simulator' CHECK (collector_mode IN ('windows','simulator')),
    registered_at   TEXT NOT NULL,
    last_heartbeat  TEXT,
    offline_alerted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS merkle_batches (
    batch_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    root        TEXT NOT NULL CHECK (length(root) = 64),
    leaf_count  INTEGER NOT NULL CHECK (leaf_count > 0),
    from_seq    INTEGER NOT NULL,
    to_seq      INTEGER NOT NULL,
    levels_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    CHECK (to_seq >= from_seq)
);

CREATE TABLE IF NOT EXISTS security_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seq_id          INTEGER NOT NULL UNIQUE CHECK (seq_id > 0),
    agent_id        TEXT NOT NULL REFERENCES agents(agent_id),
    event_id        INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','critical')),
    source_host     TEXT NOT NULL,
    username        TEXT,
    source_ip       TEXT,
    message         TEXT NOT NULL,
    event_time      TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    merkle_batch_id INTEGER REFERENCES merkle_batches(batch_id)
);
CREATE INDEX IF NOT EXISTS ix_logs_agent      ON security_logs(agent_id);
CREATE INDEX IF NOT EXISTS ix_logs_event_id   ON security_logs(event_id);
CREATE INDEX IF NOT EXISTS ix_logs_event_time ON security_logs(event_time);
CREATE INDEX IF NOT EXISTS ix_logs_batch      ON security_logs(merkle_batch_id);

CREATE TABLE IF NOT EXISTS hash_chain (
    seq_id     INTEGER PRIMARY KEY REFERENCES security_logs(seq_id),
    prev_hash  TEXT NOT NULL CHECK (length(prev_hash) = 64),
    curr_hash  TEXT NOT NULL UNIQUE CHECK (length(curr_hash) = 64),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id       TEXT NOT NULL REFERENCES agents(agent_id),
    collector_mode TEXT NOT NULL DEFAULT 'simulator',
    sent_at        TEXT,
    received_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_heartbeats_agent_time ON heartbeats(agent_id, received_at);

CREATE TABLE IF NOT EXISTS blockchain_anchors (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id         INTEGER NOT NULL UNIQUE REFERENCES merkle_batches(batch_id),
    root             TEXT NOT NULL CHECK (length(root) = 64),
    mode             TEXT NOT NULL CHECK (mode IN ('REAL','SIMULATED')),
    chain_id         INTEGER NOT NULL,
    tx_hash          TEXT NOT NULL,
    block_number     INTEGER NOT NULL,
    block_timestamp  TEXT NOT NULL,
    contract_address TEXT,
    explorer_url     TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL CHECK (kind IN ('chain','proof')),
    target        TEXT NOT NULL DEFAULT 'live' CHECK (target IN ('live','sandbox')),
    result        TEXT NOT NULL CHECK (result IN ('PASS','FAIL','MATCH','MISMATCH','NOT_ANCHORED')),
    checked_count INTEGER NOT NULL DEFAULT 0,
    batch_id      INTEGER REFERENCES merkle_batches(batch_id),
    issues_json   TEXT NOT NULL DEFAULT '[]',
    verified_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_verif_time ON verification_results(verified_at);

-- incidents.seq_id has NO foreign key on purpose: a "missing" incident refers to a log that no
-- longer exists.
CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL CHECK (type IN ('modified','missing','reordered','heartbeat_timeout','merkle_mismatch')),
    severity        TEXT NOT NULL DEFAULT 'critical' CHECK (severity IN ('info','warning','critical')),
    seq_id          INTEGER,
    agent_id        TEXT REFERENCES agents(agent_id),
    batch_id        INTEGER REFERENCES merkle_batches(batch_id),
    verification_id INTEGER REFERENCES verification_results(id),
    target          TEXT NOT NULL DEFAULT 'live' CHECK (target IN ('live','sandbox')),
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    alert_channel   TEXT,
    alert_sent      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents(status, created_at);
