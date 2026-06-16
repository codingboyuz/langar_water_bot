@echo off
chcp 65001 >nul
title Langar Water Bot - hammasi birga
cd /d "%~dp0"

echo ============================================
echo   LANGAR WATER BOT
echo   Mijoz boti + Kuryer boti + Admin panel
echo   Admin panel: http://localhost:8000
echo   Toxtatish uchun: Ctrl + C
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual muhit topilmadi. Birinchi marta sozlanmoqda...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [i] .env fayli yaratildi.
)

.venv\Scripts\python.exe run_all.py

echo.
echo Toxtatildi. Yopish uchun istalgan tugmani bosing.
pause >nul
