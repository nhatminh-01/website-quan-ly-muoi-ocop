# Kết nối PostgreSQL dùng chung cho nhóm 2 người

## Mô hình thống nhất

- Chỉ máy chủ `192.168.1.41` cài và vận hành PostgreSQL 17.
- Hai thành viên dùng chung role `ptnt_team`, có toàn quyền trong database dự án `ptnt_qd5277_dev`.
- Máy cộng tác viên không tải database và không cài PostgreSQL Server. Mọi thay đổi dữ liệu đi thẳng vào database trên máy chủ.
- Không đưa `database/.env` hoặc mật khẩu lên GitHub.

## 1. Chuẩn bị trên máy chủ database

Mở PowerShell tại repository và chạy bằng tài khoản PostgreSQL quản trị:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d ptnt_qd5277_dev -f database\sql\team_role_setup.sql
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d ptnt_qd5277_dev
```

Trong màn hình `psql`, đặt mật khẩu dùng chung rồi thoát:

```text
\password ptnt_team
\q
```

Trong `C:\Program Files\PostgreSQL\17\data\pg_hba.conf`, cho phép đúng máy cộng tác viên `192.168.1.38`:

```text
host  ptnt_qd5277_dev  ptnt_team  192.168.1.38/32  scram-sha-256
```

Reload PostgreSQL, rồi mở **PowerShell bằng Run as administrator** để tạo hai Firewall rule giới hạn đúng IP cộng tác viên:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d postgres -c "SELECT pg_reload_conf();"
New-NetFirewallRule -DisplayName "PTNT PostgreSQL 5432 from 192.168.1.38" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -RemoteAddress 192.168.1.38 -Profile Private
New-NetFirewallRule -DisplayName "PTNT Web 8080 from 192.168.1.38" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -RemoteAddress 192.168.1.38 -Profile Private
```

Máy chủ nên được giữ IP cố định `192.168.1.41` bằng DHCP reservation.

## 2. Cài trên máy cộng tác viên

Cần cài Git và Python 3.11 trở lên. Sau khi clone repository:

```powershell
cd website-quan-ly-muoi-ocop
python -m venv database\.venv
.\database\.venv\Scripts\python.exe -m pip install -r database\requirements.txt
Copy-Item database\.env.example database\.env
```

Mở **file vừa sao chép** `database/.env`, thay `CHANGE_ME` bằng mật khẩu `ptnt_team` được gửi qua kênh riêng. Không sửa `database/.env.example`, không ghi mật khẩu vào tài liệu/commit và không cần tải bất kỳ file `.db` nào.

## 3. Kiểm tra kết nối và chạy web

```powershell
.\database\.venv\Scripts\python.exe -c "from backend_db import healthcheck; print(healthcheck())"
.\START_WINDOWS.bat
```

Sau khi máy chủ đã chạy web, cộng tác viên cùng LAN mở:

```text
http://192.168.1.41:8080
```

`192.168.1.41` là IP máy chủ web/database; `192.168.1.38` là IP máy cộng tác viên được cấp quyền truy cập.

Kết nối DBeaver dùng cùng thông tin:

| Trường | Giá trị |
|---|---|
| Host | `192.168.1.41` |
| Port | `5432` |
| Database | `ptnt_qd5277_dev` |
| Username | `ptnt_team` |
| Password | Gửi riêng, không lưu trong Git |
| SSL | Tắt khi chỉ dùng trong LAN tin cậy |

Nếu hai máy không cùng LAN, dùng VPN như Tailscale và thay `PGHOST` bằng IP VPN của máy chủ. Không port-forward cổng 5432 trực tiếp ra Internet.

## 4. Quy tắc làm việc chung

1. Mỗi người làm code trên branch riêng và tạo pull request vào `main`.
2. Trước khi bắt đầu: `git switch main`, `git pull --ff-only`, rồi tạo branch mới.
3. Chỉ một người chạy migration SQL tại một thời điểm.
   Sau khi tạo `ptnt_team`, các migration mới phải chạy bằng role này để object mới tiếp tục thuộc quyền chung của nhóm.
4. Sao lưu PostgreSQL trước migration hoặc thao tác dữ liệu lớn.
5. Test phá dữ liệu phải dùng database PostgreSQL tạm, không dùng `ptnt_qd5277_dev`.
