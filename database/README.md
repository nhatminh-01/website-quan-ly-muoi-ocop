# Database PTNT — production và development

Repository hỗ trợ PostgreSQL production `ocop_db` (17.6) và một database dev
riêng để kiểm thử. Production dùng `.env.production` (tệp secret không commit);
dev dùng `.env`. QĐ 5277 canonical và QĐ 5333 non-spatial được triển khai bằng
các migration đánh số 014–015; bốn bảng hình học QĐ 5333 chờ PostGIS.

## Mã hành chính

Reference canonical của mục 79 — Thành phố Hồ Chí Minh — nằm tại
`database/reference/hcmc_admin_units_2025.csv`, gồm 168 đơn vị cấp xã theo
Quyết định 19/2025/QĐ-TTg: 113 phường, 54 xã và 1 đặc khu. Migration
`021_hcmc_168_admin_units.sql` upsert toàn bộ danh mục, hỗ trợ `dackhu` và giữ
nguyên các dòng lịch sử/TMP thay vì xóa hoặc tự map mã.

Chạy audit read-only và validation sau migration:

```powershell
.\.venv\Scripts\python.exe validation\audit_hcmc_admin_units.py --json
.\.venv\Scripts\python.exe validation\validate_hcmc_admin_units.py
```

Tên sai `Xã An Thời Đông` trong workbook được ánh xạ về `Xã An Thới Đông`
(`27673`), trong khi staging vẫn giữ nguyên giá trị nguồn để truy vết.

## Phần mềm

- Windows 11
- Python 3.14.7 (đạt yêu cầu Python 3.12+)
- PostgreSQL 17.11, cài tại `C:\Program Files\PostgreSQL\17`
- pgAdmin 4 v9.17, đi kèm bộ cài PostgreSQL
- Python packages đã cài: `openpyxl 3.1.5`, `psycopg 3.3.5`, `python-dotenv 1.2.3`

## Database dev (tùy chọn)

- Database: `ptnt_qd5277_dev`
- Schema chuẩn: `qd5277`
- Schema ETL: `staging`
- Schema ứng dụng: `app`
- Sheet: `21.8-Tuan 34`
- Snapshot được giữ trong staging: `2026-08-21`

## Database production

- Database: `ocop_db` trên PostgreSQL 17.6 tại máy chủ được cấp phát.
- Schema: `qd5277` (30 bảng canonical), `qd5333` (22 bảng non-spatial),
  `app` (runtime) và `staging` (raw import).
- Secret kết nối: `database/.env.production`, chỉ lưu cục bộ trên máy được ủy quyền.

## Cài môi trường Python

```powershell
cd <thu-muc-repo>\database
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Điền `PGPASSWORD` trong `.env`; không commit tệp này.

## Start/stop PostgreSQL

Windows service là `postgresql-x64-17`, cấu hình tự khởi động:

```powershell
Get-Service -Name 'postgresql-x64-17'
Start-Service -Name 'postgresql-x64-17'
Stop-Service -Name 'postgresql-x64-17'
```

## Khởi động web bằng một lần bấm

Chạy `START_WINDOWS.bat` ở thư mục gốc repository. Script sẽ kiểm tra service
`postgresql-x64-17`, thử khởi động service nếu đang dừng, áp dụng các migration
ứng dụng chưa có trong `app.schema_migrations`, kiểm tra kết nối rồi mới chạy
`server.py`. Nếu Windows báo thiếu quyền khi start service, mở file bằng
**Run as administrator** hoặc khởi động PostgreSQL thủ công trong Services.

## Kết nối và migration

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d postgres -f sql\001_create_database.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\002_qd5277_schema.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\003_seed_validation_data.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\004_app_schema.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\005_monthly_salt_sync.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\006_official_admin_units.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\007_ocop_init_only.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\008_ocop_dynamic_criteria.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\009_staff_role.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\010_weekly_salt_imports.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -v ON_ERROR_STOP=1 -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\011_weekly_foundation.sql
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -v ON_ERROR_STOP=1 -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\012_admin_units.sql
```

Migration 012 dùng `qd5277.DM_DonViHanhChinh` làm danh mục chung, thêm Xã Tân Nhựt
27595 thuộc TP.HCM 79 nếu mã chưa tồn tại, tạo `app.admin_unit_aliases` và bổ sung
mapping tài khoản còn thiếu khi tên khớp duy nhất. Migration chạy trong transaction,
chạy lại an toàn, không xóa dữ liệu hoặc ghi đè tên/trạng thái/mapping đã có.
Server kiểm tra schema đã nâng cấp; không tự seed danh mục PostgreSQL lúc khởi động.

## Khởi tạo PostgreSQL production

