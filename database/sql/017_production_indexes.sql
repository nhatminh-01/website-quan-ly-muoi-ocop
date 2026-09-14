BEGIN;

-- Foreign-key indexes required by production reads and imports.
CREATE INDEX IF NOT EXISTS ix_qd5277_th_tonghop_period
    ON qd5277.TH_TongHop (Ma_ThoiGian, Ma_Nganh);
CREATE INDEX IF NOT EXISTS ix_qd5277_trongtrot_unit_period
    ON qd5277.NN_TrongTrot_TongHop (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_bvtv_unit_period
    ON qd5277.NN_BVTV_TongHop (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_channuoi_unit_period
    ON qd5277.NN_ChanNuoi_TongHop (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_thuy_unit_period
    ON qd5277.NN_ThuY_TongHop (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_rung_unit_period
    ON qd5277.LN_DienTichRung (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_lamnghiep_unit_period
    ON qd5277.LN_SanPhamLamNghiep (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_nuoitrong_unit_period
    ON qd5277.TS_NuoiTrong (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_khaithac_unit_period
    ON qd5277.TS_KhaiThac (Ma_DonViHanhChinh, Ma_ThoiGian);
CREATE INDEX IF NOT EXISTS ix_qd5277_hocua_unit
    ON qd5277.TL_Antoandap_Hochuathuyloi (Ma_DonViHanhChinh);
CREATE INDEX IF NOT EXISTS ix_qd5277_thuyloi_unit
    ON qd5277.TL_CongTrinhThuyloi (Ma_DonViHanhChinh);

CREATE INDEX IF NOT EXISTS ix_qd5333_baocao_cos
    ON qd5333.BaoCaoSXCBMuoi (maCoSo, kyBaoCao);
CREATE INDEX IF NOT EXISTS ix_qd5333_nhapkhau_cos
    ON qd5333.NhapKhauMuoi (maCoSo);
CREATE INDEX IF NOT EXISTS ix_qd5333_congbo_cos
    ON qd5333.CongBoSanPhamMuoi (maCoSo);
CREATE INDEX IF NOT EXISTS ix_qd5333_lienket_cos
    ON qd5333.LienKetHopTacSXMuoi (maCoSo);
CREATE INDEX IF NOT EXISTS ix_qd5333_cos_sanpham
    ON qd5333.CoSoSanXuat (maSanPham);
CREATE INDEX IF NOT EXISTS ix_qd5333_danhgia_sanpham
    ON qd5333.DanhGiaSanPhamOCOP (maSanPham);
CREATE INDEX IF NOT EXISTS ix_qd5333_thuonghieu_sanpham
    ON qd5333.ThuongHieuBaoHo (maSanPham);
CREATE INDEX IF NOT EXISTS ix_qd5333_thitruong_sanpham
    ON qd5333.ThiTruongTieuThu (maSanPham);
CREATE INDEX IF NOT EXISTS ix_qd5333_hotro_sanpham
    ON qd5333.HoTroPhatTrienSanPhamOCOP (maSanPham);
CREATE INDEX IF NOT EXISTS ix_app_code_mappings_lookup
    ON app.code_mappings (mapping_type, source_code, is_active);

INSERT INTO app.schema_migrations(version)
VALUES ('production_001_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
