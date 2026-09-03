@echo off
cd /d "%~dp0"
echo ================================================================
echo CHAVE SECRETA PARA SINCRONIZACAO V11
echo ================================================================
python GERAR_CHAVE_SYNC.py
echo.
echo Copie a chave acima. Use exatamente a mesma no servidor online
echo e no menu Online / Offline do computador local.
pause
