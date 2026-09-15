BEGIN;

-- Keep PostgreSQL identity generators aligned after insert-only data copies.
-- This is safe for both populated and empty tables and does not change rows.
DO $$
DECLARE
    target record;
    sequence_name text;
    maximum bigint;
BEGIN
    FOR target IN
        SELECT *
        FROM (VALUES
            ('app'::text, 'salt_import_batches'::text, 'id'::text),
            ('app'::text, 'salt_weekly_records'::text, 'id'::text),
            ('staging'::text, 'salt_weekly_import_rows'::text, 'id'::text)
        ) AS values(schema_name, table_name, column_name)
    LOOP
        SELECT pg_get_serial_sequence(
            format('%I.%I', target.schema_name, target.table_name),
            target.column_name
        )
        INTO sequence_name;

        IF sequence_name IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format(
            'SELECT max(%I) FROM %I.%I',
            target.column_name, target.schema_name, target.table_name
        )
        INTO maximum;

        IF maximum IS NULL THEN
            PERFORM setval(sequence_name, 1, false);
        ELSE
            PERFORM setval(sequence_name, maximum, true);
        END IF;
    END LOOP;
END $$;

INSERT INTO app.schema_migrations(version)
VALUES ('app_018_repair_identity_sequences')
ON CONFLICT (version) DO NOTHING;

COMMIT;
