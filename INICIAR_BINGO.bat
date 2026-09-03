@echo off
chcp 65001 >nul
title Bingo Comunidade V11 - Online + Offline
cd /d "%~dp0"

echo ================================================================
echo BINGO COMUNIDADE V11 - SISTEMA HIBRIDO ONLINE + OFFLINE
echo ================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: Python nao foi encontrado.
  echo Instale Python 3.11 ou superior e marque Add Python to PATH.
  pause
  exit /b 1
)

python -c "import flask, reportlab, qrcode, PIL" >nul 2>&1
if errorlevel 1 (
  echo Dependencias ausentes. Instalando agora...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Nao foi possivel instalar as dependencias.
    pause
    exit /b 1
  )
)

echo Iniciando servidor LOCAL em uma porta livre automaticamente...
echo NAO feche esta janela enquanto estiver usando o sistema.
echo.
python launcher.py
pause
