# Deployment Guide: Tencent Ubuntu Server + Hostinger Domain

## Overview

Deploy KTV Multilayer API to Tencent Cloud Ubuntu server with domain **api-v2.sustainit.id**

**Stack:**
- OS: Ubuntu 20.04/22.04 LTS
- Web Server: Nginx (reverse proxy)
- Application: FastAPI + Uvicorn
- Process Manager: Systemd
- SSL: Let's Encrypt (Certbot)
- Domain: Hostinger DNS

---

## Prerequisites

### 1. Tencent Cloud Server
- Ubuntu 20.04 or 22.04 LTS
- Minimum 2GB RAM (4GB recommended for GEE processing)
- 20GB+ storage
- Public IP address
- SSH access enabled

### 2. Domain Setup (Hostinger)
- Domain: sustainit.id
- Subdomain: api-v2.sustainit.id
- DNS management access

### 3. Local Requirements
- Git repository ready
- Service account JSON files (16 files for Earth Engine)
- Environment variables documented

---

## Step 1: Initial Server Setup

### Connect to Server
```bash
ssh root@YOUR_TENCENT_SERVER_IP
# atau
ssh ubuntu@YOUR_TENCENT_SERVER_IP
```

### Update System
```bash
sudo apt update
sudo apt upgrade -y
```

### Create Application User
```bash
# Create dedicated user
sudo adduser ktv --disabled-password --gecos ""

# Add to sudo group (if needed)
sudo usermod -aG sudo ktv

# Switch to ktv user
su - ktv
```

---

## Step 2: Install Dependencies

### Install Python 3.10+
```bash
sudo apt install -y python3.10 python3.10-venv python3-pip
python3.10 --version  # Verify
```

### Install Git
```bash
sudo apt install -y git
git --version
```

### Install Nginx
```bash
sudo apt install -y nginx
sudo systemctl status nginx
sudo systemctl enable nginx
```

### Install Certbot (SSL)
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### Install Additional Tools
```bash
sudo apt install -y curl wget htop unzip
```

---

## Step 3: Clone Repository

```bash
# Navigate to home directory
cd /home/ktv

# Clone repository
git clone https://github.com/YOUR_USERNAME/ktv-multilayer-api.git
# atau jika private repo
git clone https://YOUR_TOKEN@github.com/YOUR_USERNAME/ktv-multilayer-api.git

cd ktv-multilayer-api/ktv-multilayer-api
```

---

## Step 4: Setup Python Environment

### Create Virtual Environment
```bash
python3.10 -m venv venv
source venv/bin/activate
```

### Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Verify Installation
```bash
pip list | grep fastapi
pip list | grep earthengine-api
```

---

## Step 5: Setup Environment Variables

### Create .env File
```bash
nano .env
```

**Add these variables:**
```bash
# Earth Engine Service Accounts
EE_SINGLE_SERVICE_ACCOUNT_PATH=./authentication/deforestation-0.json
EE_SERVICE_ACCOUNT_PATH=./authentication/eudr-0.json

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_ENV=production
API_DEBUG=false

# CORS Configuration
ALLOWED_ORIGINS=https://api-v2.sustainit.id,https://sustainit.id,http://localhost:3000

# Database (if used)
# DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Optional: Rate Limiting
RATE_LIMIT_PER_MINUTE=60
```

**Save:** `Ctrl+X`, then `Y`, then `Enter`

---

## Step 6: Upload Service Account Files

### Option A: Using SCP (from local machine)
```bash
# On your local machine (Windows PowerShell)
cd D:\b_outside\z_locanix\Backend\ktv-multilayer-api\ktv-multilayer-api

# Upload authentication folder
scp -r authentication ktv@YOUR_SERVER_IP:/home/ktv/ktv-multilayer-api/ktv-multilayer-api/
```

### Option B: Using SFTP
```bash
# On local machine
sftp ktv@YOUR_SERVER_IP

# Navigate
cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api

# Upload folder
put -r authentication
```

### Verify Files
```bash
# On server
ls -la /home/ktv/ktv-multilayer-api/ktv-multilayer-api/authentication/
# Should see 32 JSON files (16 deforestation + 16 eudr)
```

---

## Step 7: Test Application

### Run Locally First
```bash
cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api
source venv/bin/activate

# Test run
uvicorn app:app --host 0.0.0.0 --port 8000
```

**Open browser:** `http://YOUR_SERVER_IP:8000/docs`

