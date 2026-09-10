# Diêm nghiệp - kiểm thử CSDL QĐ 5277

Dự án development cục bộ để import thử sheet `21.8-Tuan 34` từ `CCPTNT Diemnghiep.xlsx`. Không triển khai QĐ 5333 hoặc GIS.

## Mã hành chính

Tám địa bàn đã dùng mã chính thức theo Quyết định 19/2025/QĐ-TTg. Tên sai
`Xã An Thời Đông` trong workbook được ánh xạ về `Xã An Thới Đông` (`27673`),
trong khi staging vẫn giữ nguyên giá trị nguồn để truy vết.

## Phần mềm

- Windows 11
- Python 3.14.7 (đạt yêu cầu Python 3.12+)
- PostgreSQL 17.11, cài tại `C:\Program Files\PostgreSQL\17`
- pgAdmin 4 v9.17, đi kèm bộ cài PostgreSQL
- Python packages đã cài: `openpyxl 3.1.5`, `psycopg 3.3.5`, `python-dotenv 1.2.3`

## Database

- Database: `ptnt_qd5277_dev`
- Schema chuẩn: `qd5277`
- Schema ETL: `staging`
- Schema ứng dụng: `app`
- Sheet: `21.8-Tuan 34`
- Snapshot được giữ trong staging: `2026-08-21`

## Cài môi trường Python

```powershell
cd <thu-muc-repo>\database
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config\.env.example .env
```

Điền `PGPASSWORD` trong `.env`; không commit tệp này.

## Start/stop PostgreSQL

Windows service là `postgresql-x64-17`, cấu hình tự khởi động:

```powershell
Get-Service -Name 'postgresql-x64-17'
Start-Service -Name 'postgresql-x64-17'
Stop-Service -Name 'postgresql-x64-17'
```

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
```

Migration dữ liệu website SQLite cũ (chạy lặp an toàn):

```powershell
.\.venv\Scripts\python.exe migration\migrate_sqlite_to_postgres.py
```

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

- B → mã hành chính; kỳ snapshot → `2026-08`.
- D/G/T → diện tích/sản lượng/giá `Truyền thống`.
- E/H/U → diện tích/sản lượng/giá `Trải bạt`.
- Giá đơn rõ ràng được giữ; khoảng giá/giá không rõ → NULL, nguồn vẫn ở staging.
- Bỏ phương pháp rỗng/toàn 0. UPSERT theo đơn vị/kỳ/phương pháp; không xóa staging.

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

Số dòng target phụ thuộc các phương pháp có dữ liệu (tối đa 16 cho 8 địa bàn). Đối chiếu D/E và G/H riêng; không ép tổng chi tiết bằng cột tổng nếu workbook nguồn có sai lệch.

## Nâng cấp tài khoản và chuyển OCOP

Sau migration 008, áp dụng `sql/009_staff_role.sql` với `psql -v ON_ERROR_STOP=1`.
Thực hiện trong thời gian bảo trì và sao lưu PostgreSQL trước khi chuyển dữ liệu.

```powershell
python migration/migrate_sqlite_to_postgres.py --source <nguon_SQLite.db> --dry-run
python migration/migrate_sqlite_to_postgres.py --source <nguon_SQLite.db>
```

Nếu đã chuyển dữ liệu và chỉ cần sửa chuẩn hóa muối:

```powershell
python migration/migrate_sqlite_to_postgres.py --repair-salt-only --dry-run
python migration/migrate_sqlite_to_postgres.py --repair-salt-only
```

Xem [báo cáo triển khai và rollback](../UI_ROLE_MIGRATION_REPORT.md).
