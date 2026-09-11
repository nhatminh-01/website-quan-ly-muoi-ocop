BEGIN;
CREATE TABLE IF NOT EXISTS app.user_admin_units (
user_id INTEGER NOT NULL PRIMARY KEY REFERENCES app.users(id),
ma_don_vi_hanh_chinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh));
CREATE TABLE IF NOT EXISTS app.admin_unit_aliases (
alias TEXT PRIMARY KEY,
unit_code VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh));
CREATE INDEX IF NOT EXISTS IX_AdminUnitAliasCode ON app.admin_unit_aliases(unit_code);
INSERT INTO qd5277.DM_DonViHanhChinh
(Ma_DonViHanhChinh,Ma_DonViCapTren,TenDonVi,CapHanhChinh,TinhTrang) VALUES
('79',NULL,'Thành phố Hồ Chí Minh','tinh',TRUE),
('27673','79','Xã An Thới Đông','xa',TRUE),
('27676','79','Xã Thạnh An','xa',TRUE),
('27664','79','Xã Cần Giờ','xa',TRUE),
('26659','79','Xã Long Điền','xa',TRUE),
('26545','79','Xã Long Sơn','xa',TRUE),
('26542','79','Phường Phước Thắng','phuong',TRUE),
('26566','79','Phường Long Hương','phuong',TRUE),
('26560','79','Phường Bà Rịa','phuong',TRUE),
('27595','79','Xã Tân Nhựt','xa',TRUE)
ON CONFLICT(Ma_DonViHanhChinh) DO NOTHING;
INSERT INTO app.admin_unit_aliases(alias,unit_code) VALUES('Xã An Thời Đông','27673')
ON CONFLICT(alias) DO NOTHING;
INSERT INTO app.user_admin_units(user_id,ma_don_vi_hanh_chinh)
SELECT u.id, MIN(d.Ma_DonViHanhChinh) FROM app.users u
JOIN qd5277.DM_DonViHanhChinh d ON d.TenDonVi=u.unit_name
WHERE u.role='unit' AND d.TinhTrang=TRUE AND d.CapHanhChinh IN ('xa','phuong')
AND upper(d.Ma_DonViHanhChinh) NOT LIKE 'TMP%'
AND NOT EXISTS (SELECT 1 FROM app.user_admin_units m WHERE m.user_id=u.id)
GROUP BY u.id HAVING COUNT(*)=1
ON CONFLICT(user_id) DO NOTHING;
INSERT INTO app.schema_migrations(version) VALUES('app_010_admin_units') ON CONFLICT(version) DO NOTHING;
COMMIT;
