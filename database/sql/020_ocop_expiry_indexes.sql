BEGIN;

-- Current-recognition expiry reports filter by expiry date while joining on
-- product_id. Keep the index partial so historical recognitions stay out.
CREATE INDEX IF NOT EXISTS IX_OCOP_RecognitionCurrentExpiry
    ON app.ocop_recognitions(expiry_date, product_id)
    WHERE is_current = TRUE;

INSERT INTO app.schema_migrations(version)
VALUES ('app_020_ocop_expiry_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
