@echo off
setlocal

rem Optional: override host/port
set HOST=0.0.0.0
set PORT=8080
set DEBUG_LOG_URL=false
set use_finance_eastmoney_v2=true
rem Cookie: load from D:\stock\cookies\*.txt (FIN_COOKIE_DIR takes precedence)
set FIN_COOKIE_DIR=D:\stock\cookies
rem MongoDB: use docker-compose MongoDB instance (host port 27017 -> etf-mongodb)
set FIN_MONGO_URI=mongodb://127.0.0.1:27017
set FIN_MONGO_DB=stock

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m uvicorn app.main:app --host %HOST% --port %PORT% --no-access-log
  goto :eof
)

python -m uvicorn app.main:app --host %HOST% --port %PORT% --no-access-log
