#!/bin/bash
# Script setup untuk 16 Google Service Accounts
# Jalankan script ini setelah membuat service accounts di Google Cloud Console

echo "=== EUDR Service Accounts Setup ==="
echo "This script will help you verify and test 16 Google Service Accounts"
echo ""

# Check if authentication directory exists
if [ ! -d "authentication" ]; then
    echo "Creating authentication directory..."
    mkdir -p authentication
fi

echo "Checking for service account files..."
echo "Required files: eudr-0.json to eudr-15.json"
echo ""

# Check each service account file
missing_count=0
existing_count=0

for i in {0..15}; do
    file="authentication/eudr-${i}.json"
    if [ -f "$file" ]; then
        echo "✅ $file exists"
        existing_count=$((existing_count + 1))
    else
        echo "❌ $file missing"
        missing_count=$((missing_count + 1))
    fi
done

echo ""
echo "Summary:"
echo "  Existing: $existing_count"
echo "  Missing: $missing_count"
echo ""

if [ $missing_count -gt 0 ]; then
    echo "⚠️  You need to add $missing_count more service account files"
    echo ""
    echo "Steps to add missing service accounts:"
    echo "1. Go to Google Cloud Console > IAM & Admin > Service Accounts"
    echo "2. Create new service accounts with names: eudr-0, eudr-1, etc."
    echo "3. Download JSON keys and place them in authentication/ folder"
    echo "4. Register each account with Earth Engine API"
    echo ""
fi

# Check if Python dependencies are available
echo "Checking Python dependencies..."
python3 -c "import ee" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ earthengine-api is available"
    
    echo ""
    echo "Testing service account authentication..."
    python3 authentication/auth_helper.py
else
    echo "❌ earthengine-api not found"
    echo "Install with: pip install earthengine-api"
fi

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Add missing service account JSON files"
echo "2. Run: python authentication/auth_helper.py"
echo "3. Test with your EUDR compliance API"
