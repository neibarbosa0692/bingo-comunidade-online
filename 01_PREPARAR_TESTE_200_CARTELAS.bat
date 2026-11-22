@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bingo Comunidade - Preparar teste 200 cartelas
where py >nul 2>nul
if %errorlevel%==0 (
  py "01_PREPARAR_TESTE_200_CARTELAS.py"
) else (
  python "01_PREPARAR_TESTE_200_CARTELAS.py"
)
echo.
pause
