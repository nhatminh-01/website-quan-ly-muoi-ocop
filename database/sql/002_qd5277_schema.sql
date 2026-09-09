BEGIN;

CREATE SCHEMA IF NOT EXISTS qd5277;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS qd5277.DM_DonViHanhChinh (
    Ma_DonViHanhChinh VARCHAR(10) PRIMARY KEY,
    Ma_DonViCapTren VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    TenDonVi VARCHAR(255),
    CapHanhChinh VARCHAR(10),
    TinhTrang BOOLEAN
);

CREATE TABLE IF NOT EXISTS qd5277.DM_KhoangThoiGian (
    Ma_ThoiGian VARCHAR(10) PRIMARY KEY,
    Nam INTEGER,
    Thang INTEGER,
    VuMua VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS qd5277.DM_SanPham (
    Ma_SanPham VARCHAR(10) PRIMARY KEY,
    TenSanPham VARCHAR(255),
    NhomSanPham VARCHAR(100),
    DonViTinh VARCHAR(50),
    TrangThai BOOLEAN
);

CREATE TABLE IF NOT EXISTS qd5277.DM_CoSo (
    Ma_CoSo VARCHAR(10) PRIMARY KEY,
    TenCoSo VARCHAR(255),
    LoaiCoSo VARCHAR(100),
    DiaChi VARCHAR(255),
    Ma_DonViHanhChinh VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh)
);

CREATE TABLE IF NOT EXISTS qd5277.DM_TieuChuanChatLuong (
    Ma_TieuChuanChatLuong VARCHAR(10) PRIMARY KEY,
    TenTieuChuan VARCHAR(255),
    LoaiTieuChuan VARCHAR(50),
    CoCongBoTieuChuan VARCHAR(100),
    NgayBanHanh DATE,
    NgayHetHieuLuc DATE
);

