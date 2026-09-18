# Tài khoản xã/phường lưu lịch sử — v1.2

Hệ thống chỉ sử dụng tài khoản nội bộ có vai trò `admin` và `staff`. Tài khoản
`unit` hoặc `legacy` là danh tính lịch sử, không được đăng nhập, kích hoạt lại,
đổi vai trò hoặc đổi đơn vị để sử dụng lại. Danh sách tài khoản mặc định chỉ
hiển thị tài khoản nội bộ; bộ lọc tài khoản cũ cho phép đối chiếu lịch sử.

## Migration 022

`database/sql/022_archive_legacy_users.sql` chạy trong một transaction và có thể
chạy lại an toàn. Migration chỉ chuyển `app.users.active` của tài khoản cũ về
`FALSE`; không đổi mã người dùng, tên đăng nhập, vai trò, đơn vị hoặc thời điểm
tạo. Không xóa tài khoản, thông tin xác thực, hồ sơ cá nhân, ánh xạ địa bàn,
báo cáo hay nhật ký.

Migration bổ sung trigger `users_protect_archived_identity` để:

- Buộc tài khoản `unit`/`legacy` mới được nạp vào database ở trạng thái ngừng hoạt động.
- Chặn kích hoạt lại tài khoản cũ và thay đổi `id`, `username`, `role` của tài khoản đó.
- Chặn đổi tên đơn vị tùy ý; chỉ cho đồng bộ tên chính thức từ danh mục theo đúng mã địa bàn đã được ánh xạ.
- Chặn xóa vật lý tài khoản cũ, kể cả tài khoản chưa có dữ liệu tham chiếu.

Khi quản trị viên sửa tên chính thức của một đơn vị hành chính, logic danh mục hiện có vẫn được phép đồng bộ tên đó cho tài khoản cũ đang ánh xạ đúng mã đơn vị. Đây không phải đổi địa bàn: migration không thay đổi `user_admin_units`, và tài khoản vẫn ngừng hoạt động. Backend quản lý tài khoản vẫn chặn sửa tài khoản cũ.

Trigger không thay đổi tài khoản nội bộ `admin`/`staff`. Ràng buộc các giá trị
vai trò hiện có được giữ nguyên: migration không mở thêm khả năng tạo vai trò
`legacy` nếu database hiện không cho phép giá trị đó.

Các khóa ngoại và giá trị lịch sử được giữ nguyên, bao gồm
`records.created_by`, `audit_logs.user_id`, `user_admin_units`, các trường
`created_by`/`reviewer_id` của OCOP và những bảng khác đang tham chiếu `users.id`.
Không có thay đổi nghiệp vụ Diêm nghiệp, OCOP hoặc danh mục 168 đơn vị hành chính.

## Áp dụng và đối chiếu số lượng

`apply_pending.py` nhận diện migration qua marker
`app_022_archive_legacy_users`; bootstrap database mới cũng có migration 022
trong danh sách. Khi chỉ cần áp dụng đúng thay đổi này vào một database đã có
schema ứng dụng, dùng `psql` của môi trường tương ứng và chạy riêng file
`database/sql/022_archive_legacy_users.sql` với `ON_ERROR_STOP=1`.
Không cần chạy lại bootstrap hay các migration cũ.

Trước khi áp dụng, ghi nhận số tài khoản sắp được ngừng:

```sql
SELECT COUNT(*) AS legacy_to_deactivate
FROM app.users
WHERE role IN ('unit', 'legacy') AND active IS DISTINCT FROM FALSE;
```

Migration in thông báo `Legacy commune/ward accounts deactivated: N` với số
bản ghi thực sự thay đổi trong lần chạy đó. Chạy lại khi dữ liệu đã đúng trả về
`0`; số này khác tổng số tài khoản lịch sử đang được giữ lại.

Sau khi áp dụng, đối chiếu:

```sql
SELECT role, active, COUNT(*) AS account_count
FROM app.users
GROUP BY role, active
ORDER BY role, active;

SELECT COUNT(*) AS legacy_still_active
FROM app.users
WHERE role IN ('unit', 'legacy') AND active IS DISTINCT FROM FALSE;
```

`legacy_still_active` phải bằng `0`. Số tài khoản đã ngừng trên database thực tế
phải được báo từ lần chạy migration thực tế; kết quả từ database kiểm thử không
được dùng thay cho số liệu này.
