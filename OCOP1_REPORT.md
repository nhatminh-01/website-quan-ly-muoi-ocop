# Báo cáo triển khai OCOP giai đoạn 1

Ngày hoàn tất kiểm tra: 09/09/2026.

Giai đoạn 1 bổ sung quản lý chủ thể, sản phẩm và hồ sơ OCOP vào website hiện tại.
Giữ Python, SQLite, `ThreadingHTTPServer`, cơ chế đăng nhập dùng chung, CSS/JS hiện có
và các URL Diêm nghiệp. Đây là bản kiểm thử, chưa đưa migration lên database chính.

## 1. Các file đã sửa

| File | Nội dung |
|---|---|
| `server.py` | Menu bốn nhóm; tích hợp route OCOP; cấu hình đường dẫn database/cổng; chế độ khởi động TEST; phân địa bàn OCOP; kiểm tra lại tài khoản/phiên; xét liên kết OCOP khi khóa/xóa tài khoản; thông báo lỗi OCOP an toàn. |
| `assets/app.css` | Bổ sung kiểu hiển thị dưới `.ocop-page` cho tổng quan, biểu mẫu, bảng, phân trang và lịch sử. Giữ nguyên các bộ chọn CSS cũ. |
| `README.md` | Cách mở OCOP TEST, liên kết báo cáo, cập nhật tình trạng import Excel. |

`assets/app.js`, `START_WINDOWS.bat`, các bản `server_*_cu.py`, hình quốc huy và các database backup không được sửa trong triển khai OCOP 1.

## 2. Các file tạo mới

| File | Chức năng |
|---|---|
| `ocop_db.py` | Migration cộng thêm, kiểm tra cấu trúc, ánh xạ địa bàn ban đầu. Không có tác dụng phụ khi import. |
| `ocop_services.py` | Quyền theo mã hành chính, kiểm tra dữ liệu, chuyển trạng thái, giao dịch và nhật ký. |
| `ocop_pages.py` | Giao diện OCOP sử dụng khung trang chung. |
| `prepare_ocop_test.py` | Tạo snapshot bằng SQLite backup từ kết nối nguồn chỉ đọc; từ chối ghi đè bản TEST đã tồn tại. |
| `migrate_ocop.py` | Lệnh migration dành riêng cho tệp `*_TEST.db`; chặn database chính và đường dẫn trỏ cùng tệp. |
| `START_OCOP_TEST_WINDOWS.bat` | Kiểm tra Python, chạy migration an toàn rồi mở server TEST ở cổng 8081. |
| `tests/test_ocop_migration.py` | 14 kiểm thử migration trên SQLite trong bộ nhớ. |
| `tests/test_integration.py` | 9 kiểm thử tích hợp HTTP/nghiệp vụ trên database tạm riêng. |
| `OCOP1_REPORT.md` | Báo cáo và hướng dẫn này. |
| `salt_management_TEST.db` | Bản sao riêng dùng thử; giữ dữ liệu Diêm nghiệp và bổ sung cấu trúc OCOP. |

## 3. Các bảng tạo mới

| Bảng | Vai trò |
|---|---|
| `DM_SanPham` | Danh mục sản phẩm: mã, tên, nhóm, đơn vị tính, trạng thái. |
| `DM_CoSo` | Danh mục cơ sở: mã, tên, loại, địa chỉ, mã hành chính. |
| `ocop_entities` | Thông tin chi tiết chủ thể, liên kết duy nhất với `DM_CoSo`. |
| `ocop_products` | Sản phẩm nghiệp vụ; liên kết hai danh mục và mã hành chính. |
| `ocop_applications` | Hồ sơ, loại đăng ký, năm, trạng thái, phiên bản sửa, bản chụp thông tin khi gửi. |
| `ocop_reviews` | Lịch sử tạo/sửa/gửi/kiểm tra/trả/xác nhận/hủy hồ sơ. |
| `PTNT_OCOP` | Lớp chuẩn chính thức theo cấu trúc yêu cầu; hiện để trống. |
| `user_admin_units` | Gắn tài khoản xã/phường với mã hành chính dùng cho quyền OCOP. |
| `schema_migrations` | Ghi nhận phiên bản migration đã áp dụng. |

