BEGIN;

-- CHECK replacement only; preserve users, credentials, identities and all FKs.
DO $$
DECLARE constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT c.conname FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attname='role'
        WHERE c.conrelid='app.users'::regclass AND c.contype='c'
          AND c.conkey=ARRAY[a.attnum]::smallint[]
    LOOP
        EXECUTE format('ALTER TABLE app.users DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;
ALTER TABLE app.users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin','staff','unit'));

INSERT INTO app.schema_migrations(version) VALUES ('app_007_staff_role')
ON CONFLICT(version) DO NOTHING;
COMMIT;