Production dùng PostgreSQL 17.6, database `ocop_db` và cấu hình không commit tại
`database/.env.production`. Tệp này phải có `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, `PGPASSWORD` và tùy chọn `PGSSLMODE`; tuyệt đối không đưa mật khẩu vào
GitHub.

Chỉ chạy bootstrap một lần trên database production mới và đang trống:

```powershell
cd <thu-muc-repo>
database\.venv\Scripts\python.exe database\migration\bootstrap_production.py --env-file database\.env.production
database\.venv\Scripts\python.exe database\validation\validate_production.py --env-file database\.env.production
```

Bootstrap thực hiện tuần tự QĐ 5277 (30 bảng), QĐ 5333 non-spatial (22 bảng),
schema app/staging và index. Script từ chối chạy nếu đã có bảng trong các schema
đích để tránh ghi đè dữ liệu. Các lần sau dùng `migration\apply_pending.py`;
không chạy lại bootstrap.

Bốn bảng hình học QĐ 5333 (`QuyHoachDatLamMuoi`, `VungDatLamMuoi`,
`KhoDuTruMuoi`, `SanPhamOCOP`) đang **PENDING_POSTGIS** vì role ứng dụng chưa
được cấp quyền bật PostGIS. Không dùng TEXT/JSON thay cho Geometry và chưa đoán
SRID. Xem `validation/production_schema_report.md` và `schema_issues.md`.

Production đã có role ứng dụng do DBA cấp (hiện là `ocop`). Không chạy
`team_role_setup.sql` trên `ocop_db` nếu chưa được DBA duyệt; xem
[hướng dẫn kết nối nhóm](../POSTGRESQL_TEAM_GUIDE.md) để cấu hình máy cộng tác viên.

Kết nối thủ công:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev
```

## Import lại Excel

```powershell
.\.venv\Scripts\python.exe etl\import_diem_nghiep.py
```

Đặt workbook nội bộ tại `database\data\CCPTNT Diemnghiep.xlsx` hoặc truyền đường dẫn bằng `--workbook`. Thư mục `database\data` bị Git bỏ qua.

Importer đọc workbook hai lần: `data_only=False` để giữ formula và `data_only=True` để giữ cached calculated value. Staging lưu riêng raw/cached của đủ A:AB và loại giá trị để phân biệt số 0, blank, dấu `-`, formula và date.

Mapping target theo phương pháp (không dùng tổng C/F):

- B → mã/tên chính thức từ `DM_DonViHanhChinh` đang hoạt động (có hỗ trợ alias); kỳ snapshot → `2026-08`.
- D+E → `DienTich`, G+H → `SanLuong` của một record `PhuongPhapSX = 'Truyền thống'`.
- D/G và E/H vẫn giữ riêng trong staging; C/F giữ nguyên để đối chiếu, không thay tổng tính từ chi tiết.
- T/U chỉ giữ ở staging; `GiaBanBinhQuan` để NULL vì source không có một giá bình quân chung đáng tin cậy.
- Bỏ địa bàn rỗng/toàn 0. UPSERT theo đơn vị/kỳ/phương pháp; không xóa staging.

## Chạy validation

```powershell
.\.venv\Scripts\python.exe validation\validate_import.py
```

Script cập nhật `validation/validation_report.md` và `validation/validation_issues.csv`. Exit code 1 nghĩa là đã phát hiện lỗi dữ liệu; không có nghĩa import bị rollback.

## Query kiểm tra

```sql
SELECT *
FROM qd5277.DN_SanLuongMuoi
ORDER BY Ma_DonViHanhChinh;

SELECT COUNT(*) AS records,
       SUM(DienTich) AS tong_dien_tich,
       SUM(SanLuong) AS tong_san_luong
FROM qd5277.DN_SanLuongMuoi;
```

Workbook mẫu có 8 địa bàn; importer tra cứu danh mục DB, không giới hạn danh sách 8 đơn vị.
Validation đối chiếu C với D+E và F với G+H;
raw C/F không bị sửa khi nguồn có sai lệch, target luôn lấy D+E và G+H.

## Import báo cáo tuần trong website

- `app.salt_import_batches` lưu nguồn gốc và kết quả từng đợt import.
- `staging.salt_weekly_import_rows` giữ đủ 28 ô raw/cached để truy vết.
- `app.salt_weekly_records` lưu dữ liệu có hiệu lực cho mỗi xã/tuần, gồm tổng báo cáo và chi tiết hai loại nền.
- `app.v_dn_sanluongmuoi_weekly_qd5277` trả bảy trường tương thích `qd5277.DN_SanLuongMuoi` nhưng chưa xuất bản dữ liệu tuần vào bảng chuẩn chính thức.
- Import gồm hai bước xem trước và xác nhận; dòng lỗi bị chặn, dòng cảnh báo phải được người dùng nhìn thấy trước khi ghi.
- Dashboard đọc dữ liệu có hiệu lực, không đọc lần upload bị skip. So sánh với tuần có dữ liệu gần nhất trước đó, không so hai batch cùng tuần.
- Migration 011 bổ sung tổng tiêu thụ/tồn kho từ raw của batch đang có hiệu lực; chạy lại không ghi đè các giá trị đã lưu. View chuẩn tuần lấy D+E / G+H, một dòng `Truyền thống` cho mỗi xã/tuần.

## Nâng cấp tài khoản và OCOP

Sau migration 008, áp dụng `sql/009_staff_role.sql` với `psql -v ON_ERROR_STOP=1`.
Thực hiện trong thời gian bảo trì và sao lưu PostgreSQL trước khi chạy migration.
