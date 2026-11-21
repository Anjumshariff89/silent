-- =====================================================================
-- Row Level Security for Supabase (run AFTER schema_postgres.sql; the migration file does both).
--
-- Design: the tamper-evident log is ONE shared hash chain for the whole SOC (every log links to the previous
-- one), so rows are not owned by individual users. Policies therefore:
--   * signed-in Supabase users (role `authenticated`) may only READ;
--   * anonymous visitors (role `anon`, i.e. the public anon key) get nothing;
--   * nobody can INSERT/UPDATE/DELETE through the Supabase Data API. Writes happen only through the FastAPI
--     backend, which connects with DATABASE_URL as the table owner (owners bypass RLS) and enforces the
--     append-only hash chain itself.
--   * the optional restricted role `log_writer` (roles_postgres.sql) keeps INSERT + SELECT on security_logs.
-- Safe to run more than once.
-- =====================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['agents', 'security_logs', 'hash_chain', 'heartbeats', 'merkle_batches',
                             'blockchain_anchors', 'verification_results', 'incidents']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('DROP POLICY IF EXISTS "signed-in users can read" ON public.%I', t);
            EXECUTE format('CREATE POLICY "signed-in users can read" ON public.%I FOR SELECT TO authenticated USING (true)', t);
        END IF;
    END LOOP;

    -- Belt and braces: the Data API roles never get write privileges on these tables.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM authenticated;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'log_writer') THEN
        DROP POLICY IF EXISTS "log_writer inserts" ON public.security_logs;
        DROP POLICY IF EXISTS "log_writer reads" ON public.security_logs;
        CREATE POLICY "log_writer inserts" ON public.security_logs FOR INSERT TO log_writer WITH CHECK (true);
        CREATE POLICY "log_writer reads" ON public.security_logs FOR SELECT TO log_writer USING (true);
    END IF;
END
$$;
