@echo off
title Khoi dong AutoSub AI V4.0 Enterprise
color 0B

echo ===================================================
echo     DANG KHOI DONG AUTOSUB AI - NITRO V4.0
echo ===================================================
echo.

:: --- ÉP HUGGINGFACE TẢI MODEL VỀ Ô D (BẢO VỆ Ổ C) ---
set HF_HOME=D:\AutoSub_V4\.cache
set HF_HUB_DISABLE_SYMLINKS=1
:: ---------------------------------------------------

echo Dang kiem tra moi truong va thu vien tren o D...
.\venv\Scripts\python main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [CANH BAO] Phan mem gap loi hoac bi dong dot ngot!
    pause
)