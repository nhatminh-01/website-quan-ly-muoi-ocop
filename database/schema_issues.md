# Các vấn đề và chuẩn hóa kỹ thuật của schema

1. PDF QĐ 5277 có khoảng trắng nội tại trong `Ma_ SanLuongMuoi`, `MA_ OCOP`, `Ma_ TieuChuanChatLuong` và `Ma_ ChiTieuThongKe`. PostgreSQL được chuẩn hóa thành `Ma_SanLuongMuoi`, `MA_OCOP`, `Ma_TieuChuanChatLuong`, `Ma_ChiTieuThongKe` để tạo identifier hợp lệ và nhất quán. Không thay đổi ý nghĩa nghiệp vụ.
2. Nhóm metadata chỉ ghi kiểu `String`/`Chuỗi ký tự`, không quy định độ dài. Chuẩn hóa kỹ thuật thành `VARCHAR(255)`; cần quyết định độ dài chính thức nếu cơ quan quản lý ban hành ràng buộc chi tiết.
3. PDF mô tả mỗi trường “Mã đối tượng” metadata là duy nhất nhưng cột Khóa không được trình bày riêng. Áp dụng PRIMARY KEY lần lượt cho `sieuDuLieuID`, `sieuDuLieuDVID`, và `maDoiTuongID` theo mô tả “xác định duy nhất đối tượng”.
4. `QLCL_ATTP` trong PDF đánh dấu chỉ `Ma_CoSoCheBien` là PK, dù có `Ma_TieuChuanChatLuong` và `Ma_ThoiGian`. Giữ nguyên PK theo QĐ 5277; hệ quả là một cơ sở không thể có nhiều dòng theo tiêu chuẩn/thời gian trong bảng này.
5. `QLCL_ATTP` có cả `NgayKiemTra` và `NgayKiemTraGanNhat`, trong khi mô tả của `NgayKiemTra` cũng ghi “Ngày kiểm tra gần nhất”. Giữ cả hai field, không tự hợp nhất.
6. `DM_ChatLuongDuLieu` dùng tên `muaDoDayDuTT` trong PDF, có khả năng là typo của “mức độ”. Giữ đúng tên `muaDoDayDuTT` theo tài liệu, không sửa âm thầm.
7. PDF có chỗ ở bảng liên quan gọi `PTNT_SanPhamOCOP`, `CS_CoSoCheBien`, `QL_ChatLuong_ATTP`, `TH_SanXuatHuuCo`, nhưng phần cấu trúc chi tiết dùng `PTNT_OCOP`, `QLCL_CoSoCheBien`, `QLCL_ATTP`, `QLCL_SanXuatHuuCo`. Triển khai theo tên ở phần cấu trúc chi tiết và yêu cầu task.
8. Mô tả `PhuongPhapSX` của PDF liệt kê “truyền thống, trải bạt, công nghiệp”, mâu thuẫn business rule đã xác nhận rằng trải bạt là nền kết tinh thuộc phương pháp truyền thống. Lần import này dùng đúng một record/địa bàn với `PhuongPhapSX='Truyền thống'`; chi tiết đất/trải bạt chỉ giữ ở staging.
9. Tổng cột C của source là 1953.8, trong khi tổng D 356.4 cộng tổng E 1597.5 bằng 1953.9. Không sửa source/schema; validation phải báo mismatch ở dữ liệu chi tiết tương ứng.

10. QĐ 5277 có 11 bảng còn thiếu trong migration ban đầu. Migration
    `014_qd5277_full_schema.sql` bổ sung đúng tên và các trường đã đọc được;
    tổng số bảng canonical hiện là 30.
11. Bảng `LN_SanPhamLamNghiep` trong tài liệu lặp tên trường
    `Ma_SanPhamLamNghiep` cho cả khóa bản ghi và mã loại sản phẩm. PostgreSQL
    không cho phép hai cột cùng tên, nên cột mã loại được triển khai vật lý là
    `Ma_LoaiSanPhamLamNghiep` và phải được xác nhận lại khi có đặc tả chính thức.
12. QĐ 5277 không mô tả khóa ngoại cho `Ma_Nganh`, `Ma_DinhDanhLo` và mã
    loại sản phẩm lâm nghiệp; không tạo FK suy diễn sang một danh mục chưa có.
13. QĐ 5333 ghi hai danh mục `DM_PhanLoaiMayThietBiNN` và
    `DM_LoaiHinhNganhNghe` theo dạng mã/giá trị/mô tả nhưng không đặt tên cột
    khóa rõ ràng. Migration dùng khóa số (`maMayThietBi`, `maLoaiHinh`) và
    giữ ghi chú này để cơ quan nghiệp vụ xác nhận.
14. QĐ 5333 có các lỗi chính tả trong tên trường `maLienKetHopTacc` và
    `thoigGianDanhGia`; đã giữ nguyên để bám tài liệu nguồn, không đổi âm thầm.
15. QĐ 5333 liệt kê `maNguonVon` ở `ThiTruongTieuThu` nhưng không định nghĩa
    danh mục nguồn vốn tương ứng; trường được giữ độc lập, không tạo FK giả.
16. Bốn bảng có hình học của QĐ 5333 (`QuyHoachDatLamMuoi`,
    `VungDatLamMuoi`, `KhoDuTruMuoi`, `SanPhamOCOP`) chưa tạo vì role ứng dụng
    chưa có quyền `CREATE EXTENSION postgis`. Trạng thái là
    `PENDING_POSTGIS`; không dùng TEXT/JSON để giả Geometry và chưa đoán SRID.
17. Production dùng `app.ocop_import_batches` như một view tương thích trỏ về
    `staging.ocop_import_batches`, vì importer hiện tại lưu raw import ở staging.
    Đây là compatibility layer, không phải nguồn dữ liệu chuẩn lâu dài.
18. `qd5333.CoSoSanXuat.maSanPham` được tài liệu liên kết tới bảng
    `SanPhamOCOP`, nhưng bảng này thuộc nhóm spatial đang hoãn. Vì vậy FK này
    chưa tạo trong phase non-spatial; sẽ bổ sung cùng migration PostGIS sau khi
    bảng và khóa được DBA xác nhận.
19. DB dev có 116 dòng `app.admin_unit_code_mapping` nhưng cột
    `official_code` hiện đều NULL. Migration production không thể tự suy diễn
    mã chính thức nên không chép các dòng này; cần cơ quan nghiệp vụ bổ sung
    mapping trước khi đưa vào `app.code_mappings`.
