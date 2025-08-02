# 🔐 Setup 16 Google Service Accounts untuk EUDR API

## 📁 Struktur File dan Lokasi

### 1. **Lokasi Penyimpanan**
```
ktv-multilayer-api/
├── authentication/              # 👈 Folder utama untuk credentials
│   ├── eudr-0.json             # Service Account 1
│   ├── eudr-1.json             # Service Account 2
│   ├── eudr-2.json             # Service Account 3
│   ├── ...
│   ├── eudr-15.json            # Service Account 16
│   ├── README.md               # Dokumentasi setup
│   ├── auth_helper.py          # Helper functions
│   ├── .env.example            # Template environment
│   ├── setup_accounts.bat      # Windows setup script
│   └── setup_accounts.sh       # Linux/Mac setup script
├── config.py                   # Configuration module
├── .env                        # Environment variables
└── .gitignore                  # Updated untuk exclude *.json
```

### 2. **Naming Convention**
- File harus dinamai: `eudr-0.json`, `eudr-1.json`, ..., `eudr-15.json`
- Total: **16 files** (eudr-0 sampai eudr-15)
- Format: JSON service account keys dari Google Cloud

---

## 🚀 Langkah-langkah Setup

### **Step 1: Buat Google Cloud Project**
1. Buka [Google Cloud Console](https://console.cloud.google.com)
2. Buat project baru atau gunakan project existing
3. Enable **Earth Engine API**
4. Enable **Cloud Resource Manager API**

### **Step 2: Buat 16 Service Accounts**
```bash
# Via gcloud CLI (optional)
for i in {0..15}; do
  gcloud iam service-accounts create eudr-$i \
    --display-name="EUDR Service Account $i" \
    --description="Earth Engine processing account $i"
done
```

Atau via Web Console:
1. Go to **IAM & Admin > Service Accounts**
2. Click **"Create Service Account"**
3. Name: `eudr-0`, `eudr-1`, etc.
4. Role: **Earth Engine Resource Viewer**
5. Create JSON key dan download

### **Step 3: Download JSON Keys**
Untuk setiap service account:
1. Click **"Keys"** tab
2. **"Add Key"** > **"Create new key"** 
3. Select **JSON** format
4. Rename file sesuai pattern: `eudr-0.json`, `eudr-1.json`, etc.
5. Simpan di folder `authentication/`

### **Step 4: Register ke Earth Engine**
Setiap service account harus didaftarkan:
```bash
# Method 1: Via earthengine CLI
earthengine authenticate --service_account_file=authentication/eudr-0.json

# Method 2: Via Google Earth Engine registration
# Visit: https://signup.earthengine.google.com/
```

### **Step 5: Setup Environment**
```bash
# Copy template
cp authentication/.env.example .env

# Edit .env file
EE_SERVICE_ACCOUNT_PATH=authentication/
TOTAL_SERVICE_ACCOUNTS=16
ENABLE_PARALLEL_PROCESSING=true
```

### **Step 6: Test Setup**
```bash
# Windows
authentication\setup_accounts.bat

# Linux/Mac  
chmod +x authentication/setup_accounts.sh
./authentication/setup_accounts.sh

# Python test
python authentication/auth_helper.py
```

---

## 📊 Quota & Performance

### **Earth Engine Limits**
- **Per Account**: 25,000 requests/day
- **Total Capacity**: 400,000 requests/day (16 accounts)
- **Concurrent**: ~1,000 requests/minute per account
- **Total Concurrent**: ~16,000 requests/minute

### **Usage Monitoring**
```python
# Check quota usage
from authentication.auth_helper import test_all_accounts

results = test_all_accounts()
print(f"Available accounts: {len(results['successful'])}")
```

---

## 🔒 Security Best Practices

### **1. File Permissions**
```bash
# Linux/Mac - Restrict access
chmod 600 authentication/*.json
chmod 700 authentication/

# Windows - Set file permissions via Properties
```

### **2. Git Protection**
File `.gitignore` sudah diupdate:
```gitignore
# Earth Engine Service Account Credentials
authentication/*.json
authentication/eudr-*.json
.env
authentication/.env
```

### **3. Production Security**
- **Rotate credentials** setiap 90 hari
- **Monitor usage** via Google Cloud Console
- **Set up alerts** untuk unusual activity
- **Use secret management** di production (Google Secret Manager, AWS Secrets, etc.)

---

## 🧪 Testing & Verification

### **Quick Test**
```python
# Test single account
from authentication.auth_helper import auth_init_ee

try:
    auth_init_ee("eudr-0")
    print("✅ Authentication successful!")
except Exception as e:
    print(f"❌ Error: {e}")
```

### **Full System Test**
```python
# Test EUDR API with multi-account support
from services.data.multilayer_service import MultilayerService

service = MultilayerService()
result = service.analyze_eudr_compliance(
    coordinates={"latitude": -2.5, "longitude": 115.0},
    buffer_km=5.0
)
print(f"Analysis completed: {result['overall_compliance_status']['status']}")
```

---

## 🚨 Troubleshooting

### **Common Issues**

**❌ "Service account not found"**
```bash
# Check file exists and naming
ls -la authentication/eudr-*.json

# Verify JSON format
python -m json.tool authentication/eudr-0.json
```

**❌ "Earth Engine not initialized"**
```bash
# Register service account
earthengine authenticate --service_account_file=authentication/eudr-0.json

# Check project access
gcloud projects get-iam-policy YOUR-PROJECT-ID
```

**❌ "Quota exceeded"**
```python
# Implement account rotation
import random
from authentication.auth_helper import get_available_accounts

accounts = get_available_accounts()
selected_account = random.choice(accounts)
auth_init_ee(selected_account)
```

### **Verification Commands**
```bash
# Check all files exist
python -c "
import os
missing = []
for i in range(16):
    file = f'authentication/eudr-{i}.json'
    if not os.path.exists(file):
        missing.append(file)
if missing:
    print(f'Missing: {missing}')
else:
    print('✅ All 16 files found')
"

# Test authentication
python authentication/auth_helper.py
```

---

## 📈 Production Deployment

### **Environment Variables**
```bash
# Production .env
EE_SERVICE_ACCOUNT_PATH=/secure/path/to/credentials/
TOTAL_SERVICE_ACCOUNTS=16
ENABLE_PARALLEL_PROCESSING=true
GOOGLE_CLOUD_PROJECT_ID=your-production-project
LOG_LEVEL=INFO
ENABLE_EE_QUOTA_MONITORING=true
```

### **Docker Deployment**
```dockerfile
# Add to Dockerfile
COPY authentication/ /app/authentication/
RUN chmod 600 /app/authentication/*.json
ENV EE_SERVICE_ACCOUNT_PATH=/app/authentication/
```

### **Kubernetes Secrets**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ee-service-accounts
type: Opaque
data:
  eudr-0.json: <base64-encoded-json>
  eudr-1.json: <base64-encoded-json>
  # ... etc
```

---

## ✅ Summary Checklist

- [ ] **16 service accounts** dibuat di Google Cloud
- [ ] **JSON keys** downloaded dengan naming yang benar
- [ ] **Files** disimpan di `authentication/eudr-{0-15}.json`
- [ ] **Earth Engine** registration completed
- [ ] **Environment** variables configured
- [ ] **Git protection** active (files tidak ke-commit)
- [ ] **Authentication test** passed
- [ ] **API integration** working
- [ ] **Quota monitoring** setup

**🎯 Target**: 16 accounts × 25k requests/day = **400,000 requests/day capacity**
