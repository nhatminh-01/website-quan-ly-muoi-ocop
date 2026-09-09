BEGIN;

DO $$
DECLARE
    missing_tables TEXT;
BEGIN
    SELECT string_agg(required.name, ', ' ORDER BY required.name)
    INTO missing_tables
    FROM (VALUES
        ('ocop_entities'), ('ocop_products'),
        ('ocop_applications'), ('ocop_reviews')
    ) AS required(name)
    WHERE to_regclass('app.' || required.name) IS NULL;

    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Thiếu bảng OCOP: %', missing_tables;
    END IF;
END $$;

-- Deliberately no OCOP seed data.  This marker records the agreed init-only state.
INSERT INTO app.schema_migrations(version)
VALUES ('app_005_ocop_init_only')
ON CONFLICT (version) DO NOTHING;

COMMIT;
