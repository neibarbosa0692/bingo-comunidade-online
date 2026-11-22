@echo off
setlocal
cd /d "%~dp0"
title Bingo Comunidade - Gerar EXE

echo ============================================================
echo BINGO COMUNIDADE - GERACAO DO EXECUTAVEL WINDOWS
echo ============================================================
echo.

if not exist "bingo.db" (
  echo ERRO: bingo.db nao foi encontrado nesta pasta.
  echo Gere o EXE somente dentro da pasta que contem o banco oficial.
  pause
  exit /b 1
)

if not exist ".venv_exe\Scripts\python.exe" (
  py -m venv .venv_exe 2>nul || python -m venv .venv_exe
)
call ".venv_exe\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements_desktop.txt
if errorlevel 1 goto :erro

python -m PyInstaller --noconfirm --clean BingoComunidade.spec
if errorlevel 1 goto :erro

if not exist "dist\Bingo Comunidade.exe" goto :erro
copy /Y "bingo.db" "dist\bingo.db" >nul
if exist ".secret_key" copy /Y ".secret_key" "dist\.secret_key" >nul

echo.
echo ============================================================
echo PRONTO.
echo EXE: %CD%\dist\Bingo Comunidade.exe
echo BANCO: %CD%\dist\bingo.db
echo ============================================================
echo.
echo IMPORTANTE: o banco copiado e o banco oficial existente neste momento.
echo Para uso definitivo, mantenha Bingo Comunidade.exe e bingo.db juntos.
pause
exit /b 0

:erro
echo.
echo ERRO ao gerar o executavel.
pause
exit /b 1
