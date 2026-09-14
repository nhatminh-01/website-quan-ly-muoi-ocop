# Production schema report — 2026-09-14

## Kết nối

- Database: `ocop_db`
- User: `ocop`
- PostgreSQL: `17.6`
- Migration markers: `14`

## Kết quả canonical

| Phạm vi | Mong đợi | Thực tế | Trạng thái |
|---|---:|---:|---|
| QĐ 5277 canonical | 30 | 30 | PASS |
| QĐ 5333 non-spatial | 22 | 22 | PASS |
| QĐ 5333 spatial | 4 | 0 | PENDING_POSTGIS |

### QĐ 5277

- PK constraints found: `30`
- Missing: `none`
- Unexpected: `none`

### QĐ 5333 non-spatial

- PK constraints found: `22`
- Missing: `none`
- Unexpected: `none`

## PostGIS

- Available in PostgreSQL catalog: `True`
- Enabled for application role: `False`
- Deferred tables: `QuyHoachDatLamMuoi`, `VungDatLamMuoi`, `KhoDuTruMuoi`, `SanPhamOCOP`
- Status: **PENDING_POSTGIS** (no fake geometry column and no SRID guessed)

## Ràng buộc và dữ liệu đã chuyển

- FK constraints theo schema: `app=32, qd5277=47, qd5333=10, staging=4`
- Indexes theo schema: `app=53, qd5277=42, qd5333=31, staging=8`
- Row count mẫu sau migrate: `app.users=10, app.ocop_entities=404, app.ocop_products=1024, app.ocop_recognitions=1069, app.salt_weekly_records=16, staging.ocop_import_rows=1024, qd5277.dm_donvihanhchinh=114, qd5277.dm_sanpham=2048, qd5277.dm_coso=810, qd5277.ptnt_ocop=1069, app.code_mappings=0`

## Ghi chú

Các khác biệt/typo của QĐ được ghi tại `database/schema_issues.md`.
