-- Upgrade existing 010 installations without replaying upload history.
BEGIN;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='app'
                   AND table_name='salt_weekly_records' AND column_name='sold_total') THEN
        ALTER TABLE app.salt_weekly_records ADD COLUMN sold_total NUMERIC(12,2)
            NOT NULL DEFAULT 0 CHECK(sold_total>=0);
        UPDATE app.salt_weekly_records r SET sold_total=COALESCE(
            (SELECT (s.canonical_data_json::jsonb->>'sold_total')::numeric
             FROM staging.salt_weekly_import_rows s WHERE s.batch_id=r.batch_id
             AND s.ma_don_vi_hanh_chinh=r.ma_don_vi_hanh_chinh ORDER BY s.id LIMIT 1),
            r.sold_land+r.sold_tarp);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='app'
                   AND table_name='salt_weekly_records' AND column_name='remaining_total') THEN
        ALTER TABLE app.salt_weekly_records ADD COLUMN remaining_total NUMERIC(12,2)
            NOT NULL DEFAULT 0 CHECK(remaining_total>=0);
        UPDATE app.salt_weekly_records r SET remaining_total=COALESCE(
            (SELECT (s.canonical_data_json::jsonb->>'remaining_total')::numeric
             FROM staging.salt_weekly_import_rows s WHERE s.batch_id=r.batch_id
             AND s.ma_don_vi_hanh_chinh=r.ma_don_vi_hanh_chinh ORDER BY s.id LIMIT 1),
            r.remaining_land+r.remaining_tarp);
    END IF;
END $$;

CREATE OR REPLACE VIEW app.v_dn_sanluongmuoi_weekly_qd5277 AS
SELECT id AS Ma_SanLuongMuoi, ma_don_vi_hanh_chinh AS Ma_DonViHanhChinh,
       week_code AS Ma_ThoiGian, CAST('Truyền thống' AS VARCHAR(100)) AS PhuongPhapSX,
       CAST(area_land+area_tarp AS NUMERIC(12,2)) AS DienTich,
       CAST(harvest_land+harvest_tarp AS NUMERIC(12,2)) AS SanLuong,
       CAST(NULL AS NUMERIC(12,2)) AS GiaBanBinhQuan
FROM app.salt_weekly_records;

INSERT INTO app.schema_migrations(version) VALUES('app_009_weekly_foundation')
ON CONFLICT(version) DO NOTHING;
COMMIT;
