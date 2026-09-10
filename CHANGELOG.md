# Changelog

Tài liệu này ghi lại các thay đổi đáng chú ý của hệ thống Quản lý muối – OCOP.

## Chưa phát hành — Đồng bộ quy tắc nền sản xuất muối

- Thêm luồng import báo cáo tuần hai bước: xem trước/validation rồi mới xác nhận ghi dữ liệu.
- Thêm bảng đợt import, staging raw, record tuần và view tuần tương thích cấu trúc `DN_SanLuongMuoi`.
- Đổi trang tra cứu tuần sang mô hình một sheet import là một báo cáo; xã/phường là dòng con, không phải record báo cáo độc lập.
- Cho phép chọn sheet đã import và render lại bảng 28 cột theo bố cục Excel, gồm tiêu đề nhóm, tổng cộng, ngày chốt và nguồn file.
- Tối ưu đọc Excel theo một lượt tuần tự; sheet có 1.000 dòng định dạng không còn treo lâu. Nút import hiển thị trạng thái đang kiểm tra sau khi gửi.
- Dashboard đọc sheet tuần theo ngày chốt, cho phép chọn kỳ và hiển thị chênh lệch so với sheet liền trước; không cộng chồng dữ liệu lũy tiến.
- Thay các thẻ trạng thái báo cáo cũ bằng số sheet, số đơn vị, cảnh báo và kỳ so sánh; bảng chi tiết lấy trực tiếp từ dòng con của sheet.
- Tab dữ liệu chuẩn QĐ 5277 được ghi rõ chỉ nhận báo cáo tháng đã duyệt; dữ liệu tuần không tự xuất bản vào bảng tháng.
- Thêm thanh tab Diêm nghiệp trên các màn hình dữ liệu, giúp chuyển trực tiếp giữa dữ liệu báo cáo, tra cứu tuần và import Excel tuần.
- Làm sạch 32 báo cáo app, 33 audit log, 24 dòng muối chuẩn và staging ETL cũ; import sheet `21.8-Tuan 34` gồm 8 đơn vị cho tuần `2026-W34`. Tài khoản, cấu trúc và danh mục QĐ 5277 được giữ nguyên.
- Tạo bản sao lưu trước khi làm sạch tại `DB/backups/before_weekly_2026-W34_20260910.dump` (file backup nằm ngoài repository website).
- Dữ liệu tuần chưa tự ghi vào `qd5277.DN_SanLuongMuoi`; template và quy tắc báo cáo tháng sẽ triển khai riêng.
- Muối nền đất và nền trải bạt cùng được tổng hợp thành một record `PhuongPhapSX = 'Truyền thống'` trong `qd5277.DN_SanLuongMuoi`.
- Chi tiết hai loại nền tiếp tục được giữ trong `app.records` và staging; không thêm cột ngoài cấu trúc QĐ 5277.
- `Công nghiệp` là một giá trị được QĐ 5277 mô tả cho `PhuongPhapSX`, không phải một trường riêng; app chưa thêm đầu vào khi chưa có dữ liệu thực tế.
- `GiaBanBinhQuan` để NULL vì hai giá nguồn theo nền không đủ để suy ra một giá bình quân chung.

## 2026-09-10 — Sidebar, chuyên viên và migration dữ liệu

