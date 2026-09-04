@echo off
setlocal

rem Optional: override host/port
set HOST=0.0.0.0
set PORT=8080
set NO_ACCESS_LOG=1
set DEBUG_LOG_URL=false
set use_finance_eastmoney_v2=true
rem Cookie: load from D:\stock\cookies\*.txt (FIN_COOKIE_DIR takes precedence)
set FIN_COOKIE_DIR=D:\stock\cookies

rem Optional: override log file path, e.g. D:\stock\logs\urlLogs.log
rem set DEBUG_LOG_URL_PATH=D:\stock\logs\urlLogs.log
rem Optional: set LOG_LEVEL=warning|error|critical

dist\fin-service.exe
