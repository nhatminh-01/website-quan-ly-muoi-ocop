# Kết nối PostgreSQL production dùng chung cho nhóm

## Mô hình thống nhất

- Chỉ máy chủ `10.206.16.19` cài và vận hành PostgreSQL 17.6.
- Database dùng chung là `ocop_db`; ứng dụng kết nối bằng role `ocop` do DBA cấp.
- Máy cộng tác viên không tải database và không cài PostgreSQL Server. Mọi thay đổi dữ liệu đi thẳng vào database production.
- Không đưa `database/.env`, `database/.env.production` hoặc mật khẩu lên GitHub.

## 1. Chuẩn bị trên máy chủ database

DBA đã tạo database/schema và role `ocop` theo các migration trong
`database/sql`. Khi thêm máy cộng tác viên, DBA chỉ cần cho phép đúng IP máy đó
trong `pg_hba.conf` (thay `CLIENT_IP`, không mở toàn mạng):

```text
host  ocop_db  ocop  CLIENT_IP/32  scram-sha-256
```

Reload PostgreSQL, rồi mở **PowerShell bằng Run as administrator** để tạo hai Firewall rule giới hạn đúng IP cộng tác viên:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d postgres -c "SELECT pg_reload_conf();"
New-NetFirewallRule -DisplayName "PTNT PostgreSQL 5432 from CLIENT_IP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -RemoteAddress CLIENT_IP -Profile Private
New-NetFirewallRule -DisplayName "PTNT Web 8080 from CLIENT_IP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -RemoteAddress CLIENT_IP -Profile Private
```

Máy chủ nên được giữ IP cố định `10.206.16.19` bằng DHCP reservation.

## 2. Cài trên máy cộng tác viên

Cần cài Git và Python 3.11 trở lên. Sau khi clone repository:

```powershell
cd website-quan-ly-muoi-ocop
python -m venv database\.venv
.\database\.venv\Scripts\python.exe -m pip install -r database\requirements.txt
Copy-Item database\.env.example database\.env
```

Mở **file vừa sao chép** `database/.env`, đặt `PGHOST=10.206.16.19`,
`PGDATABASE=ocop_db`, `PGUSER=ocop`, rồi thay `CHANGE_ME` bằng mật khẩu được
gửi qua kênh riêng. Không sửa `database/.env.example`, không ghi mật khẩu vào
tài liệu/commit và không cần tải bất kỳ file `.db` nào.

## 3. Kiểm tra kết nối và chạy web

```powershell
.\database\.venv\Scripts\python.exe -c "from backend_db import healthcheck; print(healthcheck())"
.\START_WINDOWS.bat
```

Sau khi máy chủ đã chạy web, cộng tác viên cùng LAN mở:

```text
http://10.206.16.19:8080
```

`10.206.16.19` là IP máy chủ database production. IP máy cộng tác viên phải được
DBA cho phép riêng trong `pg_hba.conf` và Windows Firewall.

Kết nối DBeaver dùng cùng thông tin:

| Trường | Giá trị |
|---|---|
| Host | `10.206.16.19` |
| Port | `5432` |
| Database | `ocop_db` |
| Username | `ocop` |
| Password | Gửi riêng, không lưu trong Git |
| SSL | Tắt khi chỉ dùng trong LAN tin cậy |

Nếu hai máy không cùng LAN, dùng VPN như Tailscale và thay `PGHOST` bằng IP VPN của máy chủ. Không port-forward cổng 5432 trực tiếp ra Internet.

## 4. Quy tắc làm việc chung

1. Mỗi người làm code trên branch riêng và tạo pull request vào `main`.
2. Trước khi bắt đầu: `git switch main`, `git pull --ff-only`, rồi tạo branch mới.
3. Chỉ một người chạy migration SQL tại một thời điểm.
   Các migration production mới phải chạy bằng role được DBA cấp (hiện là `ocop`).
4. Sao lưu PostgreSQL trước migration hoặc thao tác dữ liệu lớn.
5. Test phá dữ liệu phải dùng database PostgreSQL tạm, không dùng `ocop_db` production.
