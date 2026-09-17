# Audit danh mục hành chính TP Hồ Chí Minh

Ngày chạy: 17/09/2026
Database: `ptnt_qd5277_dev`
Reference: `database/reference/hcmc_admin_units_2025.csv`
Nguồn: Quyết định số 19/2025/QĐ-TTg ngày 30/06/2025, mục 79 trong Phụ lục II.

`current_count` dưới đây là số dòng đang có `Ma_DonViCapTren='79'` trước/sau
migration; không tính thành phố cấp tỉnh mã `79`.

## Before audit

| Trường | Kết quả |
|---|---:|
| Reference rows | 168 |
| Reference phuong / xa / dackhu | 113 / 54 / 1 |
| current_count | 9 |
| canonical_present_count | 113 |
| missing_codes | 55 |
| extra_codes | 0 |
| wrong_name | 0 |
| wrong_level | 1 (`26732`) |
| wrong_parent_code | 104 |
| inactive_canonical_codes | 0 |
| TMP rows vật lý | 116 |

55 mã thiếu là:

`25945, 25951, 25969, 25975, 26713, 26737, 26740, 26758, 26773, 26791, 26800, 26803, 26809, 26824, 26833, 26842, 26848, 26857, 26878, 26884, 26890, 26905, 26911, 26929, 26956, 26968, 26977, 26983, 26995, 27004, 27007, 27043, 27094, 27097, 27139, 27142, 27154, 27169, 27211, 27238, 27259, 27286, 27301, 27343, 27349, 27364, 27367, 27424, 27427, 27439, 27448, 27457, 27478, 27484, 27487`.

Kiểm tra các cột/bảng liên quan cho thấy 0 bản ghi nghiệp vụ trỏ vào
`extra_codes`. 116 mã TMP chỉ được tham chiếu bởi chính bảng danh mục, không
có tham chiếu trong OCOP, muối, mapping tài khoản hoặc staging.

## Migration và xử lý lịch sử

Đã tạo `database/sql/021_hcmc_168_admin_units.sql`. Migration:

- upsert thành phố mã `79` và toàn bộ 168 dòng canonical bằng `ON CONFLICT ... DO UPDATE`;
- cập nhật tên, cấp, parent và trạng thái về reference;
- không delete, không tự map mã ngoài canonical;
- giữ các dòng direct-child ngoài canonical để bảo toàn FK/lịch sử và đặt inactive;
- giữ toàn bộ 116 dòng TMP vật lý, đặt `TinhTrang=FALSE`;
- ghi version `app_021_hcmc_168_admin_units`.

`database/migration/apply_pending.py` đã nhận diện và chạy migration. Chạy lại
script lần thứ hai không replay migration.

## After migration

| Trường | Kết quả |
|---|---:|
| current_count | 168 |
| canonical_present_count | 168 |
| missing_codes | 0 |
| extra_codes | 0 |
| wrong_name / wrong_level / wrong_parent_code | 0 / 0 / 0 |
| inactive_canonical_codes | 0 |
| active phuong / xa / dackhu | 113 / 54 / 1 |
| active TMP | 0 |
| tổng dòng vật lý DM_DonViHanhChinh | 285 |

Kiểm tra cụ thể đạt:

`26732 -> Đặc khu Côn Đảo -> dackhu -> parent 79 -> active TRUE`.

Không có mã trùng vì mã là khóa chính; toàn bộ 168 mã trong reference đều tồn
tại trong `qd5277.DM_DonViHanhChinh` và không có TMP trong current catalog.

## Bảo toàn dữ liệu nghiệp vụ

| Bảng | Before | After |
|---|---:|---:|
| `app.ocop_products` | 1024 | 1024 |
| `app.ocop_recognitions` | 1069 | 1069 |
| `qd5277.ptnt_ocop` | 1069 | 1069 |
| `app.user_admin_units` | 8 | 8 |
| `app.salt_weekly_records` | 16 | 16 |
| `staging.ocop_import_rows` | 1024 | 1024 |
| `staging.salt_weekly_import_rows` | 16 | 16 |
| `qd5277.dn_sanluongmuoi` | 0 | 0 |

Không phải xử lý hoặc sửa FK nào; migration chỉ cập nhật thuộc tính catalog và
trạng thái, không xóa dòng nghiệp vụ, không rewrite mã sản phẩm/báo cáo.

## Test/validation

- `database/validation/audit_hcmc_admin_units.py --json`: audit read-only trước và sau.
- `database/validation/validate_hcmc_admin_units.py`: PASS, tổng 168 và phân bổ đúng.
- `python -B -m unittest discover -s tests -v`: 82 passed, 43 skipped do môi trường local không bật disposable PostgreSQL/browser tests.
- `tests/test_hcmc_admin_units.py`: reference shape, mã Côn Đảo và migration contract đều PASS.
