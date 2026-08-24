@echo off
title Gerador - Consulta de Preco PDF

echo ==========================================
echo   GERANDO Consulta de Preco PDF
echo ==========================================
echo.

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar dependencias.
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean --onefile --windowed --name ConsultaPrecoPDF app.py

echo.
echo ==========================================
echo   PRONTO!
echo ==========================================
echo.
echo O programa esta em:
echo dist\ConsultaPrecoPDF.exe
echo.
pause
