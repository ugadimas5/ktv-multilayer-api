@echo off
REM Windows batch script untuk setup 16 Google Service Accounts
REM Jalankan script ini setelah membuat service accounts di Google Cloud Console

echo === EUDR Service Accounts Setup (Windows) ===
echo This script will help you verify and test 16 Google Service Accounts
echo.

REM Check if authentication directory exists
if not exist "authentication" (
    echo Creating authentication directory...
    mkdir authentication
)

echo Checking for service account files...
echo Required files: eudr-0.json to eudr-15.json
echo.

REM Check each service account file
set missing_count=0
set existing_count=0

for /L %%i in (0,1,15) do (
    set file=authentication\eudr-%%i.json
    if exist "!file!" (
        echo ✅ !file! exists
        set /a existing_count+=1
    ) else (
        echo ❌ !file! missing
        set /a missing_count+=1
    )
)

echo.
echo Summary:
echo   Existing: %existing_count%
echo   Missing: %missing_count%
echo.

if %missing_count% GTR 0 (
    echo ⚠️  You need to add %missing_count% more service account files
    echo.
    echo Steps to add missing service accounts:
    echo 1. Go to Google Cloud Console ^> IAM ^& Admin ^> Service Accounts
    echo 2. Create new service accounts with names: eudr-0, eudr-1, etc.
    echo 3. Download JSON keys and place them in authentication\ folder
    echo 4. Register each account with Earth Engine API
    echo.
)

REM Check if Python dependencies are available
echo Checking Python dependencies...
python -c "import ee" 2>nul
if %errorlevel% EQU 0 (
    echo ✅ earthengine-api is available
    echo.
    echo Testing service account authentication...
    python authentication\auth_helper.py
) else (
    echo ❌ earthengine-api not found
    echo Install with: pip install earthengine-api
)

echo.
echo === Setup Complete ===
echo Next steps:
echo 1. Add missing service account JSON files
echo 2. Run: python authentication\auth_helper.py
echo 3. Test with your EUDR compliance API

pause