Tiếp tục dùng chung `DM_DonViHanhChinh` và `DM_KhoangThoiGian`. Không tạo danh mục địa phương OCOP riêng.
Không tạo thêm bảng `PTNT_SanPhamOCOP`; hiện chưa có nhu cầu VIEW tương thích.

`PTNT_OCOP` có đúng các trường: `MA_OCOP`, `Ma_DonViHanhChinh`, `Ma_ThoiGian`,
`Ma_SanPham`, `TenSanPham`, `XepHang`, `ChuTheSXKD`, `DoanhThuNam`, `TrangThai`.
Hạng chính thức chỉ chấp nhận `3*`, `4*`, `5*`. Doanh thu phải là số không âm, tối đa
12 chữ số phần nguyên và 2 chữ số thập phân; đơn vị triệu đồng. Chưa tự đặt bảng mã
hiệu lực cho `TrangThai` khi tài liệu chỉ mô tả ý nghĩa, chưa quy định bộ mã cụ thể.

## 4. Các cột được thêm

Chỉ thêm ba cột nullable vào bảng cũ `audit_logs`:

- `module TEXT`;
- `object_type TEXT`;
- `object_id TEXT`.

Dòng nhật ký OCOP dùng `module='ocop'`, `record_id=NULL` và định danh đối tượng OCOP.
Không đưa mã hồ sơ vào khóa ngoại `record_id` của báo cáo muối. Các dòng audit cũ và cách ghi audit muối vẫn hoạt động.

Các cột bổ trợ nằm trong bảng mới: `created_by`, `archived_at` cho chủ thể;
`revision`, `submission_snapshot_json` cho hồ sơ. Mỗi lần gửi đều lưu thêm snapshot
trong audit để giữ được thông tin các lần gửi trước.

Không sửa cấu trúc `users`, `records`, `DN_SanLuongMuoi` hoặc hai danh mục cũ.

## 5. Migration đã chạy và bảo toàn dữ liệu

Phiên bản: **`ocop_001_foundation`**.

- Chạy lần đầu trên `salt_management_TEST.db`, sau đó chạy lại: không trùng dữ liệu;
  lần thứ hai không đổi nội dung tệp.
- DDL dùng `CREATE TABLE IF NOT EXISTS`; kiểm tra cấu trúc trước khi dùng bảng đã có.
  Chỉ `ALTER TABLE ADD COLUMN` cho các cột audit còn thiếu.
- SAVEPOINT cho phép rollback cả CREATE/ALTER và dữ liệu nếu bất kỳ bước nào lỗi.
  Giữ quyền commit/rollback của giao dịch ngoài nếu caller đã mở giao dịch.
- Không DROP bảng, không DELETE dữ liệu cũ, không dựng lại `users`, không gọi bootstrap/chuẩn hóa muối trong migration OCOP.
- Tự ánh xạ được 8 tài khoản đơn vị khi tên khớp duy nhất với xã/phường chính thức đang hoạt động.
  Tên không khớp, mã TMP hoặc danh mục trùng tên không được suy đoán.
- Kiểm tra `integrity_check`: `ok`; `foreign_key_check`: không có vi phạm.

Trong lần đối chiếu cuối: hai bản có 10 tài khoản, 24 báo cáo muối, 25 dòng audit cũ,
10 đơn vị hành chính, 3 kỳ thời gian và 39 dòng dữ liệu muối chuẩn. Các dòng tài khoản,
báo cáo, nhật ký, danh mục và toàn bộ giá trị muối theo khóa đơn vị/kỳ/phương pháp khớp nhau.
Mã tự tăng của dòng `DN_SanLuongMuoi` khác giữa hai snapshot; cơ chế chuẩn hóa cũ có
DELETE/INSERT. Migration OCOP đã được kiểm tra riêng là giữ nguyên cả ID của bản TEST tại thời điểm chạy.

