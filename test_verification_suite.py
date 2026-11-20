import urllib.request
import urllib.parse
import json
import http.cookiejar
import sqlite3
import sys

BASE_URL = "http://localhost:8099"

def run_tests():
    print("=== BẮT ĐẦU KIỂM TRA TOÀN DIỆN HỆ THỐNG CRM LONG ZHUANG (PORT 8099) ===")
    
    # 1. Setup Opener with Cookie Support
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    def api_req(path, data=None, token=None, method=None):
        url = BASE_URL + path
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req_data = json.dumps(data).encode('utf-8') if data is not None else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            with opener.open(req) as resp:
                raw = resp.read().decode('utf-8')
                content_type = resp.headers.get('Content-Type', '')
                cookies = resp.headers.get_all('Set-Cookie') or []
                return resp.status, content_type, raw, cookies
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8')
            content_type = e.headers.get('Content-Type', '')
            return e.code, content_type, raw, []

    # ----------------------------------------------------
    # TEST LỖI 3: ĐĂNG NHẬP & PHIÊN LÀM VIỆC BỀN VỮNG
    # ----------------------------------------------------
    print("\n--- [TEST LỖI 3] Đăng nhập, Cookie HttpOnly, Token, Lưu phiên vào SQLite ---")
    status, ctype, raw, cookies = api_req("/api/login", {"identifier": "sep@demo.vn", "password": "123456"})
    assert status == 200, f"Login failed: status {status}, raw: {raw}"
    assert "application/json" in ctype, f"Content-Type not JSON: {ctype}"
    login_res = json.loads(raw)
    assert login_res["success"] is True, f"Login returned success=False: {login_res}"
    admin_token = login_res["token"]
    admin_user = login_res["user"]
    print(f"✓ Đăng nhập Admin thành công: {admin_user['full_name']} (token: {admin_token[:15]}...)")
    
    # Check Set-Cookie was sent
    has_session_cookie = any("crm_session=" in c for c in cookies)
    print(f"✓ Set-Cookie crm_session có trong header response: {has_session_cookie}")
    assert has_session_cookie, "Missing Set-Cookie header in login response"
    
    # Check session in SQLite database
    conn = sqlite3.connect("crm_data.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, expires_at, last_active FROM sessions WHERE token = ?", (admin_token,))
    sess_row = cur.fetchone()
    assert sess_row is not None, "Session token not persisted in SQLite database"
    print(f"✓ Phiên làm việc được lưu bền vững vào bảng 'sessions': user_id={sess_row[0]}, expires={sess_row[1]}")
    conn.close()

    # Test /api/status endpoint using cookie (opener holds cookie)
    status, ctype, raw, _ = api_req("/api/status")
    assert status == 200
    status_res = json.loads(raw)
    assert status_res["logged_in"] is True
    print(f"✓ /api/status nhận diện phiên từ Cookie: user_id={status_res['current_user']['id']}")

    # ----------------------------------------------------
    # TEST LỖI 2: KHÔNG THÊM ĐƯỢC NHÂN VIÊN & API PHẢI TRẢ JSON
    # ----------------------------------------------------
    print("\n--- [TEST LỖI 2] Tuyệt đối không trả HTML, bắt lỗi chi tiết, tạo nhân viên mới ---")
    
    # Check 404 on invalid API route must return JSON, NOT index.html!
    status, ctype, raw, _ = api_req("/api/invalid_route_xyz")
    assert status == 404, f"Expected 404, got {status}"
    assert "application/json" in ctype, f"404 route did not return JSON: {ctype}"
    assert "DOCTYPE" not in raw, "404 route returned HTML <!DOCTYPE...!"
    print("✓ Route không tồn tại /api/invalid_route_xyz trả đúng JSON 404, không rơi vào HTML index.html")

    import random
    rnd = random.randint(100000, 999999)

    # 1. Duplicate phone error
    status, ctype, raw, _ = api_req("/api/employees/save", {
        "code": f"KD-PH{rnd}",
        "full_name": "Nhân Viên Trùng SĐT",
        "phone": "0986944491", # Sếp's phone in DB
        "email": f"unique_email_{rnd}@demo.vn",
        "role": "sales"
    }, token=admin_token)
    assert status == 400, f"Expected 400 for duplicate phone, got {status}: {raw}"
    res_dup_phone = json.loads(raw)
    assert res_dup_phone["field"] == "phone", f"Expected field='phone', got {res_dup_phone}"
    print(f"✓ Báo lỗi chuẩn JSON khi trùng SĐT: field={res_dup_phone['field']}, msg={res_dup_phone['message']}")

    # 2. Duplicate email error
    status, ctype, raw, _ = api_req("/api/employees/save", {
        "code": f"KD-EM{rnd}",
        "full_name": "Nhân Viên Trùng Email",
        "phone": f"0919{rnd}",
        "email": "nhanvien1@demo.vn", # Existing email in DB
        "role": "sales"
    }, token=admin_token)
    assert status == 400, f"Expected 400, got {status}: {raw}"
    res_dup_email = json.loads(raw)
    assert res_dup_email["field"] == "email", f"Expected field='email', got {res_dup_email}"
    print(f"✓ Báo lỗi chuẩn JSON khi trùng email: field={res_dup_email['field']}, msg={res_dup_email['message']}")

    # 3. Duplicate code error
    status, ctype, raw, _ = api_req("/api/employees/save", {
        "code": "GD-01", # Existing code
        "full_name": "Nhân Viên Trùng Mã",
        "phone": f"0918{rnd}",
        "email": f"unique_code_{rnd}@demo.vn",
        "role": "sales"
    }, token=admin_token)
    assert status == 400, f"Expected 400 for duplicate code, got {status}: {raw}"
    res_dup_code = json.loads(raw)
    assert res_dup_code["field"] == "code", f"Expected field='code', got {res_dup_code}"
    print(f"✓ Báo lỗi chuẩn JSON khi trùng mã nhân viên: field={res_dup_code['field']}, msg={res_dup_code['message']}")

    # Successfully add employee with optional CCCD/DOB left blank and auto-generated temporary password
    import random
    test_num = random.randint(1000, 9999)
    new_emp_code = f"KD-TEST{test_num}"
    new_emp_email = f"sales_test{test_num}@longzhuang.vn"
    new_emp_phone = f"0936{test_num:06d}"
    
    status, ctype, raw, _ = api_req("/api/employees/save", {
        "code": new_emp_code,
        "full_name": f"Nguyễn Thị Test {test_num}",
        "phone": new_emp_phone,
        "email": new_emp_email,
        "password": "", # Blank -> auto generate random LZ@...
        "role": "sales",
        "position": "Chuyên viên Kinh doanh",
        "dob": "", # Optional
        "cccd": "", # Optional
        "monthly_target": 120000000
    }, token=admin_token)
    assert status == 200, f"Failed to save employee: {raw}"
    new_emp_res = json.loads(raw)
    temp_pw = new_emp_res.get("temporary_password")
    assert temp_pw and temp_pw.startswith("LZ@"), f"Temporary password not generated correctly: {temp_pw}"
    new_emp_id = new_emp_res["employee_id"]
    print(f"✓ Tạo nhân viên mới thành công: ID={new_emp_id}, Mã={new_emp_code}, Mật khẩu tạm={temp_pw}")

    # Verify that new employee can log in with temporary password and has must_change_password=1
    status, ctype, raw, _ = api_req("/api/login", {"identifier": new_emp_email, "password": temp_pw})
    assert status == 200
    sales_login = json.loads(raw)
    assert sales_login["user"]["must_change_password"] == 1
    sales_token = sales_login["token"]
    print(f"✓ Nhân viên mới đăng nhập thành công với mật khẩu tạm, cờ must_change_password = 1")

    # Change password for new employee
    new_pw = "matkhauMoi@2026"
    status, ctype, raw, _ = api_req("/api/change_password", {
        "old_password": temp_pw,
        "new_password": new_pw
    }, token=sales_token)
    assert status == 200
    print("✓ Nhân viên đổi mật khẩu thành công")

    # Verify updated must_change_password flag
    status, ctype, raw, _ = api_req("/api/status", token=sales_token)
    status_data = json.loads(raw)
    assert status_data["current_user"]["must_change_password"] == 0
    print("✓ Cờ must_change_password đã được xóa sau khi đổi mật khẩu (must_change_password = 0)")

    # ----------------------------------------------------
    # TEST LỖI 1: FORM TẠO ĐƠN HÀNG THIẾU Ô CHỌN KHÁCH HÀNG
    # ----------------------------------------------------
    print("\n--- [TEST LỖI 1] Kiểm tra validation Khách hàng trong Form Tạo đơn hàng ---")
    
    # 1. Missing customer_id must fail with 400 and clear Vietnamese message
    status, ctype, raw, _ = api_req("/api/orders/add", {
        "customer_id": None,
        "items_text": "5000 bộ bulong M10",
        "total_amount": 5000000
    }, token=admin_token)
    assert status == 400, f"Expected 400 for missing customer_id, got {status}"
    err_res = json.loads(raw)
    assert "chọn khách hàng" in err_res["message"].lower()
    print(f"✓ Server chặn tạo đơn khi thiếu khách hàng: {err_res['message']}")

    # 2. Add customer for sales rep
    status, ctype, raw, _ = api_req("/api/customers/add", {
        "full_name": f"Xưởng Cơ khí Test {test_num}",
        "phone": f"0912{test_num:06d}",
        "customer_type": "Xưởng gia công",
        "source": "Đến trực tiếp",
        "address": "KCN Đình Vũ, Hải Phòng",
        "demand": "Bulong neo M20",
        "assigned_user_id": new_emp_id
    }, token=admin_token)
    assert status == 200
    cust_res = json.loads(raw)
    test_cust_id = cust_res["customer_id"]
    print(f"✓ Tạo khách hàng test thành công: ID={test_cust_id}")

    # 3. Sales rep creates order with assigned customer -> success
    order_code_test = f"DH-TEST-{test_num}"
    status, ctype, raw, _ = api_req("/api/orders/add", {
        "customer_id": test_cust_id,
        "order_code": order_code_test,
        "total_amount": 18500000,
        "status": "Đã giao",
        "delivery_date": "2026-11-17",
        "items_text": "1.000 con bulong hóa chất M16x190\n200 lọ keo cấy thép Ramset",
        "notes": "Giao chân công trình Đình Vũ"
    }, token=sales_token)
    assert status == 200, f"Sales rep failed to create order: {raw}"
    print(f"✓ Nhân viên kinh doanh tạo đơn hàng thành công: Mã={order_code_test}")

    # 4. Check that 4 care milestones were automatically generated
    conn = sqlite3.connect("crm_data.db")
    cur = conn.cursor()
    cur.execute("SELECT milestone_code, milestone_days, status, scheduled_date FROM care_tasks WHERE customer_id = ? ORDER BY milestone_days ASC", (test_cust_id,))
    tasks = cur.fetchall()
    assert len(tasks) == 4, f"Expected 4 milestones, found {len(tasks)}"
    print(f"✓ Tự động sinh đủ 4 mốc chăm sóc (5d, 7d, 15d, 30d): {[t[0] for t in tasks]}")
    conn.close()

    # 5. Sales rep attempting to create order for customer assigned to someone else -> forbidden 403
    status, ctype, raw, _ = api_req("/api/orders/add", {
        "customer_id": 1, # Customer 1 belongs to someone else
        "order_code": f"DH-FORBIDDEN-{test_num}",
        "total_amount": 5000000,
        "status": "Mới",
        "items_text": "Bulong thử nghiệm"
    }, token=sales_token)
    assert status == 403, f"Expected 403 when creating order for unassigned customer, got {status}"
    print("✓ Nhân viên kinh doanh bị chặn (403) khi tạo đơn cho khách hàng của người khác")

    # ----------------------------------------------------
    # TEST YÊU CẦU 4: LOGO CHỮ "LZ"
    # ----------------------------------------------------
    print("\n--- [TEST YÊU CẦU 4] Kiểm tra Logo chữ 'LZ' và xóa sạch file ảnh cũ ---")
    import os
    for old_file in ['logo.png', 'logo_icon.png', 'logo_transparent.png', 'avatar.png', 'sidebar_banner.png', 'qrcode.min.js']:
        old_path = os.path.join("web", old_file)
        assert not os.path.exists(old_path), f"Old file {old_path} was not deleted!"
    print("✓ Toàn bộ file ảnh logo và qrcode cũ đã được xóa sạch")

    with open("web/index.html", "r", encoding="utf-8") as f:
        html_code = f.read()
    assert "<title>LZ | CRM LONG ZHUANG - Tổng kho Bu lông Kim khí</title>" in html_code
    assert 'image/svg+xml' in html_code and ('%3ELZ%3C' in html_code or '>LZ<' in html_code)
    print("✓ Tiêu đề trình duyệt và Favicon SVG hiển thị chuẩn chữ 'LZ'")

    # ----------------------------------------------------
    # TEST YÊU CẦU 5: INTERACTIVE DASHBOARD CHARTS & PHÂN QUYỀN
    # ----------------------------------------------------
    print("\n--- [TEST YÊU CẦU 5] Dashboard Charts, KPI Sparklines, Phân quyền dữ liệu ---")
    
    # 1. Admin Dashboard
    status, ctype, raw, _ = api_req("/api/dashboard", token=admin_token)
    assert status == 200
    dash_admin = json.loads(raw)
    assert "kpi_cards" in dash_admin, "Missing kpi_cards in admin dashboard"
    assert "donut_breakdown" in dash_admin, "Missing donut_breakdown"
    assert "sources_chart" in dash_admin, "Missing sources_chart"
    assert "revenue_12m" in dash_admin, "Missing revenue_12m"
    assert "admin_extras" in dash_admin, "Missing admin_extras in admin dashboard"
    assert len(dash_admin["donut_breakdown"]) == 5, f"Expected 5 donut categories, got {len(dash_admin['donut_breakdown'])}"
    print(f"✓ Admin Dashboard trả đầy đủ dữ liệu: KPI cards, Donut 5 trạng thái, Doanh thu 12 tháng, Bảng xếp hạng NV")

    # 2. Sales Rep Dashboard isolation: No company totals or admin extras leaked
    status, ctype, raw, _ = api_req("/api/dashboard", token=sales_token)
    assert status == 200
    dash_sales = json.loads(raw)
    assert dash_sales.get("role") == "sales"
    assert "sales_rep_stats" in dash_sales, "Missing sales_rep_stats for sales rep"
    assert "admin_extras" not in dash_sales, "SECURITY LEAK: admin_extras leaked to sales rep!"
    print(f"✓ Phân quyền bảo mật Dashboard: Sales Rep chỉ thấy chỉ tiêu cá nhân ({dash_sales['sales_rep_stats']['target_percent']}% KPI), không lộ doanh thu toàn công ty hay nhân viên khác")

    # 3. Chart.js local file exists and loaded
    chart_local_path = os.path.join("web", "chart.umd.min.js")
    assert os.path.exists(chart_local_path), f"Chart.js offline bundle missing at {chart_local_path}"
    assert os.path.getsize(chart_local_path) > 100000, "Chart.js offline bundle is too small"
    print(f"✓ Thư viện Chart.js offline cục bộ tồn tại ({os.path.getsize(chart_local_path)} bytes) hoạt động không cần mạng Internet")

    print("\n🎉 TẤT CẢ 5 BÀI TEST ĐÃ VƯỢT QUA 100% HOÀN TOÀN KHÔNG CÓ LỖI!")

if __name__ == "__main__":
    run_tests()
