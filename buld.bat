@echo off
title Dong goi AutoSub AI thanh file EXE
color 0A

echo ===================================================
echo     DANG DONG GOI AUTOSUB AI - ENTERPRISE V4.0
echo ===================================================
echo.

:: Kiem tra xem da cai PyInstaller chua
.\venv\Scripts\python -m PyInstaller --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [THONG BAO] Chua co PyInstaller trong venv, dang tu dong cai dat...
    .\venv\Scripts\pip install pyinstaller
)

echo.
echo [1/3] Dang xoa cac ban build cu (neu co)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AutoSub_AI_Enterprise.spec del /f /q AutoSub_AI_Enterprise.spec

echo.
echo [2/3] Dang tien hanh dong goi. Vui long doi vai phut...
:: Lệnh đóng gói (Build dạng thư mục --onedir)
.\venv\Scripts\python -m PyInstaller ^
    --onedir ^
    --windowed ^
    --name "AutoSub_AI_Enterprise" ^
    --add-data "ffmpeg.exe;." ^
    --collect-all customtkinter ^
    --collect-all faster_whisper ^
    --collect-all edge_tts ^
    --collect-all pydub ^
    main.py

echo.
if %ERRORLEVEL% equ 0 (
    echo [3/3] HOAN TAT! 
    echo Phan mem da duoc dong goi thanh cong.
    echo Ban hay vao thu muc "dist\AutoSub_AI_Enterprise" de tim file .exe nhe!
    echo (Nho copy file config.json hoac api_keys.txt bo vao cung thu muc file .exe de app chay duoc).
) else (
    echo [LỖI] Qua trinh dong goi that bai. Vui long doc thong bao loi o tren.
)

pause