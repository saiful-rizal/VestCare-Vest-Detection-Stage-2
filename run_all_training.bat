@echo off
setlocal
cd /d "%~dp0"
python start_train.py %*
exit /b %errorlevel%
