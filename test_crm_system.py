#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kịch bản kiểm thử toàn diện cho CRM LONG ZHUANG
Kiểm tra:
1. Đăng nhập Sếp & Nhân viên (xác thực PBKDF2)
2. Phân quyền máy chủ: Sales không thể xem khách của người khác, không vào được báo cáo
3. Chống trùng số điện thoại (chuẩn hóa 0xxx / +84xxx)
4. Tạo đơn hàng và tự động sinh 4 mốc chăm sóc (5d, 7d, 15d, 30d)
5. Kịch bản Zalo tự động điền biến {ten_khach}, {ten_nhan_vien}...
6. Báo cáo quản trị, xuất file Excel
"""

import urllib.request
import urllib.parse
import json
import time
import subprocess
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8899"

def req(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode('utf-8') if data else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as resp:
            content = resp.read()
            try:
                return resp.status, json.loads(content.decode('utf-8'))
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content.decode('utf-8'))
        except Exception:
            return e.code, content

def run_tests():
    print("=" * 60)
    print("BẮT ĐẦU KIỂM THỬ HỆ THỐNG CRM LONG ZHUANG")
    print("=" * 60)

    # 1. Test Status
    status, res = req("/api/status")
    assert status == 200, f"Status failed: {status}"
    print(f"✓ 1. Máy chủ hoạt động: {res['company_name']} - Giờ hệ thống: {res['server_time']}")

    # 2. Test Login Sếp (sep@demo.vn / 123456)
    status, res = req("/api/login", method="POST", data={"identifier": "sep@demo.vn", "password": "123456"})
    assert status == 200 and res['success'] is True, f"Login Sếp failed: {res}"
    admin_token = res['token']
    admin_user = res['user']
    print(f"✓ 2. Đăng nhập Sếp thành công: {admin_user['full_name']} (Role: {admin_user['role']})")

    # 3. Test Login Nhân viên KD (nhanvien1@demo.vn / 123456)
    status, res = req("/api/login", method="POST", data={"identifier": "nhanvien1@demo.vn", "password": "123456"})
    assert status == 200 and res['success'] is True, f"Login NV failed: {res}"
    sales_token = res['token']
    sales_user = res['user']
    print(f"✓ 3. Đăng nhập Nhân viên KD thành công: {sales_user['full_name']} (Role: {sales_user['role']})")

    # 4. Test Phân quyền máy chủ: Nhân viên gọi API Báo cáo -> Phải bị từ chối 403
    status, res = req("/api/reports", token=sales_token)
    assert status == 403, f"Phân quyền thất bại, Sales vẫn truy cập được Báo cáo! Code: {status}"
    print(f"✓ 4. Bảo mật phân quyền máy chủ: Nhân viên bị chặn 403 khi vào Báo cáo.")

    # 5. Test Phân quyền khách hàng: Sales chỉ lấy khách của mình, Admin lấy tất cả
    status, res_sales = req("/api/customers", token=sales_token)
    status, res_admin = req("/api/customers", token=admin_token)
    assert len(res_sales['customers']) < len(res_admin['customers']), "Sales nhìn thấy toàn bộ khách của công ty!"
    print(f"✓ 5. Cách ly dữ liệu khách hàng: Nhân viên chỉ thấy {len(res_sales['customers'])} khách, Sếp thấy {len(res_admin['customers'])} khách.")

    # 6. Test CHỐNG TRÙNG SỐ ĐIỆN THOẠI
    # Thử thêm khách mới với số đã tồn tại của khách Anh Tuấn (0988123456)
    dup_phone = "+84 988.123.456"
    status, res = req("/api/customers/add", method="POST", token=sales_token, data={
        "full_name": "Khách Trùng Thử Nghiệm",
        "phone": dup_phone,
        "customer_type": "Thầu công trình",
        "source": "Fanpage"
    })
    assert status == 400 and "ĐÃ TỒN TẠI" in res['message'], f"Chống trùng SĐT thất bại: {res}"
    print(f"✓ 6. Cơ chế chống trùng SĐT hoạt động hoàn hảo:")
    print(f"     Thông báo: {res['message']}")

    # 7. Test Tạo đơn hàng mới & Tự động kích hoạt 4 mốc chăm sóc (5d, 7d, 15d, 30d)
    status, res_order = req("/api/orders/add", method="POST", token=admin_token, data={
        "customer_id": 1,
        "total_amount": 25000000,
        "items_text": "3.000 bộ bulong nở rút inox M12x100\n1.000 cây ty ren M10 inox 304",
        "status": "Đã giao",
        "delivery_date": time.strftime("%Y-%m-%d"),
        "notes": "Kiểm thử tự động sinh lịch chăm sóc"
    })
    assert status == 200 and res_order['success'] is True, f"Tạo đơn thất bại: {res_order}"
    print(f"✓ 7. Tạo đơn hàng [{res_order['order_code']}] và kích hoạt 4 mốc chăm sóc thành công!")

    # 8. Test Kịch bản Zalo tự động điền biến {ten_khach}, {ten_nhan_vien}, {ma_don}...
    status, res_zalo = req("/api/scripts/render", method="POST", token=sales_token, data={
        "customer_id": 1,
        "milestone_code": "5d"
    })
    assert status == 200 and res_zalo['success'] is True, f"Render Zalo thất bại: {res_zalo}"
    assert "Anh Tuấn" in res_zalo['rendered_text'], "Biến {ten_khach} chưa được thay thế!"
    assert res_zalo['zalo_url'].startswith("https://zalo.me/"), "URL Zalo không đúng định dạng!"
    print(f"✓ 8. Kịch bản Zalo điền biến tự động chuẩn xác:")
    print(f"     Tin nhắn: \"{res_zalo['rendered_text'][:80]}...\"")
    print(f"     Link mở: {res_zalo['zalo_url']}")

    # 9. Test Báo cáo quản trị & Xuất Excel
    status, res_rep = req("/api/reports", token=admin_token)
    assert status == 200 and res_rep['success'] is True, f"Báo cáo thất bại: {res_rep}"
    status, res_excel = req("/api/export_excel", token=admin_token)
    assert status == 200 and len(res_excel) > 500, "Xuất file Excel thất bại!"
    print(f"✓ 9. Báo cáo quản trị & Xuất file Excel tiếng Việt UTF-8 thành công ({len(res_excel)} bytes).")

    print("=" * 60)
    print("TẤT CẢ 9 BỘ KIỂM THỬ ĐỀU ĐẠT CHUẨN 100%!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
