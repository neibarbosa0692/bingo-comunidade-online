@echo off
chcp 65001 >nul
title Instalar e iniciar Bingo Comunidade V11
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Python nao foi encontrado. Instale Python 3.11 ou superior e marque Add Python to PATH.
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)
call "%~dp0INICIAR_BINGO.bat"
