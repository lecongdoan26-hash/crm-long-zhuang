@echo off
chcp 65001 >nul
title KET NOI CRM LONG ZHUANG TU XA (MIEN PHI 100%%)
color 0B

echo ======================================================================
echo          LONG ZHUANG CRM PRO - KET NOI TU XA QUA CLOUDFLARE
echo               (Dung duoc tren Dien thoai / 4G / O nha)
echo ======================================================================
echo.
echo [*] Dang kiem tra cong cu Cloudflare Tunnel...

if not exist "%~dp0cloudflared.exe" (
    echo [*] Dang tu dong tai Cloudflare Tunnel chinh hang (chi ton ~15 giay)...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%~dp0cloudflared.exe'"
    if exist "%~dp0cloudflared.exe" (
        echo [OK] Da tai xong Cloudflare Tunnel!
    ) else (
        echo [!] Khong the tai tu dong. Vui long kiem tra ket noi mang.
        pause
        exit /b
    )
)

echo.
echo ======================================================================
echo [*] DANG KHOI TAO DUONG LINK TRUY CAP TU XA SECURE HTTPS...
echo [*] Duong link co dang: https://xxxx-xxxx.trycloudflare.com
echo [*] Hay copy duong link xuat hien ben duoi de gui cho Sep va Nhan vien!
echo ======================================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8899

pause
