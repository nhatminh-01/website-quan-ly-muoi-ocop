# Website nội bộ quản lý số liệu sản xuất muối

Lịch sử thay đổi hệ thống: [CHANGELOG.md](CHANGELOG.md).

## OCOP giai đoạn 1 — bản kiểm thử

Đã bổ sung quản lý chủ thể, sản phẩm, hồ sơ OCOP và phân quyền theo mã xã/phường,
trên nền Python HTTP Server + PostgreSQL. Chi tiết thay đổi, migration, kiểm thử
và giới hạn: [OCOP1_REPORT.md](OCOP1_REPORT.md).

**Mở `START_OCOP_TEST_WINDOWS.bat`**, sau đó truy cập **http://127.0.0.1:8081/ocop**.
Tệp chạy này dùng riêng `salt_management_TEST.db`, tự kiểm tra migration đã chạy
và không chạy lại chuẩn hóa muối khi khởi động. Tài khoản là các tài khoản trong bản test.
Nếu máy chưa có Python trên PATH, tệp chạy sẽ thử Python có sẵn trong bộ công cụ Codex.

Nếu chưa có database test, tạo bản sao một lần bằng `python prepare_ocop_test.py`.
Lệnh này chỉ đọc database chính, không ghi đè database test đã tồn tại.

`START_WINDOWS.bat` chạy hệ thống Diêm nghiệp với PostgreSQL mặc định. Cấu hình mẫu,
DDL, migration, ETL và validation nằm trong thư mục `database` của repository.

OCOP 1 chưa có chấm điểm, chứng nhận, đồng bộ kết quả chính thức hoặc upload minh chứng.
Hồ sơ hợp lệ chỉ có nghĩa hoàn thành bước kiểm tra hồ sơ, chưa được công nhận hạng sao.

Chạy kiểm thử tự động bằng `python -B -m unittest discover -s tests -v`.
Các bài kiểm thử tạo database tạm riêng, không sửa dữ liệu trong hai database của người dùng.

## Phạm vi đã xây dựng

Hệ thống bám theo bảng Excel mẫu gồm:

- Diện tích sản xuất muối: Cộng, Muối đất, Muối trải bạt.
- Sản lượng muối thu hoạch: Cộng, Muối đất, Muối trải bạt.
- Sản lượng muối tiêu thụ: Cộng, Muối đất, Muối trải bạt.
- Sản lượng còn lại: Cộng, Muối đất, Muối trải bạt.
- Sản lượng muối chế biến: Cộng, Muối tinh, Muối I-ốt.
- Số hộ làm muối.
- Số lao động làm muối.
- Giá bán: Muối đất, Muối trải bạt.
- Năng suất bình quân.
- Thiệt hại do mưa trái mùa: Cộng, Muối đất, Muối trải bạt.

Các cột **Cộng** và **Năng suất bình quân** được tính tự động để hạn chế sai số cộng tay.

## Luồng nghiệp vụ

1. Xã/phường đăng nhập tài khoản riêng.
2. Nhập và lưu bản nháp số liệu theo ngày/kỳ chốt.
3. Đơn vị bấm **Gửi Chi cục**.
4. Chi cục Phát triển nông thôn xem số liệu của tất cả đơn vị.
5. Chi cục chọn **Duyệt** hoặc **Trả chỉnh sửa** và ghi ý kiến.
6. Số liệu đã duyệt được đưa lên Dashboard tổng hợp.
7. Có thể tra cứu theo đơn vị, trạng thái, thời gian và xuất Excel.
8. Hệ thống lưu nhật ký các lần tạo, sửa, gửi, duyệt, trả chỉnh sửa.

## Chạy trên Windows

1. Cài PostgreSQL và chuẩn bị môi trường theo `database\README.md`.
2. Sao chép `database\config\.env.example` thành `database\.env`, rồi điền thông tin kết nối.
3. Chạy website:

```bat
START_WINDOWS.bat
```

4. Trên máy chủ mở:

```text
http://127.0.0.1:8080
```

5. Các máy cùng mạng LAN mở:

```text
http://IP-MAY-CHU:8080
```

Ví dụ máy chủ có IP `192.168.1.20` thì các xã/phường truy cập `http://192.168.1.20:8080`.

> Có thể cần cho phép cổng TCP 8080 trong Windows Firewall.

## Tài khoản demo

- Chi cục: `chicuc` / `123456`
- Xã An Thới Đông: `an_thoi_dong` / `123456`
- Xã Thạnh An: `thanh_an` / `123456`
- Xã Cần Giờ: `can_gio` / `123456`
- Xã Long Điền: `long_dien` / `123456`
- Xã Long Sơn: `long_son` / `123456`
- Phường Phước Thắng: `phuoc_thang` / `123456`
- Phường Long Hương: `long_huong` / `123456`
- Phường Bà Rịa: `ba_ria` / `123456`

**Đổi toàn bộ mật khẩu trước khi dùng thật.**

## Dữ liệu lưu ở đâu?

Dữ liệu vận hành nằm trong PostgreSQL database `ptnt_qd5277_dev`: schema `app`
cho nghiệp vụ website, `qd5277` cho dữ liệu chuẩn và `staging` cho dữ liệu nhập thô.
File `salt_management.db` chỉ còn là nguồn lịch sử/rollback; không phải database mặc định.

Mật khẩu PostgreSQL chỉ lưu trong `database\.env`, không ghi cứng hoặc commit vào source.
Nên sao lưu PostgreSQL định kỳ trước khi đưa vào vận hành chính thức.

## Lưu ý trước khi đưa vào vận hành thật

Bản này là **MVP/prototype chạy được**, phù hợp để trình diễn và thử quy trình nội bộ. Khi triển khai chính thức nên bổ sung:

- HTTPS hoặc truy cập qua VPN/mạng nội bộ được kiểm soát.
- Sao lưu tự động, nhật ký hệ thống và giám sát.
- Chính sách mật khẩu mạnh, khóa tài khoản, thời gian hết phiên.
- Phân quyền chi tiết hơn nếu có nhiều cấp quản lý.
- Kiểm thử bảo mật, kiểm thử tải và quy trình vận hành.
- Nếu số người dùng và dữ liệu lớn: chuyển SQLite sang PostgreSQL/SQL Server.
- Tích hợp đăng nhập tập trung nếu đơn vị đã có hệ thống tài khoản dùng chung.

## Các bước nâng cấp tiếp theo gợi ý

- Import trực tiếp file Excel hiện hữu đã được hỗ trợ cho tài khoản Chi cục.
- Biểu đồ theo tháng/quý/năm.
- So sánh kỳ này với kỳ trước.
- Cảnh báo bất thường: tiêu thụ > thu hoạch, còn lại âm, năng suất tăng/giảm đột biến.
- Nhắc đơn vị chưa gửi báo cáo.
- Xuất báo cáo đúng biểu mẫu hành chính của Chi cục.
- API chia sẻ dữ liệu sang hệ thống khác.