- Sidebar Diêm nghiệp/OCOP mở đóng độc lập, tự mở nhóm route đang dùng; footer hai dòng căn giữa.
- Vai trò `staff` có quyền nghiệp vụ toàn Chi cục; quản lý tài khoản và phân địa bàn chỉ dành cho `admin`.
- Kích hoạt/ngưng kích hoạt giữ nguyên tài khoản và dữ liệu, thu hồi các phiên hiện có.
- Đăng nhập chỉ thông báo tài khoản ngưng hoạt động khi mật khẩu đúng.
- Bản phát hành này từng tách muối đất (`Truyền thống`) và trải bạt (`Trải bạt`); mục “Chưa phát hành” phía trên thay thế quy tắc đó theo nghiệp vụ đã xác nhận.
- Giá nguồn được giữ ở dữ liệu chi tiết; PostgreSQL chuẩn lưu NULL. SQLite giữ 0 theo ràng buộc NOT NULL hiện có, không hiểu là giá thực bằng 0.
- Migration SQLite → PostgreSQL bổ sung danh mục, OCOP 2, audit metadata, kiểm tra trùng ID, rollback và dry-run. Không ghi PTNT_OCOP.
- Thêm `009_staff_role.sql` và `migrate_roles.py` (SQLite sao lưu trước khi đổi CHECK).
- SQLite TEST không cần psycopg/python-dotenv; kiểm thử PostgreSQL dùng database tạm riêng.
- Chi tiết chạy, rollback và kiểm thử: [UI_ROLE_MIGRATION_REPORT.md](UI_ROLE_MIGRATION_REPORT.md).

## 2026-09-09 — Chuyển backend từ SQLite sang PostgreSQL

### Tổng quan

- Backend vận hành mặc định bằng PostgreSQL 17, database `ptnt_qd5277_dev`.
- Frontend, giao diện, CSS, JavaScript và URL hiện có được giữ nguyên.
- SQLite `salt_management.db` không còn là database vận hành mặc định; file được giữ làm nguồn lịch sử và phương án rollback.
- DDL, migration, ETL, validation và cấu hình mẫu được đóng gói trong thư mục `database` của repository.

### Kiến trúc database

- Giữ schema `qd5277` gồm 19 bảng dữ liệu chuẩn theo cấu trúc đã thống nhất.
- Giữ schema `staging` để lưu dữ liệu thô và giá trị nguồn từ Excel.
- Thêm schema `app` gồm 14 bảng phục vụ tài khoản, báo cáo, audit và workflow OCOP.
- Thêm bảng `app.schema_migrations` để theo dõi các migration đã áp dụng.
- Thêm sequence kỹ thuật cho khóa chính `DN_SanLuongMuoi.Ma_SanLuongMuoi`.
- Thêm unique index theo đơn vị, tháng và phương pháp sản xuất để UPSERT không tạo dòng trùng.

### Tài khoản và đăng nhập

- Hồ sơ tài khoản chuyển sang `app.users`.
- Mật khẩu local được tách khỏi hồ sơ và lưu trong `app.user_credentials`.
- Thêm `app.user_identities` để có thể liên kết VNeID hoặc nhà cung cấp định danh khác trong tương lai.
- Đăng nhập hiện tại vẫn dùng username/password cũ; chưa triển khai đăng nhập VNeID.
- Mật khẩu PostgreSQL chỉ đọc từ `database\.env` hoặc biến `PTNT_DB_ENV_FILE`, không ghi cứng trong source.

### Quy tắc dữ liệu muối

- Mã thời gian chuẩn đổi từ ngày `YYYYMMDD` sang tháng `YYYY-MM`.
- Mỗi đơn vị trong một tháng có một dòng chuẩn với `PhuongPhapSX = 'Truyền thống'`.
- `DienTich` bằng diện tích muối đất cộng diện tích muối trải bạt.
- `SanLuong` bằng sản lượng thu hoạch muối đất cộng sản lượng thu hoạch muối trải bạt.
- Báo cáo nguồn được xác định là số liệu lũy tiến: dòng chuẩn của tháng lấy báo cáo đã duyệt mới nhất, không cộng bốn tuần.
- `GiaBanBinhQuan` để `NULL`; hệ thống không tự suy diễn từ hai trường giá nguồn.
- Import hoặc đồng bộ lại cùng kỳ sử dụng UPSERT, không sinh thêm dòng chuẩn trùng.

### Danh mục hành chính

- Nạp mã Thành phố Hồ Chí Minh `79` và 8 xã/phường chính thức theo Quyết định 19/2025/QĐ-TTg.
- Chuẩn hóa `Xã An Thới Đông` với mã `27673`.
- Alias sai trong nguồn `Xã An Thời Đông` được ánh xạ thành `Xã An Thới Đông`; staging vẫn giữ nguyên giá trị nguồn để truy vết.
- Chuyển 8 dòng dữ liệu ban đầu từ mã `TMP...` sang mã chính thức và xóa toàn bộ mã tạm.
- Import mới từ chối đơn vị chưa có trong danh mục chính thức, không tự sinh mã `TMP`.

