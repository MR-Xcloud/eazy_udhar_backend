# EazyUdhar Backend — VPS Deployment Guide

Deploy the Django API so **seller app**, **customer app**, **admin panel**, **SMS**, **FCM push**, **Razorpay**, and **CORS** all work on the client VPS.

---

## Architecture

```
Mobile apps (seller/customer)  ──►  https://api.yourdomain.com
Admin panel (browser)          ──►  https://admin.yourdomain.com  ──CORS──►  API
                                      │
Nginx :443/:80 ──► Gunicorn :8099 ──► Django
                      │
                   MySQL (recommended)
                   firebase/*.json (FCM)
                   media/ uploads
```

**API prefixes (unchanged after deploy):**

| App | Base URL |
|-----|----------|
| Customer | `https://api.yourdomain.com/sapp/` |
| Seller | `https://api.yourdomain.com/capp/` |
| Admin | `https://api.yourdomain.com/admin-api/v1/` |
| Django admin | `https://api.yourdomain.com/admin/` |

---

## Step 1 — Prepare VPS (Ubuntu 22/24)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-dev build-essential \
  nginx mariadb-server mariadb-client libmariadb-dev pkg-config git curl
```

---

## Step 2 — MySQL database

```bash
sudo mysql -e "
CREATE DATABASE eazyudhar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'eazyudhar'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON eazyudhar.* TO 'eazyudhar'@'localhost';
FLUSH PRIVILEGES;
"
```

---

## Step 3 — Copy code to VPS

**Option A — Git (recommended)**

```bash
sudo mkdir -p /opt/eazyudhar
sudo chown $USER:$USER /opt/eazyudhar
cd /opt/eazyudhar
git clone YOUR_REPO_URL easyudhar
```

**Option B — Zip from your PC**

On Windows (PowerShell):

```powershell
cd "C:\Users\hp\Desktop\khata backend"
# Exclude venv, sqlite, __pycache__
tar -czf eazyudhar-deploy.tgz --exclude=__pycache__ --exclude=.git --exclude=myenv --exclude=db.sqlite3 easyudhar
scp eazyudhar-deploy.tgz user@YOUR_VPS_IP:/opt/eazyudhar/
```

On VPS:

```bash
cd /opt/eazyudhar && tar -xzf eazyudhar-deploy.tgz
```

---

## Step 4 — Secrets & config (critical)

```bash
cp /opt/eazyudhar/easyudhar/deploy/.env.production.example /opt/eazyudhar/.env
nano /opt/eazyudhar/.env
```

**Must set:**

| Variable | Example |
|----------|---------|
| `DJANGO_SECRET_KEY` | Random 50+ char string |
| `DJANGO_DEBUG` | `false` |
| `ALLOWED_HOSTS` | `api.yourdomain.com,203.0.113.10` |
| `PUBLIC_STATEMENT_BASE_URL` | `https://api.yourdomain.com` |
| `CORS_ALLOWED_ORIGINS` | `https://admin.yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://admin.yourdomain.com,https://api.yourdomain.com` |
| `BEHIND_HTTPS_PROXY` | `true` (after SSL) |
| `DB_ENGINE` | `mysql` |
| `DB_*` | MySQL credentials from step 2 |
| `RAZORPAY_*` | Live keys for production |
| `NIMBUS_*` | SMS credentials |
| `POSTMARK_SERVER_TOKEN` | Email OTP |

### Firebase (push notifications)

Copy from your PC (file is gitignored):

```powershell
scp "C:\Users\hp\Desktop\khata backend\easyudhar\firebase\eazyudhar-firebase-adminsdk-*.json" `
  user@VPS:/opt/eazyudhar/easyudhar/firebase/
```

Verify on VPS:

```bash
cd /opt/eazyudhar/easyudhar
source /opt/eazyudhar/venv/bin/activate  # after step 5
python manage.py verify_fcm
```

### Migrate existing data (optional)

If you want data from local SQLite:

```bash
# On PC — export
cd easyudhar
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > data.json

