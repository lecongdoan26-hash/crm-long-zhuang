# 🔩 CRM LONG ZHUANG - Hệ Thống Quản Trị Khách Hàng & Đơn Hàng Kim Khí

> **Phiên bản nội bộ dành cho Tổng kho Bulong, Ốc vít & Kim khí Long Zhuang Hải Phòng.**
> Thiết kế chuẩn Glassmorphism hiện đại, tối ưu cho máy tính & điện thoại (giao diện tiếng Việt).

---

## 🌟 4 Trọng Tâm Nghiệp Vụ
1. **Quản lý Đơn hàng:** Lưu mã đơn, thông tin khách hàng, số tiền, ngày giao, vật tư kim khí. Tự động kích hoạt chu trình chăm sóc khách hàng 4 mốc khi đơn hoàn tất.
2. **Quản lý Dữ liệu Khách hàng:** Phân loại theo nguồn (*Fanpage, Đến trực tiếp, Khách lẻ, Giới thiệu*), loại khách (*Thầu công trình, Xưởng cơ khí, Đại lý, Khách lẻ*) và giai đoạn (*Tiềm năng / Khách cũ*).
3. **Lịch chăm sóc khách hàng tự động 4 mốc:** 5 ngày (*Kiểm tra trải nghiệm*), 7 ngày (*Hỏi tiến độ & hao hụt*), 15 ngày (*Đánh giá chất lượng*), 30 ngày (*Nhắc đặt lại/hỏi thăm*). Tích hợp kịch bản mẫu soạn sẵn gửi qua Zalo 1 chạm.
4. **Phân quyền & Quản lý Kinh doanh (RBAC):**
   - **Sếp / Quản lý:** Xem toàn bộ dữ liệu, chuyển khách giữa các sale, xem bảng xếp hạng doanh thu và biểu đồ phân tích.
   - **Nhân viên Kinh doanh:** Chỉ xem khách và đơn hàng do mình phụ trách, xem mục tiêu KPI cá nhân.

---

## 🚀 Hướng Dẫn Deploy Lên Render.com (Miễn Phí & Có HTTPS)

Render cung cấp hosting miễn phí có sẵn chứng chỉ SSL/HTTPS và tên miền con `*.onrender.com` rất tiện lợi để sếp duyệt trước khi gắn tên miền chính.

### Cách 1: Tạo Web Service thủ công (Khuyên dùng - Nhanh nhất)
1. Đăng nhập vào [Render.com](https://render.com) (chọn đăng nhập bằng GitHub).
2. Bấm nút **New +** ở góc trên bên phải ➔ Chọn **Web Service**.
3. Chọn kho lưu trữ GitHub `crm-long-zhuang` vừa tạo.
4. Điền các thông số cơ bản:
   - **Name:** `crm-long-zhuang` (hoặc tên bạn muốn)
   - **Region:** `Singapore` (để truy cập từ Việt Nam nhanh nhất)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python server.py`
   - **Instance Type:** `Free`
5. Bấm **Deploy Web Service**.
6. Đợi 1–2 phút cho Render build xong, bạn sẽ nhận được đường link HTTPS dạng: `https://crm-long-zhuang.onrender.com`.

### Cách 2: Dùng Blueprint (render.yaml)
Kho lưu trữ đã có sẵn file `render.yaml`. Trên Render.com:
- Chọn **New +** ➔ **Blueprint** ➔ Chọn repository `crm-long-zhuang`.
- Render sẽ tự động đọc cấu hình và tạo Web Service chỉ sau 1 cú click!

---

## 🔑 Tài Khoản Trải Nghiệm Mẫu

Hệ thống đã được nạp sẵn dữ liệu mẫu thực tế của ngành bulong kim khí:

| Vai trò | Email đăng nhập | Số điện thoại | Mật khẩu |
| :--- | :--- | :--- | :--- |
| **Sếp / Quản lý** | `sep@demo.vn` | `0986944491` | `123456` |
| **Nhân viên KD 01** | `nhanvien1@demo.vn` | `0912345671` | `123456` |
| **Nhân viên KD 02** | `nhanvien2@demo.vn` | `0912345672` | `123456` |
| **Nhân viên KD 03** | `nhanvien3@demo.vn` | `0912345673` | `123456` |

---

## 💻 Chạy Cục Bộ (Localhost)
Nếu muốn chạy lại trên máy tính cá nhân:
```bash
python server.py
```
Mở trình duyệt truy cập: [http://localhost:8099](http://localhost:8099)
Hoặc click đúp file `Chay_CRM.bat`.

---

## 🛠️ Công Nghệ
- **Backend:** Python Standard Library (`http.server.ThreadingHTTPServer`, `sqlite3`, `hashlib.pbkdf2_hmac`). Không cần cài thêm thư viện phụ thuộc.
- **Frontend:** HTML5, CSS3 Glassmorphism (Inter, Playfair Display), Vanilla JavaScript ES6+.
- **Biểu đồ:** Chart.js 4.4.1 (chạy offline nội bộ qua `chart.umd.min.js`).