**Test endpoints:**
- GET `/api/v1/gee/flood/datasets`
- GET `/api/v1/gee/commodity/datasets`

**Stop test:** `Ctrl+C`

---

## Step 8: Configure DNS (Hostinger)

### Login to Hostinger
1. Go to https://hpanel.hostinger.com
2. Navigate to: **Domains → sustainit.id → DNS Zone**

### Add A Record
```
Type: A
Name: api-v2
Points to: YOUR_TENCENT_SERVER_IP
TTL: 3600 (1 hour)
```

**Example:**
```
A    api-v2    123.456.789.012    3600
```

### Wait for DNS Propagation
```bash
# On your local machine, check DNS
nslookup api-v2.sustainit.id

# Or use online tool
# https://dnschecker.org
```

Usually takes 5-60 minutes.

---

## Step 9: Configure Nginx

### Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/ktv-api
```

**Add this configuration:**
```nginx
# KTV Multilayer API - Nginx Configuration
# Domain: api-v2.sustainit.id

upstream ktv_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    listen [::]:80;
    server_name api-v2.sustainit.id;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/ktv-api-access.log;
    error_log /var/log/nginx/ktv-api-error.log;

    # Max upload size for GeoJSON files
    client_max_body_size 100M;

    # Timeout settings for long GEE processes
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    proxy_read_timeout 300;
    send_timeout 300;

    location / {
        proxy_pass http://ktv_api;
        proxy_http_version 1.1;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Static files (if any)
    location /static/ {
        alias /home/ktv/ktv-multilayer-api/ktv-multilayer-api/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

**Save:** `Ctrl+X`, `Y`, `Enter`

### Enable Site
```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/ktv-api /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### Test HTTP Access
```bash
# From server
curl http://api-v2.sustainit.id/health

# From local machine
curl http://api-v2.sustainit.id/health
# Should return: healthy
```

---

## Step 10: Setup SSL Certificate (HTTPS)

### Get Let's Encrypt Certificate
```bash
sudo certbot --nginx -d api-v2.sustainit.id
```

**Follow prompts:**
1. Enter email: your-email@example.com
2. Agree to Terms of Service: Y
3. Share email with EFF: N (optional)
4. Redirect HTTP to HTTPS: 2 (Yes, recommended)

### Verify SSL
```bash
# Test HTTPS
curl https://api-v2.sustainit.id/health

# Check certificate
sudo certbot certificates
```

### Auto-renewal Test
```bash
# Dry run
sudo certbot renew --dry-run

# Certbot auto-renews via systemd timer
sudo systemctl status certbot.timer
```

---

## Step 11: Create Systemd Service

### Create Service File
```bash
sudo nano /etc/systemd/system/ktv-api.service
```

**Add this configuration:**
```ini
[Unit]
Description=KTV Multilayer API Service
After=network.target

[Service]
Type=simple
User=ktv
Group=ktv
WorkingDirectory=/home/ktv/ktv-multilayer-api/ktv-multilayer-api
Environment="PATH=/home/ktv/ktv-multilayer-api/ktv-multilayer-api/venv/bin"
ExecStart=/home/ktv/ktv-multilayer-api/ktv-multilayer-api/venv/bin/uvicorn app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log

# Restart policy
Restart=always
RestartSec=10

# Limits
LimitNOFILE=65535

# Logging
StandardOutput=append:/var/log/ktv-api/stdout.log
StandardError=append:/var/log/ktv-api/stderr.log

[Install]
WantedBy=multi-user.target
```

**Save:** `Ctrl+X`, `Y`, `Enter`

### Create Log Directory
```bash
sudo mkdir -p /var/log/ktv-api
sudo chown ktv:ktv /var/log/ktv-api
```

### Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable ktv-api

# Start service
sudo systemctl start ktv-api

# Check status
sudo systemctl status ktv-api
```

### Service Commands
```bash
# Start
sudo systemctl start ktv-api

# Stop
sudo systemctl stop ktv-api

# Restart
sudo systemctl restart ktv-api

# Status
sudo systemctl status ktv-api

# Logs (real-time)
sudo journalctl -u ktv-api -f

# Logs (last 100 lines)
sudo journalctl -u ktv-api -n 100
```

---

## Step 12: Firewall Configuration

### UFW (Ubuntu Firewall)
```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP
sudo ufw allow 80/tcp

# Allow HTTPS
sudo ufw allow 443/tcp

# Check status
sudo ufw status

# Should show:
# 22/tcp    ALLOW   Anywhere
# 80/tcp    ALLOW   Anywhere
# 443/tcp   ALLOW   Anywhere
```

### Tencent Cloud Security Group
Login to Tencent Cloud Console → Security Groups:

**Inbound Rules:**
| Protocol | Port | Source | Description |
|----------|------|--------|-------------|
| TCP | 22 | 0.0.0.0/0 | SSH |
| TCP | 80 | 0.0.0.0/0 | HTTP |
| TCP | 443 | 0.0.0.0/0 | HTTPS |

---

## Step 13: Verify Deployment

### Test API Endpoints
```bash
# Health check
curl https://api-v2.sustainit.id/health

# API docs
curl https://api-v2.sustainit.id/docs
# Open in browser: https://api-v2.sustainit.id/docs

# Flood datasets
curl https://api-v2.sustainit.id/api/v1/gee/flood/datasets

# Commodity datasets
curl https://api-v2.sustainit.id/api/v1/gee/commodity/datasets
```

### Test from Browser
1. **Swagger UI:** https://api-v2.sustainit.id/docs
2. **Flood Viewer:** https://api-v2.sustainit.id/test.html
3. **Test tile:** 
   ```
   https://api-v2.sustainit.id/api/v1/gee/flood/tiles/flood_hazard/10/512/384
   ```

---

## Step 14: Monitoring & Maintenance

### Check Application Logs
```bash
# Systemd logs (real-time)
sudo journalctl -u ktv-api -f

# Application logs
tail -f /var/log/ktv-api/stdout.log
tail -f /var/log/ktv-api/stderr.log

# Nginx logs
sudo tail -f /var/log/nginx/ktv-api-access.log
sudo tail -f /var/log/nginx/ktv-api-error.log
```

### Monitor System Resources
```bash
# CPU, Memory, Disk
htop

# Disk usage
df -h

# Service status
sudo systemctl status ktv-api nginx
```

### Auto-restart on Failure
Already configured in systemd service:
- `Restart=always`
- `RestartSec=10`

Service automatically restarts if it crashes.

---

## Step 15: Update Application (Git Pull)

### Update Code
```bash
# SSH to server
ssh ktv@YOUR_SERVER_IP

# Navigate to project
cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api

# Pull latest changes
git pull origin main-dimas

# Activate venv
source venv/bin/activate

# Update dependencies (if requirements.txt changed)
pip install -r requirements.txt

# Restart service
sudo systemctl restart ktv-api

# Check status
sudo systemctl status ktv-api
```

### Deployment Script (Optional)
Create `deploy.sh`:
```bash
nano /home/ktv/ktv-multilayer-api/deploy.sh
```

```bash
#!/bin/bash
# KTV API Deployment Script

echo "🚀 Deploying KTV Multilayer API..."

cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api

# Pull latest
echo "📥 Pulling latest code..."
git pull origin main-dimas

# Activate venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Restart service
echo "🔄 Restarting service..."
sudo systemctl restart ktv-api

# Check status
echo "✅ Service status:"
sudo systemctl status ktv-api --no-pager

echo "🎉 Deployment complete!"
```

Make executable:
```bash
chmod +x /home/ktv/ktv-multilayer-api/deploy.sh
```

Run deployment:
```bash
/home/ktv/ktv-multilayer-api/deploy.sh
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u ktv-api -n 50

# Check Python errors
tail -f /var/log/ktv-api/stderr.log

# Test manually
cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Nginx 502 Bad Gateway
```bash
# Service down?
sudo systemctl status ktv-api

# Restart service
sudo systemctl restart ktv-api

# Check nginx config
sudo nginx -t
```

### SSL Certificate Issues
```bash
# Check certificate
sudo certbot certificates

# Renew manually
sudo certbot renew

# Restart nginx
sudo systemctl restart nginx
```

### DNS Not Resolving
```bash
# Check DNS
nslookup api-v2.sustainit.id

# Flush local DNS (local machine)
ipconfig /flushdns  # Windows
sudo systemd-resolve --flush-caches  # Linux
```

### Earth Engine Authentication Errors
```bash
# Verify JSON files exist
ls -la /home/ktv/ktv-multilayer-api/ktv-multilayer-api/authentication/

# Check .env file
cat /home/ktv/ktv-multilayer-api/ktv-multilayer-api/.env

# Check logs for EE errors
sudo journalctl -u ktv-api | grep "Earth Engine"
```

---

## Security Best Practices

### 1. Keep System Updated
```bash
# Weekly updates
sudo apt update && sudo apt upgrade -y
```

### 2. Secure SSH
```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Change:
PermitRootLogin no
PasswordAuthentication no  # Use SSH keys only
Port 2222  # Change default port (update firewall!)

# Restart SSH
sudo systemctl restart sshd
```

### 3. Fail2Ban (Brute Force Protection)
```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 4. Secure Service Account Files
```bash
# Set strict permissions
chmod 600 /home/ktv/ktv-multilayer-api/ktv-multilayer-api/authentication/*.json
chown ktv:ktv /home/ktv/ktv-multilayer-api/ktv-multilayer-api/authentication/*.json
```

### 5. Environment Variables
```bash
# Never commit .env to git
# Set strict permissions
chmod 600 /home/ktv/ktv-multilayer-api/ktv-multilayer-api/.env
```

---

## Performance Optimization

### 1. Workers Configuration
```bash
# Calculate optimal workers
# Formula: (2 x CPU cores) + 1

# Check CPU cores
nproc

# 2 cores → 5 workers
# 4 cores → 9 workers
```

Edit `/etc/systemd/system/ktv-api.service`:
```ini
ExecStart=/home/ktv/.../venv/bin/uvicorn app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 9 \  # Adjust based on CPU
    --log-level info
```

### 2. Nginx Caching (Optional)
```nginx
# In /etc/nginx/sites-available/ktv-api
location ~ ^/api/v1/gee/.*/tiles/ {
    proxy_pass http://ktv_api;
    
    # Cache tiles
    proxy_cache tiles_cache;
    proxy_cache_valid 200 1h;
    proxy_cache_key "$request_uri";
    
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 3. Gzip Compression
```nginx
# In /etc/nginx/nginx.conf
gzip on;
gzip_vary on;
gzip_types text/plain text/css application/json application/javascript;
gzip_comp_level 6;
```

---

## Backup Strategy

### Database Backup (if using)
```bash
# Create backup script
nano /home/ktv/backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/home/ktv/backups

mkdir -p $BACKUP_DIR

# Backup database (if using PostgreSQL)
# pg_dump dbname > $BACKUP_DIR/db_$DATE.sql

# Backup service account files
tar -czf $BACKUP_DIR/auth_$DATE.tar.gz /home/ktv/ktv-multilayer-api/ktv-multilayer-api/authentication/

# Keep only last 7 backups
ls -t $BACKUP_DIR/auth_*.tar.gz | tail -n +8 | xargs rm -f

echo "Backup completed: $DATE"
```

```bash
chmod +x /home/ktv/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e

# Add line:
0 2 * * * /home/ktv/backup.sh >> /var/log/ktv-backup.log 2>&1
```

---

## Summary Checklist

- [ ] Server setup (Ubuntu + dependencies)
- [ ] Repository cloned
- [ ] Python environment created
- [ ] Dependencies installed
- [ ] Environment variables configured
- [ ] Service account files uploaded
- [ ] DNS A record added (api-v2.sustainit.id)
- [ ] Nginx configured
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] Systemd service created and enabled
- [ ] Firewall configured (UFW + Tencent)
- [ ] API tested (docs, endpoints)
- [ ] Monitoring setup
- [ ] Backup strategy implemented

---

## Quick Reference

### URLs
- **API Documentation:** https://api-v2.sustainit.id/docs
- **Flood Viewer:** https://api-v2.sustainit.id/test.html
- **Health Check:** https://api-v2.sustainit.id/health

### Important Paths
- **App Directory:** `/home/ktv/ktv-multilayer-api/ktv-multilayer-api`
- **Venv:** `/home/ktv/ktv-multilayer-api/ktv-multilayer-api/venv`
- **Logs:** `/var/log/ktv-api/`
- **Nginx Config:** `/etc/nginx/sites-available/ktv-api`
- **Service File:** `/etc/systemd/system/ktv-api.service`

### Common Commands
```bash
# Restart API
sudo systemctl restart ktv-api

# View logs
sudo journalctl -u ktv-api -f

# Update code
cd /home/ktv/ktv-multilayer-api/ktv-multilayer-api && git pull

# Restart nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status ktv-api nginx
```

---

## Support

For issues:
1. Check logs: `sudo journalctl -u ktv-api -n 100`
2. Verify service: `sudo systemctl status ktv-api`
3. Test manually: Run uvicorn directly
4. Check documentation: `/docs` endpoint

**Deployment Complete!** 🎉

Your API is now live at: **https://api-v2.sustainit.id**