# On VPS — after migrate
python manage.py loaddata data.json
```

Or copy `db.sqlite3` only for small tests (set `DB_ENGINE=sqlite`, not recommended for production).

---

## Step 5 — Deploy script

```bash
chmod +x /opt/eazyudhar/easyudhar/deploy/deploy.sh
sudo /opt/eazyudhar/easyudhar/deploy/deploy.sh
```

Create admin user:

```bash
cd /opt/eazyudhar/easyudhar
source /opt/eazyudhar/venv/bin/activate
set -a && source /opt/eazyudhar/.env && set +a
python manage.py seed_admin_data   # if first time
# Or: python manage.py createsuperuser (Django admin only)
```

---

## Step 6 — Nginx + SSL

```bash
sudo cp /opt/eazyudhar/easyudhar/deploy/nginx-eazyudhar.conf /etc/nginx/sites-available/eazyudhar
sudo nano /etc/nginx/sites-available/eazyudhar   # replace api.yourdomain.com
sudo ln -sf /etc/nginx/sites-available/eazyudhar /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

Ensure `.env` has `BEHIND_HTTPS_PROXY=true`, then:

```bash
sudo systemctl restart eazyudhar
```

---

## Step 7 — Cron jobs (SMS reminders)

```bash
sudo cp /opt/eazyudhar/easyudhar/deploy/cron-eazyudhar /etc/cron.d/eazyudhar
sudo chmod 644 /etc/cron.d/eazyudhar
```

---

## Step 8 — Update clients (one-time)

### Seller & Customer mobile apps

Point API base URL to:

```
https://api.yourdomain.com
```

(Seller uses `/capp/`, customer uses `/sapp/` — same as local, only host changes.)

### Admin panel

In `udhar-insight-hub/.env`:

```
VITE_ADMIN_API_BASE=https://api.yourdomain.com/admin-api/v1
```

Rebuild and deploy admin static site to `https://admin.yourdomain.com`.

### Razorpay dashboard

Add webhook URL:

```
https://api.yourdomain.com/sapp/customer/payments/webhook
```

Use the webhook secret in `RAZORPAY_LIVE_WEBHOOK_SECRET`.

---

## Step 9 — Smoke test checklist

Run after deploy:

```bash
# Health (needs admin JWT for full response, or use admin panel)
curl -s https://api.yourdomain.com/admin-api/v1/system/health

# FCM
python manage.py verify_fcm

# SMS (optional test number)
python manage.py shell -c "from sellerapp.nimbus_sms import send_sms; print(send_sms('9999999999', 'Test', template_id='...'))"
```

| Check | URL / action |
|-------|----------------|
| Seller login | `POST /capp/auth/seller/login` |
| Customer login | `POST /sapp/auth/login` |
| Admin login | `POST /admin-api/v1/auth/login` |
| Payment order | `POST /sapp/customer/payments/create-order` |
| Token refresh | `POST /capp/auth/refresh` |
| Push | Trigger notification from app |
| CORS | Open admin in browser, login works |
| Cron | Admin → System → Cron Jobs → trigger |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CORS error in admin | Add admin URL to `CORS_ALLOWED_ORIGINS` in `.env`, restart gunicorn |
| 400 Bad Request (DisallowedHost) | Add domain/IP to `ALLOWED_HOSTS` |
| FCM not configured | Copy firebase JSON; run `verify_fcm` |
| Payment 400 | Set Razorpay live keys; `RAZORPAY_ROUTE_ENABLED=false` until Route enabled |
| SMS failed | Check Nimbus templates approved; vars max 30 chars |
| 502 from nginx | `sudo systemctl status eazyudhar` — check gunicorn logs |
| Static/admin CSS missing | `python manage.py collectstatic` |

---

## Updating later

```bash
cd /opt/eazyudhar/easyudhar
git pull
sudo /opt/eazyudhar/easyudhar/deploy/deploy.sh
```

---

## File layout on VPS

```
/opt/eazyudhar/
├── .env                          # secrets (never commit)
├── venv/
└── easyudhar/
    ├── manage.py
    ├── db.sqlite3                # only if DB_ENGINE=sqlite
    ├── firebase/                 # FCM service account JSON
    ├── media/                    # uploads
    ├── staticfiles/              # collectstatic output
    └── deploy/
        ├── deploy.sh
        ├── gunicorn.conf.py
        ├── nginx-eazyudhar.conf
        ├── eazyudhar.service
        └── cron-eazyudhar
```
