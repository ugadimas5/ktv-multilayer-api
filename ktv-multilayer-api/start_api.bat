@echo off
REM KTV EUDR Multilayer API - Windows Startup Script
REM Loads environment variables and starts the API server

echo 🚀 Starting KTV EUDR Multilayer API...
echo ====================================

REM Check if .env file exists
if not exist ".env" (
    echo ❌ .env file not found!
    echo 📋 Please copy .env.example to .env and configure your settings
    echo.
    echo Commands:
    echo   copy .env.example .env
    echo   notepad .env
    echo.
    pause
    exit /b 1
)

REM Load environment variables from .env file
echo 📄 Loading environment variables from .env...
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if not "%%a"=="" if not "%%a:~0,1"=="#" (
        set "%%a=%%b"
        echo    ✅ %%a=%%b
    )
)

echo.
echo 🔧 Configuration:
echo    📁 Service Accounts: %EE_SERVICE_ACCOUNT_PATH%
echo    ⚡ Parallel Processing: %ENABLE_PARALLEL_PROCESSING%
echo    👥 Max Workers: %MAX_PARALLEL_WORKERS%
echo    🌍 Host: %API_HOST%:%API_PORT%
echo.

REM Check if service accounts exist
echo 🔑 Checking service accounts...
set /a count=0
for %%f in (authentication\eudr-*.json) do set /a count+=1

if %count% gtr 0 (
    echo    ✅ Found %count% service account files
) else (
    echo    ⚠️  No service account files found in authentication/
    echo    📋 Expected files: eudr-0.json, eudr-1.json, ..., eudr-15.json
)

echo.
echo 🚀 Starting API server...
echo    📊 Open browser: http://localhost:%API_PORT%/docs
echo    📈 API Documentation: http://localhost:%API_PORT%/redoc
echo.

REM Start the server
uvicorn app:app --host %API_HOST% --port %API_PORT% --reload

pause
