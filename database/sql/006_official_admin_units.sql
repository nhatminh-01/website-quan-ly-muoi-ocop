BEGIN;

INSERT INTO qd5277.DM_DonViHanhChinh
    (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
VALUES ('79', NULL, 'Thành phố Hồ Chí Minh', 'tinh', TRUE)
ON CONFLICT (Ma_DonViHanhChinh) DO UPDATE SET
    TenDonVi=excluded.TenDonVi,
    CapHanhChinh=excluded.CapHanhChinh,
    TinhTrang=TRUE;

INSERT INTO qd5277.DM_DonViHanhChinh
    (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
VALUES
    ('27673', '79', 'Xã An Thới Đông', 'xa', TRUE),
    ('27676', '79', 'Xã Thạnh An', 'xa', TRUE),
    ('27664', '79', 'Xã Cần Giờ', 'xa', TRUE),
    ('26659', '79', 'Xã Long Điền', 'xa', TRUE),
    ('26545', '79', 'Xã Long Sơn', 'xa', TRUE),
    ('26542', '79', 'Phường Phước Thắng', 'phuong', TRUE),
    ('26566', '79', 'Phường Long Hương', 'phuong', TRUE),
    ('26560', '79', 'Phường Bà Rịa', 'phuong', TRUE)
ON CONFLICT (Ma_DonViHanhChinh) DO UPDATE SET
    Ma_DonViCapTren=excluded.Ma_DonViCapTren,
    TenDonVi=excluded.TenDonVi,
    CapHanhChinh=excluded.CapHanhChinh,
    TinhTrang=TRUE;

UPDATE qd5277.DN_SanLuongMuoi AS salt
SET Ma_DonViHanhChinh = mapping.official_code
FROM (VALUES
    ('TMP000001', '27673'), ('TMP000002', '27676'),
    ('TMP000003', '27664'), ('TMP000004', '26659'),
    ('TMP000005', '26545'), ('TMP000006', '26542'),
    ('TMP000007', '26566'), ('TMP000008', '26560')
) AS mapping(temp_code, official_code)
WHERE salt.Ma_DonViHanhChinh = mapping.temp_code;

DELETE FROM qd5277.DM_DonViHanhChinh
WHERE Ma_DonViHanhChinh LIKE 'TMP%';

INSERT INTO app.schema_migrations(version)
VALUES ('app_003_official_admin_units')
ON CONFLICT (version) DO NOTHING;

COMMIT;
