#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hạt giống dữ liệu mẫu (Seeder) cho CRM LONG ZHUANG
Tạo 1 Sếp, 3 Nhân viên, 42 Khách hàng kim khí, 25 Đơn hàng, Lịch chăm sóc 5 trạng thái, Kịch bản mẫu, v.v.
"""

import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

def hash_pw(pw, salt=None):
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 100000)
    return hashed.hex(), salt.hex()

def seed():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. users
    cur.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'sales', -- 'admin' hoặc 'sales'
        is_active INTEGER DEFAULT 1,
        must_change_password INTEGER DEFAULT 0,
        failed_attempts INTEGER DEFAULT 0,
        locked_until TEXT DEFAULT NULL,
        created_at TEXT,
        updated_at TEXT
    )''')

    # 2. employee_profiles
    cur.execute('''
    CREATE TABLE employee_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        code TEXT,
        dob TEXT,
        gender TEXT,
        cccd TEXT,
        address TEXT,
        start_date TEXT,
        position TEXT,
        contract_type TEXT,
        monthly_target INTEGER DEFAULT 150000000,
        notes TEXT,
        avatar_color TEXT DEFAULT '#3B5BFF',
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # 3. customers
    cur.execute('''
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        zalo TEXT,
        address TEXT,
        customer_type TEXT DEFAULT 'Thầu công trình',
        source TEXT DEFAULT 'Fanpage',
        stage TEXT DEFAULT 'Khách tiềm năng', -- 'Khách tiềm năng' hoặc 'Khách cũ'
        demand TEXT,
        assigned_user_id INTEGER NOT NULL,
        status TEXT DEFAULT 'Mới nhận',
        last_contacted_at TEXT,
        next_followup_at TEXT,
        notes TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(assigned_user_id) REFERENCES users(id)
    )''')

    # 4. customer_transfers
    cur.execute('''
    CREATE TABLE customer_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        from_user_id INTEGER NOT NULL,
        to_user_id INTEGER NOT NULL,
        reason TEXT NOT NULL,
        transferred_by_user_id INTEGER NOT NULL,
        created_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(from_user_id) REFERENCES users(id),
        FOREIGN KEY(to_user_id) REFERENCES users(id)
    )''')

    # 5. orders
    cur.execute('''
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        delivery_date TEXT,
        total_amount INTEGER NOT NULL DEFAULT 0,
        items_text TEXT NOT NULL,
        status TEXT DEFAULT 'Mới', -- 'Mới', 'Đã báo giá', 'Chốt', 'Đã giao', 'Hoàn tất'
        notes TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # 6. care_tasks
    cur.execute('''
    CREATE TABLE care_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        customer_id INTEGER NOT NULL,
        assigned_user_id INTEGER NOT NULL,
        milestone_code TEXT NOT NULL, -- '5d', '7d', '15d', '30d'
        milestone_days INTEGER NOT NULL,
        milestone_title TEXT NOT NULL,
        scheduled_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Chưa đến hạn', -- 'Chưa đến hạn', 'Đến hạn hôm nay', 'Quá hạn', 'Đã chăm', 'Khách đã đặt lại'
        result_status TEXT DEFAULT '', -- 'Khách cần báo giá', 'Hẹn gọi lại', 'Chưa có nhu cầu', 'Đã đặt đơn mới'
        result_notes TEXT DEFAULT '',
        cared_by_user_id INTEGER,
        cared_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(assigned_user_id) REFERENCES users(id)
    )''')

    # 7. message_templates (kịch bản)
    cur.execute('''
    CREATE TABLE message_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        milestone_code TEXT NOT NULL,
        milestone_title TEXT NOT NULL,
        customer_type TEXT NOT NULL DEFAULT 'Tất cả',
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        is_default INTEGER DEFAULT 1,
        created_at TEXT
    )''')

    # 8. interactions (lịch sử trao đổi / ghi chú thời gian)
    cur.execute('''
    CREATE TABLE interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        contact_type TEXT DEFAULT 'Gọi điện',
        content TEXT NOT NULL,
        reaction TEXT DEFAULT 'Quan tâm',
        next_date TEXT,
        created_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # 9. audit_logs
    cur.execute('''
    CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_name TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        details TEXT,
        ip_address TEXT,
        created_at TEXT
    )''')

    # 10. settings
    cur.execute('''
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # 11. sessions (Lưu phiên đăng nhập bền vững)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_active TEXT NOT NULL,
        ip_address TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Insert Settings
    settings_data = [
        ('company_name', 'TỔNG KHO BULONG ỐC VÍT LONG ZHUANG'),
        ('brand_tagline', 'Tổng Kho Kim Khí & Vật Tư Cơ Điện M&E Hải Phòng'),
        ('hotline', '0986.944.491'),
        ('address', 'Số 168 Đường Hùng Vương, Quán Toan, Hồng Bàng, Hải Phòng'),
        ('milestone_5d', '5'),
        ('milestone_7d', '7'),
        ('milestone_15d', '15'),
        ('milestone_30d', '30'),
        ('mask_phone', '0'),
        ('auto_care_active', '1'),
    ]
    cur.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings_data)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now.strftime("%Y-%m-%d")

    # Insert Users
    pw_hash, salt = hash_pw("123456")

    users_data = [
        (1, 'sep@demo.vn', 'sep@demo.vn', '0986944491', pw_hash, salt, 'Lê Công Đoàn (Sếp / Quản Lý)', 'admin', 1, 0, 0, None, now_str, now_str),
        (2, 'nhanvien1@demo.vn', 'nhanvien1@demo.vn', '0912345671', pw_hash, salt, 'Nguyễn Thị Linh (KD 01 - Thầu M&E)', 'sales', 1, 0, 0, None, now_str, now_str),
        (3, 'nhanvien2@demo.vn', 'nhanvien2@demo.vn', '0912345672', pw_hash, salt, 'Trần Anh Tuấn (KD 02 - Xưởng Cơ Khí)', 'sales', 1, 0, 0, None, now_str, now_str),
        (4, 'nhanvien3@demo.vn', 'nhanvien3@demo.vn', '0912345673', pw_hash, salt, 'Lê Văn Hoàng (KD 03 - Đại Lý & Phụ Kiện)', 'sales', 1, 0, 0, None, now_str, now_str),
    ]
    cur.executemany('''
    INSERT INTO users (id, username, email, phone, password_hash, salt, full_name, role, is_active, must_change_password, failed_attempts, locked_until, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', users_data)

    # Insert Employee Profiles
    profiles_data = [
        (1, 1, 'GD-01', '1985-05-18', 'Nam', '031085001234', 'Ngô Quyền, Hải Phòng', '2020-01-01', 'Tổng Giám Đốc', 'HĐ Không thời hạn', 500000000, 'Điều hành chung toàn bộ tổng kho', '#3B5BFF'),
        (2, 2, 'KD-01', '1995-09-12', 'Nữ', '031195009876', 'Lê Chân, Hải Phòng', '2023-02-15', 'Chuyên viên Kinh doanh M&E', 'HĐ 3 năm', 180000000, 'Chuyên phát triển thầu cơ điện PCCC, nhà xưởng', '#10B981'),
        (3, 3, 'KD-02', '1993-11-20', 'Nam', '031193005544', 'Kiến An, Hải Phòng', '2022-08-01', 'Chuyên viên Kinh doanh Cơ khí', 'HĐ 3 năm', 160000000, 'Phụ trách khách xưởng gia công chế tạo kết cấu', '#F59E0B'),
        (4, 4, 'KD-03', '1998-04-05', 'Nam', '031198007788', 'Thủy Nguyên, Hải Phòng', '2024-03-01', 'Chuyên viên Phát triển Đại lý', 'HĐ 1 năm', 120000000, 'Phát triển chuỗi cửa hàng kim khí các huyện và tỉnh lân cận', '#8B5CF6'),
    ]
    cur.executemany('''
    INSERT INTO employee_profiles (id, user_id, code, dob, gender, cccd, address, start_date, position, contract_type, monthly_target, notes, avatar_color)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', profiles_data)

    # Insert Message Templates (Kịch bản chăm sóc theo 4 mốc & loại khách)
    templates_data = [
        (
            '5d', 'Mốc 5 ngày (Kiểm tra hàng & Trải nghiệm)', 'Tất cả',
            'Kịch bản 5 ngày - Chuẩn công ty',
            'Chào anh/chị {ten_khach}, em là {ten_nhan_vien} bên {ten_cong_ty}. Đơn hàng {ma_don} anh/chị nhận cách đây 5 ngày (giao ngày {ngay_giao}), không biết hàng dùng có ổn không ạ? Ren bulong siết có êm tay không anh? Cần bổ sung gì anh/chị cứ nhắn em hỗ trợ ngay nhé ạ!'
        ),
        (
            '5d', 'Mốc 5 ngày (Thầu công trình & PCCC)', 'Thầu công trình',
            'Kịch bản 5 ngày - Thầu công trình',
            'Dạ em chào anh {ten_khach}, em {ten_nhan_vien} bên {ten_cong_ty} ạ. Lô hàng bulong nở rút và ty ren đơn {ma_don} giao chân công trình hôm {ngay_giao} thợ thi công lắp ráp thuận lợi không anh? Nếu công trình cần thêm chứng chỉ chất lượng CO/CQ bản cứng hoặc giao bù số lượng phát sinh thì anh ới em chuyển hỏa tốc ngay nhé ạ!'
        ),
        (
            '7d', 'Mốc 7 ngày (Hỏi thăm tiến độ & Hao hụt)', 'Tất cả',
            'Kịch bản 7 ngày - Chuẩn công ty',
            'Em chào anh/chị {ten_khach}, em {ten_nhan_vien} bên {ten_cong_ty}. Tuần vừa rồi anh/chị triển khai công việc với lô vật tư {ma_don} thế nào rồi ạ? Hàng họ có hao hụt gì không anh? Kho bên em đang sẵn rất nhiều quy cách mới xuất kho ngay trong ngày, nếu chuẩn bị vào đợt mới anh nhắn em gửi giá tốt nhé!'
        ),
        (
            '7d', 'Mốc 7 ngày (Xưởng cơ khí)', 'Xưởng cơ khí',
            'Kịch bản 7 ngày - Xưởng gia công',
            'Anh {ten_khach} ơi, em {ten_nhan_vien} Long Zhuang đây ạ. Lô bulong lục giác chìm 8.8 và inox 304 anh lấy hôm {ngay_giao} đưa lên đồ gá gia công ăn ren chuẩn chứ anh? Xưởng mình đợt này có nhận thêm đơn gia công kết cấu mới nào không để em giữ giá xuất kho ưu đãi cho xưởng mình nhé!'
        ),
        (
            '15d', 'Mốc 15-20 ngày (Dự toán đợt 2 & Bổ sung)', 'Tất cả',
            'Kịch bản 15-20 ngày - Chuẩn công ty',
            'Chào anh {ten_khach}, em {ten_nhan_vien} bên {ten_cong_ty}. Nửa tháng vừa rồi công trình bên mình tiến độ chắc đã sang hạng mục tiếp theo rồi anh nhỉ? Đơn {ma_don} đợt trước vật tư sắp hết chưa anh? Anh gửi em bảng dự toán vật tư đợt tới để em tính chiết khấu tốt nhất cho mình nhé!'
        ),
        (
            '15d', 'Mốc 15-20 ngày (Đại lý kim khí)', 'Đại lý',
            'Kịch bản 15 ngày - Nhập hàng đại lý',
            'Chị {ten_khach} ơi, lô bulong đai ốc thùng bên em giao đợt {ngay_giao} bán chạy không chị? Các mã thông dụng M6, M8, M10 cửa hàng có bị đứt mẫu nào không để em xếp chuyến xe tải ghép đơn chuyển sang Bắc Ninh / Hải Phòng luôn trong tuần này chị nhé!'
        ),
        (
            '30d', 'Mốc 30 ngày (Chăm sóc định kỳ tháng & Tái mua)', 'Tất cả',
            'Kịch bản 30 ngày - Chuẩn công ty',
            'Em chào anh {ten_khach}, em {ten_nhan_vien} bên {ten_cong_ty} ạ. Tròn 1 tháng kể từ đơn hàng {ma_don}, em xin phép hỏi thăm tình hình công việc và dự án bên mình tháng này thế nào rồi ạ? Tháng này kho Long Zhuang có chương trình tri ân khách hàng thân thiết chiết khấu thêm 3-5% cho đơn thầu, anh có nhu cầu lấy thêm vật tư gì không ạ?'
        ),
        (
            '30d', 'Mốc 30 ngày (Khách lâu ngày chưa mua lại)', 'Tất cả',
            'Kịch bản 30 ngày - Hâm nóng khách cũ',
            'Anh {ten_khach} ơi, đợt này bên mình có vào dự án cơ điện hay lắp ráp nhà xưởng nào mới không anh? Kho Long Zhuang bên em vừa về container hàng bulong ốc vít đủ size inox 304 và mạ kẽm nhúng nóng giá tại kho cực tốt. Em gửi anh bảng báo giá mới nhất để anh tham khảo làm dự toán nhé ạ!'
        )
    ]
    cur.executemany('''
    INSERT INTO message_templates (milestone_code, milestone_title, customer_type, title, content)
    VALUES (?, ?, ?, ?, ?)
    ''', templates_data)

    # 42 Khách hàng thực tế ngành kim khí Hải Phòng & miền Bắc
    customers_raw = [
        # (full_name, phone, address, customer_type, source, stage, demand, assigned_user_id, status, notes, days_ago_created)
        ('Anh Tuấn - Thầu M&E Vinhomes', '0988123456', 'Khu đô thị Vinhomes Imperia, Hồng Bàng, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách cũ', '5.000 bộ Bulong lục giác chìm DIN 912 Inox 304 M8x30 + Ecu + Long đền', 2, 'Đã chốt đơn', 'Khách quen lấy đều cho các căn biệt thự M&E', 35),
        ('Anh Hùng - Xưởng Cơ Khí Hoàng Mai', '0977654321', 'Cụm CN Hoàng Mai, Kiến An, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách cũ', 'Thanh ren suốt mạ kẽm cấp bền 8.8 M10 x 1000mm và nở đạn M10', 3, 'Đã giao', 'Xưởng chuyên gia công kết cấu khung thép tiền chế', 22),
        ('Chị Mai - Đại Lý Kim Khí Yên Phong', '0912987654', 'Ngã tư Đông Yên, Yên Phong, Bắc Ninh', 'Đại lý', 'Đến trực tiếp', 'Khách cũ', 'Lấy sỉ theo bao tải bulong đầu tròn cổ vuông M8, M10, M12 mạ kẽm', 4, 'Đã giao', 'Đại lý lớn phân phối cho thợ xây dựng và xưởng gỗ', 16),
        ('Anh Quyết - Nhà Thầu PCCC Tràng Duệ', '0965333888', 'KCN Tràng Duệ, An Dương, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách cũ', 'Bulong nở rút inox M12x100, quang treo ống nước PCCC, kẹp xà gồ', 2, 'Đã giao', 'Thi công nhà xưởng LG Electronics, yêu cầu chứng chỉ CO/CQ chuẩn', 8),
        ('Anh Minh - Cửa Hàng Kim Khí Thủy Nguyên', '0934112233', 'Thị trấn Núi Đèo, Thủy Nguyên, Hải Phòng', 'Cửa hàng', 'Giới thiệu', 'Khách cũ', 'Vít tự khoan đầu giác bọc cao su chống dột, vít bắn tôn mạ kẽm 5x50', 4, 'Đã giao', 'Cửa hàng bán rất chạy các dòng ốc vít lợp mái tôn mùa mưa bão', 6),
        ('Anh Dũng - Xưởng Chế Tạo Máy Đình Vũ', '0945223344', 'Khu kinh tế Đình Vũ, Hải An, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách cũ', 'Bulong cường độ cao 10.9 M16x80, M20x100 dùng cho máy nén ép', 3, 'Đã giao', 'Yêu cầu thép đặc chủng chịu lực va đập lớn', 28),
        ('Anh Thắng - Thầu Lắp Dựng Nam Sách', '0983115599', 'Cụm CN Nam Sách, Hải Dương', 'Thầu công trình', 'Khách lẻ', 'Khách cũ', 'Bản mã 200x200x10mm và bulong neo móng bẻ L M24x800', 2, 'Đã giao', 'Đang đổ sàn móng xưởng dệt may đợt 1', 32),
        ('Chị Lan - Cửa Hàng Điện Nước Kiến Thụy', '0978998811', 'Ngã ba Đoàn Xá, Kiến Thụy, Hải Phòng', 'Cửa hàng', 'Đến trực tiếp', 'Khách cũ', 'Tắc kê nhựa, vít bắt gỗ đầu dù bake, đinh bê tông các size', 4, 'Đã giao', 'Cửa hàng nông thôn tiêu thụ đều hàng dân dụng hàng tháng', 45),
        ('Anh Sơn - Cơ Khí Tàu Biển Bến Kiền', '0904123888', 'Gần nhà máy đóng tàu Bến Kiền, Thủy Nguyên, HP', 'Xưởng cơ khí', 'Giới thiệu', 'Khách cũ', 'Bulong inox 316 kháng muối biển M12x60, ecu hãm chống rung', 3, 'Đã giao', 'Khách hàng phân khúc cao cấp đóng mới tàu dịch vụ sông biển', 19),
        ('Anh Khang - Thầu Nhôm Kính Tiên Lãng', '0915667788', 'Thị trấn Tiên Lãng, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách cũ', 'Vít inox bắt hệ mặt dựng nhôm xingfa 4.2x38 và ke góc nhôm', 2, 'Đã giao', 'Đang hoàn thiện dự án nhà văn hóa huyện', 12),
        ('Anh Bách - Đại Lý Bulong Thái Bình', '0982554433', 'Đường Lý Bôn, TP. Thái Bình', 'Đại lý', 'Đến trực tiếp', 'Khách cũ', 'Đơn buôn 3 tấn bulong lục giác đen cấp bền 4.6 và 8.8 M8 đến M16', 4, 'Hoàn tất', 'Đại lý ruột lấy hàng định kỳ 2 tuần một chuyến xe tải 5 tấn', 65),
        ('Anh Cường - Xưởng Hàn Cắt An Lão', '0936778899', 'Thị trấn An Lão, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách cũ', 'Đá mài, đá cắt kim loại Hải Dương và que hàn KT-421 3.2mm', 3, 'Hoàn tất', 'Xưởng gia công cổng sắt mỹ thuật và lan can ban công', 50),
        ('Anh Phát - Thầu Hạ Tầng Vsip Hải Phòng', '0968112244', 'KCN VSIP Hải Phòng, Thủy Nguyên', 'Thầu công trình', 'Fanpage', 'Khách cũ', 'Bulong mạ kẽm nhúng nóng M14x50 dùng cho hệ giàn năng lượng áp mái', 2, 'Đã giao', 'Dự án điện mặt trời mái nhà kho xưởng ngoại quan', 5),
        ('Chị Hoa - Kim Khí Tổng Hợp Quảng Ninh', '0973224466', 'Cột 5, Phường Hồng Hà, TP. Hạ Long, Quảng Ninh', 'Đại lý', 'Giới thiệu', 'Khách cũ', 'Ốc siết cáp inox, tăng đơ 2 đầu tròn mạ kẽm, ma ní cẩu hàng', 4, 'Đã giao', 'Bán lẻ vật tư cho các tàu du lịch vịnh Hạ Long', 25),
        ('Anh Đại - Xưởng Bồn Bể Áp Lực Quán Toan', '0989334455', 'Ngã tư Quán Toan, Hồng Bàng, Hải Phòng', 'Xưởng cơ khí', 'Đến trực tiếp', 'Khách cũ', 'Bulong mặt bích tiêu chuẩn JIS 10K / ANSI B16.5 size M16x70', 3, 'Đã giao', 'Gần kho Long Zhuang nên thường xuyên tự cho xe lôi ra bốc hàng', 7),
        ('Anh Triều - Thầu Nội Thất Chung Cư Hoàng Huy', '0913889900', 'Hoàng Huy Commerce, Lê Chân, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách cũ', 'Ốc liên kết cam gỗ, vít bake ren thưa bắt gỗ MDF, bản lề hơi', 2, 'Hoàn tất', 'Thi công 40 căn hộ mẫu tòa tháp Sakura', 70),
        ('Anh Nghĩa - Xưởng Ép Cọc Bê Tông Thủy Nguyên', '0906223311', 'Xã Lưu Kiếm, Thủy Nguyên, Hải Phòng', 'Xưởng cơ khí', 'Giới thiệu', 'Khách cũ', 'Bulong đầu chìm nối cọc ly tâm M20 và keo cấy thép Ramset G5', 3, 'Đã giao', 'Xưởng ép cọc công trình nền móng cầu đường', 18),
        ('Chị Ngân - Cửa Hàng Vật Tư Đồ Sơn', '0979445566', 'Phường Vạn Hương, Quận Đồ Sơn, Hải Phòng', 'Cửa hàng', 'Khách lẻ', 'Khách cũ', 'Bulong lục giác chìm inox chống han rỉ cho các nhà hàng ven biển', 4, 'Đã giao', 'Khu du lịch Đồ Sơn ven biển chuộng hàng inox 304 không rỉ', 21),
        ('Anh Duy - Nhà Thầu Cơ Điện Royal Island Vũ Yên', '0981992233', 'Đảo Vũ Yên, Thủy Nguyên, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách cũ', '10.000 cây ty ren suốt M10 và 20.000 đai treo quả trám', 2, 'Đã giao', 'Dự án đại đô thị đảo nghỉ dưỡng lớn nhất Hải Phòng, tiềm năng cực cao', 4),
        ('Anh Việt - Xưởng Xe Nâng Cơ Khí Lê Chân', '0932556677', 'Đường Nguyễn Văn Linh, Lê Chân, Hải Phòng', 'Xưởng cơ khí', 'Đến trực tiếp', 'Khách cũ', 'Bulong cấp bền 12.9 chuyên siết moay-ơ và bánh răng xe nâng', 3, 'Hoàn tất', 'Thợ sửa chữa xe nâng công nghiệp chuyên nghiệp', 90),

        # Khách tiềm năng (chưa mua hoặc đang tư vấn/báo giá)
        ('Anh Hải - Thầu Xây Dựng KCN Nam Đình Vũ', '0984123999', 'KCN Nam Đình Vũ, Hải An, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách tiềm năng', 'Khảo sát báo giá 50.000 con vít bắn tôn chống bão mạ kẽm nhúng nóng', 2, 'Đã báo giá', 'Đang đợi chủ đầu tư duyệt dự toán thầu mái tôn xưởng 20.000m2', 3),
        ('Anh Giang - Xưởng Sản Xuất Thang Máng Cáp', '0975667799', 'Cụm CN Tân Liên, Vĩnh Bảo, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách tiềm năng', 'Bulong đầu tròn cổ vuông mạ kẽm điện phân M8x15 số lượng 10 vạn con', 3, 'Đang tư vấn', 'Đã gửi hàng mẫu đến xưởng test độ khớp lỗ dập thang cáp', 5),
        ('Chị Vân - Đại Lý Điện Nước Phù Cừ', '0916334455', 'Thị trấn Phù Cừ, Hưng Yên', 'Đại lý', 'Đến trực tiếp', 'Khách tiềm năng', 'Hỏi chính sách đại lý cấp 1 và chiết khấu công nợ 30 ngày', 4, 'Khách phân vân', 'Muốn công ty cho nợ gối đầu mới nhập, Sếp đang xem xét duyệt', 9),
        ('Anh Trung - Thầu PCCC Bệnh Viện Kiến An', '0987112233', 'Đường Trần Tất Văn, Kiến An, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách tiềm năng', 'Nở đạn M12 inox 304 và thanh ren treo hệ thống chữa cháy khí FM200', 2, 'Mới nhận', 'Lead nóng vừa đăng ký form Facebook Ads sáng nay', 1),
        ('Anh Tuấn Anh - Gia Công Inox An Dương', '0903887766', 'KCN An Dương, Hải Phòng', 'Xưởng cơ khí', 'Giới thiệu', 'Khách tiềm năng', 'Bulong lục giác chìm đầu dù M5, M6 inox 304 lắp vỏ tủ điện xuất khẩu', 3, 'Đang tư vấn', 'Yêu cầu dung sai ren 6g chuẩn quốc tế', 4),
        ('Anh Bình - Thầu Trần Thạch Cao Cát Bi', '0935221144', 'Gần sân bay Cát Bi, Hải An, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách tiềm năng', 'Ty treo trần M8x1000 và nở rút sắt M8 chuyên dụng bắn súng hơi', 2, 'Đã báo giá', 'Hẹn chiều mai chốt lấy trước 2.000 cây', 2),
        ('Chị Thảo - Cửa Hàng Phụ Kiện Kim Khí An Lão', '0974998833', 'Ngã tư Quang Thanh, An Lão, Hải Phòng', 'Cửa hàng', 'Khách lẻ', 'Khách tiềm năng', 'Báo giá vít bắn gỗ đầu bằng ren thưa và đinh tán nhôm', 4, 'Đang tư vấn', 'Cửa hàng đang chuẩn bị khai trương thêm cơ sở 2', 7),
        ('Anh Trọng - Cơ Khí Lắp Máy Tiêu Chuẩn', '0985443322', 'KCN Đồng Hòa, Kiến An, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách tiềm năng', 'Bulong vòng cẩu mắt DIN 580 M12, M16 nâng hạ động cơ điện', 3, 'Mới nhận', 'Cần bảng thông số tải trọng an toàn SWL', 1),
        ('Anh Vũ - Thầu Thi Công Nhà Thép Tiền Chế', '0912445577', 'Xã Kiến Thiết, Tiên Lãng, Hải Phòng', 'Thầu công trình', 'Giới thiệu', 'Khách tiềm năng', 'Bulong kết cấu thép ASTM A325 M22x75 kèm đai ốc 2H', 2, 'Khách phân vân', 'So sánh giá với bên kho Hà Nội, đang giải thích lợi thế sẵn kho Hải Phòng', 6),
        ('Anh Lâm - Thợ Cơ Điện Lạnh Thủy Nguyên', '0948332211', 'Xã Hòa Bình, Thủy Nguyên, Hải Phòng', 'Khách lẻ', 'Fanpage', 'Khách tiềm năng', 'Bulong gắn chân máy điều hòa multi VRV và lò xo giảm chấn', 1, 'Mới nhận', 'Sếp phân bổ cho nhân viên KD 01', 2),
        ('Chị Yến - Cửa Hàng Ốc Vít Uông Bí', '0976112233', 'Thành phố Uông Bí, Quảng Ninh', 'Cửa hàng', 'Đến trực tiếp', 'Khách tiềm năng', 'Hỏi giá xe tải giao tận cửa hàng các loại vít tự khoan', 4, 'Đang tư vấn', 'Cách kho khoảng 35km, có thể ghép chuyến xe giao', 8),
        ('Anh Thể - Xưởng Cắt CNC Laser Hải Phòng', '0908776655', 'Đường Nguyễn Bỉnh Khiêm, Hải An, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách tiềm năng', 'Tán rút inox (ecu rút) M6, M8 và kìm tán rút dùng hơi khí nén', 3, 'Đã báo giá', 'Đã báo giá bộ kìm và 5.000 con tán rút', 3),
        ('Anh Lợi - Thầu Lắp Camera & Điện Nhẹ', '0986774411', 'Quận Hồng Bàng, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách tiềm năng', 'Vít nở thạch cao bướm nhựa và đai kẹp ống luồn dây ruột gà', 2, 'Mới nhận', 'Dự án thi công hệ thống mạng trường liên cấp', 1),
        ('Anh Đạt - Xưởng Chế Tạo Băng Tải Con Lăn', '0914998800', 'Đường Máng Nước, An Dương, Hải Phòng', 'Xưởng cơ khí', 'Đến trực tiếp', 'Khách tiềm năng', 'Vòng bi con lăn, bulong đầu nấm M10 siết thanh chắn băng chuyền', 3, 'Đang tư vấn', 'Khách đã ghé kho trực tiếp xem mẫu hôm thứ Hai', 4),
        ('Chị Quyên - Tổng Đại Lý Kim Khí Tiền Hải', '0972334488', 'Thị trấn Tiền Hải, Thái Bình', 'Đại lý', 'Giới thiệu', 'Khách tiềm năng', 'Báo giá 1 côngtenơ bulong inox 201 và 304', 4, 'Khách phân vân', 'Dự kiến tháng sau mở kho mới tại thị trấn', 11),
        ('Anh Thuận - Thầu Thi Công Biển Bảng Quảng Cáo', '0937665544', 'Lê Hồng Phong, Ngô Quyền, Hải Phòng', 'Khách lẻ', 'Fanpage', 'Khách tiềm năng', 'Tắc kê khung sắt hộp, vít bắn tôn đầu bake mạ niken sáng', 1, 'Mới nhận', 'Lấy số lượng vài trăm con mỗi công trình', 2),
        ('Anh Sang - Xưởng Mộc & Sofa Cao Cấp', '0981223388', 'Phù Liễn, Kiến An, Hải Phòng', 'Xưởng cơ khí', 'Khách lẻ', 'Khách tiềm năng', 'Bulong lục giác chìm cấy gỗ, ốc liên kết ren lửng', 3, 'Đang tư vấn', 'Xưởng nội thất gỗ tự nhiên', 7),
        ('Anh Hào - Thầu Sửa Chữa Cầu Cảng Hải Phòng', '0902446688', 'Cảng Chùa Vẽ, Đông Hải, Hải An, HP', 'Thầu công trình', 'Giới thiệu', 'Khách tiềm năng', 'Bulong neo chữ J mạ kẽm nhúng nóng M30x1000 chịu lực lớn', 2, 'Đã báo giá', 'Dự án đại tu cầu cảng bến số 3', 5),
        ('Chị Dung - Đại Lý Sơn & Kim Khí Kim Thành', '0918776655', 'Huyện Kim Thành, Hải Dương', 'Đại lý', 'Đến trực tiếp', 'Khách tiềm năng', 'Bảng giá sỉ bulong ren suốt và nở sắt các kích cỡ', 4, 'Mới nhận', 'Khách qua kho lấy catalogue và bảng giá', 1),
        ('Anh Tuấn Kiệt - Xưởng Đúc Gang Đóng Mát', '0971556677', 'Mỹ Đức, An Lão, Hải Phòng', 'Xưởng cơ khí', 'Fanpage', 'Khách tiềm năng', 'Bulong lục giác chìm đầu trụ cấp bền 10.9 M24 chịu nhiệt độ cao', 3, 'Đang tư vấn', 'Đang đợi xưởng thử nghiệm độ bền kéo', 6),
        ('Anh Sơn Bách - Nhà Thầu Cơ Điện PCCC Cát Bà', '0983664422', 'Thị trấn Cát Bà, Cát Hải, Hải Phòng', 'Thầu công trình', 'Fanpage', 'Khách tiềm năng', 'Ty ren mạ kẽm nhúng nóng và bulong nở inox chống muối mặn Cát Bà', 2, 'Đã báo giá', 'Hẹn tuần tới ra đảo thi công sẽ chốt tạm ứng', 3),
        ('Anh Trí - Khách Tự Sửa Chữa Cơ Khí Nhà Xưởng', '0938114477', 'Đường Tôn Đức Thắng, An Dương, HP', 'Khách lẻ', 'Fanpage', 'Khách tiềm năng', 'Cần 200 bộ bulong ecu M12x40 và 50 con nở rút inox', 1, 'Mới nhận', 'Khách lẻ tự làm xưởng gia đình', 1)
    ]

    cust_insert_data = []
    for idx, c in enumerate(customers_raw, 1):
        c_time = (now - timedelta(days=c[10])).strftime("%Y-%m-%d %H:%M:%S")
        cust_insert_data.append((
            idx, c[0], c[1], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8],
            (now - timedelta(days=c[10]//2)).strftime("%Y-%m-%d %H:%M:%S") if c[5] == 'Khách cũ' else None,
            now.strftime("%Y-%m-%d"),
            c[9], c_time, now_str
        ))

    cur.executemany('''
    INSERT INTO customers (
        id, full_name, phone, zalo, address, customer_type, source, stage, demand, assigned_user_id, status, last_contacted_at, next_followup_at, notes, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', cust_insert_data)

    # 25 Đơn hàng mẫu
    orders_raw = [
        # (order_code, customer_id, user_id, days_ago_order, days_ago_delivery, total_amount, items_text, status, notes)
        ('DH-LZ-2601', 1, 2, 35, 34, 18500000, '5.000 bộ Bulong lục giác chìm DIN 912 Inox 304 M8x30\n5.000 con Ecu Inox 304 M8\n10.000 con Long đền phẳng inox 304 M8', 'Hoàn tất', 'Giao tới chân công trình Vinhomes Imperia'),
        ('DH-LZ-2602', 2, 3, 22, 21, 24600000, '1.200 cây Thanh ren suốt M10 x 1000mm mạ kẽm 8.8\n2.400 con Nở đạn mạ kẽm M10\n4.800 con Ecu mạ kẽm M10', 'Đã giao', 'Xưởng nhận đủ hàng, đang chạy tiến độ'),
        ('DH-LZ-2603', 3, 4, 16, 15, 36800000, '30 bao Bulong đầu tròn cổ vuông mạ kẽm M8x40 (50kg/bao)\n20 bao Bulong cổ vuông M10x50\n50 bao Ecu mạ kẽm các loại', 'Đã giao', 'Chuyến xe tải ghép đơn sang Yên Phong Bắc Ninh'),
        ('DH-LZ-2604', 4, 2, 8, 7, 15200000, '2.000 con Bulong nở rút inox 304 M12x100\n500 cái Kẹp xà gồ treo ty M10\n1.000 bộ Đai treo quả trám D60', 'Đã giao', 'Kèm chứng chỉ CO/CQ và hóa đơn VAT'),
        ('DH-LZ-2605', 5, 4, 6, 5, 9400000, '10 vạn Vít tự khoan đầu giác mạ kẽm 5x50 có đệm cao su\n5 vạn Vít bắn tôn 5x35 chống bão', 'Đã giao', 'Giao cửa hàng kim khí Núi Đèo'),
        ('DH-LZ-2606', 6, 3, 28, 27, 42000000, '800 bộ Bulong cường độ cao cấp bền 10.9 M16x80\n500 bộ Bulong 10.9 M20x100\n1.300 con Đai ốc tự hãm 10.9', 'Đã giao', 'Lắp máy ép thủy lực KCN Đình Vũ'),
        ('DH-LZ-2607', 7, 2, 32, 31, 28500000, '120 tấm Bản mã 200x200x10mm dập 4 lỗ\n480 bộ Bulong neo móng bẻ L M24x800 kèm 2 ecu', 'Đã giao', 'Xưởng dệt may Nam Sách Hải Dương'),
        ('DH-LZ-2608', 8, 4, 45, 44, 7800000, '20 thùng Tắc kê nhựa số 6 và số 8\n50 hộp Vít bắt gỗ đầu dù bake 4x40\n10 bao Đinh bê tông 5cm', 'Hoàn tất', 'Giao xe buýt chạy tuyến Đồ Sơn - Kiến Thụy'),
        ('DH-LZ-2609', 9, 3, 19, 18, 55000000, '1.500 bộ Bulong inox 316 kháng muối biển M12x60\n1.500 con Ecu hãm nylon inox 316 M12\n3.000 con Long đền vênh inox 316', 'Đã giao', 'Phục vụ đóng mới tàu du lịch vịnh Lan Hạ'),
        ('DH-LZ-2610', 10, 2, 12, 11, 11600000, '15 vạn Vít inox 410 tự khoan đầu bằng 4.2x38\n2.000 cái Ke góc nhôm xingfa đúc định hình', 'Đã giao', 'Hoàn thiện hệ mặt dựng nhôm kính'),
        ('DH-LZ-2611', 11, 4, 65, 64, 118000000, '3 tấn Bulong lục giác đen cấp bền 8.8 M8 đến M16\n1 tấn Đai ốc đen 8.8\n500kg Vòng đệm phẳng và vênh', 'Hoàn tất', 'Đại lý Thái Bình - Chuyến xe 5 tấn xuất kho'),
        ('DH-LZ-2612', 12, 3, 50, 49, 14200000, '50 hộp Đá cắt kim loại Hải Dương 355mm\n30 thùng Que hàn KT-421 Kim Tín 3.2mm\n500 cái Khóa cáp thép', 'Hoàn tất', 'Xưởng cơ khí An Lão'),
        ('DH-LZ-2613', 13, 2, 5, 4, 38900000, '3.500 bộ Bulong mạ kẽm nhúng nóng M14x50 cấp bền 5.6\n3.500 con Long đền phẳng mạ kẽm nhúng nóng dày 3mm', 'Đã giao', 'Lắp giàn pin năng lượng mái xưởng VSIP'),
        ('DH-LZ-2614', 14, 4, 25, 24, 21500000, '200 cái Ma ní cẩu hàng Omega mạ kẽm 3.25 tấn\n100 bộ Tăng đơ 2 đầu tròn M16\n500 con Ốc siết cáp phi 14', 'Đã giao', 'Cửa hàng Hồng Hà TP Hạ Long'),
        ('DH-LZ-2615', 15, 3, 7, 6, 16800000, '300 bộ Bulong mặt bích JIS 10K M16x70 thép mạ điện phân\n300 bộ Bulong ANSI B16.5 M20x80 kèm gioăng amiang', 'Đã giao', 'Giao trực tiếp kho xưởng Quán Toan'),
        ('DH-LZ-2616', 16, 2, 70, 69, 13400000, '5 vạn Ốc cam liên kết 3 chi tiết cho gỗ công nghiệp\n10 vạn Vít ren thưa bắt gỗ 3.5x30 mạ vàng\n500 đôi Bản lề hơi giảm chấn inox 304', 'Hoàn tất', 'Thi công 40 căn hộ Hoàng Huy'),
        ('DH-LZ-2617', 17, 3, 18, 17, 48000000, '2.000 con Bulong đầu chìm cọc ly tâm M20x90\n30 tuýp Keo cấy thép Ramset Epcon G5 Pro 585ml kèm súng bắn', 'Đã giao', 'Xưởng ép cọc Thủy Nguyên đổ nền móng'),
        ('DH-LZ-2618', 18, 4, 21, 20, 8900000, '600 bộ Bulong lục giác chìm inox 304 M10x40\n1.200 con Vít gỗ inox 304 5x60\n300 cái Bản lề cối inox chịu lực', 'Đã giao', 'Sửa chữa nhà hàng ven biển Đồ Sơn'),
        ('DH-LZ-2619', 19, 2, 4, 3, 62000000, '10.000 cây Ty ren suốt Inox 304 M10x1000mm\n20.000 con Đai treo ống quả trám D90 mạ kẽm\n20.000 con Ecu M10 inox 304', 'Đã giao', 'Dự án trọng điểm Đảo Vũ Yên Thủy Nguyên'),
        ('DH-LZ-2620', 1, 2, 2, 1, 8500000, '1.000 bộ Bulong neo bẻ J M20x600 mạ kẽm điện phân\n2.000 con Ecu mạ kẽm M20', 'Đã giao', 'Bổ sung móng cổng trục Vinhomes (đơn mới lặp lại của Anh Tuấn!)'),
        ('DH-LZ-2621', 21, 2, 3, None, 58000000, '50.000 con Vít bắn tôn chống bão mạ kẽm nhúng nóng 5.5x65\n50.000 con Long đền cao su EPDM chịu nhiệt', 'Đã báo giá', 'Chờ duyệt dự toán Nam Đình Vũ'),
        ('DH-LZ-2622', 22, 3, 5, None, 32000000, '10 vạn Bulong đầu tròn cổ vuông mạ kẽm M8x15 dập thang cáp\n10 vạn Ecu M8 mạ kẽm', 'Chốt', 'Đã nhận đặt cọc 20 triệu, đang chuẩn bị đóng bao'),
        ('DH-LZ-2623', 24, 2, 1, None, 12500000, '500 con Nở đạn inox 304 M12\n500 cây Thanh ren inox 304 M12x1000\n1.000 con Ecu inox 304 M12', 'Mới', 'Bệnh viện Kiến An yêu cầu báo gấp trong ngày'),
        ('DH-LZ-2624', 26, 2, 2, None, 9200000, '2.000 cây Ty treo trần thạch cao M8x1000\n4.000 con Nở sắt M8 đóng súng hơi', 'Đã báo giá', 'Hẹn chiều mai giao hàng'),
        ('DH-LZ-2625', 28, 3, 1, None, 6800000, '50 cái Bulong vòng mắt DIN 580 M16 mạ kẽm\n50 cái DIN 582 M16', 'Mới', 'Kiểm tra tải an toàn trước khi chốt')
    ]

    orders_insert_data = []
    for idx, o in enumerate(orders_raw, 1):
        o_date = (now - timedelta(days=o[3])).strftime("%Y-%m-%d")
        d_date = (now - timedelta(days=o[4])).strftime("%Y-%m-%d") if o[4] is not None else None
        orders_insert_data.append((
            idx, o[0], o[1], o[2], o_date, d_date, o[5], o[6], o[7], o[8],
            f"{o_date} 09:30:00", f"{o_date} 15:45:00"
        ))

    cur.executemany('''
    INSERT INTO orders (id, order_code, customer_id, user_id, order_date, delivery_date, total_amount, items_text, status, notes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', orders_insert_data)

    # 4 Mốc chăm sóc (Care Tasks) tự động sinh từ ngày giao hàng
    # Mốc: 5 ngày, 7 ngày, 15 ngày, 30 ngày
    # Trạng thái: 'Chưa đến hạn', 'Đến hạn hôm nay', 'Quá hạn', 'Đã chăm', 'Khách đã đặt lại'
    # Hãy tạo ra một phân bổ cực kỳ sinh động và thực tế:
    # - Đến hạn hôm nay (vàng/cam): 6 task
    # - Quá hạn (đỏ): 5 task (có 2 task quá hạn > 15 ngày để Sếp thấy cảnh báo)
    # - Đã chăm (xanh lá): 18 task
    # - Khách đã đặt lại (tím): 4 task (các mốc của đơn 1 bị hủy khi đơn 20 đặt lại!)
    # - Chưa đến hạn (xám): 14 task

    care_tasks_data = [
        # --- ĐƠN 1 (Khách Tuấn M&E - Đã chăm mốc 5d, 7d, 15d; mốc 30d bị huỷ thành 'Khách đã đặt lại' do có đơn 20!) ---
        (1, 1, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=29)).strftime("%Y-%m-%d"), 'Đã chăm', 'Khách cần báo giá', 'Khách khen ren siết êm, khớp đồ gá thi công m&e', 2, (now - timedelta(days=29, hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 1, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=27)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Hàng đủ dùng cho phân khu 1, chưa cần thêm', 2, (now - timedelta(days=27, hours=4)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 1, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now - timedelta(days=19)).strftime("%Y-%m-%d"), 'Đã chăm', 'Đã đặt đơn mới', 'Khách chuẩn bị đặt thêm lô bulong neo cổng trục', 2, (now - timedelta(days=19, hours=1)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 1, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now - timedelta(days=4)).strftime("%Y-%m-%d"), 'Khách đã đặt lại', 'Đã đặt đơn mới', 'Khách đã lên đơn DH-LZ-2620, chu kỳ chăm sóc mới bắt đầu', 2, (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")),

        # --- ĐƠN 20 (Đơn mới của khách Tuấn - Đang chạy chu kỳ mới) ---
        (20, 1, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now + timedelta(days=4)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (20, 1, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now + timedelta(days=6)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (20, 1, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=14)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (20, 1, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=29)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 2 (Khách Hùng - Giao 21 ngày trước) ---
        (2, 2, 3, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=16)).strftime("%Y-%m-%d"), 'Đã chăm', 'Chưa có nhu cầu', 'Đã nhận đủ hàng thanh ren 8.8', 3, (now - timedelta(days=16)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 2, 3, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=14)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Đang hàn khung kèo xưởng', 3, (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 2, 3, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now - timedelta(days=6)).strftime("%Y-%m-%d"), 'Quá hạn', '', 'Chưa gọi được khách, bận đi công trình (Quá hạn 6 ngày)', None, None),
        (2, 2, 3, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=9)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 3 (Chị Mai Đại Lý - Giao 15 ngày trước) -> Mốc 15d là ĐẾN HẠN HÔM NAY! ---
        (3, 3, 4, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=10)).strftime("%Y-%m-%d"), 'Đã chăm', 'Chưa có nhu cầu', 'Đại lý xếp hàng lên kệ đầy đủ', 4, (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")),
        (3, 3, 4, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=8)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Bán lẻ túc tắc cho thợ', 4, (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")),
        (3, 3, 4, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', today_str, 'Đến hạn hôm nay', '', 'Cần gọi hỏi thăm nhập thêm hàng thùng M8, M10', None, None),
        (3, 3, 4, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=15)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 4 (Anh Quyết PCCC Tràng Duệ - Giao 7 ngày trước) -> Mốc 7d là ĐẾN HẠN HÔM NAY! ---
        (4, 4, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=2)).strftime("%Y-%m-%d"), 'Đã chăm', 'Khách cần báo giá', 'Khách hỏi thêm kẹp xà gồ M12', 2, (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
        (4, 4, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', today_str, 'Đến hạn hôm nay', '', 'Hôm nay cần gọi kiểm tra số lượng bù kẹp xà gồ', None, None),
        (4, 4, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=8)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (4, 4, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=23)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 5 (Anh Minh Thủy Nguyên - Giao 5 ngày trước) -> Mốc 5d là ĐẾN HẠN HÔM NAY! ---
        (5, 5, 4, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', today_str, 'Đến hạn hôm nay', '', 'Kiểm tra đệm cao su vít tôn xem khách thử bắn có bị rách không', None, None),
        (5, 5, 4, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now + timedelta(days=2)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (5, 5, 4, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=10)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (5, 5, 4, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=25)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 15 (Anh Đại Quán Toan - Giao 6 ngày trước) -> Mốc 5d bị QUÁ HẠN 1 ngày! ---
        (15, 15, 3, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=1)).strftime("%Y-%m-%d"), 'Quá hạn', '', 'Quên chưa gọi hỏi bulong mặt bích JIS 10K', None, None),
        (15, 15, 3, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now + timedelta(days=1)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (15, 15, 3, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=9)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (15, 15, 3, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=24)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 10 (Anh Khang Nhôm Kính - Giao 11 ngày trước) -> Mốc 7d bị QUÁ HẠN 4 ngày! ---
        (10, 10, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=6)).strftime("%Y-%m-%d"), 'Đã chăm', 'Khách cần báo giá', 'Vít bắn êm, hỏi thêm ke góc nhôm 55', 2, (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")),
        (10, 10, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=4)).strftime("%Y-%m-%d"), 'Quá hạn', '', 'Hôm nay phải gọi bù gấp hỏi ke góc nhôm', None, None),
        (10, 10, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=4)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (10, 10, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=19)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 6 (Anh Dũng Đình Vũ - Giao 27 ngày trước) -> Mốc 15d QUÁ HẠN > 15 NGÀY (CẢNH BÁO CHO SẾP!) ---
        (6, 6, 3, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=22)).strftime("%Y-%m-%d"), 'Đã chăm', 'Chưa có nhu cầu', 'Đã nhận bulong 10.9', 3, (now - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")),
        (6, 6, 3, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=20)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Đang thử tải máy nén ép', 3, (now - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")),
        (6, 6, 3, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now - timedelta(days=12)).strftime("%Y-%m-%d"), 'Quá hạn', '', 'CẢNH BÁO: Quá hạn 12 ngày chưa liên hệ lại khách hàng VIP!', None, None),
        (6, 6, 3, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=3)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 7 (Anh Thắng Nam Sách - Giao 31 ngày trước) -> Mốc 30d QUÁ HẠN 1 ngày (HÔM QUA)! ---
        (7, 7, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now - timedelta(days=26)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Đang ghép cốt pha đổ móng', 2, (now - timedelta(days=26)).strftime("%Y-%m-%d %H:%M:%S")),
        (7, 7, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now - timedelta(days=24)).strftime("%Y-%m-%d"), 'Đã chăm', 'Chưa có nhu cầu', 'Hàng đủ dùng', 2, (now - timedelta(days=24)).strftime("%Y-%m-%d %H:%M:%S")),
        (7, 7, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now - timedelta(days=16)).strftime("%Y-%m-%d"), 'Đã chăm', 'Hẹn gọi lại', 'Đổ xong sàn đợt 1', 2, (now - timedelta(days=16)).strftime("%Y-%m-%d %H:%M:%S")),
        (7, 7, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now - timedelta(days=1)).strftime("%Y-%m-%d"), 'Quá hạn', '', 'Đến hạn chăm 30 ngày hỏi thăm đổ móng giai đoạn 2', None, None),

        # --- ĐƠN 13 (Anh Phát VSIP - Giao 4 ngày trước) -> Mốc 5d là ĐẾN HẠN NGÀY MAI (Sắp tới) ---
        (13, 13, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now + timedelta(days=1)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', 'Chuẩn bị hỏi thăm bulong nhúng nóng áp mái', None, None),
        (13, 13, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now + timedelta(days=3)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (13, 13, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=11)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (13, 13, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=26)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # --- ĐƠN 19 (Anh Duy Đảo Vũ Yên - Giao 3 ngày trước) -> Mốc 5d sắp tới ---
        (19, 19, 2, '5d', 5, 'Mốc 5 ngày: Hỏi thăm nhận hàng & kiểm tra ren', (now + timedelta(days=2)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', 'Hỏi thăm 1 vạn ty ren M10 và đai treo quả trám', None, None),
        (19, 19, 2, '7d', 7, 'Mốc 7 ngày: Hỏi thăm tiến độ & hao hụt', (now + timedelta(days=4)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (19, 19, 2, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', (now + timedelta(days=12)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),
        (19, 19, 2, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', (now + timedelta(days=27)).strftime("%Y-%m-%d"), 'Chưa đến hạn', '', '', None, None),

        # Thêm các task 'Đến hạn hôm nay' cho Nhân viên 2 & Nhân viên 3 để đủ 6 lịch hôm nay
        (9, 9, 3, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', today_str, 'Đến hạn hôm nay', '', 'Hôm nay gọi anh Sơn Cơ khí tàu biển hỏi lắp bulong 316', None, None),
        (14, 14, 4, '30d', 30, 'Mốc 30 ngày: Chăm sóc định kỳ tháng', today_str, 'Đến hạn hôm nay', '', 'Gọi chị Hoa Kim khí Hạ Long lấy thêm ma ní cẩu hàng', None, None),
        (17, 17, 3, '15d', 15, 'Mốc 15-20 ngày: Dự toán đợt 2 & bổ sung', today_str, 'Đến hạn hôm nay', '', 'Hỏi thăm xưởng cọc ép Ramset G5 hôm nay', None, None),
    ]

    care_tasks_insert = []
    for idx, ct in enumerate(care_tasks_data, 1):
        care_tasks_insert.append((
            idx, ct[0], ct[1], ct[2], ct[3], ct[4], ct[5], ct[6], ct[7], ct[8], ct[9], ct[10], ct[11],
            now_str, now_str
        ))

    cur.executemany('''
    INSERT INTO care_tasks (
        id, order_id, customer_id, assigned_user_id, milestone_code, milestone_days, milestone_title, scheduled_date, status, result_status, result_notes, cared_by_user_id, cared_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', care_tasks_insert)

    # 15 Lịch sử trao đổi tương tác mẫu (interactions)
    interactions_data = [
        (1, 2, 'Gọi điện', 'Gọi điện chào hỏi, gửi bảng báo giá chi tiết bulong inox M8 qua Zalo', 'Rất quan tâm', today_str, (now - timedelta(days=35)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 2, 'Nhắn Zalo', 'Khách xác nhận lấy 5.000 bộ M8x30, gửi hóa đơn thanh toán trước 50%', 'Đã chốt đơn', today_str, (now - timedelta(days=34)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 2, 'Gặp trực tiếp', 'Ghé chân công trình kiểm tra giao hàng và hỗ trợ thợ thử siết súng hơi', 'Hài lòng', today_str, (now - timedelta(days=29)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 3, 'Gọi điện', 'Gửi báo giá thanh ren M10 và nở đạn mạ kẽm', 'Quan tâm', today_str, (now - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")),
        (3, 4, 'Nhắn Zalo', 'Đại lý hỏi hàng thùng M8, M10. Gửi catalogue hình ảnh thực tế kho Hải Phòng', 'Rất quan tâm', today_str, (now - timedelta(days=16)).strftime("%Y-%m-%d %H:%M:%S")),
        (4, 2, 'Gọi điện', 'Báo giá gấp lô bulong nở rút inox cho nhà xưởng LG Tràng Duệ', 'Khẩn cấp', today_str, (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")),
        (6, 3, 'Gặp trực tiếp', 'Khách sang tổng kho Quán Toan xem mẫu bulong 10.9 và kiểm tra độ cứng', 'Tin tưởng', today_str, (now - timedelta(days=28)).strftime("%Y-%m-%d %H:%M:%S")),
        (19, 2, 'Nhắn Zalo', 'Chốt hợp đồng 10.000 cây ty ren M10 inox 304 công trình Vũ Yên', 'Đã chốt đơn', today_str, (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")),
        (21, 2, 'Gọi điện', 'Tư vấn loại vít chống bão tôn mạ kẽm nhúng nóng dày 5.5mm', 'Cần cân nhắc giá', today_str, (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")),
        (22, 3, 'Nhắn Zalo', 'Gửi hình ảnh mẫu bulong đầu tròn dập thang máng cáp', 'Đã ưng mẫu', today_str, (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    cur.executemany('''
    INSERT INTO interactions (customer_id, user_id, contact_type, content, reaction, next_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', interactions_data)

    # 15 Nhật ký hoạt động mẫu (Audit logs)
    audit_data = [
        (1, 'Phạm Hải Đăng (Sếp)', 'LOGIN', 'auth', '1', 'Đăng nhập thành công từ IP máy chủ văn phòng', '192.168.1.10', (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 'Nguyễn Thị Linh', 'LOGIN', 'auth', '2', 'Đăng nhập từ điện thoại iPhone (Safari)', '192.168.1.45', (now - timedelta(hours=2, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 'Nguyễn Thị Linh', 'CREATE', 'customer', '19', 'Tạo mới khách hàng Anh Duy - Nhà Thầu Cơ Điện Vũ Yên', '192.168.1.45', (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 'Nguyễn Thị Linh', 'CREATE', 'order', 'DH-LZ-2619', 'Tạo đơn hàng 62.000.000đ cho khách Anh Duy', '192.168.1.45', (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")),
        (2, 'Nguyễn Thị Linh', 'UPDATE', 'order', 'DH-LZ-2619', 'Cập nhật trạng thái đơn sang [Đã giao] -> Tự sinh 4 mốc chăm sóc', '192.168.1.45', (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")),
        (3, 'Trần Anh Tuấn', 'LOGIN', 'auth', '3', 'Đăng nhập từ máy tính làm việc', '192.168.1.22', (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
        (3, 'Trần Anh Tuấn', 'UPDATE', 'care_task', '10', 'Hoàn thành mốc chăm sóc 5 ngày khách Anh Dũng xưởng Đình Vũ', '192.168.1.22', (now - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")),
        (4, 'Lê Văn Hoàng', 'LOGIN', 'auth', '4', 'Đăng nhập hệ thống kinh doanh', '192.168.1.33', (now - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 'Phạm Hải Đăng (Sếp)', 'TRANSFER', 'customer', '20', 'Chuyển quyền quản lý khách Anh Lâm từ Sếp sang Nguyễn Thị Linh', '192.168.1.10', (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
        (1, 'Phạm Hải Đăng (Sếp)', 'VIEW', 'report', 'all', 'Xem báo cáo doanh thu và tỷ lệ chăm sóc đúng hạn toàn công ty', '192.168.1.10', (now - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    cur.executemany('''
    INSERT INTO audit_logs (user_id, user_name, action, entity_type, entity_id, details, ip_address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', audit_data)

    conn.commit()
    conn.close()
    print(">>> SEED DATABASE SUCCESSFUL! CRM LONG ZHUANG DATA READY!")

if __name__ == '__main__':
    seed()
