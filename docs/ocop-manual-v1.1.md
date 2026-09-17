# Nhập trực tiếp OCOP v1.1

Tại **OCOP → Nhập dữ liệu trực tiếp** (`/ocop/manual`), quản trị hoặc chuyên viên
chọn chủ thể, địa bàn đang hoạt động, nhóm sản phẩm và nhập một hoặc nhiều lần
công nhận. Tài khoản xã/phường cũ không có quyền sử dụng route hoặc service lưu.

Nếu sản phẩm đã tồn tại trong cùng chủ thể và địa bàn, hệ thống yêu cầu chọn
**Xem sản phẩm**, **Thêm lần công nhận**, hoặc **Hủy**. Nếu đã có nhiều chủ thể
trùng tên, phải chọn một chủ thể rõ ràng; không ghép gần đúng. Thông tin liên hệ
của chủ thể được sử dụng lại không bị thay thế bởi biểu mẫu nhập sản phẩm mới.

`ocop_registry.publish` là đường ghi chung cho Excel và nhập trực tiếp. Service
kiểm tra payload, xác thực địa bàn trong transaction, tìm chủ thể/sản phẩm theo
tên đã chuẩn hóa và mã địa bàn, lưu công nhận, chọn công nhận hiện hành, cập nhật
`current_star` và đồng bộ `qd5277.PTNT_OCOP`. Khóa transaction theo địa bàn bảo vệ
các lần lưu đồng thời từ hai nguồn.

Lần công nhận hiện hành được chọn theo năm, ngày công nhận và thứ tự lần công
nhận. Bổ sung một lần cũ không hạ hạng hiện hành. Số thứ tự mới luôn nối tiếp
lịch sử đã có; không đánh số lại các dòng cũ. Excel vẫn giữ quy tắc cảnh báo
ngày/năm không khớp của dữ liệu lịch sử; dữ liệu nhập tay bị chặn nếu không khớp.

Nhập tay dùng chính `app.ocop_entities`, `app.ocop_products`,
`app.ocop_recognitions`. Các cột `application_id`, `source_batch_id`, `source_row`
của công nhận nhập tay là NULL; không tạo hồ sơ đánh giá hay staging giả.
Không cần migration mới: schema đến 020 hiện có đủ trường và ràng buộc.
Không sửa hoặc đánh số lại hai migration 020 đang có trên nhánh tích hợp.

Nhật ký dùng `app.audit_logs` và `activity_log.write_activity`, lưu người dùng,
vai trò, phòng tại thời điểm thao tác, đối tượng và kết quả. Log thành công cùng
transaction với dữ liệu nghiệp vụ; lỗi ghi nghiệp vụ hoặc audit làm rollback
lần lưu. Log thất bại HTTP được ghi sau rollback với nội dung cố định.

Dữ liệu xuất hiện ngay trong tra cứu, chi tiết, lịch sử, thống kê hết hạn,
phân bố sao và xuất Excel. Phần Diêm nghiệp không thay đổi.

Kiểm thử: `python -B -m unittest discover -s tests -v`. PostgreSQL dùng database
test tạm qua `OCOP_TEST_PG_DSN`; `OCOP_TEST_BROWSER=1` bật kiểm thử Chromium với
Playwright trong CI. Không chạy migration hay test trên database production.
