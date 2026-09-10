# Sidebar, chuyên viên và migration — 10/09/2026

Nền triển khai: `main` tại `86e134c`. Nhánh `feature/ui-role-account-postgres-fix`.
Giữ custom Python HTTP server, SQLite/PostgreSQL compatibility và OCOP 2.
Không chạy migration trên database chính hoặc bản SQLite 8081 đang sử dụng.

## Thay đổi

- `permissions.py`, `server.py`, `ocop_services.py`, `ocop_pages.py`: quyền nghiệp vụ chung cho admin/staff; `/users` và `/ocop/access` chỉ admin ở cả GET/POST. Header và form hiển thị đủ ba vai trò.
- `repositories.py`: tìm username không lọc active; mật khẩu được kiểm tra trước thông báo ngưng hoạt động. Kích hoạt chỉ đổi active; ngưng kích hoạt và sửa tài khoản thu hồi phiên. Chặn tự ngưng kích hoạt/hạ quyền/xóa.
- `server.py`, `assets/app.css`, `assets/app.js`: hai nhóm menu mở độc lập, tự mở nhóm hiện tại, giữ active, dùng details/summary hỗ trợ bàn phím; footer hai dòng căn giữa, giữ sidebar nhỏ và mobile.
- `salt_normalization.py`: mapping phương pháp dùng chung; UPSERT khóa đơn vị/kỳ/phương pháp, loại dòng rỗng. Web dùng báo cáo lũy kế đã duyệt mới nhất của tháng.
- `database/etl/import_diem_nghiep.py`, `mappings.py`, `validation/validate_import.py`: D/G/T cho muối đất, E/H/U cho trải bạt; giữ staging và cập nhật UPSERT. Không phân bổ tổng C/F khi chi tiết nguồn không khớp.
- `database/migration/migrate_sqlite_to_postgres.py`: nguồn mode=ro và snapshot nhất quán; chuyển các danh mục, users/credentials, scope, tiêu chí/cây/lựa chọn, chủ thể/sản phẩm/hồ sơ/review, records/audit. Giữ ID, criteria_set_id, revision, snapshot và audit metadata. Chỉ đọc bảng tồn tại; không tạo đối tượng giả hoặc ghi PTNT_OCOP.
- `backend_db.py`: dependency PostgreSQL optional; giao dịch compatibility khởi động khi ghi như SQLite, tránh mất thay đổi OCOP sau các truy vấn đọc. Snapshot hỗ trợ DATE/Decimal PostgreSQL.
- Launcher SQLite chạy migration role có backup trước OCOP migration.
- Tests: `test_roles_accounts.py`, `test_postgres_backend.py`, cập nhật kỳ vọng tách phương pháp trong `test_integration.py`; workflow `.github/workflows/tests.yml`.

## Migration và triển khai

### PostgreSQL

Dừng ghi nghiệp vụ, sao lưu database bằng `pg_dump` theo quy trình của đơn vị.
Sau các schema migration hiện có đến 008, áp dụng:

```text
psql -v ON_ERROR_STOP=1 <thong-tin-ket-noi> -f database/sql/009_staff_role.sql
python database/migration/migrate_sqlite_to_postgres.py --source <nguon.db> --dry-run
python database/migration/migrate_sqlite_to_postgres.py --source <nguon.db>
```

009 chỉ đổi CHECK role, ghi marker `app_007_staff_role`, không dựng lại bảng users.
Migration dữ liệu ghi marker `app_008_sqlite_ocop_data`, giữ nguồn SQLite, có transaction/khóa chống ghi đồng thời.
Chạy lại cập nhật cùng khóa, không nhân bản. Cây tiêu chí được chuyển cha trước con.
ID trùng nhưng khác định danh (ví dụ mã bộ tiêu chí/username) hoặc cột nguồn chưa có mapping sẽ báo lỗi và rollback; không tự remap ID hay ghi đè đối tượng khác.

Nếu chỉ sửa muối đã chuyển trước đó, dùng `--repair-salt-only --dry-run`, kiểm tra rồi chạy lại bỏ `--dry-run`.
Lệnh này chỉ tái tính các tháng có báo cáo lũy kế đã duyệt, không sửa raw records/staging.

### SQLite TEST

Đóng server TEST trước khi nâng cấp cấu trúc; mở `START_OCOP_TEST_WINDOWS.bat`.
Hoặc chạy `python migrate_roles.py --db <database_TEST.db>` rồi migration OCOP hiện có.
`migrate_roles.py` tạo backup `.before-staff-<timestamp>.bak` khi cần sửa CHECK.
SQLite không hỗ trợ ALTER CHECK: dùng quy trình thay bảng trong transaction của SQLite,
giữ nguyên DDL/cột/ID/index/trigger/sequence, kiểm tra FK/integrity trước khi commit.
Chạy lần hai không thay dữ liệu. Không dùng writable_schema.
Tham khảo: https://www.sqlite.org/lang_altertable.html

### Giá bán và rollback

Giá đơn rõ ràng (ví dụ `1.200` hoặc `1200,50`) lưu riêng từng phương pháp.
Khoảng giá/chuỗi không rõ không lấy trung bình: PostgreSQL lưu NULL, SQLite dùng 0 vì cột cũ NOT NULL.
Giá nguồn vẫn được giữ nguyên; 0 này không khẳng định giá thực bằng 0.
Dòng rỗng/toàn 0 bị bỏ; dòng có giá nhưng chưa có diện tích/sản lượng vẫn được giữ.

Nếu migration lỗi: rollback transaction. Dry-run rollback cả việc chuyển dữ liệu; sequence có thể có khoảng trống do quy tắc PostgreSQL, không ảnh hưởng ID/FK.
Sau commit, rollback vận hành bằng bản sao lưu PostgreSQL/SQLite và phiên bản code tương ứng.
Giữ code hỗ trợ staff nếu database đã có staff; không ép role mới về unit hoặc xóa tài khoản để chạy code cũ.

## Kiểm thử

```text
SALT_WEB_BACKEND=sqlite python -B -m unittest discover -s tests -v
```

PostgreSQL: đặt `OCOP_TEST_PG_DSN` tới kết nối bảo trì có quyền CREATEDB, rồi chạy cùng bộ test.
Mỗi test tạo database tên ngẫu nhiên `ocop_test_*`, áp dụng schema, kiểm thử và xóa riêng database vừa tạo.
Không sử dụng cấu hình database vận hành hoặc giả định số tài khoản/báo cáo thật.
Workflow GitHub Actions cung cấp PostgreSQL 17 riêng và một job SQLite không cài psycopg/dotenv.

Kết quả cuối cùng và trạng thái CI được cập nhật trước khi bàn giao PR.
PostgreSQL portable trên Windows hiện bị Smart App Control chặn libssl/libcrypto; không thay đổi chính sách bảo vệ của máy.

## Giới hạn

- Chưa triển khai production, chưa migrate dữ liệu thật. Sao lưu và bảo trì là bắt buộc trước chuyển dữ liệu.
- Migration cập nhật các bản ghi có cùng ID/định danh từ snapshot nguồn; không phải công cụ hòa giải hai database đã phát triển độc lập.
- PostgreSQL và SQLite vẫn dùng cơ chế session RAM hiện có. Việc thu hồi phiên áp dụng tiến trình hiện tại, đồng thời mỗi request kiểm tra lại active/role/hash từ DB.
- Không bổ sung chấm điểm Hội đồng/chứng nhận ngoài OCOP 2.