Database chính chỉ được mở để đọc/sao lưu/đối chiếu trong công việc này. Không chạy server
hoặc migration với database chính. SHA-256 ghi nhận ở lần kiểm tra cuối:
`20f9bb734a38b282039eddf43ba5408b8cd3ed174468447b039b0caac0f9c7a3`.

Các bảng chủ thể, sản phẩm, hồ sơ và `PTNT_OCOP` trong bản TEST bàn giao đều đang trống.
Các dữ liệu giả phục vụ kiểm thử nằm trong database tạm, không đưa vào bản TEST bàn giao.

## 6. Route mới

| Phương thức | Route | Chức năng |
|---|---|---|
| GET | `/ocop` | Tổng quan, lọc địa bàn/năm hồ sơ. |
| GET | `/ocop/entities`, `/ocop/products`, `/ocop/applications` | Danh sách, tìm kiếm, bộ lọc, phân trang. |
| GET/POST | `/ocop/entities/new`, `/ocop/products/new`, `/ocop/applications/new` | Biểu mẫu và tạo bản ghi. |
| GET | `/ocop/entities/{id}`, `/ocop/products/{id}`, `/ocop/applications/{id}` | Chi tiết. |
| GET/POST | Các route chi tiết thêm `/edit` | Biểu mẫu và cập nhật. |
| POST | `/ocop/entities/{id}/archive`, `/ocop/products/{id}/archive` | Ngừng sử dụng, có kiểm tra liên kết; không xóa cứng. |
| POST | `/ocop/applications/{id}/submit` | Gửi/gửi lại hồ sơ. |
| POST | `/ocop/applications/{id}/start-review` | Bắt đầu kiểm tra. |
| POST | `/ocop/applications/{id}/return` | Trả bổ sung, bắt buộc lý do. |
| POST | `/ocop/applications/{id}/eligible` | Xác nhận hồ sơ hợp lệ. |
| POST | `/ocop/applications/{id}/cancel` | Hủy theo quyền và trạng thái; giữ lịch sử. |
| GET/POST | `/ocop/access` | Chi cục phân địa bàn OCOP cho tài khoản. |

Các route ghi dữ liệu đều kiểm tra đăng nhập, CSRF, quyền tại server và trạng thái/phiên bản.
Form OCOP bị giới hạn 256 KiB trước khi đọc body; chưa nhận multipart/upload.
Danh sách và các lựa chọn trong biểu mẫu đều giới hạn theo địa bàn của người dùng.

## 7. Phân quyền

Giữ hai vai trò `admin` và `unit` trong giai đoạn 1. Chưa thêm `council`, vì bảng `users`
hiện có CHECK chỉ nhận hai vai trò này; việc phân quyền Hội đồng thuộc giai đoạn 3.

- **Chi cục:** xem toàn bộ dữ liệu OCOP, CRUD nền, kiểm tra/trả/xác nhận hồ sơ,
  hủy theo trạng thái và phân địa bàn tài khoản.
- **Xã/phường:** chỉ xem và thao tác trong mã hành chính được gán; tạo/cập nhật nháp,
  bổ sung hồ sơ được trả, gửi/gửi lại; không được tự xác nhận hợp lệ.
- Tài khoản chưa có địa bàn OCOP vẫn sử dụng Diêm nghiệp theo cơ chế cũ nhưng chưa truy cập được OCOP.
  Admin vào **Tài khoản → Phân địa bàn OCOP** để gán mã đã có trong danh mục.
- Kiểm tra lại tài khoản hoạt động và quyền trên mỗi yêu cầu. Phiên cũ mất hiệu lực
  khi tài khoản bị khóa, mật khẩu thay đổi hoặc địa bàn được gán lại.
- Tài khoản có liên kết OCOP được khóa thay vì xóa; các dữ liệu liên quan được giữ nguyên.

## 8. Quy trình OCOP đã có

