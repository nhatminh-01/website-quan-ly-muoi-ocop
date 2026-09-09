# Báo cáo triển khai OCOP - Giai đoạn 2

## 1. Mục tiêu

Giai đoạn 2 xây dựng **danh mục và cấu trúc bộ tiêu chí OCOP dạng dữ liệu động**. Mục tiêu là khi bổ sung tiêu chí chi tiết/chấm điểm, hệ thống đọc cấu trúc từ cơ sở dữ liệu thay vì viết 26 biểu mẫu HTML/Python riêng.

Căn cứ nghiệp vụ cho danh mục là Quyết định số **26/2026/QĐ-TTg ngày 22/05/2026**. Phụ lục I phân loại 06 nhóm sản phẩm; Phụ lục II liệt kê 26 bộ sản phẩm. Khung điểm chung đang được lưu cho mỗi bộ: Phần A 40 điểm, Phần B 25 điểm, Phần C 35 điểm, tổng 100 điểm.

> Các mã `QD26-01` đến `QD26-26` và phiên bản dữ liệu `2026.1` là mã quản trị **nội bộ của phần mềm**, không phải mã pháp lý do Quyết định 26 quy định.

## 2. Migration mới

Migration mới: `ocop_002_dynamic_criteria`.

Migration vẫn chạy qua `migrate_ocop.py` và chỉ cho phép tệp `*_TEST.db`. `START_OCOP_TEST_WINDOWS.bat` tự chạy migration trước khi mở server TEST tại cổng 8081.

Migration là cộng thêm và có thể chạy lặp lại an toàn:

- Giữ nguyên `ocop_001_foundation`.
- Tạo `ocop_criteria_sets` - danh mục 26 bộ tiêu chí.
- Tạo `ocop_criteria` - cây mục/nhóm/tiêu chí động, có `parent_id`.
- Tạo `ocop_criteria_options` - các lựa chọn điểm cho tiêu chí chi tiết ở giai đoạn chấm điểm.
- Thêm `criteria_set_id` nullable vào `ocop_products`.
- Thêm `criteria_set_id` nullable vào `ocop_applications`.
- Không tự đoán/bổ sung bộ tiêu chí cho dữ liệu OCOP cũ. Bản ghi cũ giữ `NULL` đến khi người dùng chọn đúng bộ tiêu chí.
- Không ghi dữ liệu vào `PTNT_OCOP`.

## 3. Danh mục 26 bộ tiêu chí

Hệ thống đã nạp 26 bộ theo thứ tự Phụ lục II, từ rau/củ/quả/hạt tươi đến dịch vụ du lịch cộng đồng, du lịch sinh thái và điểm du lịch. Mỗi bộ lưu thêm phân loại Phụ lục I: nhóm sản phẩm lớn, nhóm và phân nhóm.

Mỗi bộ hiện có 03 node cấp cao:

- A - Sản phẩm và sức mạnh của cộng đồng: 40 điểm.
- B - Khả năng tiếp thị: 25 điểm.
- C - Chất lượng sản phẩm: 35 điểm.

Tổng điểm mỗi bộ là 100.

**Phạm vi giai đoạn 2:** mới nạp danh mục 26 bộ và khung A/B/C. Các tiêu chí con, lựa chọn điểm, điều kiện loại, yêu cầu minh chứng và chấm điểm từng thành viên Hội đồng chưa được nạp ở giai đoạn này. Cấu trúc bảng đã sẵn sàng để nạp các phần đó ở giai đoạn tiếp theo mà không thay đổi 26 form riêng.

## 4. Giao diện

Đã thêm menu **OCOP > Bộ tiêu chí**:

- `/ocop/criteria`: xem/tra cứu 26 bộ tiêu chí, lọc theo nhóm sản phẩm lớn.
- `/ocop/criteria/{id}`: xem phân loại, căn cứ, phiên bản dữ liệu, hiệu lực và cấu trúc điểm A/B/C.

Trang bộ tiêu chí là **chỉ đọc** trong giai đoạn 2. Không có POST để người dùng sửa dữ liệu pháp lý.

Form **Sản phẩm OCOP** không còn nhập tự do `Nhóm sản phẩm`; thay bằng dropdown chọn 1 trong 26 bộ tiêu chí. Sau khi chọn:

- `criteria_set_id` được lưu trên sản phẩm.
- `product_group`/`DM_SanPham.NhomSanPham` được lấy tự động từ nhóm tương ứng.
- Hồ sơ mới tự kế thừa `criteria_set_id` của sản phẩm.
- Sản phẩm chưa có bộ tiêu chí không thể tạo hồ sơ mới.

Khi hồ sơ gửi lần đầu, snapshot lưu cả thông tin bộ tiêu chí. Hồ sơ đã từng gửi giữ bộ tiêu chí lịch sử, tránh thay đổi kết quả do sản phẩm được chỉnh phân loại về sau.

## 5. Tệp đã thay đổi

- `ocop_db.py`
- `ocop_services.py`
- `ocop_pages.py`
- `server.py`
- `assets/app.css`
- `migrate_ocop.py`
- `tests/test_ocop_migration.py`
- `tests/test_integration.py`
- `README.md`
- `OCOP2_REPORT.md` (mới)

## 6. Kiểm thử

Bộ test hiện có 28 bài và đã chạy đạt 28/28. Test bao gồm:

- migration cộng thêm, rollback và idempotent;
- đúng 26 bộ tiêu chí và 78 node A/B/C;
- mỗi bộ tổng 100 điểm;
- không tự sửa dữ liệu pháp lý nếu seed hiện hữu bị xung đột;
- dữ liệu OCOP cũ được giữ nguyên và chỉ thêm liên kết nullable;
- quyền xem danh mục cho admin/đơn vị;
- sản phẩm bắt buộc chọn bộ tiêu chí;
- hồ sơ kế thừa và snapshot bộ tiêu chí;
- quy trình OCOP giai đoạn 1 vẫn chạy;
- hồi quy toàn bộ nghiệp vụ Diêm nghiệp, import/export và chuẩn hóa muối.

Kiểm tra trực tiếp `salt_management_TEST.db` sau migration:

- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: không có lỗi.
- 26 dòng `ocop_criteria_sets`.
- 78 dòng `ocop_criteria`.
- 0 dòng `ocop_criteria_options` (dành cho tiêu chí chi tiết ở giai đoạn tiếp theo).
- `PTNT_OCOP` vẫn 0 dòng.
- Các bảng Diêm nghiệp và dữ liệu nghiệp vụ cũ không thay đổi.

## 7. Cách chạy TEST

Trên Windows, mở:

```bat
START_OCOP_TEST_WINDOWS.bat
```

Sau đó truy cập:

```text
http://127.0.0.1:8081/ocop/criteria
```

Không chạy migration này vào `salt_management.db` chính. Khi giai đoạn 2 và các bước chấm điểm đã kiểm thử ổn định mới lập kế hoạch chuyển chính thức.

## 8. Giai đoạn tiếp theo

Giai đoạn 3 nên nạp **tiêu chí chi tiết + phương án điểm + điều kiện bắt buộc/loại**, sau đó bổ sung Hội đồng, thành viên Hội đồng, phân công hồ sơ, điểm từng tiêu chí và tổng hợp điểm. Các bảng `ocop_criteria` và `ocop_criteria_options` của giai đoạn 2 là nền để thực hiện mà không hard-code biểu mẫu.
