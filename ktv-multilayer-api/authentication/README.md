# Google Earth Engine Service Accounts Configuration

## Overview
Folder ini menyimpan 16 Google Service Account credentials untuk parallel processing Earth Engine dalam EUDR compliance analysis.

## File Structure
```
authentication/
├── eudr-0.json     # Service Account 1
├── eudr-1.json     # Service Account 2
├── eudr-2.json     # Service Account 3
├── ...
├── eudr-15.json    # Service Account 16
└── README.md       # This file
```

## Setup Instructions

### 1. Create Google Cloud Project & Service Accounts
1. Buat Google Cloud Project di [Google Cloud Console](https://console.cloud.google.com)
2. Enable Earth Engine API
3. Buat 16 Service Accounts dengan naming convention: `eudr-0`, `eudr-1`, ..., `eudr-15`

### 2. Generate & Download JSON Keys
Untuk setiap service account:
1. Go to IAM & Admin > Service Accounts
2. Click on service account
3. Go to Keys tab
4. Click "Add Key" > "Create new key"
5. Choose JSON format
6. Download and rename sesuai pattern: `eudr-{number}.json`

### 3. Earth Engine Registration
Daftarkan setiap service account ke Earth Engine:
```bash
# For each service account
earthengine authenticate --service_account_file=eudr-0.json
earthengine authenticate --service_account_file=eudr-1.json
# ... and so on
```

### 4. Required Permissions
Setiap service account harus memiliki:
- Earth Engine Resource Viewer
- Earth Engine Resource Writer (jika diperlukan)
- Storage Object Viewer (untuk akses dataset)

### 5. Environment Configuration
Set environment variable dalam .env:
```bash
EE_SERVICE_ACCOUNT_PATH=authentication/
```

## Security Notes
- ⚠️ **JANGAN** commit file .json ke git
- Add `authentication/*.json` ke .gitignore
- Simpan backup credentials di secure location
- Rotate credentials secara berkala

## Testing Authentication
Test dengan script berikut:
```python
from services.data.multilayer_service import MultilayerService

# Test authentication untuk semua accounts
for i in range(16):
    try:
        auth_init_ee(f"eudr-{i}", auth_path="authentication/")
        print(f"✅ eudr-{i} authenticated successfully")
    except Exception as e:
        print(f"❌ eudr-{i} failed: {e}")
```

## Production Usage
Dalam production environment:
- Store credentials dalam secure key management system
- Use environment variables atau secret manager
- Monitor usage quotas untuk setiap account
- Implement proper rotation strategy

## Monitoring & Quotas
- Earth Engine quota: 25,000 requests/day per account
- Total capacity: 400,000 requests/day (16 accounts)
- Monitor usage di Google Cloud Console
- Set up alerts untuk quota limits

## Troubleshooting
**Error "Service account not found":**
- Check file naming convention
- Verify file permissions
- Ensure JSON format is valid

**Error "Earth Engine not initialized":**
- Register service account dengan Earth Engine
- Check API permissions
- Verify project billing status

**Quota exceeded:**
- Implement rate limiting
- Distribute load across accounts
- Monitor daily usage patterns