CREATE TABLE IF NOT EXISTS qd5277.DM_TieuChuanHuuCo (
    Ma_TieuChuanHuuCo VARCHAR(50) PRIMARY KEY,
    TenTieuChuan VARCHAR(255),
    PhienBan VARCHAR(20),
    CoQuanBanHanh VARCHAR(255),
    PhamViApDung VARCHAR(255),
    QuocGiaApDung VARCHAR(100),
    NgayHieuLuc DATE,
    NgayHetHieuLuc DATE,
    TinhTrang BOOLEAN,
    MoTaChiTiet VARCHAR(255),
    LienKetTaiLieu VARCHAR(255),
    NguonCapNhat VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5277.DM_ChiTieuThongKe (
    Ma_ChiTieuThongKe VARCHAR(10) PRIMARY KEY,
    NhomChiTieu VARCHAR(50),
    TenChiTieu VARCHAR(255),
    PhanNhom VARCHAR(255),
    KySoLieu INTEGER,
    NguonSoLieu VARCHAR(255),
    DonViTinh VARCHAR(50),
    LinhVuc VARCHAR(50),
    MoTa VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5277.DN_SanLuongMuoi (
    Ma_SanLuongMuoi INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    PhuongPhapSX VARCHAR(100),
    DienTich NUMERIC(12,2),
    SanLuong NUMERIC(12,2),
    GiaBanBinhQuan NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS qd5277.PTNT_OCOP (
    MA_OCOP INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    TenSanPham VARCHAR(255),
    XepHang VARCHAR(50),
    ChuTheSXKD VARCHAR(255),
    DoanhThuNam NUMERIC(14,2),
    TrangThai VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS qd5277.QLCL_CoSoCheBien (
    Ma_DonViHanhChinh VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_CoSoCheBien VARCHAR(10) REFERENCES qd5277.DM_CoSo(Ma_CoSo),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    CongSuat NUMERIC(12,2),
    SanLuong NUMERIC(12,2),
    ChungNhanATTP BOOLEAN,
    SoGiayPhepATTP VARCHAR(10),
    PRIMARY KEY (Ma_DonViHanhChinh, Ma_CoSoCheBien)
);

CREATE TABLE IF NOT EXISTS qd5277.QLCL_ATTP (
    Ma_CoSoCheBien VARCHAR(10) PRIMARY KEY REFERENCES qd5277.DM_CoSo(Ma_CoSo),
    Ma_TieuChuanChatLuong VARCHAR(10) REFERENCES qd5277.DM_TieuChuanChatLuong(Ma_TieuChuanChatLuong),
    Ma_ThoiGian VARCHAR(10) REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    NgayKiemTra DATE,
    KetQuaKiemTra VARCHAR(100),
    SoLanViPham INTEGER,
    NgayKiemTraGanNhat DATE,
    CoQuanKiemTra VARCHAR(255),
    GhiChu VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS qd5277.QLCL_SanXuatHuuCo (
    Ma_SanXuatHuuCo INTEGER PRIMARY KEY,
    Ma_DonViHanhChinh VARCHAR(10) REFERENCES qd5277.DM_DonViHanhChinh(Ma_DonViHanhChinh),
    Ma_ThoiGian VARCHAR(10) REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    Ma_TieuChuanHuuCo VARCHAR(50) REFERENCES qd5277.DM_TieuChuanHuuCo(Ma_TieuChuanHuuCo),
    DienTichHuuCo NUMERIC(12,2),
    SanLuongHuuCo NUMERIC(12,2),
    ToChucChungNhan VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5277.TT_ThiTruongGiaCa (
    Ma_SanPham VARCHAR(10) REFERENCES qd5277.DM_SanPham(Ma_SanPham),
    Ma_ThoiGian VARCHAR(10) REFERENCES qd5277.DM_KhoangThoiGian(Ma_ThoiGian),
    TenSanPham VARCHAR(255),
    LoaiGia VARCHAR(50),
    GiaBinhQuan NUMERIC(12,2),
    SanLuongTieuThu NUMERIC(12,2),
    DiaDiem VARCHAR(50),
    PRIMARY KEY (Ma_SanPham, Ma_ThoiGian)
);

-- QD 5277 metadata tables. String without a declared size is normalized to VARCHAR(255).
CREATE TABLE IF NOT EXISTS qd5277.DM_SieuDuLieu (
    sieuDuLieuID VARCHAR(255) PRIMARY KEY,
    loaiCapDoSDL VARCHAR(255),
    loaiDuLieu VARCHAR(255),
    loaiSieuDuLieu VARCHAR(255),
    ngonNgu VARCHAR(255),
    phamVi VARCHAR(255),
    phienBan VARCHAR(255),
    sieuDuLieuIDGoc VARCHAR(255),
    tenChuan VARCHAR(255),
    thoiGianLap DATE
);

CREATE TABLE IF NOT EXISTS qd5277.DM_DonVi (
    sieuDuLieuDVID VARCHAR(255) PRIMARY KEY,
    chucVu VARCHAR(255),
    diaChiLienHe VARCHAR(255),
    dienThoai VARCHAR(255),
    chiDanLienHe VARCHAR(255),
    eMail VARCHAR(255),
    loaiDonVi VARCHAR(255),
    moTa VARCHAR(255),
    nguoiDaiDien VARCHAR(255),
    soGiayPhep VARCHAR(255),
    tenDonVi VARCHAR(255),
    thongTinLienHe VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS qd5277.DM_ThuocTinh (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    dinhDangDuLieu VARCHAR(255),
    moTa VARCHAR(255),
    nguonGocDuLieu VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5277.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDoiTuong INTEGER,
    thoiDiemHinhThanh DATE
);

CREATE TABLE IF NOT EXISTS qd5277.DM_PhiCauTruc (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    dinhDangDuLieu VARCHAR(255),
    moTa VARCHAR(255),
    nguonGocDuLieu VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5277.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDoiTuong INTEGER,
    thoiDiemHinhThanh DATE
);

CREATE TABLE IF NOT EXISTS qd5277.DM_ChatLuongDuLieu (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    ghiChu VARCHAR(255),
    ketQuaDanhGia VARCHAR(255),
    loaiDuLieu VARCHAR(255),
    mucDoDanhGia VARCHAR(255),
    muaDoDayDuTT VARCHAR(255),
    phuongPhapDGCL VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5277.DM_SieuDuLieu(sieuDuLieuID),
    soLuongDanhGia INTEGER,
    thoiDiemDanhGia DATE
);

CREATE TABLE IF NOT EXISTS qd5277.DM_PhuongThucChiaSe (
    maDoiTuongID VARCHAR(255) PRIMARY KEY,
    chiTietPhanPhoi VARCHAR(255),
    dinhDangPhanPhoi VARCHAR(255),
    ghiChu VARCHAR(255),
    hinhThucPhanPhoi VARCHAR(255),
    loaiDuLieuID VARCHAR(255),
    phienBan VARCHAR(255),
    sieuDuLieuID VARCHAR(255) REFERENCES qd5277.DM_SieuDuLieu(sieuDuLieuID),
    tenTaiLieu VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS staging.diem_nghiep_2026_w34_raw (
    source_sheet VARCHAR(255) NOT NULL,
    excel_row INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    source_workbook VARCHAR(255) NOT NULL,
    a_raw TEXT, a_cached TEXT, b_raw TEXT, b_cached TEXT,
    c_raw TEXT, c_cached TEXT, d_raw TEXT, d_cached TEXT,
    e_raw TEXT, e_cached TEXT, f_raw TEXT, f_cached TEXT,
    g_raw TEXT, g_cached TEXT, h_raw TEXT, h_cached TEXT,
    i_raw TEXT, i_cached TEXT, j_raw TEXT, j_cached TEXT,
    k_raw TEXT, k_cached TEXT, l_raw TEXT, l_cached TEXT,
    m_raw TEXT, m_cached TEXT, n_raw TEXT, n_cached TEXT,
    o_raw TEXT, o_cached TEXT, p_raw TEXT, p_cached TEXT,
    q_raw TEXT, q_cached TEXT, r_raw TEXT, r_cached TEXT,
    s_raw TEXT, s_cached TEXT, t_raw TEXT, t_cached TEXT,
    u_raw TEXT, u_cached TEXT, v_raw TEXT, v_cached TEXT,
    w_raw TEXT, w_cached TEXT, x_raw TEXT, x_cached TEXT,
    y_raw TEXT, y_cached TEXT, z_raw TEXT, z_cached TEXT,
    aa_raw TEXT, aa_cached TEXT, ab_raw TEXT, ab_cached TEXT,
    value_kinds JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_sheet, excel_row)
);

COMMIT;

