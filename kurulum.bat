@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === gameeng2tr kurulumu ===
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul || (
        echo Python bulunamadi. https://www.python.org/downloads/ adresinden Python 3.11 veya 3.12 kurun
        echo ve kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
        pause
        exit /b 1
    )
    set "PY=python"
)

if not exist venv (
    echo [1/4] Sanal ortam olusturuluyor...
    %PY% -m venv venv || (echo Sanal ortam olusturulamadi & pause & exit /b 1)
)

echo [2/4] Paketler kuruluyor...
venv\Scripts\python -m pip install --upgrade pip >nul
venv\Scripts\python -m pip install -r requirements.txt || (echo Paket kurulumu basarisiz & pause & exit /b 1)

echo [3/4] OneOCR hazirlaniyor (istege bagli)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0oneocr_kur.ps1"

echo [4/4] Ceviri modelleri hazirlaniyor (bir kez, internet gerekir)...
venv\Scripts\python -m gameeng2tr.setup_models

echo.
echo Kurulum bitti. Uygulamayi baslatmak icin baslat.bat dosyasini calistirin.
pause
