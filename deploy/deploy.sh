#!/usr/bin/env bash
# Run on VPS as root or with sudo after cloning repo to /opt/eazyudhar
set -euo pipefail

APP_ROOT="/opt/eazyudhar"
REPO_DIR="$APP_ROOT/easyudhar"
VENV="$APP_ROOT/venv"
ENV_FILE="$APP_ROOT/.env"

echo "==> EazyUdhar deploy"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: Create $ENV_FILE from deploy/.env.production.example first."
  exit 1
fi

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r "$REPO_DIR/requirements.txt"

set -a
source "$ENV_FILE"
set +a

cd "$REPO_DIR"
python manage.py check --deploy || python manage.py check
python manage.py migrate --noinput
python manage.py collectstatic --noinput

mkdir -p /var/log/eazyudhar
chown -R www-data:www-data "$REPO_DIR/media" "$REPO_DIR/staticfiles" 2>/dev/null || true
chown -R www-data:www-data /var/log/eazyudhar 2>/dev/null || true

echo "==> Verify integrations"
python manage.py verify_fcm || echo "WARN: FCM check failed — copy firebase JSON to easyudhar/firebase/"

echo "==> Install systemd + nginx + cron (manual if not root)"
if command -v systemctl >/dev/null; then
  cp "$REPO_DIR/deploy/eazyudhar.service" /etc/systemd/system/eazyudhar.service
  systemctl daemon-reload
  systemctl enable eazyudhar
  systemctl restart eazyudhar
  systemctl status eazyudhar --no-pager || true
fi

echo "Done. Test: curl -s http://127.0.0.1:8099/admin-api/v1/system/health"
