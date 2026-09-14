# Production schema report — 2026-09-14

## Kết nối

- Host: `10.206.16.19`
- Port: `5432`
- Database: `ocop_db`
- User: `ocop`
- PostgreSQL: `17.6`
- Kết nối: thành công

## Khảo sát trước triển khai

- Database hiện chưa có schema `qd5277`, `qd5333`, `app` hoặc `staging`.
- Không có bảng người dùng hoặc object nghiệp vụ trùng tên cần bảo toàn.
- User có quyền `CREATE` trên database; tạo schema và table thử nghiệm thành công (đã rollback).
- Extension `postgis` có trong danh sách extension khả dụng nhưng user `ocop` chưa có quyền tạo extension.

## Kết luận

Chưa triển khai DDL canonical. Cần quản trị PostgreSQL cấp quyền tạo extension PostGIS (hoặc tạo extension bằng tài khoản quản trị), đồng thời cung cấp/duyệt specification đầy đủ cho 30 bảng `qd5277` và 26 bảng `qd5333` trước khi tạo migration production.

## Backup

Schema-only dump trước triển khai: `database/backups/ocop_db_production_schema_20260914.sql`.
