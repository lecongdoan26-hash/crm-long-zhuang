#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRM LONG ZHUANG - HỆ THỐNG QUẢN LÝ BÁN HÀNG & CHĂM SÓC KHÁCH HÀNG TỰ ĐỘNG
Công ty Tổng kho Bulong Ốc Vít & Kim Khí Long Zhuang Hải Phòng
Backend HTTP Server REST API (Chuẩn Python Standard Library, Không cần pip install)
Hỗ trợ bảo mật phiên đăng nhập, phân quyền máy chủ (RBAC), chống trùng SĐT, tự động tạo lịch chăm sóc.
"""

import http.server
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import socket
import socketserver
import json
import sqlite3
import os
import sys
import uuid
import shutil
import hashlib
import secrets
import urllib.parse
from datetime import datetime, timedelta
import threading
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 8099))
SECRET_KEY = os.environ.get("CRM_SECRET_KEY", "LONG_ZHUANG_CRM_PRODUCTION_SECRET_2026_HaiPhong")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR, exist_ok=True)

# Cấu hình phiên làm việc (8 giờ, lưu bền vững trong SQLite)
SESSION_EXPIRY_HOURS = 8

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn

def ensure_database_ready():
    """Tự động tạo cơ sở dữ liệu và dữ liệu mẫu nếu chưa có dữ liệu"""
    need_seed = False
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        need_seed = True
    else:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            row = cur.fetchone()
            conn.close()
            if not row:
                need_seed = True
        except Exception:
            need_seed = True

    if need_seed:
        try:
            print("[*] Đang khởi tạo dữ liệu mẫu CRM Long Zhuang ban đầu...")
            import seed_db
            seed_db.seed()
            print("[*] Đã khởi tạo dữ liệu mẫu thành công!")
        except Exception as e:
            print(f"[!] Lỗi khi tự động khởi tạo dữ liệu: {e}")

def init_system_tables():
    """Khởi tạo bảng sessions và cập nhật cột cần thiết để đảm bảo phiên bền vững khi restart server"""
    try:
        ensure_database_ready()
        conn = get_db()
        cur = conn.cursor()
        cur.execute('PRAGMA journal_mode = WAL;')
        # 1. Bảng lưu phiên đăng nhập bền vững
        cur.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_active TEXT NOT NULL,
            ip_address TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')

        # 2. Thêm cột must_change_password vào users nếu chưa có
        user_cols = [r[1] for r in cur.execute('PRAGMA table_info(users)').fetchall()]
        if 'must_change_password' not in user_cols:
            cur.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0')

        # 3. Thêm cột code vào employee_profiles nếu chưa có
        ep_cols = [r[1] for r in cur.execute('PRAGMA table_info(employee_profiles)').fetchall()]
        if 'code' not in ep_cols:
            cur.execute('ALTER TABLE employee_profiles ADD COLUMN code TEXT')

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[INIT DB ERROR] {e}")

init_system_tables()

def hash_pw(pw, salt=None):
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 100000)
    return hashed.hex(), salt.hex()

def verify_pw(pw, pw_hash, salt_hex):
    try:
        salt = bytes.fromhex(salt_hex)
        hashed = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(hashed.hex(), pw_hash)
    except Exception:
        return False

def normalize_phone(phone_str):
    if not phone_str:
        return ""
    cleaned = "".join([c for c in phone_str if c.isdigit() or c == '+'])
    if cleaned.startswith("+84"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("84") and len(cleaned) >= 11:
        cleaned = "0" + cleaned[2:]
    return cleaned

def log_audit(user_id, user_name, action, entity_type, entity_id, details, ip_address="127.0.0.1"):
    try:
        conn = get_db()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute('''
        INSERT INTO audit_logs (user_id, user_name, action, entity_type, entity_id, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_name, action, entity_type, str(entity_id), details, ip_address, now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")

def auto_daily_backup():
    """Tự động sao lưu database hàng ngày vào thư mục backups/"""
    while True:
        try:
            time.sleep(3600 * 6) # Kiểm tra mỗi 6 tiếng
            today_str = datetime.now().strftime("%Y%m%d")
            backup_file = os.path.join(BACKUP_DIR, f"crm_backup_{today_str}.db")
            if not os.path.exists(backup_file) and os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, backup_file)
                print(f"[BACKUP] Tự động tạo bản sao lưu: {backup_file}")
        except Exception as e:
            print(f"[BACKUP ERROR] {e}")

# Khởi chạy thread sao lưu ngầm
backup_thread = threading.Thread(target=auto_daily_backup, daemon=True)
backup_thread.start()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

class CRMRequestHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def send_json(self, data, status=200, headers=None):
        encoded = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-User-Id, X-Requested-With')
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-User-Id, X-Requested-With')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def get_client_ip(self):
        forwarded = self.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def get_current_user(self):
        auth_header = self.headers.get('Authorization', '')
        token = ""
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1].strip()
        
        if not token and 'Cookie' in self.headers:
            raw_cookie = self.headers.get('Cookie', '')
            for part in raw_cookie.split(';'):
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    if k.strip() == 'crm_session':
                        token = v.strip()
                        break

        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Tra cứu phiên bền vững trong bảng SQLite sessions
        if token:
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute('''
                SELECT s.token, s.expires_at, u.id, u.username, u.email, u.phone, u.full_name, u.role, u.is_active,
                       COALESCE(u.must_change_password, 0) as must_change_password,
                       COALESCE(ep.code, '') as code, COALESCE(ep.position, '') as position
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                LEFT JOIN employee_profiles ep ON u.id = ep.user_id
                WHERE s.token = ?
                ''', (token,))
                row = cur.fetchone()

                if row:
                    row_dict = dict(row)
                    if row_dict['is_active'] == 1 and row_dict['expires_at'] > now_str:
                        # Tự động gia hạn phiên thêm 8 giờ khi đang hoạt động
                        new_expires = (now + timedelta(hours=SESSION_EXPIRY_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
                        cur.execute("UPDATE sessions SET expires_at = ?, last_active = ? WHERE token = ?", (new_expires, now_str, token))
                        conn.commit()
                        conn.close()
                        return row_dict
                    else:
                        # Đã hết hạn hoặc tài khoản bị khóa -> Xóa phiên
                        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
                        conn.commit()
                conn.close()
            except Exception as e:
                print(f"[AUTH ERROR] {e}")

        # 2. Hỗ trợ header X-User-Id cho môi trường test
        user_id = self.headers.get('X-User-Id')
        if user_id:
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute('''
                SELECT u.id, u.username, u.email, u.phone, u.full_name, u.role, u.is_active,
                       COALESCE(u.must_change_password, 0) as must_change_password,
                       COALESCE(ep.code, '') as code, COALESCE(ep.position, '') as position
                FROM users u
                LEFT JOIN employee_profiles ep ON u.id = ep.user_id
                WHERE u.id = ?
                ''', (int(user_id),))
                row = cur.fetchone()
                conn.close()
                if row and row['is_active'] == 1:
                    return dict(row)
            except Exception:
                pass

        return None

    def require_auth(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"success": False, "message": "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại."}, status=401)
            return None
        return user

    def require_admin(self):
        user = self.require_auth()
        if not user:
            return None
        if user.get('role') != 'admin':
            self.send_json({"success": False, "message": "Bạn không có quyền quản trị (Chỉ dành cho Ban Giám Đốc)."}, status=403)
            return None
        return user

    def read_post_body(self):
        if getattr(self, '_cached_body', None) is not None:
            return self._cached_body
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            self._cached_body = {}
            return self._cached_body
        raw = self.rfile.read(length).decode('utf-8', errors='ignore')
        try:
            self._cached_body = json.loads(raw)
        except Exception:
            parsed = urllib.parse.parse_qs(raw)
            result = {}
            for k, v in parsed.items():
                result[k] = v[0] if isinstance(v, list) and len(v) > 0 else v
            self._cached_body = result
        return self._cached_body

    def do_GET(self):
        self._cached_body = None
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = urllib.parse.parse_qs(parsed.query)

            if path.startswith("/api/") or path == "/api":
                if path == "/api/status":
                    self.handle_status()
                    return
                elif path == "/api/me":
                    self.handle_me()
                    return
                elif path == "/api/dashboard":
                    self.handle_dashboard(params)
                    return
                elif path == "/api/customers":
                    self.handle_get_customers(params)
                    return
                elif path.startswith("/api/customers/"):
                    cust_id = path.replace("/api/customers/", "")
                    if cust_id.isdigit():
                        self.handle_get_customer_detail(int(cust_id))
                        return
                elif path == "/api/orders":
                    self.handle_get_orders(params)
                    return
                elif path == "/api/care_tasks":
                    self.handle_get_care_tasks(params)
                    return
                elif path == "/api/notifications":
                    self.handle_get_notifications()
                    return
                elif path == "/api/scripts":
                    self.handle_get_scripts(params)
                    return
                elif path == "/api/employees":
                    self.handle_get_employees()
                    return
                elif path == "/api/reports":
                    self.handle_get_reports(params)
                    return
                elif path == "/api/export_excel":
                    self.handle_export_excel()
                    return
                elif path == "/api/audit_logs":
                    self.handle_get_audit_logs(params)
                    return
                elif path == "/api/settings":
                    self.handle_get_settings()
                    return
                elif path == "/api/backup_db":
                    self.handle_download_backup()
                    return

                # BẮT BUỘC: Mọi route /api/* không tồn tại PHẢI trả về JSON 404, tuyệt đối không trả HTML!
                self.send_json({
                    "success": False,
                    "error": "Not Found",
                    "message": f"Endpoint API [{path}] không tồn tại trên hệ thống CRM."
                }, status=404)
                return

            super().do_GET()
        except Exception as e:
            if self.path.startswith("/api/") or self.path == "/api":
                self.send_json({"success": False, "error": "Server error", "message": f"Lỗi máy chủ API: {str(e)}"}, status=500)
            else:
                super().do_GET()

    def do_POST(self):
        self._cached_body = None
        try:
            # Luôn đọc cạn toàn bộ request body trước để tránh nghẽn socket HTTP keep-alive
            _ = self.read_post_body()
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/") or path == "/api":
                if path == "/api/login":
                    self.handle_login()
                    return
                elif path == "/api/logout":
                    self.handle_logout()
                    return
                elif path == "/api/change_password":
                    self.handle_change_password()
                    return
                elif path == "/api/customers/add":
                    self.handle_add_customer()
                    return
                elif path == "/api/customers/update":
                    self.handle_update_customer()
                    return
                elif path == "/api/customers/delete":
                    self.handle_delete_customer()
                    return
                elif path == "/api/customers/transfer":
                    self.handle_transfer_customer()
                    return
                elif path == "/api/customers/import_csv":
                    self.handle_import_csv()
                    return
                elif path == "/api/orders/add":
                    self.handle_add_order()
                    return
                elif path == "/api/orders/update":
                    self.handle_update_order()
                    return
                elif path == "/api/orders/delete":
                    self.handle_delete_order()
                    return
                elif path == "/api/care_tasks/complete":
                    self.handle_complete_care_task()
                    return
                elif path == "/api/scripts/save":
                    self.handle_save_script()
                    return
                elif path == "/api/scripts/delete":
                    self.handle_delete_script()
                    return
                elif path == "/api/scripts/render":
                    self.handle_render_script()
                    return
                elif path == "/api/employees/save":
                    self.handle_save_employee()
                    return
                elif path == "/api/employees/toggle_lock":
                    self.handle_toggle_lock_employee()
                    return
                elif path == "/api/employees/reset_password":
                    self.handle_reset_employee_password()
                    return
                elif path == "/api/settings/save":
                    self.handle_save_settings()
                    return

                self.send_json({
                    "success": False,
                    "error": "Not Found",
                    "message": f"Endpoint POST [{path}] không tồn tại trên hệ thống CRM."
                }, status=404)
                return

            self.send_json({"success": False, "error": "Not Found", "message": f"Đường dẫn [{path}] không tồn tại."}, status=404)
        except Exception as e:
            self.send_json({"success": False, "error": "Server error", "message": f"Lỗi POST: {str(e)}"}, status=500)

    # ==================== HANDLERS ====================

    def handle_status(self):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        settings_dict = dict(cur.fetchall())
        conn.close()

        user = self.get_current_user()
        today = datetime.now().strftime("%Y-%m-%d")
        self.send_json({
            "status": "online",
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "today": today,
            "company_name": settings_dict.get('company_name', 'TỔNG KHO BULONG ỐC VÍT LONG ZHUANG'),
            "brand_tagline": settings_dict.get('brand_tagline', 'Kim Khí & Vật Tư Cơ Điện M&E Hải Phòng'),
            "local_ip": get_local_ip(),
            "port": PORT,
            "logged_in": user is not None,
            "current_user": user
        })

    def handle_login(self):
        body = self.read_post_body()
        identifier = body.get('identifier', '').strip() # email, username, hoặc SĐT
        password = body.get('password', '').strip()
        ip = self.get_client_ip()

        if not identifier or not password:
            self.send_json({"success": False, "message": "Vui lòng nhập tài khoản (Email/SĐT) và mật khẩu."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        # Tìm user theo email, username hoặc số điện thoại
        clean_phone = normalize_phone(identifier)
        cur.execute('''
        SELECT id, username, email, phone, password_hash, salt, full_name, role, is_active, failed_attempts, locked_until,
               COALESCE(must_change_password, 0) as must_change_password
        FROM users
        WHERE email = ? OR username = ? OR phone = ? OR phone = ?
        ''', (identifier, identifier, identifier, clean_phone))
        row = cur.fetchone()

        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        if not row:
            conn.close()
            self.send_json({"success": False, "message": "Tài khoản hoặc mật khẩu không chính xác."}, status=400)
            return

        user_data = dict(row)

        # Kiểm tra tài khoản bị khóa bởi Sếp
        if user_data['is_active'] == 0:
            conn.close()
            self.send_json({"success": False, "message": "Tài khoản của bạn đã bị khóa bởi Ban Giám Đốc. Vui lòng liên hệ quản trị viên."}, status=403)
            return

        # Kiểm tra tạm khóa do nhập sai nhiều lần
        if user_data['locked_until']:
            try:
                locked_time = datetime.strptime(user_data['locked_until'], "%Y-%m-%d %H:%M:%S")
                if now < locked_time:
                    remaining_mins = int((locked_time - now).total_seconds() / 60) + 1
                    conn.close()
                    self.send_json({"success": False, "message": f"Tài khoản bị tạm khóa do nhập sai nhiều lần. Vui lòng thử lại sau {remaining_mins} phút."}, status=403)
                    return
            except Exception:
                pass

        # Xác thực mật khẩu PBKDF2
        is_valid = verify_pw(password, user_data['password_hash'], user_data['salt'])

        if not is_valid:
            new_failed = (user_data['failed_attempts'] or 0) + 1
            locked_until_val = None
            msg = "Mật khẩu không chính xác."
            if new_failed >= 5:
                locked_until_val = (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
                msg = "Bạn đã nhập sai mật khẩu 5 lần liên tiếp. Tài khoản bị tạm khóa trong 15 phút."

            cur.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?", (new_failed, locked_until_val, user_data['id']))
            conn.commit()
            conn.close()
            self.send_json({"success": False, "message": msg}, status=400)
            return

        # Đăng nhập thành công -> Reset failed attempts
        cur.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_data['id'],))
        cur.execute("SELECT code, position FROM employee_profiles WHERE user_id = ?", (user_data['id'],))
        prof = cur.fetchone()
        conn.commit()
        conn.close()

        # Tạo Session Token và lưu bền vững vào bảng SQLite sessions
        token = str(uuid.uuid4())
        emp_code = prof['code'] if (prof and prof['code']) else ('GD-01' if user_data['role'] == 'admin' else f"KD-0{user_data['id']}")
        emp_position = prof['position'] if (prof and prof['position']) else ('Ban Giám Đốc Điều Hành' if user_data['role'] == 'admin' else 'Chuyên viên Kinh Doanh')

        expires_at = (now + timedelta(hours=SESSION_EXPIRY_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
        INSERT OR REPLACE INTO sessions (token, user_id, expires_at, created_at, last_active, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (token, user_data['id'], expires_at, now_str, now_str, ip))
        conn.commit()
        conn.close()

        safe_user = {
            "id": user_data['id'],
            "username": user_data['username'],
            "email": user_data['email'],
            "phone": user_data['phone'],
            "full_name": user_data['full_name'],
            "role": user_data['role'],
            "must_change_password": user_data.get('must_change_password', 0),
            "code": emp_code,
            "position": emp_position
        }

        # Ghi audit log
        log_audit(safe_user['id'], safe_user['full_name'], 'LOGIN', 'auth', str(safe_user['id']), f"Đăng nhập thành công từ {ip}", ip)

        cookie_header = f"crm_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_EXPIRY_HOURS * 3600}"
        self.send_json({
            "success": True,
            "message": f"Xin chào, {safe_user['full_name']}!",
            "token": token,
            "user": safe_user
        }, headers={"Set-Cookie": cookie_header})

    def handle_logout(self):
        user = self.get_current_user()
        token = ""
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1].strip()
        if not token and 'Cookie' in self.headers:
            raw_cookie = self.headers.get('Cookie', '')
            for part in raw_cookie.split(';'):
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    if k.strip() == 'crm_session':
                        token = v.strip()
                        break

        if token:
            try:
                conn = get_db()
                conn.cursor().execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                conn.close()
            except Exception:
                pass

        if user:
            log_audit(user['id'], user['full_name'], 'LOGOUT', 'auth', str(user['id']), "Đăng xuất khỏi hệ thống", self.get_client_ip())

        expired_cookie = "crm_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
        self.send_json({"success": True, "message": "Đã đăng xuất thành công."}, headers={"Set-Cookie": expired_cookie})

    def handle_me(self):
        user = self.require_auth()
        if not user:
            return
        self.send_json({"success": True, "user": user})

    def handle_change_password(self):
        user = self.require_auth()
        if not user:
            return
        body = self.read_post_body()
        old_pw = body.get('old_password', '').strip()
        new_pw = body.get('new_password', '').strip()

        if len(new_pw) < 6:
            self.send_json({"success": False, "message": "Mật khẩu mới phải có ít nhất 6 ký tự."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password_hash, salt, must_change_password FROM users WHERE id = ?", (user['id'],))
        row = cur.fetchone()

        if not row:
            conn.close()
            self.send_json({"success": False, "message": "Người dùng không tồn tại."}, status=404)
            return

        # Nếu không phải bắt buộc đổi mật khẩu lần đầu thì kiểm tra mật khẩu cũ
        if row['must_change_password'] != 1 and old_pw:
            if not verify_pw(old_pw, row['password_hash'], row['salt']):
                conn.close()
                self.send_json({"success": False, "message": "Mật khẩu hiện tại không chính xác."}, status=400)
                return

        new_h, new_s = hash_pw(new_pw)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0, failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?", (new_h, new_s, now_str, user['id']))
        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'CHANGE_PW', 'auth', str(user['id']), "Đổi mật khẩu tài khoản thành công", self.get_client_ip())
        self.send_json({"success": True, "message": "Đổi mật khẩu thành công!"})

    def handle_dashboard(self, params=None):
        user = self.require_auth()
        if not user:
            return

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        conn = get_db()
        cur = conn.cursor()

        is_admin = user['role'] == 'admin'

        # Cập nhật tự động trạng thái các care task quá hạn hoặc đến hạn hôm nay
        cur.execute('''
        UPDATE care_tasks
        SET status = CASE
            WHEN scheduled_date < ? THEN 'Quá hạn'
            WHEN scheduled_date = ? THEN 'Đến hạn hôm nay'
            ELSE 'Chưa đến hạn'
        END
        WHERE status NOT IN ('Đã chăm', 'Khách đã đặt lại')
        ''', (today, today))
        conn.commit()

        user_filter_sql = "" if is_admin else f"AND assigned_user_id = {user['id']}"
        care_joined_filter_sql = "" if is_admin else f"AND ct.assigned_user_id = {user['id']}"
        order_user_sql = "" if is_admin else f"AND user_id = {user['id']}"

        # 1. Donut Tình hình chăm khách (5 trạng thái với màu chuẩn)
        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE status = 'Chưa đến hạn' {user_filter_sql}")
        count_upcoming = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE status = 'Đến hạn hôm nay' {user_filter_sql}")
        count_due_today = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE status = 'Quá hạn' {user_filter_sql}")
        count_overdue = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE status = 'Đã chăm' {user_filter_sql}")
        count_done = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE status = 'Khách đã đặt lại' {user_filter_sql}")
        count_repurchased = cur.fetchone()[0]

        donut_total = count_upcoming + count_due_today + count_overdue + count_done + count_repurchased
        donut_breakdown = [
            {"label": "Chưa đến hạn", "status": "Chưa đến hạn", "count": count_upcoming, "color": "#94A3B8"},
            {"label": "Đến hạn hôm nay", "status": "Đến hạn hôm nay", "count": count_due_today, "color": "#F59E0B"},
            {"label": "Quá hạn", "status": "Quá hạn", "count": count_overdue, "color": "#EF4444"},
            {"label": "Đã chăm", "status": "Đã chăm", "count": count_done, "color": "#10B981"},
            {"label": "Khách đã đặt lại", "status": "Khách đã đặt lại", "count": count_repurchased, "color": "#8B5CF6"}
        ]

        # 2. KPI Cards (So sánh tháng này vs tháng trước kèm sparkline 7 ngày)
        cur_month_start = now.strftime("%Y-%m-01")
        first_of_cur = datetime(now.year, now.month, 1)
        last_month_end_dt = first_of_cur - timedelta(days=1)
        last_month_start = datetime(last_month_end_dt.year, last_month_end_dt.month, 1).strftime("%Y-%m-%d")
        last_month_end = last_month_end_dt.strftime("%Y-%m-%d")

        cust_where = "" if is_admin else f"WHERE assigned_user_id = {user['id']}"
        cust_and = "" if is_admin else f"AND assigned_user_id = {user['id']}"

        # Khách mới
        cur.execute(f"SELECT COUNT(*) FROM customers WHERE created_at >= ? {cust_and}", (cur_month_start,))
        cur_new_cust = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM customers WHERE created_at >= ? AND created_at <= ? {cust_and}", (last_month_start, last_month_end + " 23:59:59"))
        prev_new_cust = cur.fetchone()[0]
        cust_change_pct = round(((cur_new_cust - prev_new_cust) / prev_new_cust * 100), 1) if prev_new_cust > 0 else (100.0 if cur_new_cust > 0 else 0.0)

        # Đơn hàng
        cur.execute(f"SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders WHERE order_date >= ? {order_user_sql}", (cur_month_start,))
        row_cur_orders = cur.fetchone()
        cur_orders_cnt, cur_revenue = row_cur_orders[0], row_cur_orders[1]

        cur.execute(f"SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders WHERE order_date >= ? AND order_date <= ? {order_user_sql}", (last_month_start, last_month_end))
        row_prev_orders = cur.fetchone()
        prev_orders_cnt, prev_revenue = row_prev_orders[0], row_prev_orders[1]

        orders_change_pct = round(((cur_orders_cnt - prev_orders_cnt) / prev_orders_cnt * 100), 1) if prev_orders_cnt > 0 else (100.0 if cur_orders_cnt > 0 else 0.0)
        revenue_change_pct = round(((cur_revenue - prev_revenue) / prev_revenue * 100), 1) if prev_revenue > 0 else (100.0 if cur_revenue > 0 else 0.0)

        # Tỷ lệ chăm sóc đúng hạn
        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE scheduled_date <= ? {user_filter_sql}", (today,))
        total_due_tasks = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM care_tasks WHERE scheduled_date <= ? AND status IN ('Đã chăm', 'Khách đã đặt lại') {user_filter_sql}", (today,))
        done_due_tasks = cur.fetchone()[0]
        care_rate = round((done_due_tasks / total_due_tasks * 100), 1) if total_due_tasks > 0 else 100.0

        # Sparklines 7 ngày gần nhất
        spark_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        spark_cust = []
        spark_orders = []
        spark_rev = []
        for d in spark_days:
            cur.execute(f"SELECT COUNT(*) FROM customers WHERE created_at LIKE ? {cust_and}", (f"{d}%",))
            spark_cust.append(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders WHERE order_date = ? {order_user_sql}", (d,))
            r = cur.fetchone()
            spark_orders.append(r[0])
            spark_rev.append(int(r[1] / 1000000)) # in Millions for clean sparklines

        kpi_cards = {
            "new_customers": {"current": cur_new_cust, "previous": prev_new_cust, "change_pct": cust_change_pct, "sparkline": spark_cust},
            "orders": {"current": cur_orders_cnt, "previous": prev_orders_cnt, "change_pct": orders_change_pct, "sparkline": spark_orders},
            "revenue": {"current": cur_revenue, "previous": prev_revenue, "change_pct": revenue_change_pct, "sparkline": spark_rev},
            "care_rate": {"rate": care_rate, "done": done_due_tasks, "total": total_due_tasks, "sparkline": [90, 92, 88, 94, 91, 95, care_rate]}
        }

        # 3. Phễu chuyển đổi (Sales Funnel)
        cur.execute(f"SELECT COUNT(*) FROM customers {cust_where}")
        funnel_stage1 = cur.fetchone()[0] or 1 # Khách mới tiếp cận
        cur.execute(f"SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status IN ('Đã báo giá', 'Chốt', 'Đã giao', 'Hoàn tất') {order_user_sql}")
        funnel_stage2 = cur.fetchone()[0] # Đã gửi báo giá
        cur.execute(f"SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status IN ('Chốt', 'Đã giao', 'Hoàn tất') {order_user_sql}")
        funnel_stage3 = cur.fetchone()[0] # Đã chốt đơn
        cur.execute(f"SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status IN ('Đã giao', 'Hoàn tất') {order_user_sql}")
        funnel_stage4 = cur.fetchone()[0] # Đã giao hàng

        funnel_base = max(1, funnel_stage1)
        sales_funnel = [
            {"step": "Khách mới", "count": funnel_stage1, "pct": 100.0},
            {"step": "Đã báo giá", "count": funnel_stage2, "pct": round(funnel_stage2 / funnel_base * 100, 1)},
            {"step": "Chốt đơn", "count": funnel_stage3, "pct": round(funnel_stage3 / funnel_base * 100, 1)},
            {"step": "Đã giao", "count": funnel_stage4, "pct": round(funnel_stage4 / funnel_base * 100, 1)}
        ]

        # 4. Doanh thu 12 tháng gần nhất (Line/Area Chart)
        revenue_12m = {"labels": [], "current_year": [], "previous_year": []}
        for i in range(11, -1, -1):
            m_dt = (first_of_cur - timedelta(days=i * 28)).replace(day=1)
            m_str = m_dt.strftime("%Y-%m")
            m_label = m_dt.strftime("T%m/%y")
            revenue_12m["labels"].append(m_label)

            cur.execute(f"SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE order_date LIKE ? {order_user_sql}", (f"{m_str}%",))
            revenue_12m["current_year"].append(cur.fetchone()[0])

            # Cùng kỳ năm ngoái
            prev_year_m_str = f"{m_dt.year - 1}-{m_dt.month:02d}"
            cur.execute(f"SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE order_date LIKE ? {order_user_sql}", (f"{prev_year_m_str}%",))
            revenue_12m["previous_year"].append(cur.fetchone()[0])

        # 5. Khách mới theo nguồn (Sources Bar Chart: Week / Month / Quarter)
        sources_list = ["Fanpage", "Đến trực tiếp", "Khách lẻ", "Giới thiệu"]
        seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        ninety_days_ago = (now - timedelta(days=90)).strftime("%Y-%m-%d")

        sources_chart = {"sources": sources_list, "week": [], "month": [], "quarter": []}
        for src in sources_list:
            cur.execute(f"SELECT COUNT(*) FROM customers WHERE source = ? AND created_at >= ? {cust_and}", (src, seven_days_ago))
            sources_chart["week"].append(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM customers WHERE source = ? AND created_at >= ? {cust_and}", (src, cur_month_start))
            sources_chart["month"].append(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM customers WHERE source = ? AND created_at >= ? {cust_and}", (src, ninety_days_ago))
            sources_chart["quarter"].append(cur.fetchone()[0])

        # 6. Dữ liệu bổ sung cho Sếp (Admin Extras)
        admin_extras = {}
        if is_admin:
            # Xếp hạng nhân viên kinh doanh theo doanh thu
            cur.execute('''
            SELECT u.id, u.full_name, COALESCE(ep.code, printf('KD-0%d', u.id)) as code,
                   ep.position, ep.avatar_color, ep.monthly_target,
                   COUNT(DISTINCT c.id) as customer_count,
                   COALESCE(SUM(o.total_amount), 0) as month_revenue,
                   COUNT(DISTINCT o.id) as month_orders,
                   SUM(CASE WHEN ct.status = 'Quá hạn' THEN 1 ELSE 0 END) as overdue_count,
                   SUM(CASE WHEN ct.status = 'Đã chăm' THEN 1 ELSE 0 END) as done_count
            FROM users u
            LEFT JOIN employee_profiles ep ON u.id = ep.user_id
            LEFT JOIN customers c ON u.id = c.assigned_user_id
            LEFT JOIN orders o ON u.id = o.user_id AND o.order_date >= ?
            LEFT JOIN care_tasks ct ON u.id = ct.assigned_user_id
            WHERE u.role = 'sales' AND u.is_active = 1
            GROUP BY u.id
            ORDER BY month_revenue DESC
            ''', (cur_month_start,))
            rankings = []
            for r in cur.fetchall():
                d = dict(r)
                tgt = d.get('monthly_target') or 150000000
                rev = d.get('month_revenue') or 0
                d['target'] = tgt
                d['percent'] = min(100, round((rev / tgt) * 100)) if tgt > 0 else 0
                rankings.append(d)
            admin_extras['employee_rankings'] = rankings

            # Nhân viên có nhiều lịch quá hạn nhất
            top_overdue_rep = None
            if rankings:
                sorted_by_overdue = sorted(rankings, key=lambda x: x.get('overdue_count', 0), reverse=True)
                if sorted_by_overdue and sorted_by_overdue[0].get('overdue_count', 0) > 0:
                    top_overdue_rep = sorted_by_overdue[0]
            admin_extras['top_overdue_rep'] = top_overdue_rep

            # Cảnh báo khách quá hạn > 15 ngày
            fifteen_days_ago = (now - timedelta(days=15)).strftime("%Y-%m-%d")
            cur.execute('''
            SELECT ct.id, ct.scheduled_date, c.full_name, c.phone, u.full_name as assigned_name, ct.milestone_title,
                   ROUND(julianday(?) - julianday(ct.scheduled_date)) as overdue_days
            FROM care_tasks ct
            JOIN customers c ON ct.customer_id = c.id
            JOIN users u ON ct.assigned_user_id = u.id
            WHERE ct.status = 'Quá hạn' AND ct.scheduled_date <= ?
            ORDER BY ct.scheduled_date ASC
            LIMIT 15
            ''', (today, fifteen_days_ago))
            admin_extras['severe_overdue_warnings'] = [dict(r) for r in cur.fetchall()]

        # 7. Dữ liệu chuyên biệt cho Nhân viên KD (Sales Rep Stats)
        sales_rep_stats = {}
        if not is_admin:
            cur.execute("SELECT monthly_target FROM employee_profiles WHERE user_id = ?", (user['id'],))
            tgt_row = cur.fetchone()
            target_val = tgt_row[0] if (tgt_row and tgt_row[0]) else 150000000
            target_pct = min(100, round((cur_revenue / target_val) * 100, 1)) if target_val > 0 else 0.0

            # 4 tuần gần nhất
            weekly_stats = {"labels": ["Tuần 1", "Tuần 2", "Tuần 3", "Tuần này"], "customers": [], "orders": []}
            for w in range(3, -1, -1):
                w_start = (now - timedelta(days=(w + 1) * 7)).strftime("%Y-%m-%d")
                w_end = (now - timedelta(days=w * 7)).strftime("%Y-%m-%d")
                cur.execute("SELECT COUNT(*) FROM customers WHERE assigned_user_id = ? AND created_at >= ? AND created_at < ?", (user['id'], w_start, w_end))
                weekly_stats["customers"].append(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND order_date >= ? AND order_date < ?", (user['id'], w_start, w_end))
                weekly_stats["orders"].append(cur.fetchone()[0])

            sales_rep_stats = {
                "target": target_val,
                "current_revenue": cur_revenue,
                "target_percent": target_pct,
                "weekly_stats": weekly_stats
            }

        # 8. Danh sách "Hôm nay cần chăm ai" (Quá hạn trước, sau đó đến hạn hôm nay)
        cur.execute(f'''
        SELECT ct.id, ct.milestone_title, ct.scheduled_date, ct.status, ct.order_id,
               c.id as customer_id, c.full_name as customer_name, c.phone as customer_phone,
               c.customer_type, c.source, c.address, u.full_name as assigned_name, u.id as assigned_id,
               o.order_code, o.delivery_date
        FROM care_tasks ct
        JOIN customers c ON ct.customer_id = c.id
        JOIN users u ON ct.assigned_user_id = u.id
        LEFT JOIN orders o ON ct.order_id = o.id
        WHERE ct.status IN ('Quá hạn', 'Đến hạn hôm nay') {care_joined_filter_sql}
        ORDER BY CASE WHEN ct.status = 'Quá hạn' THEN 1 ELSE 2 END, ct.scheduled_date ASC
        LIMIT 20
        ''')
        urgent_care_list = [dict(r) for r in cur.fetchall()]
        conn.close()

        stats = {
            "due_today_count": count_due_today,
            "overdue_count": count_overdue,
            "month_orders_count": cur_orders_cnt,
            "month_revenue": cur_revenue,
            "total_customers": cur_new_cust,
            "existing_customers": funnel_stage4,
            "potential_customers": max(0, funnel_stage1 - funnel_stage4),
            "total_active_today_care": count_due_today + count_overdue
        }

        resp_data = {
            "success": True,
            "role": user['role'],
            "stats": stats,
            "kpi_cards": kpi_cards,
            "donut_breakdown": donut_breakdown,
            "donut_total": donut_total,
            "sources_chart": sources_chart,
            "revenue_12m": revenue_12m,
            "sales_funnel": sales_funnel,
            "urgent_care_list": urgent_care_list
        }
        if is_admin:
            resp_data["admin_extras"] = admin_extras
        else:
            resp_data["sales_rep_stats"] = sales_rep_stats

        self.send_json(resp_data)

    def handle_get_customers(self, params):
        user = self.require_auth()
        if not user:
            return

        conn = get_db()
        cur = conn.cursor()

        is_admin = user['role'] == 'admin'

        conditions = []
        sql_params = []

        # Phân quyền: Nhân viên kinh doanh chỉ thấy khách của mình
        if not is_admin:
            conditions.append("c.assigned_user_id = ?")
            sql_params.append(user['id'])
        else:
            if 'user_id' in params and params['user_id'][0]:
                conditions.append("c.assigned_user_id = ?")
                sql_params.append(int(params['user_id'][0]))

        # Search query
        if 'search' in params and params['search'][0].strip():
            kw = f"%{params['search'][0].strip()}%"
            conditions.append("(c.full_name LIKE ? OR c.phone LIKE ? OR c.demand LIKE ?)")
            sql_params.extend([kw, kw, kw])

        # Filter theo nguồn
        if 'source' in params and params['source'][0] and params['source'][0] != 'all':
            conditions.append("c.source = ?")
            sql_params.append(params['source'][0])

        # Filter theo loại khách
        if 'customer_type' in params and params['customer_type'][0] and params['customer_type'][0] != 'all':
            conditions.append("c.customer_type = ?")
            sql_params.append(params['customer_type'][0])

        # Filter theo giai đoạn (Khách tiềm năng / Khách cũ)
        if 'stage' in params and params['stage'][0] and params['stage'][0] != 'all':
            conditions.append("c.stage = ?")
            sql_params.append(params['stage'][0])

        # Filter theo trạng thái tư vấn
        if 'status' in params and params['status'][0] and params['status'][0] != 'all':
            conditions.append("c.status = ?")
            sql_params.append(params['status'][0])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f'''
        SELECT c.*, u.full_name as assigned_name, u.role as assigned_role,
               (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) as total_orders,
               (SELECT COALESCE(SUM(total_amount), 0) FROM orders o WHERE o.customer_id = c.id) as total_spent,
               (SELECT scheduled_date FROM care_tasks ct WHERE ct.customer_id = c.id AND ct.status IN ('Đến hạn hôm nay', 'Quá hạn', 'Chưa đến hạn') ORDER BY scheduled_date ASC LIMIT 1) as next_care_date,
               (SELECT status FROM care_tasks ct WHERE ct.customer_id = c.id AND ct.status IN ('Đến hạn hôm nay', 'Quá hạn', 'Chưa đến hạn') ORDER BY scheduled_date ASC LIMIT 1) as next_care_status
        FROM customers c
        JOIN users u ON c.assigned_user_id = u.id
        {where_clause}
        ORDER BY c.id DESC
        '''

        cur.execute(query, sql_params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "customers": rows, "count": len(rows)})

    def handle_get_customer_detail(self, cust_id):
        user = self.require_auth()
        if not user:
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
        SELECT c.*, u.full_name as assigned_name, u.phone as assigned_phone
        FROM customers c
        JOIN users u ON c.assigned_user_id = u.id
        WHERE c.id = ?
        ''', (cust_id,))
        cust = cur.fetchone()

        if not cust:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy khách hàng."}, status=404)
            return

        cust_dict = dict(cust)

        # Kiểm tra quyền: nhân viên chỉ được xem khách của mình
        if user['role'] != 'admin' and cust_dict['assigned_user_id'] != user['id']:
            conn.close()
            self.send_json({"success": False, "message": "Bạn không có quyền xem thông tin khách hàng của nhân viên khác."}, status=403)
            return

        # Danh sách đơn hàng của khách
        cur.execute('''
        SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC
        ''', (cust_id,))
        orders = [dict(r) for r in cur.fetchall()]

        # Lịch sử các mốc chăm sóc
        cur.execute('''
        SELECT ct.*, u.full_name as cared_by_name
        FROM care_tasks ct
        LEFT JOIN users u ON ct.cared_by_user_id = u.id
        WHERE ct.customer_id = ?
        ORDER BY ct.scheduled_date ASC
        ''', (cust_id,))
        care_tasks = [dict(r) for r in cur.fetchall()]

        # Lịch sử trao đổi / tương tác
        cur.execute('''
        SELECT i.*, u.full_name as user_name
        FROM interactions i
        JOIN users u ON i.user_id = u.id
        WHERE i.customer_id = ?
        ORDER BY i.created_at DESC
        ''', (cust_id,))
        interactions = [dict(r) for r in cur.fetchall()]

        # Lịch sử chuyển quyền chăm sóc (nếu có)
        cur.execute('''
        SELECT ct.*, u1.full_name as from_name, u2.full_name as to_name, ub.full_name as transferred_by_name
        FROM customer_transfers ct
        JOIN users u1 ON ct.from_user_id = u1.id
        JOIN users u2 ON ct.to_user_id = u2.id
        JOIN users ub ON ct.transferred_by_user_id = ub.id
        WHERE ct.customer_id = ?
        ORDER BY ct.created_at DESC
        ''', (cust_id,))
        transfers = [dict(r) for r in cur.fetchall()]

        conn.close()

        self.send_json({
            "success": True,
            "customer": cust_dict,
            "orders": orders,
            "care_tasks": care_tasks,
            "interactions": interactions,
            "transfers": transfers
        })

    def handle_add_customer(self):
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        full_name = body.get('full_name', '').strip()
        phone_raw = body.get('phone', '').strip()
        customer_type = body.get('customer_type', 'Thầu công trình')
        source = body.get('source', 'Fanpage')
        demand = body.get('demand', '').strip()
        address = body.get('address', '').strip()
        notes = body.get('notes', '').strip()
        zalo = body.get('zalo', '').strip() or phone_raw

        if not full_name or not phone_raw:
            self.send_json({"success": False, "message": "Vui lòng nhập Tên khách hàng và Số điện thoại."}, status=400)
            return

        phone = normalize_phone(phone_raw)
        if len(phone) < 9:
            self.send_json({"success": False, "message": "Số điện thoại không hợp lệ."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        # CHỐNG TRÙNG SỐ ĐIỆN THOẠI
        cur.execute('''
        SELECT c.id, c.full_name, c.created_at, u.full_name as assigned_name
        FROM customers c
        JOIN users u ON c.assigned_user_id = u.id
        WHERE c.phone = ?
        ''', (phone,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            created_fmt = existing['created_at'][:10] if existing['created_at'] else "trước đây"
            self.send_json({
                "success": False,
                "message": f"Số điện thoại {phone} ĐÃ TỒN TẠI trên hệ thống! Khách này đã thuộc quyền quản lý của [{existing['assigned_name']}], nhập ngày {created_fmt}."
            }, status=400)
            return

        # Tự động gán nhân viên đang đăng nhập làm người phụ trách
        # (Nếu Sếp đăng nhập và có chỉ định nhân viên thì lấy theo Sếp chọn)
        assigned_user_id = user['id']
        if user['role'] == 'admin' and body.get('assigned_user_id'):
            try:
                assigned_user_id = int(body.get('assigned_user_id'))
            except (ValueError, TypeError):
                assigned_user_id = user['id']

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute('''
        INSERT INTO customers (
            full_name, phone, zalo, address, customer_type, source, stage, demand,
            assigned_user_id, status, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'Khách tiềm năng', ?, ?, 'Mới nhận', ?, ?, ?)
        ''', (full_name, phone, zalo, address, customer_type, source, demand, assigned_user_id, notes, now_str, now_str))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'CREATE', 'customer', str(new_id), f"Thêm mới khách hàng: {full_name} ({phone})", self.get_client_ip())

        self.send_json({"success": True, "message": "Thêm khách hàng thành công!", "customer_id": new_id})

    def handle_update_customer(self):
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        cust_id = body.get('id')
        if not cust_id:
            self.send_json({"success": False, "message": "Thiếu mã khách hàng."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT * FROM customers WHERE id = ?", (cust_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy khách hàng."}, status=404)
            return

        # Kiểm tra quyền: nhân viên chỉ được sửa khách của mình
        if user['role'] != 'admin' and cust['assigned_user_id'] != user['id']:
            conn.close()
            self.send_json({"success": False, "message": "Bạn không có quyền sửa thông tin khách hàng của người khác."}, status=403)
            return

        full_name = body.get('full_name', cust['full_name']).strip()
        phone_raw = body.get('phone', cust['phone']).strip()
        phone = normalize_phone(phone_raw)

        # Kiểm tra trùng phone nếu số bị đổi
        if phone != cust['phone']:
            cur.execute("SELECT id, full_name, u.full_name as assigned_name FROM customers c JOIN users u ON c.assigned_user_id = u.id WHERE c.phone = ? AND c.id != ?", (phone, cust_id))
            dup = cur.fetchone()
            if dup:
                conn.close()
                self.send_json({"success": False, "message": f"Số điện thoại {phone} đã thuộc về khách [{dup['full_name']}] do [{dup['assigned_name']}] phụ trách!"}, status=400)
                return

        customer_type = body.get('customer_type', cust['customer_type'])
        source = body.get('source', cust['source'])
        stage = body.get('stage', cust['stage'])
        status = body.get('status', cust['status'])
        demand = body.get('demand', cust['demand'])
        address = body.get('address', cust['address'])
        notes = body.get('notes', cust['notes'])
        zalo = body.get('zalo', cust['zalo'])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute('''
        UPDATE customers
        SET full_name = ?, phone = ?, zalo = ?, address = ?, customer_type = ?,
            source = ?, stage = ?, status = ?, demand = ?, notes = ?, updated_at = ?
        WHERE id = ?
        ''', (full_name, phone, zalo, address, customer_type, source, stage, status, demand, notes, now_str, cust_id))
        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'UPDATE', 'customer', str(cust_id), f"Cập nhật thông tin khách: {full_name}", self.get_client_ip())

        self.send_json({"success": True, "message": "Cập nhật thông tin khách hàng thành công!"})

    def handle_delete_customer(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        cust_id = body.get('id')
        if not cust_id:
            self.send_json({"success": False, "message": "Thiếu mã khách hàng cần xóa."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT full_name FROM customers WHERE id = ?", (cust_id,))
        c = cur.fetchone()
        name = c['full_name'] if c else str(cust_id)

        cur.execute("DELETE FROM care_tasks WHERE customer_id = ?", (cust_id,))
        cur.execute("DELETE FROM orders WHERE customer_id = ?", (cust_id,))
        cur.execute("DELETE FROM interactions WHERE customer_id = ?", (cust_id,))
        cur.execute("DELETE FROM customer_transfers WHERE customer_id = ?", (cust_id,))
        cur.execute("DELETE FROM customers WHERE id = ?", (cust_id,))
        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'DELETE', 'customer', str(cust_id), f"Xóa khách hàng: {name}", self.get_client_ip())

        self.send_json({"success": True, "message": f"Đã xóa khách hàng [{name}] thành công."})

    def handle_transfer_customer(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        cust_id = body.get('customer_id')
        to_user_id = body.get('to_user_id')
        reason = body.get('reason', '').strip() or "Sếp điều phối lại danh mục khách hàng"

        if not cust_id or not to_user_id:
            self.send_json({"success": False, "message": "Thiếu thông tin chuyển giao khách."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT assigned_user_id, full_name FROM customers WHERE id = ?", (cust_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy khách hàng."}, status=404)
            return

        from_user_id = cust['assigned_user_id']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Cập nhật nhân viên phụ trách khách
        cur.execute("UPDATE customers SET assigned_user_id = ?, updated_at = ? WHERE id = ?", (to_user_id, now_str, cust_id))

        # Cập nhật các lịch chăm sóc chưa hoàn thành sang nhân viên mới
        cur.execute('''
        UPDATE care_tasks
        SET assigned_user_id = ?, updated_at = ?
        WHERE customer_id = ? AND status IN ('Đến hạn hôm nay', 'Quá hạn', 'Chưa đến hạn')
        ''', (to_user_id, now_str, cust_id))

        # Ghi nhận lịch sử chuyển giao
        cur.execute('''
        INSERT INTO customer_transfers (customer_id, from_user_id, to_user_id, reason, transferred_by_user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (cust_id, from_user_id, to_user_id, reason, admin['id'], now_str))

        conn.commit()

        # Lấy tên nhân viên mới để thông báo
        cur.execute("SELECT full_name FROM users WHERE id = ?", (to_user_id,))
        to_user = cur.fetchone()
        to_name = to_user['full_name'] if to_user else f"NV #{to_user_id}"
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'TRANSFER', 'customer', str(cust_id), f"Chuyển quyền khách [{cust['full_name']}] sang {to_name}. Lý do: {reason}", self.get_client_ip())

        self.send_json({"success": True, "message": f"Đã chuyển khách hàng sang nhân viên [{to_name}] thành công!"})

    def handle_import_csv(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        rows = body.get('rows', [])
        if not rows:
            self.send_json({"success": False, "message": "Không có dữ liệu import."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        imported_count = 0
        skipped_duplicates = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for r in rows:
            name = r.get('full_name', '').strip()
            phone_raw = r.get('phone', '').strip()
            if not name or not phone_raw:
                continue

            phone = normalize_phone(phone_raw)
            cur.execute("SELECT id, full_name FROM customers WHERE phone = ?", (phone,))
            dup = cur.fetchone()
            if dup:
                skipped_duplicates.append(f"{name} ({phone})")
                continue

            c_type = r.get('customer_type', 'Thầu công trình')
            src = r.get('source', 'Fanpage')
            addr = r.get('address', '')
            demand = r.get('demand', '')
            notes = r.get('notes', '')
            try:
                assigned_id = int(r.get('assigned_user_id') or admin['id'])
            except (ValueError, TypeError):
                assigned_id = admin['id']

            cur.execute('''
            INSERT INTO customers (
                full_name, phone, zalo, address, customer_type, source, stage, demand,
                assigned_user_id, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Khách tiềm năng', ?, ?, 'Mới nhận', ?, ?, ?)
            ''', (name, phone, phone, addr, c_type, src, demand, assigned_id, notes, now_str, now_str))
            imported_count += 1

        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'IMPORT', 'customer', 'batch', f"Import hàng loạt {imported_count} khách, bỏ qua {len(skipped_duplicates)} số trùng.", self.get_client_ip())

        self.send_json({
            "success": True,
            "message": f"Đã import thành công {imported_count} khách hàng!",
            "imported_count": imported_count,
            "skipped_duplicates": skipped_duplicates
        })

    # ==================== ĐƠN HÀNG (ORDERS) ====================

    def handle_get_orders(self, params):
        user = self.require_auth()
        if not user:
            return

        conn = get_db()
        cur = conn.cursor()

        is_admin = user['role'] == 'admin'
        conditions = []
        sql_params = []

        if not is_admin:
            conditions.append("o.user_id = ?")
            sql_params.append(user['id'])

        if 'status' in params and params['status'][0] and params['status'][0] != 'all':
            conditions.append("o.status = ?")
            sql_params.append(params['status'][0])

        if 'customer_id' in params and params['customer_id'][0]:
            conditions.append("o.customer_id = ?")
            sql_params.append(int(params['customer_id'][0]))

        if 'search' in params and params['search'][0].strip():
            kw = f"%{params['search'][0].strip()}%"
            conditions.append("(o.order_code LIKE ? OR c.full_name LIKE ? OR c.phone LIKE ? OR o.items_text LIKE ?)")
            sql_params.extend([kw, kw, kw, kw])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f'''
        SELECT o.*, c.full_name as customer_name, c.phone as customer_phone, c.address as customer_address,
               c.customer_type, u.full_name as user_name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN users u ON o.user_id = u.id
        {where_clause}
        ORDER BY o.order_date DESC, o.id DESC
        ''', sql_params)

        orders = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "orders": orders, "count": len(orders)})

    def generate_care_tasks_for_order(self, cur, order_id, customer_id, user_id, delivery_date):
        """
        TỰ ĐỘNG TẠO 4 MỐC CHĂM KHÁCH KHI ĐƠN CHUYỂN SANG 'ĐÃ GIAO':
        - Mốc 5 ngày
        - Mốc 7 ngày
        - Mốc 15 ngày (hoặc theo cấu hình)
        - Mốc 30 ngày
        VÀ ĐÁNH DẤU CÁC MỐC CHƯA CHĂM CỦA CÁC ĐƠN CŨ THÀNH 'Khách đã đặt lại'!
        """
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        today_str = now.strftime("%Y-%m-%d")

        # 1. Đánh dấu các mốc chăm sóc cũ còn tồn đọng của khách này thành 'Khách đã đặt lại'
        cur.execute('''
        UPDATE care_tasks
        SET status = 'Khách đã đặt lại',
            result_status = 'Đã đặt đơn mới',
            result_notes = 'Khách đã phát sinh đơn hàng mới, chu kỳ chăm sóc được làm mới.',
            updated_at = ?
        WHERE customer_id = ? AND order_id != ? AND status IN ('Chưa đến hạn', 'Đến hạn hôm nay', 'Quá hạn')
        ''', (now_str, customer_id, order_id))

        # 2. Lấy cấu hình số ngày từ settings
        cur.execute("SELECT key, value FROM settings WHERE key IN ('milestone_5d', 'milestone_7d', 'milestone_15d', 'milestone_30d')")
        m_conf = dict(cur.fetchall())
        d5 = int(m_conf.get('milestone_5d', 5))
        d7 = int(m_conf.get('milestone_7d', 7))
        d15 = int(m_conf.get('milestone_15d', 15))
        d30 = int(m_conf.get('milestone_30d', 30))

        # Tính ngày hẹn từ delivery_date (hoặc ngày hôm nay nếu không có delivery_date)
        try:
            base_date = datetime.strptime(delivery_date, "%Y-%m-%d")
        except Exception:
            base_date = now

        milestones = [
            ('5d', d5, f"Mốc {d5} ngày: Hỏi thăm nhận hàng & kiểm tra ren"),
            ('7d', d7, f"Mốc {d7} ngày: Hỏi thăm tiến độ & hao hụt"),
            ('15d', d15, f"Mốc {d15} ngày: Dự toán đợt 2 & bổ sung quy cách"),
            ('30d', d30, f"Mốc {d30} ngày: Chăm sóc định kỳ tháng & chính sách mới"),
        ]

        # Kiểm tra xem đơn này đã từng có care tasks chưa để tránh nhân đôi mốc
        cur.execute("SELECT id, milestone_code FROM care_tasks WHERE order_id = ?", (order_id,))
        existing_tasks = {r['milestone_code']: r['id'] for r in cur.fetchall()}

        for code, days, title in milestones:
            sched_date = (base_date + timedelta(days=days)).strftime("%Y-%m-%d")
            status = 'Chưa đến hạn'
            if sched_date == today_str:
                status = 'Đến hạn hôm nay'
            elif sched_date < today_str:
                status = 'Quá hạn'

            if code in existing_tasks:
                cur.execute('''
                UPDATE care_tasks
                SET scheduled_date = ?, status = ?, assigned_user_id = ?, updated_at = ?
                WHERE id = ?
                ''', (sched_date, status, user_id, now_str, existing_tasks[code]))
            else:
                cur.execute('''
                INSERT INTO care_tasks (
                    order_id, customer_id, assigned_user_id, milestone_code, milestone_days,
                    milestone_title, scheduled_date, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (order_id, customer_id, user_id, code, days, title, sched_date, status, now_str, now_str))

    def handle_add_order(self):
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        customer_id = body.get('customer_id')
        try:
            total_amount = int(str(body.get('total_amount', 0)).replace('.', '').replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            total_amount = 0
        if total_amount < 0:
            self.send_json({"success": False, "field": "total_amount", "message": "Tổng tiền đơn hàng không được là số âm."}, status=400)
            return

        items_text = body.get('items_text', '').strip()
        status = body.get('status', 'Mới') # 'Mới', 'Đã báo giá', 'Chốt', 'Đã giao', 'Hoàn tất'
        order_date = body.get('order_date', '').strip() or datetime.now().strftime("%Y-%m-%d")
        delivery_date = body.get('delivery_date', '').strip() or (order_date if status in ('Đã giao', 'Hoàn tất') else None)
        notes = body.get('notes', '').strip()

        if not customer_id:
            self.send_json({"success": False, "field": "customer_id", "message": "Vui lòng chọn khách hàng cho đơn hàng."}, status=400)
            return

        if not items_text:
            self.send_json({"success": False, "field": "items_text", "message": "Vui lòng nhập danh sách hàng hóa quy cách bu lông, ốc vít."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        # Kiểm tra khách hàng
        cur.execute("SELECT id, full_name, assigned_user_id, stage FROM customers WHERE id = ?", (customer_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            self.send_json({"success": False, "field": "customer_id", "message": "Khách hàng không tồn tại trong hệ thống."}, status=404)
            return

        # Quyền: sales chỉ được tạo đơn cho khách của mình
        if user['role'] != 'admin' and cust['assigned_user_id'] != user['id']:
            conn.close()
            self.send_json({"success": False, "message": "Bạn chỉ được tạo đơn hàng cho khách do mình phụ trách."}, status=403)
            return

        # Tự sinh mã đơn nếu không có
        order_code = body.get('order_code', '').strip()
        if not order_code:
            now_code_str = datetime.now().strftime("%y%m")
            cur.execute("SELECT COUNT(*) FROM orders")
            cnt = cur.fetchone()[0] + 1
            order_code = f"DH-LZ-{now_code_str}-{cnt:03d}"

        # Nhân viên phụ trách đơn: mặc định theo khách, Sếp được phép chọn nhân viên khác
        order_user_id = cust['assigned_user_id']
        if user['role'] == 'admin' and body.get('assigned_user_id'):
            try:
                order_user_id = int(body.get('assigned_user_id'))
            except (ValueError, TypeError):
                order_user_id = cust['assigned_user_id']

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute('''
        INSERT INTO orders (order_code, customer_id, user_id, order_date, delivery_date, total_amount, items_text, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_code, customer_id, order_user_id, order_date, delivery_date, total_amount, items_text, status, notes, now_str, now_str))
        new_order_id = cur.lastrowid

        # KHI KHÁCH CÓ ĐƠN HÀNG: Tự động chuyển Khách tiềm năng -> Khách cũ
        if cust['stage'] != 'Khách cũ':
            cur.execute("UPDATE customers SET stage = 'Khách cũ', updated_at = ? WHERE id = ?", (now_str, customer_id))

        # KHI ĐƠN HÀNG CHUYỂN SANG "ĐÃ GIAO": Tự động sinh 4 mốc chăm khách!
        if status in ('Đã giao', 'Hoàn tất'):
            self.generate_care_tasks_for_order(cur, new_order_id, customer_id, order_user_id, delivery_date)

        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'CREATE', 'order', order_code, f"Tạo đơn hàng {order_code} ({total_amount:,}đ) cho khách {cust['full_name']}", self.get_client_ip())

        self.send_json({
            "success": True,
            "message": f"Tạo đơn hàng [{order_code}] thành công!",
            "order_id": new_order_id,
            "order_code": order_code
        })

    def handle_update_order(self):
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        order_id = body.get('id')
        if not order_id:
            self.send_json({"success": False, "message": "Thiếu mã đơn hàng."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cur.fetchone()
        if not order:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy đơn hàng."}, status=404)
            return

        if user['role'] != 'admin' and order['user_id'] != user['id']:
            conn.close()
            self.send_json({"success": False, "message": "Bạn không có quyền sửa đơn hàng của người khác."}, status=403)
            return

        old_status = order['status']
        new_status = body.get('status', old_status)
        try:
            total_amount = int(str(body.get('total_amount', order['total_amount'])).replace('.', '').replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            total_amount = order['total_amount']
        if total_amount < 0:
            conn.close()
            self.send_json({"success": False, "field": "total_amount", "message": "Tổng tiền đơn hàng không được là số âm."}, status=400)
            return

        items_text = body.get('items_text', order['items_text'])
        order_date = body.get('order_date', order['order_date'])
        delivery_date = body.get('delivery_date', order['delivery_date'])
        notes = body.get('notes', order['notes'])
        assigned_user_id = order['user_id']
        if user['role'] == 'admin' and body.get('assigned_user_id'):
            try:
                assigned_user_id = int(body.get('assigned_user_id'))
            except (ValueError, TypeError):
                assigned_user_id = order['user_id']

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Nếu trạng thái chuyển sang Đã giao và chưa có ngày giao -> lấy hôm nay
        if new_status in ('Đã giao', 'Hoàn tất') and not delivery_date:
            delivery_date = datetime.now().strftime("%Y-%m-%d")

        cur.execute('''
        UPDATE orders
        SET status = ?, user_id = ?, total_amount = ?, items_text = ?, order_date = ?, delivery_date = ?, notes = ?, updated_at = ?
        WHERE id = ?
        ''', (new_status, assigned_user_id, total_amount, items_text, order_date, delivery_date, notes, now_str, order_id))

        # Nếu trạng thái chuyển từ Mới/Báo giá/Chốt sang ĐÃ GIAO -> Tự sinh lịch chăm sóc
        if old_status not in ('Đã giao', 'Hoàn tất') and new_status in ('Đã giao', 'Hoàn tất'):
            self.generate_care_tasks_for_order(cur, order_id, order['customer_id'], assigned_user_id, delivery_date)

        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'UPDATE', 'order', order['order_code'], f"Cập nhật đơn {order['order_code']} sang [{new_status}]", self.get_client_ip())

        self.send_json({"success": True, "message": f"Cập nhật đơn hàng [{order['order_code']}] thành công!"})

    def handle_delete_order(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        order_id = body.get('id')
        if not order_id:
            self.send_json({"success": False, "message": "Thiếu mã đơn hàng."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT order_code FROM orders WHERE id = ?", (order_id,))
        o = cur.fetchone()
        code = o['order_code'] if o else str(order_id)

        cur.execute("DELETE FROM care_tasks WHERE order_id = ?", (order_id,))
        cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'DELETE', 'order', code, f"Xóa đơn hàng {code}", self.get_client_ip())

        self.send_json({"success": True, "message": f"Đã xóa đơn hàng [{code}] thành công."})

    # ==================== LỊCH CHĂM KHÁCH (CARE TASKS) ====================

    def handle_get_care_tasks(self, params):
        user = self.require_auth()
        if not user:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db()
        cur = conn.cursor()

        is_admin = user['role'] == 'admin'

        # Tự động cập nhật trạng thái ngày hôm nay và quá hạn
        cur.execute('''
        UPDATE care_tasks
        SET status = CASE
            WHEN scheduled_date < ? THEN 'Quá hạn'
            WHEN scheduled_date = ? THEN 'Đến hạn hôm nay'
            ELSE 'Chưa đến hạn'
        END
        WHERE status NOT IN ('Đã chăm', 'Khách đã đặt lại')
        ''', (today, today))
        conn.commit()

        conditions = []
        sql_params = []

        if not is_admin:
            conditions.append("ct.assigned_user_id = ?")
            sql_params.append(user['id'])
        else:
            if 'user_id' in params and params['user_id'][0]:
                conditions.append("ct.assigned_user_id = ?")
                sql_params.append(int(params['user_id'][0]))

        # Filter theo tab / status
        if 'status' in params and params['status'][0] and params['status'][0] != 'all':
            conditions.append("ct.status = ?")
            sql_params.append(params['status'][0])

        if 'milestone' in params and params['milestone'][0] and params['milestone'][0] != 'all':
            conditions.append("ct.milestone_code = ?")
            sql_params.append(params['milestone'][0])

        if 'search' in params and params['search'][0].strip():
            kw = f"%{params['search'][0].strip()}%"
            conditions.append("(c.full_name LIKE ? OR c.phone LIKE ? OR ct.milestone_title LIKE ?)")
            sql_params.extend([kw, kw, kw])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f'''
        SELECT ct.*, c.full_name as customer_name, c.phone as customer_phone, c.address as customer_address,
               c.customer_type, c.source, c.stage, u.full_name as assigned_name, u.phone as assigned_phone,
               o.order_code, o.total_amount as order_amount, o.delivery_date
        FROM care_tasks ct
        JOIN customers c ON ct.customer_id = c.id
        JOIN users u ON ct.assigned_user_id = u.id
        LEFT JOIN orders o ON ct.order_id = o.id
        {where_clause}
        ORDER BY
            CASE ct.status
                WHEN 'Quá hạn' THEN 1
                WHEN 'Đến hạn hôm nay' THEN 2
                WHEN 'Chưa đến hạn' THEN 3
                WHEN 'Đã chăm' THEN 4
                ELSE 5
            END,
            ct.scheduled_date ASC
        ''', sql_params)

        tasks = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "tasks": tasks, "count": len(tasks)})

    def handle_complete_care_task(self):
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        task_id = body.get('id')
        result_status = body.get('result_status', 'Hẹn gọi lại') # 'Khách cần báo giá', 'Hẹn gọi lại', 'Chưa có nhu cầu', 'Đã đặt đơn mới'
        result_notes = body.get('result_notes', '').strip()

        if not task_id:
            self.send_json({"success": False, "message": "Thiếu mã lịch chăm sóc."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM care_tasks WHERE id = ?", (task_id,))
        task = cur.fetchone()
        if not task:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy lịch chăm sóc."}, status=404)
            return

        if user['role'] != 'admin' and task['assigned_user_id'] != user['id']:
            conn.close()
            self.send_json({"success": False, "message": "Bạn không thể cập nhật lịch chăm sóc của người khác."}, status=403)
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute('''
        UPDATE care_tasks
        SET status = 'Đã chăm', result_status = ?, result_notes = ?,
            cared_by_user_id = ?, cared_at = ?, updated_at = ?
        WHERE id = ?
        ''', (result_status, result_notes, user['id'], now_str, now_str, task_id))

        # Đồng thời ghi nhận vào lịch sử trao đổi interactions của khách hàng
        cur.execute('''
        INSERT INTO interactions (customer_id, user_id, contact_type, content, reaction, next_date, created_at)
        VALUES (?, ?, 'Chăm sóc định kỳ', ?, ?, ?, ?)
        ''', (task['customer_id'], user['id'], f"[{task['milestone_title']}] - {result_notes or 'Đã liên hệ thăm hỏi khách hàng'}", result_status, task['scheduled_date'], now_str))

        # Cập nhật thời điểm liên hệ gần nhất cho khách
        cur.execute("UPDATE customers SET last_contacted_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, task['customer_id']))

        conn.commit()
        conn.close()

        log_audit(user['id'], user['full_name'], 'UPDATE', 'care_task', str(task_id), f"Đã chăm mốc [{task['milestone_title']}]. Kết quả: {result_status}", self.get_client_ip())

        self.send_json({"success": True, "message": "Đã ghi nhận chăm sóc khách hàng thành công!"})

    def handle_get_notifications(self):
        user = self.require_auth()
        if not user:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db()
        cur = conn.cursor()

        is_admin = user['role'] == 'admin'
        user_filter = "" if is_admin else f"AND ct.assigned_user_id = {user['id']}"

        cur.execute(f'''
        SELECT ct.id, ct.milestone_title, ct.scheduled_date, ct.status,
               c.full_name as customer_name, c.phone as customer_phone, u.full_name as assigned_name
        FROM care_tasks ct
        JOIN customers c ON ct.customer_id = c.id
        JOIN users u ON ct.assigned_user_id = u.id
        WHERE ct.status IN ('Quá hạn', 'Đến hạn hôm nay') {user_filter}
        ORDER BY CASE WHEN ct.status = 'Quá hạn' THEN 1 ELSE 2 END, ct.scheduled_date ASC
        LIMIT 10
        ''')

        items = [dict(r) for r in cur.fetchall()]
        conn.close()

        total_badge = len(items)

        self.send_json({"success": True, "badge_count": total_badge, "notifications": items})

    # ==================== KỊCH BẢN (SCRIPTS) ====================

    def handle_get_scripts(self, params):
        user = self.require_auth()
        if not user:
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT * FROM message_templates ORDER BY milestone_code ASC, id ASC")
        scripts = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "scripts": scripts})

    def handle_save_script(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        script_id = body.get('id')
        milestone_code = body.get('milestone_code', '5d')
        milestone_title = body.get('milestone_title', 'Mốc 5 ngày')
        customer_type = body.get('customer_type', 'Tất cả')
        title = body.get('title', '').strip()
        content = body.get('content', '').strip()

        if not title or not content:
            self.send_json({"success": False, "message": "Vui lòng nhập Tiêu đề và Nội dung kịch bản."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        if script_id:
            cur.execute('''
            UPDATE message_templates
            SET milestone_code = ?, milestone_title = ?, customer_type = ?, title = ?, content = ?
            WHERE id = ?
            ''', (milestone_code, milestone_title, customer_type, title, content, script_id))
        else:
            cur.execute('''
            INSERT INTO message_templates (milestone_code, milestone_title, customer_type, title, content)
            VALUES (?, ?, ?, ?, ?)
            ''', (milestone_code, milestone_title, customer_type, title, content))

        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'SAVE', 'script', title, f"Lưu mẫu kịch bản chăm sóc: {title}", self.get_client_ip())

        self.send_json({"success": True, "message": "Đã lưu kịch bản tin nhắn chăm sóc thành công!"})

    def handle_delete_script(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        script_id = body.get('id')
        if not script_id:
            self.send_json({"success": False, "message": "Thiếu mã kịch bản."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM message_templates WHERE id = ?", (script_id,))
        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'DELETE', 'script', str(script_id), "Xóa mẫu kịch bản", self.get_client_ip())

        self.send_json({"success": True, "message": "Đã xóa kịch bản thành công."})

    def handle_render_script(self):
        """
        NÚT 'GỬI ZALO':
        - Tự động điền các biến: {ten_khach}, {ten_nhan_vien}, {ma_don}, {ngay_giao}, {ten_cong_ty}
        - Trả về nội dung hoàn chỉnh và URL zalo.me/{so_dien_thoai}
        """
        user = self.require_auth()
        if not user:
            return

        body = self.read_post_body()
        customer_id = body.get('customer_id')
        milestone_code = body.get('milestone_code', '5d')
        template_id = body.get('template_id')
        order_id = body.get('order_id')
        if order_id in ('null', '', 0, '0', None):
            order_id = None

        if not customer_id:
            self.send_json({"success": False, "message": "Thiếu mã khách hàng."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()

        # 1. Thông tin khách hàng
        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        cust = cur.fetchone()
        if not cust:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy khách hàng."}, status=404)
            return

        # 2. Thông tin đơn hàng (gần nhất nếu không truyền order_id)
        order = None
        if order_id:
            cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            order = cur.fetchone()
        if not order:
            cur.execute("SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC LIMIT 1", (customer_id,))
            order = cur.fetchone()

        # 3. Kịch bản mẫu phù hợp
        template = None
        if template_id:
            cur.execute("SELECT * FROM message_templates WHERE id = ?", (template_id,))
            template = cur.fetchone()
        if not template:
            # Ưu tiên tìm theo loại khách, sau đó lấy template 'Tất cả'
            cur.execute('''
            SELECT * FROM message_templates
            WHERE milestone_code = ? AND (customer_type = ? OR customer_type = 'Tất cả')
            ORDER BY CASE WHEN customer_type = ? THEN 1 ELSE 2 END
            LIMIT 1
            ''', (milestone_code, cust['customer_type'], cust['customer_type']))
            template = cur.fetchone()

        # 4. Tên công ty
        cur.execute("SELECT value FROM settings WHERE key = 'company_name'")
        c_name_row = cur.fetchone()
        company_name = c_name_row['value'] if c_name_row else "Tổng Kho Bulong Ốc Vít Long Zhuang"

        conn.close()

        # Thay thế biến tự động
        raw_content = template['content'] if template else "Chào anh/chị {ten_khach}, em là {ten_nhan_vien} bên {ten_cong_ty}. Em xin phép hỏi thăm tình hình sử dụng vật tư bên mình ạ!"

        # Chuẩn bị dữ liệu biến
        ten_khach = cust['full_name']
        ten_nhan_vien = user['full_name']
        ma_don = order['order_code'] if order else "gần nhất"
        ngay_giao = ""
        if order and order['delivery_date']:
            try:
                dt = datetime.strptime(order['delivery_date'], "%Y-%m-%d")
                ngay_giao = dt.strftime("%d/%m/%Y")
            except Exception:
                ngay_giao = order['delivery_date']
        else:
            ngay_giao = "vừa qua"

        rendered_text = raw_content\
            .replace("{ten_khach}", ten_khach)\
            .replace("{ten_nhan_vien}", ten_nhan_vien)\
            .replace("{ma_don}", ma_don)\
            .replace("{ngay_giao}", ngay_giao)\
            .replace("{ten_cong_ty}", company_name)

        clean_phone = normalize_phone(cust['phone'])
        zalo_url = f"https://zalo.me/{clean_phone}"

        self.send_json({
            "success": True,
            "rendered_text": rendered_text,
            "customer_name": ten_khach,
            "customer_phone": clean_phone,
            "zalo_url": zalo_url,
            "template_title": template['title'] if template else "Kịch bản chuẩn"
        })

    # ==================== NHÂN VIÊN (EMPLOYEES - SẾP QUẢN LÝ) ====================

    def handle_get_employees(self):
        admin = self.require_admin()
        if not admin:
            return

        month_start = datetime.now().strftime("%Y-%m-01")
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
        SELECT u.id, u.username, u.email, u.phone, u.full_name, u.role, u.is_active, u.created_at,
               ep.code, ep.dob, ep.gender, ep.cccd, ep.address, ep.start_date, ep.position, ep.contract_type,
               ep.monthly_target, ep.notes, ep.avatar_color,
               COUNT(DISTINCT c.id) as customer_count,
               COALESCE(SUM(o.total_amount), 0) as month_revenue,
               COUNT(DISTINCT o.id) as month_orders,
               SUM(CASE WHEN ct.status = 'Quá hạn' THEN 1 ELSE 0 END) as overdue_tasks,
               SUM(CASE WHEN ct.status = 'Đã chăm' THEN 1 ELSE 0 END) as done_tasks
        FROM users u
        LEFT JOIN employee_profiles ep ON u.id = ep.user_id
        LEFT JOIN customers c ON u.id = c.assigned_user_id
        LEFT JOIN orders o ON u.id = o.user_id AND o.order_date >= ?
        LEFT JOIN care_tasks ct ON u.id = ct.assigned_user_id
        GROUP BY u.id
        ORDER BY u.role ASC, u.id ASC
        ''', (month_start,))

        employees = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "employees": employees})

    def handle_save_employee(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        emp_id = body.get('id')
        code = body.get('code', '').strip().upper()
        full_name = body.get('full_name', '').strip()
        email = body.get('email', '').strip().lower()
        phone_raw = body.get('phone', '').strip()
        phone = normalize_phone(phone_raw)
        role = body.get('role', 'sales') # 'admin' hoặc 'sales'
        password = body.get('password', '').strip()

        # Profile fields (CCCD & Ngày sinh là tùy chọn - không bắt buộc)
        dob = body.get('dob', '')
        gender = body.get('gender', 'Nam')
        cccd = body.get('cccd', '').strip()
        address = body.get('address', '').strip()
        start_date = body.get('start_date', datetime.now().strftime("%Y-%m-%d"))
        position = body.get('position', '').strip() or ('Ban Giám Đốc' if role == 'admin' else 'Chuyên viên Kinh doanh')
        contract_type = body.get('contract_type', 'Hợp đồng 1 năm')
        try:
            monthly_target = int(str(body.get('monthly_target', 150000000)).replace('.', '').replace(',', '').strip() or 150000000)
        except (ValueError, TypeError):
            monthly_target = 150000000
        notes = body.get('notes', '').strip()
        avatar_color = body.get('avatar_color', '#3B5BFF')

        # 1. Kiểm tra Họ tên
        if not full_name:
            self.send_json({"success": False, "field": "full_name", "message": "Vui lòng nhập Họ và tên nhân viên."}, status=400)
            return

        # 2. Kiểm tra Số điện thoại
        if not phone or len(phone) < 9 or len(phone) > 12:
            self.send_json({"success": False, "field": "phone", "message": "Số điện thoại không hợp lệ (phải từ 9 đến 11 chữ số)."}, status=400)
            return

        # 3. Kiểm tra Email
        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            self.send_json({"success": False, "field": "email", "message": "Địa chỉ email không đúng định dạng (ví dụ: nhanvien@longzhuang.vn)."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 4. Kiểm tra trùng Email
        if emp_id:
            cur.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, emp_id))
        else:
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            conn.close()
            self.send_json({"success": False, "field": "email", "message": f"Email [{email}] đã tồn tại trong hệ thống. Vui lòng dùng email khác."}, status=400)
            return

        # 5. Kiểm tra trùng SĐT
        if emp_id:
            cur.execute("SELECT id FROM users WHERE phone = ? AND id != ?", (phone, emp_id))
        else:
            cur.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        if cur.fetchone():
            conn.close()
            self.send_json({"success": False, "field": "phone", "message": f"Số điện thoại [{phone}] đã được đăng ký cho nhân viên khác."}, status=400)
            return

        # 6. Kiểm tra trùng Mã nhân viên
        if code:
            if emp_id:
                cur.execute("SELECT user_id FROM employee_profiles WHERE code = ? AND user_id != ?", (code, emp_id))
            else:
                cur.execute("SELECT user_id FROM employee_profiles WHERE code = ?", (code,))
            if cur.fetchone():
                conn.close()
                self.send_json({"success": False, "field": "code", "message": f"Mã nhân viên [{code}] đã tồn tại. Vui lòng chọn mã khác."}, status=400)
                return

        generated_temp_pw = None

        if emp_id:
            # Cập nhật nhân viên hiện có
            cur.execute('''
            UPDATE users
            SET full_name = ?, email = ?, phone = ?, role = ?, updated_at = ?
            WHERE id = ?
            ''', (full_name, email, phone, role, now_str, emp_id))

            # Nếu có đổi mật khẩu
            if password and len(password) >= 6:
                new_h, new_s = hash_pw(password)
                cur.execute("UPDATE users SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?", (new_h, new_s, emp_id))

            final_code = code if code else ('GD-01' if role == 'admin' else f"KD-0{emp_id}")

            cur.execute('''
            INSERT INTO employee_profiles (user_id, code, dob, gender, cccd, address, start_date, position, contract_type, monthly_target, notes, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                code=excluded.code, dob=excluded.dob, gender=excluded.gender, cccd=excluded.cccd, address=excluded.address,
                start_date=excluded.start_date, position=excluded.position, contract_type=excluded.contract_type,
                monthly_target=excluded.monthly_target, notes=excluded.notes, avatar_color=excluded.avatar_color
            ''', (emp_id, final_code, dob, gender, cccd, address, start_date, position, contract_type, monthly_target, notes, avatar_color))

            msg = f"Đã cập nhật hồ sơ nhân viên [{full_name}] thành công!"
            audit_action = 'UPDATE'
            audit_target_id = str(emp_id)
            audit_desc = f"Cập nhật hồ sơ nhân viên: {full_name}"
        else:
            # Tạo nhân viên mới: Nếu để trống mật khẩu -> Sinh mật khẩu tạm ngẫu nhiên
            if not password:
                rand_num = secrets.randbelow(900000) + 100000
                generated_temp_pw = f"LZ@{rand_num}"
                final_pw = generated_temp_pw
            else:
                if len(password) < 6:
                    conn.close()
                    self.send_json({"success": False, "field": "password", "message": "Mật khẩu phải có ít nhất 6 ký tự."}, status=400)
                    return
                final_pw = password

            pw_h, salt = hash_pw(final_pw)
            cur.execute('''
            INSERT INTO users (username, email, phone, password_hash, salt, full_name, role, is_active, must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            ''', (email, email, phone, pw_h, salt, full_name, role, now_str, now_str))
            new_uid = cur.lastrowid
            final_code = code if code else ('GD-01' if role == 'admin' else f"KD-0{new_uid}")

            cur.execute('''
            INSERT INTO employee_profiles (user_id, code, dob, gender, cccd, address, start_date, position, contract_type, monthly_target, notes, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_uid, final_code, dob, gender, cccd, address, start_date, position, contract_type, monthly_target, notes, avatar_color))

            pw_notice = f" Mật khẩu khởi tạo: [{final_pw}]. Nhân viên sẽ được yêu cầu đổi mật khẩu ở lần đăng nhập đầu tiên." if generated_temp_pw else " Nhân viên sẽ được yêu cầu đổi mật khẩu ở lần đăng nhập đầu tiên."
            msg = f"Tạo mới tài khoản nhân viên [{full_name}] ({final_code}) thành công!{pw_notice}"
            audit_action = 'CREATE'
            audit_target_id = str(new_uid)
            audit_desc = f"Tạo mới nhân viên: {full_name} ({email})"

        conn.commit()
        conn.close()

        # Gọi log_audit SAU KHI commit và đóng kết nối để tránh SQLite deadlock
        log_audit(admin['id'], admin['full_name'], audit_action, 'user', audit_target_id, audit_desc, self.get_client_ip())

        self.send_json({
            "success": True,
            "message": msg,
            "employee_id": new_uid if not emp_id else int(emp_id),
            "temp_password": generated_temp_pw,
            "temporary_password": generated_temp_pw,
            "must_change_password": True if not emp_id else False
        })

    def handle_toggle_lock_employee(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        emp_id = body.get('id')
        if not emp_id or int(emp_id) == admin['id']:
            self.send_json({"success": False, "message": "Không thể khóa tài khoản của chính mình."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT full_name, is_active FROM users WHERE id = ?", (emp_id,))
        u = cur.fetchone()
        if not u:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy người dùng."}, status=404)
            return

        new_status = 0 if u['is_active'] == 1 else 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?", (new_status, now_str, emp_id))
        if new_status == 0:
            # Xóa sạch phiên đăng nhập bền vững của nhân viên này để đăng xuất lập tức
            cur.execute("DELETE FROM sessions WHERE user_id = ?", (emp_id,))
        conn.commit()
        conn.close()

        action_name = "Khóa tài khoản" if new_status == 0 else "Mở khóa tài khoản"
        log_audit(admin['id'], admin['full_name'], 'LOCK_USER', 'user', str(emp_id), f"{action_name}: {u['full_name']}", self.get_client_ip())

        self.send_json({"success": True, "message": f"Đã {action_name.lower()} [{u['full_name']}] thành công!"})

    def handle_reset_employee_password(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        emp_id = body.get('id')
        new_pw = body.get('new_password', '123456').strip()

        if not emp_id or len(new_pw) < 6:
            self.send_json({"success": False, "message": "Mật khẩu mới phải có ít nhất 6 ký tự."}, status=400)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT full_name FROM users WHERE id = ?", (emp_id,))
        u = cur.fetchone()
        if not u:
            conn.close()
            self.send_json({"success": False, "message": "Không tìm thấy người dùng."}, status=404)
            return

        h, s = hash_pw(new_pw)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE users SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?", (h, s, now_str, emp_id))
        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'RESET_PW', 'user', str(emp_id), f"Đặt lại mật khẩu cho nhân viên {u['full_name']}", self.get_client_ip())

        self.send_json({"success": True, "message": f"Đã đặt lại mật khẩu cho [{u['full_name']}] thành [{new_pw}] thành công!"})

    # ==================== BÁO CÁO (REPORTS - SẾP QUẢN LÝ) ====================

    def handle_get_reports(self, params):
        admin = self.require_admin()
        if not admin:
            return

        conn = get_db()
        cur = conn.cursor()

        # 1. Tỷ lệ khách tiềm năng chuyển thành khách mua (Khách cũ)
        cur.execute("SELECT COUNT(*) FROM customers")
        total_cust = cur.fetchone()[0] or 1

        cur.execute("SELECT COUNT(*) FROM customers WHERE stage = 'Khách cũ'")
        converted_cust = cur.fetchone()[0]
        conversion_rate = round((converted_cust / total_cust) * 100, 1)

        # 2. Khách mới theo nguồn & doanh thu mang lại
        cur.execute('''
        SELECT c.source, COUNT(DISTINCT c.id) as customer_count,
               COUNT(DISTINCT o.id) as order_count,
               COALESCE(SUM(o.total_amount), 0) as total_revenue
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
        GROUP BY c.source
        ORDER BY total_revenue DESC
        ''')
        source_breakdown = [dict(r) for r in cur.fetchall()]

        # 3. Doanh thu theo tháng (6 tháng gần nhất)
        cur.execute('''
        SELECT strftime('%Y-%m', order_date) as month,
               COUNT(id) as order_count,
               COALESCE(SUM(total_amount), 0) as monthly_revenue
        FROM orders
        GROUP BY month
        ORDER BY month ASC
        LIMIT 6
        ''')
        revenue_by_month = [dict(r) for r in cur.fetchall()]

        # 4. Tỷ lệ chăm sóc đúng hạn theo từng nhân viên
        cur.execute('''
        SELECT u.id, u.full_name,
               COUNT(ct.id) as total_tasks,
               SUM(CASE WHEN ct.status = 'Đã chăm' THEN 1 ELSE 0 END) as done_tasks,
               SUM(CASE WHEN ct.status = 'Quá hạn' THEN 1 ELSE 0 END) as overdue_tasks,
               ROUND(
                   CASE WHEN COUNT(ct.id) > 0
                        THEN (CAST(SUM(CASE WHEN ct.status = 'Đã chăm' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(ct.id)) * 100
                        ELSE 0
                   END, 1
               ) as on_time_rate
        FROM users u
        LEFT JOIN care_tasks ct ON u.id = ct.assigned_user_id
        WHERE u.role = 'sales' AND u.is_active = 1
        GROUP BY u.id
        ORDER BY on_time_rate DESC
        ''')
        employee_care_rate = [dict(r) for r in cur.fetchall()]

        # 5. Danh sách khách lâu không mua (trên 45-60 ngày)
        forty_five_days_ago = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
        cur.execute('''
        SELECT c.id, c.full_name, c.phone, c.customer_type, u.full_name as assigned_name,
               MAX(o.order_date) as last_order_date,
               (julianday('now') - julianday(MAX(o.order_date))) as days_since_last_order,
               COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM customers c
        JOIN orders o ON c.id = o.customer_id
        JOIN users u ON c.assigned_user_id = u.id
        WHERE c.stage = 'Khách cũ'
        GROUP BY c.id
        HAVING last_order_date <= ?
        ORDER BY days_since_last_order DESC
        LIMIT 20
        ''', (forty_five_days_ago,))
        inactive_customers = [dict(r) for r in cur.fetchall()]
        for ic in inactive_customers:
            ic['days_since_last_order'] = int(ic['days_since_last_order'] or 0)

        conn.close()

        self.send_json({
            "success": True,
            "metrics": {
                "total_customers": total_cust,
                "converted_customers": converted_cust,
                "conversion_rate": conversion_rate
            },
            "source_breakdown": source_breakdown,
            "revenue_by_month": revenue_by_month,
            "employee_care_rate": employee_care_rate,
            "inactive_customers": inactive_customers
        })

    def handle_export_excel(self):
        admin = self.require_admin()
        if not admin:
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
        SELECT c.id, c.full_name, c.phone, c.address, c.customer_type, c.source, c.stage,
               u.full_name as assigned_name, c.created_at,
               (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) as order_count,
               (SELECT COALESCE(SUM(total_amount), 0) FROM orders o WHERE o.customer_id = c.id) as total_revenue
        FROM customers c
        JOIN users u ON c.assigned_user_id = u.id
        ORDER BY c.id ASC
        ''')
        rows = cur.fetchall()
        conn.close()

        # Tạo file CSV UTF-8 kèm BOM để mở thẳng trên Microsoft Excel không bị vỡ font tiếng Việt
        lines = ["Mã KH,Tên Khách Hàng,Số Điện Thoại,Địa Chỉ,Loại Khách,Nguồn Khách,Giai Đoạn,Nhân Viên Phụ Trách,Số Đơn Hàng,Tổng Doanh Số (VNĐ),Ngày Nhập"]
        for r in rows:
            name = f'"{r["full_name"]}"'
            addr = f'"{r["address"] or ""}"'
            rev = r["total_revenue"]
            line = f'{r["id"]},{name},{r["phone"]},{addr},{r["customer_type"]},{r["source"]},{r["stage"]},{r["assigned_name"]},{r["order_count"]},{rev},{r["created_at"]}'
            lines.append(line)

        csv_content = "\ufeff" + "\n".join(lines)
        encoded = csv_content.encode('utf-8')

        log_audit(admin['id'], admin['full_name'], 'EXPORT', 'customers', 'all', "Xuất báo cáo danh sách khách hàng sang Excel", self.get_client_ip())

        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename="CRM_Long_Zhuang_Export.csv"')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # ==================== CÀI ĐẶT & HỆ THỐNG ====================

    def handle_get_settings(self):
        admin = self.require_admin()
        if not admin:
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        s = dict(cur.fetchall())
        conn.close()

        self.send_json({"success": True, "settings": s})

    def handle_save_settings(self):
        admin = self.require_admin()
        if not admin:
            return

        body = self.read_post_body()
        conn = get_db()
        cur = conn.cursor()

        for k, v in body.items():
            cur.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))

        conn.commit()
        conn.close()

        log_audit(admin['id'], admin['full_name'], 'UPDATE', 'settings', 'all', "Cập nhật cấu hình hệ thống", self.get_client_ip())

        self.send_json({"success": True, "message": "Đã lưu cài đặt hệ thống thành công!"})

    def handle_get_audit_logs(self, params):
        admin = self.require_admin()
        if not admin:
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100")
        logs = [dict(r) for r in cur.fetchall()]
        conn.close()

        self.send_json({"success": True, "logs": logs})

    def handle_download_backup(self):
        admin = self.require_admin()
        if not admin:
            return

        if not os.path.exists(DB_PATH):
            self.send_json({"success": False, "message": "File cơ sở dữ liệu không tồn tại."}, status=404)
            return

        with open(DB_PATH, 'rb') as f:
            data = f.read()

        today_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_audit(admin['id'], admin['full_name'], 'BACKUP', 'database', 'download', "Tải bản sao lưu database", self.get_client_ip())

        self.send_response(200)
        self.send_header('Content-Type', 'application/x-sqlite3')
        self.send_header('Content-Disposition', f'attachment; filename="crm_long_zhuang_backup_{today_str}.db"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def run():
    server_address = ('0.0.0.0', PORT)
    httpd = ThreadingHTTPServer(server_address, CRMRequestHandler)
    local_ip = get_local_ip()
    print("=" * 70)
    print("★ TỔNG KHO BULONG ỐC VÍT LONG ZHUANG HẢI PHÒNG")
    print("★ HỆ THỐNG CRM QUẢN TRỊ & CHĂM SÓC KHÁCH HÀNG CHUYÊN NGHIỆP")
    print("=" * 70)
    print(f"[*] Máy chủ đang hoạt động tại cổng: {PORT}")
    print(f"[*] Mở trên máy tính: http://localhost:{PORT}")
    print(f"[*] Mở trên điện thoại: http://{local_ip}:{PORT}")
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Đang tắt máy chủ...")
        httpd.server_close()

if __name__ == '__main__':
    run()
