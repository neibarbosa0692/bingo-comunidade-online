@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bingo Comunidade - Simular 200 vendas
where py >nul 2>nul
if %errorlevel%==0 (
  py "02_SIMULAR_VENDAS_200_CARTELAS.py"
) else (
  python "02_SIMULAR_VENDAS_200_CARTELAS.py"
)
echo.
pause
