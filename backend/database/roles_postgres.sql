-- =====================================================================
-- Restricted role: may only INSERT and SELECT on security_logs.
-- No UPDATE, DELETE or TRUNCATE, so a stolen credential for this role cannot rewrite history.
-- Run AFTER schema_postgres.sql, in Supabase SQL Editor (as the `postgres` user).
-- Replace the password placeholder in the editor; never commit a real password.
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'log_writer') THEN
        CREATE ROLE log_writer LOGIN PASSWORD 'CHANGE_ME_IN_SQL_EDITOR';
    END IF;
END
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM log_writer;
GRANT USAGE ON SCHEMA public TO log_writer;
GRANT INSERT, SELECT ON TABLE security_logs TO log_writer;
-- Needed so INSERT can draw identity values for the surrogate `id` column.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO log_writer;
