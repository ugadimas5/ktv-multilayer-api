#!/bin/bash
# KTV EUDR Multilayer API - Linux/Mac Startup Script
# Loads environment variables and starts the API server

echo "🚀 Starting KTV EUDR Multilayer API..."
echo "===================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "📋 Please copy .env.example to .env and configure your settings"
    echo ""
    echo "Commands:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    exit 1
fi

# Load environment variables
echo "📄 Loading environment variables from .env..."
export $(grep -v '^#' .env | xargs)

echo ""
echo "🔧 Configuration:"
echo "   📁 Service Accounts: $EE_SERVICE_ACCOUNT_PATH"
echo "   ⚡ Parallel Processing: $ENABLE_PARALLEL_PROCESSING"  
echo "   👥 Max Workers: $MAX_PARALLEL_WORKERS"
echo "   🌍 Host: $API_HOST:$API_PORT"
echo ""

# Check service accounts
echo "🔑 Checking service accounts..."
count=$(ls authentication/eudr-*.json 2>/dev/null | wc -l)

if [ $count -gt 0 ]; then
    echo "   ✅ Found $count service account files"
else
    echo "   ⚠️  No service account files found in authentication/"
    echo "   📋 Expected files: eudr-0.json, eudr-1.json, ..., eudr-15.json"
fi

echo ""
echo "🚀 Starting API server..."
echo "   📊 Open browser: http://localhost:$API_PORT/docs"
echo "   📈 API Documentation: http://localhost:$API_PORT/redoc"
echo ""

# Start the server
uvicorn app:app --host $API_HOST --port $API_PORT --reload