### Migration dữ liệu cũ

- Chuyển 10 tài khoản và 10 credential từ SQLite.
- Chuyển 24 báo cáo đã duyệt và 25 audit log.
- Gán mã địa bàn chính thức cho 8 tài khoản xã/phường phù hợp.
- Chuẩn hóa 3 báo cáo có tên `Xã An Thời Đông` thành `Xã An Thới Đông`.
- Tạo 16 dòng tổng hợp lũy tiến cho hai tháng có trong dữ liệu SQLite cũ.
- Script `database\migration\migrate_sqlite_to_postgres.py` có thể chạy lặp mà không nhân đôi dữ liệu.

### OCOP

- Khởi tạo bảng chủ thể, sản phẩm, hồ sơ và lịch sử đánh giá OCOP trong schema `app`.
- Tích hợp OCOP phase 2 từ `origin/main`: thêm danh mục bộ tiêu chí, cây tiêu chí và lựa chọn điểm động.
- Nạp 26 bộ tiêu chí tham chiếu cùng ba mục A/B/C; không seed sản phẩm, chủ thể, hồ sơ hoặc kết quả OCOP.
- Chưa bổ sung tính năng VNeID, chấm điểm chi tiết hoặc chứng nhận.

### Mã nguồn backend

- Thêm `backend_db.py` để đọc cấu hình, kết nối PostgreSQL và cung cấp lớp tương thích cho các handler hiện hữu.
- Thêm `repositories.py` để quản lý truy cập tài khoản và credential.
- Cập nhật `server.py` để mặc định dùng PostgreSQL, chuẩn hóa import và đồng bộ dữ liệu tháng.
- Cập nhật `ocop_services.py` để đọc được kiểu row và lỗi transaction của PostgreSQL.
- Cập nhật `START_WINDOWS.bat` để ưu tiên môi trường Python tại `database\.venv`.
- Cập nhật README với hướng dẫn kết nối, migration và vận hành mới.

### Migration database đã áp dụng

1. `004_app_schema.sql` — tạo schema và bảng ứng dụng.
2. `005_monthly_salt_sync.sql` — bổ sung sequence và cơ chế khóa dòng chuẩn theo tháng.
3. `006_official_admin_units.sql` — nạp mã hành chính chính thức và loại bỏ mã tạm.
4. `007_ocop_init_only.sql` — xác nhận cấu trúc OCOP ở trạng thái init-only.
5. `008_ocop_dynamic_criteria.sql` — đồng bộ cấu trúc và danh mục tiêu chí động của OCOP phase 2.
6. `migrate_sqlite_to_postgres.py` — chuyển dữ liệu nghiệp vụ SQLite cũ.

### Kiểm thử và xác nhận

- 31/31 automated tests đạt sau khi tích hợp OCOP phase 2 từ nhánh chính.
- Smoke test đăng nhập và truy cập `dashboard`, báo cáo, dữ liệu chuẩn, tài khoản, OCOP đều trả HTTP 200.
- Database sau migration: 10 users, 10 credentials, 24 báo cáo và 25 audit log.
- `DN_SanLuongMuoi` có 24 dòng cho ba tháng; không có khóa tháng bị trùng và không còn mã `TMP`.
- Các bảng workflow OCOP có 0 dòng, đúng yêu cầu init-only.
- Validation workbook vẫn ghi nhận 2 lỗi có sẵn trong dữ liệu nguồn; hệ thống không tự sửa giá trị raw trong staging.

### Cách chạy sau cập nhật

Chạy `START_WINDOWS.bat` trong thư mục source. Backend sẽ kết nối PostgreSQL bằng cấu hình tại `database\.env`; máy hiện tại vẫn hỗ trợ đường dẫn DB cũ làm fallback.