Tạo chủ thể → tạo sản phẩm → tạo hồ sơ nháp → gửi → kiểm tra → trả bổ sung hoặc hợp lệ.
Hồ sơ được trả có thể sửa và gửi lại. Có hủy hồ sơ với giới hạn trạng thái tương ứng quyền.

Sửa hồ sơ chỉ ở `draft`/`returned`; thông tin chủ thể/sản phẩm liên kết với hồ sơ đã gửi
được khóa tại server. Mỗi hồ sơ có số phiên bản để chặn ghi đè khi hai người cùng sửa.
Ngừng sử dụng chủ thể/sản phẩm bị chặn nếu vẫn có hồ sơ cần bảo toàn hoặc liên kết đang hoạt động.

`eligible` chỉ là hồ sơ hợp lệ, chưa phải kết quả đánh giá hay quyết định công nhận.
Không có thao tác nhập hạng sao hoặc ghi dữ liệu chuẩn chính thức ở giai đoạn này.

## 9. Kết quả kiểm thử

**23/23 bài kiểm thử tự động đạt**, gồm 14 bài migration và 9 bài tích hợp HTTP/nghiệp vụ.
Kiểm tra cú pháp bằng `compile()` trên 8 file Python hiện hành đạt, không phát sinh bytecode.

OCOP đã kiểm tra: tạo/sửa chủ thể và sản phẩm; đồng bộ tên danh mục; tạo/sửa hồ sơ;
gửi, kiểm tra, trả bổ sung, gửi lại, xác nhận hợp lệ; hủy/ngừng sử dụng; bảo toàn snapshot/audit;
chặn sửa hồ sơ đã gửi; chặn phiên bản cũ; chặn trùng hồ sơ đang xử lý; rollback khi audit lỗi;
phân quyền chéo đơn vị kể cả sửa URL, bộ lọc và dữ liệu POST; tài khoản không có địa bàn;
khóa tài khoản; admin bị thu hồi quyền; CSRF; escape HTML; dữ liệu sai; giới hạn body;
lọc tổng quan, phân trang và biểu mẫu chọn hơn 200 chủ thể. Không đưa hồ sơ vào `PTNT_OCOP`.

Diêm nghiệp đã regression test: đăng nhập admin/unit; danh sách, dashboard, chi tiết;
nhập/sửa muối và tự tính năng suất; gửi/trả/sửa/gửi lại/duyệt; quyền đơn vị và quyền admin;
import Excel qua HTTP với skip/update; xuất Excel theo quyền/bộ lọc, kiểm tra 27 cột;
chuẩn hóa hai phương pháp muối, mã kỳ ngày và giá khoảng; đổi mật khẩu/đăng xuất;
kiểm tra thao tác OCOP không đổi `records` hoặc `DN_SanLuongMuoi` trong fixture.

Kiểm tra trực tiếp trên trình duyệt: đăng nhập Chi cục trên TEST; dashboard muối;
tổng quan OCOP; biểu mẫu chủ thể; màn hình điện thoại 390 × 844; mở/đóng menu bằng Escape,
trả focus; không có lỗi JavaScript được ghi nhận ở các trang đã xem.

## 10. Giới hạn và phần việc chưa triển khai

- Giai đoạn 2: bộ tiêu chí/version/tiêu chí động. Giai đoạn 3: Hội đồng/chấm điểm/tổng hợp.
  Giai đoạn 4: quyết định, chứng nhận, doanh thu năm, hiệu lực, đồng bộ/xuất dữ liệu chuẩn.
  Giai đoạn 5: upload minh chứng, dashboard nâng cao và kết nối API.
- Nhóm sản phẩm hiện là thông tin nhập liệu, chưa tự gắn bộ tiêu chí. Chưa có `criteria_set_id`;
  cột này sẽ được thêm bằng migration ở giai đoạn 2 khi bảng bộ tiêu chí có thật.
- Chưa triển khai tiếp nhận đầy đủ minh chứng và biểu mẫu pháp lý; giai đoạn 1 quản lý
  dữ liệu nền và trạng thái, chưa thay thế toàn bộ hồ sơ đánh giá điện tử.
