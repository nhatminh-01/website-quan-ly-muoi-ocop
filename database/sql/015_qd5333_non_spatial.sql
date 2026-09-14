BEGIN;

-- QD 5333 detail schema. Spatial tables are intentionally excluded until the
-- DBA enables PostGIS; no geometry is represented as TEXT/JSON.
CREATE SCHEMA IF NOT EXISTS qd5333;

CREATE TABLE IF NOT EXISTS qd5333.CoSoSanXuatMuoi (
    maCoSo VARCHAR(50) PRIMARY KEY,
    maDinhDanhToChuc VARCHAR(12),
    tenCoSo VARCHAR(256),
    loaiHinhHoatDong INTEGER,
    loaiCoSo INTEGER,
    soKyHieu VARCHAR(50),
    thoiGianCap DATE,
    coQuanBanHanh VARCHAR(256),
    trangThai INTEGER,
    tepDinhKem VARCHAR(256),
    dienTich DOUBLE PRECISION,
    soLuong DOUBLE PRECISION,
    ghiChu VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.BaoCaoSXCBMuoi (
    maBaoCao VARCHAR(50) PRIMARY KEY,
    maCoSo VARCHAR(50) NOT NULL REFERENCES qd5333.CoSoSanXuatMuoi(maCoSo),
    kyBaoCao VARCHAR(50),
    soLuongTieuThu DOUBLE PRECISION,
    sanLuong DOUBLE PRECISION,
    soLuongTonDong DOUBLE PRECISION,
    giaTriTieuThu DOUBLE PRECISION,
    thiTruong VARCHAR(256),
    loaiMuoiCheBien INTEGER,
    tepDinhKem VARCHAR(256),
    ghiChu VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.NhapKhauMuoi (
    maNhapKhau VARCHAR(50) PRIMARY KEY,
    maCoSo VARCHAR(50) NOT NULL REFERENCES qd5333.CoSoSanXuatMuoi(maCoSo),
    maLoaiMuoi INTEGER,
    ketQuaThuNghiem VARCHAR(256),
    soLuong DOUBLE PRECISION,
    tepDinhKem VARCHAR(256),
    ghiChu VARCHAR(256)
);

CREATE TABLE IF NOT EXISTS qd5333.CongBoSanPhamMuoi (
    maCongBo VARCHAR(50) PRIMARY KEY,
    maCoSo VARCHAR(50) NOT NULL REFERENCES qd5333.CoSoSanXuatMuoi(maCoSo),
    tepDinhKem VARCHAR(256),
    phuongThucSanXuat INTEGER,
    tieuChuanChatLuong VARCHAR(500),
    loaiSanPham INTEGER,
    giaMuoi DOUBLE PRECISION,
    ghiChu VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.LienKetHopTacSXMuoi (
    maLienKetHopTacc VARCHAR(50) PRIMARY KEY,
    maCoSo VARCHAR(50) NOT NULL REFERENCES qd5333.CoSoSanXuatMuoi(maCoSo),
    maHopDong VARCHAR(50),
    thoiGianLienKet DATE,
    hinhThucLienKet INTEGER
);

CREATE TABLE IF NOT EXISTS qd5333.DM_NhomSanPham (
    maNhomSanPham VARCHAR(50) PRIMARY KEY,
    tenNhomSanPham VARCHAR(256),
    loaiHinh INTEGER,
    moTa VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.CoSoSanXuat (
    maCoSo VARCHAR(50) PRIMARY KEY,
    maDinhDanhToChuc VARCHAR(12),
    maSanPham VARCHAR(50),
    tenCoSo VARCHAR(256),
    soDienThoai VARCHAR(20),
    thuDienTu VARCHAR(50),
    diaChi VARCHAR(256),
    loaiHinh INTEGER,
    thoiGianThamGia DATE,
    soLuong INTEGER,
    moTa VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.DanhGiaSanPhamOCOP (
    maDanhGia VARCHAR(50) PRIMARY KEY,
    maSanPham VARCHAR(50),
    tenDanhGia VARCHAR(256),
    thangDiem VARCHAR(20),
    coQuanThucHien VARCHAR(50),
    thoigGianDanhGia DATE,
    ketQuaXepLoai INTEGER
);

CREATE TABLE IF NOT EXISTS qd5333.ThuongHieuBaoHo (
    maThuongHieu VARCHAR(50) PRIMARY KEY,
    maSanPham VARCHAR(50),
    soDangKy VARCHAR(50),
    thoiGianDangKy DATE,
    coQuanThucHien VARCHAR(50),
    tinhTrang INTEGER,
    tepDinhKem VARCHAR(500),
    moTa VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.ThiTruongTieuThu (
    maThiTruong VARCHAR(50) PRIMARY KEY,
    maSanPham VARCHAR(50),
    maNguonVon VARCHAR(50),
    maDoanhNghiepPhanPhoi VARCHAR(12),
    thiTruongTrongNuoc VARCHAR(50),
    thiTruongXuatKhau VARCHAR(50),
    tongSoDoanhThu DOUBLE PRECISION,
    tyLe INTEGER
);

CREATE TABLE IF NOT EXISTS qd5333.HoTroPhatTrienSanPhamOCOP (
    maHoTro VARCHAR(50) PRIMARY KEY,
    maSanPham VARCHAR(50),
    loaiHoTro INTEGER,
    nguonVon INTEGER,
    thoiGianThucHien DATE,
    moTa VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS qd5333.ToChucHoatDongKTHT (
    maDinhDanhToChuc VARCHAR(12) PRIMARY KEY,
    tenDoanhNghiep VARCHAR(255),
    tenGiaoDich VARCHAR(255),
    tenTiengAnh VARCHAR(255),
    diaChiTruSo VARCHAR(255),
    maDinhDanhCaNhan VARCHAR(12),
    chucVu VARCHAR(255),
    soQuyetDinh VARCHAR(50),
    ngayBanHanh DATE,
    coQuanBanHanh VARCHAR(50),
    maSoThue VARCHAR(100),
    soDienThoai VARCHAR(30),
    eMail VARCHAR(50),
    maTinh VARCHAR(100),
    maDinhDanhXa VARCHAR(100)
);

-- These two catalogs are code/label tables in the source specification.
-- The source headings do not provide a separate physical key name; the
-- documented integer code is used as the primary key and the ambiguity is
-- recorded in schema_issues.md.
CREATE TABLE IF NOT EXISTS qd5333.DM_PhanLoaiMayThietBiNN (
    maMayThietBi INTEGER PRIMARY KEY,
    giaTri VARCHAR(255),
    moTa VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5333.DM_LoaiHinhNganhNghe (
    maLoaiHinh INTEGER PRIMARY KEY,
    dieuKienLapDia VARCHAR(255),
    moTa VARCHAR(500)
);

-- Shared QD 5333 metadata tables (all non-spatial).
CREATE TABLE IF NOT EXISTS qd5333.DM_SieuDuLieu (
    sieuDuLieuID VARCHAR(255) PRIMARY KEY,
    loaiCapDoSDL VARCHAR(255), loaiDuLieu VARCHAR(255), loaiSieuDuLieu VARCHAR(255),
    ngonNgu VARCHAR(255), phamVi VARCHAR(255), phienBan VARCHAR(255),
    sieuDuLieuIDGoc VARCHAR(255), tenChuan VARCHAR(255), thoiGianLap DATE
);

CREATE TABLE IF NOT EXISTS qd5333.DM_DonVi (
    sieuDuLieuDVID VARCHAR(255) PRIMARY KEY,
    chucVu VARCHAR(255), diaChiLienHe VARCHAR(255), dienThoai VARCHAR(255),
    chiDanLienHe VARCHAR(255), eMail VARCHAR(255), loaiDonVi VARCHAR(255),
    moTa VARCHAR(255), nguoiDaiDien VARCHAR(255), soGiayPhep VARCHAR(255),
    tenDonVi VARCHAR(255), thongTinLienHe VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5333.DM_HeToaDo (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    kinhTuyenTruc VARCHAR(255),
    muiChieu DOUBLE PRECISION,
    tenHeQuyChieu VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5333.DM_ThuocTinh (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    dinhDangDuLieu VARCHAR(255), moTa VARCHAR(255), nguonGocDuLieu VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5333.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDoiTuong INTEGER, thoiDiemHinhThanh DATE
);

CREATE TABLE IF NOT EXISTS qd5333.DM_KhongGian (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    dinhDangDuLieu VARCHAR(255),
    heQuyChieuID VARCHAR(255) REFERENCES qd5333.DM_HeToaDo(maDoiTuongID),
    kieuDuLieuKhongGian VARCHAR(255), moTa VARCHAR(255), nguonGocDuLieu VARCHAR(255),
    phuongPhapTaoLap VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5333.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDoiTuong INTEGER, thoiDiemHinhThanh DATE,
    toaDoGioiHanXMax DOUBLE PRECISION, toaDoGioiHanXMin DOUBLE PRECISION,
    toaDoGioiHanYMax DOUBLE PRECISION, toaDoGioiHanYMin DOUBLE PRECISION,
    tyLeBanDo VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5333.DM_PhiCauTruc (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    dinhDangDuLieu VARCHAR(255), moTa VARCHAR(255), nguonGocDuLieu VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5333.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDoiTuong INTEGER, thoiDiemHinhThanh DATE
);

CREATE TABLE IF NOT EXISTS qd5333.DM_ChatLuongDuLieu (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    ghiChu VARCHAR(255), ketQuaDanhGia VARCHAR(255), loaiDuLieu VARCHAR(255),
    mucDoDanhGia VARCHAR(255), muaDoDayDuTT VARCHAR(255), phuongPhapDGCL VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5333.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDanhGia INTEGER, thoiDiemDanhGia DATE
);

CREATE TABLE IF NOT EXISTS qd5333.DM_PhuongThucChiaSe (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    chiTietPhanPhoi VARCHAR(255), dinhDangPhanPhoi VARCHAR(255), ghiChu VARCHAR(255),
    hinhThucPhanPhoi VARCHAR(255), loaiDuLieuID VARCHAR(255), phienBan VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5333.DM_SieuDuLieu(sieuDuLieuID),
    tenTaiLieu VARCHAR(255)
);

INSERT INTO app.schema_migrations(version)
VALUES ('qd5333_001_non_spatial')
ON CONFLICT (version) DO NOTHING;

COMMIT;
