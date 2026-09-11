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
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -v ON_ERROR_STOP=1 -h localhost -p 5432 -U postgres -d ptnt_qd5277_dev -f sql\013_ocop_excel_import.sql
```

Migration 012 dùng `qd5277.DM_DonViHanhChinh` làm danh mục chung, thêm Xã Tân Nhựt
27595 thuộc TP.HCM 79 nếu mã chưa tồn tại, tạo `app.admin_unit_aliases` và bổ sung
mapping tài khoản còn thiếu khi tên khớp duy nhất. Migration chạy trong transaction,
chạy lại an toàn, không xóa dữ liệu hoặc ghi đè tên/trạng thái/mapping đã có.
Server kiểm tra schema đã nâng cấp; không tự seed danh mục PostgreSQL lúc khởi động.

Sau khi hoàn tất schema, máy chủ có thể tạo role dùng chung cho nhóm bằng
`sql\team_role_setup.sql`. Xem [hướng dẫn kết nối nhóm](../POSTGRESQL_TEAM_GUIDE.md).

Migration 013 bổ sung lớp `app` cho import OCOP (`ocop_import_batches`,
`ocop_import_errors`, `ocop_recognitions`, `admin_unit_code_mapping`). Mã OCOP và
mã xã/phường phát sinh từ Excel đều là mã tạm, không thay đổi cấu trúc `qd5277`.
Sau import, mỗi sản phẩm được đồng bộ một dòng hiện tại vào `qd5277.PTNT_OCOP`.

Trong website, tài khoản Chi cục mở **OCOP → Import dữ liệu OCOP**, chọn workbook
`.xlsx`, kiểm tra preview rồi xác nhận import. **OCOP → Sản phẩm OCOP** cho phép
lọc theo xã/phường và mở chi tiết lịch sử công nhận.

Có thể chạy cùng importer từ dòng lệnh (dùng tài khoản đã có trong `app.users`):

```powershell
.\.venv\Scripts\python.exe etl\import_ocop.py --workbook "D:\TaiLieu\PTNT\CCPTNT OCOP.xlsx" --user-id 1
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
