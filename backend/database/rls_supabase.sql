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

-- ---------------------------------------------------------------------
-- Per-user tables (logs, merkle_roots, anchors): a signed-in user can read ONLY their own rows.
-- Writes go through the backend, which also filters every query by the user id from the verified token
-- (it connects as the table owner, so it does not rely on RLS for ownership).
-- ---------------------------------------------------------------------
DO $$
BEGIN
    ALTER TABLE public.logs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.merkle_roots ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.anchors ENABLE ROW LEVEL SECURITY;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
       AND EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'auth' AND p.proname = 'uid') THEN
        DROP POLICY IF EXISTS "own logs" ON public.logs;
        CREATE POLICY "own logs" ON public.logs FOR SELECT TO authenticated
            USING (user_id = (SELECT auth.uid()));
        DROP POLICY IF EXISTS "own merkle roots" ON public.merkle_roots;
        CREATE POLICY "own merkle roots" ON public.merkle_roots FOR SELECT TO authenticated
            USING (user_id = (SELECT auth.uid()));
        DROP POLICY IF EXISTS "own anchors" ON public.anchors;
        CREATE POLICY "own anchors" ON public.anchors FOR SELECT TO authenticated
            USING (EXISTS (SELECT 1 FROM public.merkle_roots m
                           WHERE m.id = anchors.merkle_root_id AND m.user_id = (SELECT auth.uid())));
    END IF;

    -- Supabase: tie rows to real accounts (deleting a user deletes their rows).
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'logs_user_fk') THEN
            ALTER TABLE public.logs ADD CONSTRAINT logs_user_fk
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'merkle_roots_user_fk') THEN
            ALTER TABLE public.merkle_roots ADD CONSTRAINT merkle_roots_user_fk
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        END IF;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.logs, public.merkle_roots, public.anchors FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.logs, public.merkle_roots, public.anchors FROM authenticated;
    END IF;
END
$$;
