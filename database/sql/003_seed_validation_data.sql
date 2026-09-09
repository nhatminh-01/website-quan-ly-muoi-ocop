BEGIN;

INSERT INTO qd5277.DM_KhoangThoiGian (Ma_ThoiGian, Nam, Thang, VuMua)
VALUES ('2026-08', 2026, 8, NULL)
ON CONFLICT (Ma_ThoiGian) DO UPDATE
SET Nam = EXCLUDED.Nam, Thang = EXCLUDED.Thang, VuMua = EXCLUDED.VuMua;

INSERT INTO qd5277.DM_DonViHanhChinh
    (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
VALUES
    ('79', NULL, 'Thành phố Hồ Chí Minh', 'tinh', TRUE),
    ('27673', '79', 'Xã An Thới Đông', 'xa', TRUE),
    ('27676', '79', 'Xã Thạnh An', 'xa', TRUE),
    ('27664', '79', 'Xã Cần Giờ', 'xa', TRUE),
    ('26659', '79', 'Xã Long Điền', 'xa', TRUE),
    ('26545', '79', 'Xã Long Sơn', 'xa', TRUE),
    ('26542', '79', 'Phường Phước Thắng', 'phuong', TRUE),
    ('26566', '79', 'Phường Long Hương', 'phuong', TRUE),
    ('26560', '79', 'Phường Bà Rịa', 'phuong', TRUE)
ON CONFLICT (Ma_DonViHanhChinh) DO UPDATE
SET Ma_DonViCapTren = EXCLUDED.Ma_DonViCapTren,
    TenDonVi = EXCLUDED.TenDonVi,
    CapHanhChinh = EXCLUDED.CapHanhChinh,
    TinhTrang = EXCLUDED.TinhTrang;

COMMIT;
