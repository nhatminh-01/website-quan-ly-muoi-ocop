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
