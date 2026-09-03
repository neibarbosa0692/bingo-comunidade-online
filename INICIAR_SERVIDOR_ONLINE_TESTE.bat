@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bingo V11 - Servidor Online de Teste
set BINGO_MODE=cloud
set BINGO_PORT=8899
set BINGO_DB_PATH=%~dp0bingo_cloud_teste.db
if "%BINGO_SYNC_TOKEN%"=="" set BINGO_SYNC_TOKEN=TESTE-V11-TROQUE-ESTA-CHAVE
python -c "import flask, reportlab, qrcode, PIL" >nul 2>&1
if errorlevel 1 python -m pip install -r requirements.txt
echo.
echo SERVIDOR ONLINE DE TESTE: http://127.0.0.1:8899/mobile
echo Chave de teste: %BINGO_SYNC_TOKEN%
echo.
python cloud_entry.py
pause
