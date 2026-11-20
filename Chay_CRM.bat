@echo off
chcp 65001 >nul
title LONG ZHUANG CRM - HỆ THỐNG QUẢN TRỊ & CHĂM SÓC KHÁCH HÀNG
color 0B
cls
echo ====================================================================
echo   ★ TỔNG KHO BULONG ỐC VÍT LONG ZHUANG HẢI PHÒNG
echo   ★ HỆ THỐNG QUẢN LÝ & NHẮC LỊCH CHĂM SÓC KHÁCH HÀNG (CRM PRO)
echo ====================================================================
echo.
echo [*] Đang khởi động máy chủ dữ liệu bảo mật trên cổng 8099...

cd /d "%~dp0"

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8099"

echo [*] Đang mở trình duyệt web: http://localhost:8099
echo.
echo ====================================================================
echo   HỆ THỐNG ĐANG HOẠT ĐỘNG - VUI LÒNG GIỮ CỬA SỔ NÀY KHI LÀM VIỆC
echo   (Khi muốn tắt hệ thống, bạn chỉ cần đóng cửa sổ này lại)
echo ====================================================================
echo.

REM Dọn dẹp tiến trình cũ nếu cổng 8099 đang bận
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8099 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul

python server.py
pause
