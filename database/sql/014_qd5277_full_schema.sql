BEGIN;

-- QD 5277 canonical completion. Migration 002 contains the first 19 tables;
-- this migration adds the remaining 11 tables so the canonical schema is
-- complete (17 business + 7 catalog + 6 metadata = 30 tables).
CREATE SCHEMA IF NOT EXISTS qd5277;

CREATE TABLE IF NOT EXISTS qd5277.TH_TongHop (
    Ma_TongHop INTEGER PRIMARY KEY,
    Ma_Nganh VARCHAR(10) NOT NULL,
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    SanLuongTong NUMERIC(14,2),
    GiaTriSanXuat NUMERIC(14,2),
    GiaTriXuatKhauNN NUMERIC(16,2),
    TyLeSanPhamChungNhan NUMERIC(6,2),
    TangTruong NUMERIC(6,2),
    ChuTheSanXuat VARCHAR(255),
    NguonSoLieu VARCHAR(255),
    GhiChu VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5277.NN_TrongTrot_TongHop (
    Ma_TrongTrot INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    DienTichGieoTrong NUMERIC(12,2),
    DienTichChoSanPham NUMERIC(12,2),
    NangSuat NUMERIC(8,2),
    SanLuong NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.NN_BVTV_TongHop (
    Ma_BVTV INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    TongDienTichGieoTrong NUMERIC(14,2),
    DienTichNhiemSauBenh NUMERIC(14,2),
    DienTichPhongTru NUMERIC(14,2),
    Mucdonhiem VARCHAR(50),
    TyLeDienTichNhiem NUMERIC(6,2),
    SoLoaiSauBenhChuY INTEGER,
    SoMauKiemTraTonDu INTEGER,
    TyLeMauVuotNguong NUMERIC(6,2),
    SoLoHangKiemDichTV INTEGER,
    TiLeLoHangKhongDat NUMERIC(6,2),
    SoSuKienCanhBaoSauBenh INTEGER
);

CREATE TABLE IF NOT EXISTS qd5277.NN_ChanNuoi_TongHop (
    Ma_ChanNuoi INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    SoLuongVatNuoi NUMERIC(12,2),
    LoaiSanPham VARCHAR(50),
    SanLuong NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.NN_ThuY_TongHop (
    Ma_ThuY INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    TongDanVatNuoi NUMERIC(14,2),
    SoDichPhatSinh INTEGER,
    LoaiBenhThuY VARCHAR(255),
    SoLuongMacBenh INTEGER,
    SoLuongChet INTEGER,
    SoLuongConTieuHuy INTEGER,
    TyLeDichBenh NUMERIC(6,2),
    SoLoHangKiemDichDV INTEGER,
    TiLeLoHangKhongDatDV NUMERIC(6,2),
    SoMauKiemTraATTP INTEGER,
    TyLeMauKhongDatATTP NUMERIC(6,2)
);

CREATE TABLE IF NOT EXISTS qd5277.LN_DienTichRung (
    Ma_DienTichRung INTEGER PRIMARY KEY,
    Ma_DinhDanhLo VARCHAR(50),
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    NguonGocRung VARCHAR(50),
    DienTichRung NUMERIC(6,2),
    ChucNangSuDung INTEGER,
    TyLeChePhuRung NUMERIC(6,2),
    TangTruong NUMERIC(8,2)
);

CREATE TABLE IF NOT EXISTS qd5277.LN_SanPhamLamNghiep (
    Ma_SanPhamLN INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    DonViTinh VARCHAR(50),
    -- The source repeats Ma_SanPhamLamNghiep for both the row key and a
    -- product-code FK.  A separate physical name avoids an impossible
    -- duplicate column; see database/schema_issues.md.
    Ma_LoaiSanPhamLamNghiep VARCHAR(10),
    SanLuong NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.TS_NuoiTrong (
    Ma_NuoiTrongTS INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    DienTichNuoi NUMERIC(12,2),
    SanLuong NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.TS_KhaiThac (
    Ma_KhaiThac INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) NOT NULL REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    LoaiNguTruong VARCHAR(100),
    SanLuong NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.TL_Antoandap_Hochuathuyloi (
    Ma_HoChuaThuyLoi VARCHAR(10) PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    LoaiHoDap VARCHAR(50),
    TenCongTrinh VARCHAR(255),
    DungTich NUMERIC(12,2),
    CongSuatTuoi NUMERIC(12,2),
    TinhTrangCongTrinh VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS qd5277.TL_CongTrinhThuyloi (
    Ma_CongTrinhTL VARCHAR(10) PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) NOT NULL REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    TenCongTrinh VARCHAR(255),
    LoaiCongTrinh VARCHAR(100),
    CongDung VARCHAR(100),
    CongSuat NUMERIC(12,2),
    ChieuDaiKenh NUMERIC(12,2),
    TrangThai VARCHAR(100)
);

INSERT INTO app.schema_migrations(version)
VALUES ('qd5277_001_full_canonical')
ON CONFLICT (version) DO NOTHING;

COMMIT;