- Bộ lọc năm trên tổng quan áp dụng cho hồ sơ; tổng chủ thể/sản phẩm tính toàn bộ thời gian.
- Phiên đăng nhập dùng RAM như hệ thống cũ, mất khi khởi động lại; chưa thêm thời hạn phiên.
- Bootstrap Diêm nghiệp mặc định vẫn có đồng bộ lại dữ liệu chuẩn khi khởi động.
  Launcher TEST bỏ bước đó để bảo toàn snapshot. Chưa sửa thuật toán chuẩn hóa muối cũ.
  Vấn đề có sẵn: admin sửa báo cáo đã duyệt chưa đồng bộ ngay dữ liệu chuẩn; không gộp sửa nghiệp vụ này vào OCOP 1.
- Chưa phát hành lên máy chủ thật và chưa migration `salt_management.db`.

## 11. Tài liệu đã đối chiếu

Yêu cầu ban đầu chỉ có tệp văn bản yêu cầu, chưa có hai tệp quy định riêng đính kèm.
Đã tra cứu bản công bố chính thức để đối chiếu các phần liên quan đến giai đoạn 1:

- [Quyết định 26/2026/QĐ-TTg](https://chinhphu.vn/?classid=1&docid=218267&pageid=27160&typegroupid=5):
  quy trình, phân nhóm/bộ tiêu chí và các biểu mẫu hồ sơ. Chưa nhập 26 bộ tiêu chí.
- [Quyết định 5277/QĐ-BNNMT — Quy định kỹ thuật CSDL tổng hợp ngành nông nghiệp](https://sonnmt.hochiminhcity.gov.vn/document/?item=b21d06f485733b36ea044da9644b829f):
  đối chiếu cấu trúc danh mục và bảng OCOP chi tiết. Dùng tên chính `PTNT_OCOP` và danh mục `DM_KhoangThoiGian`.

## 12. Cách chạy chính xác

### Cách đơn giản trên máy hiện tại

Mở `START_OCOP_TEST_WINDOWS.bat`, giữ cửa sổ chạy và truy cập:

http://127.0.0.1:8081/ocop

Đăng nhập bằng tài khoản trong database test. Tệp chạy tự tìm Python đã cài, hoặc
dùng Python có sẵn trong Codex trên máy hiện tại. Nếu cổng 8081 đang có bản test chạy,
sử dụng bản đang mở hoặc dừng cửa sổ cũ trước khi mở thêm.

### Các lệnh PowerShell khi Python có trong PATH

```powershell
Set-Location 'C:\Users\PC\Downloads\website_quan_ly_muoi\website_quan_ly_muoi'
```

Chỉ khi chưa có TEST, tạo bản sao một lần:

```powershell
python prepare_ocop_test.py
```

Migration chạy lại được:

```powershell
python migrate_ocop.py --db salt_management_TEST.db
```

Chạy bản test:

```powershell
python server.py --db salt_management_TEST.db --skip-legacy-sync --host 127.0.0.1 --port 8081
```

Kiểm thử tự động:

```powershell
python -B -m unittest discover -s tests -v
```

Nếu chưa có `openpyxl` trong Python do người dùng cài, cài thư viện cần cho tính năng Excel:

```powershell
python -m pip install openpyxl
```

### Dùng Python sẵn có trong Codex trên máy này

```powershell
$ocopPython = 'C:\Users\PC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

```powershell
& $ocopPython migrate_ocop.py --db salt_management_TEST.db
```

```powershell
& $ocopPython server.py --db salt_management_TEST.db --skip-legacy-sync --host 127.0.0.1 --port 8081
```

```powershell
& $ocopPython -B -m unittest discover -s tests -v
```

`--db` sai hoặc không tồn tại sẽ báo lỗi, không quay về database chính.
`--skip-legacy-sync` chỉ chấp nhận tên tệp `*_TEST.db`.
Để dừng server ở cửa sổ đang chạy, nhấn Ctrl+C.
