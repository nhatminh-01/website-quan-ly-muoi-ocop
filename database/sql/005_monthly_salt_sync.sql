BEGIN;

-- DN_SanLuongMuoi in QD 5277 uses a technical integer key but the original
-- definition had no generator.  A sequence enables safe application UPSERTs
-- without changing any business field.
CREATE SEQUENCE IF NOT EXISTS qd5277.dn_sanluongmuoi_id_seq;

ALTER SEQUENCE qd5277.dn_sanluongmuoi_id_seq
    OWNED BY qd5277.DN_SanLuongMuoi.Ma_SanLuongMuoi;

ALTER TABLE qd5277.DN_SanLuongMuoi
    ALTER COLUMN Ma_SanLuongMuoi
    SET DEFAULT nextval('qd5277.dn_sanluongmuoi_id_seq');

SELECT setval(
    'qd5277.dn_sanluongmuoi_id_seq',
    COALESCE((SELECT MAX(Ma_SanLuongMuoi) + 1 FROM qd5277.DN_SanLuongMuoi), 1),
    FALSE
);

INSERT INTO app.schema_migrations(version)
VALUES ('app_002_monthly_salt_sync')
ON CONFLICT (version) DO NOTHING;

COMMIT;
