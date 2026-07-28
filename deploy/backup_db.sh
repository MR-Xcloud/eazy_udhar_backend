#!/usr/bin/env bash
# Daily MySQL/MariaDB (or SQLite) backup for EazyUdhar â€” no sudo required.
#
# Install once on server:
#   chmod +x /home/deveazy/easyudhar/deploy/backup_db.sh
#   mkdir -p /home/deveazy/db_backups /home/deveazy/easyudhar/logs
#
# Cron (02:00 IST = 20:30 UTC):
#   30 20 * * * /home/deveazy/easyudhar/deploy/backup_db.sh >> /home/deveazy/easyudhar/logs/db_backup.log 2>&1
#
# Env is read from /home/deveazy/easyudhar/.env (NOT sourced â€” safe with spaces/special chars).

set -euo pipefail

HOME_DIR="${HOME_DIR:-/home/deveazy}"
APP_ROOT="${APP_ROOT:-$HOME_DIR/easyudhar}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/.env}"
BACKUP_DIR="${BACKUP_DIR:-$HOME_DIR/db_backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_PREFIX="[db-backup $(date -Iseconds)]"

mkdir -p "$BACKUP_DIR"

get_env() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -n 1 || true)"
  if [[ -z "$line" ]]; then
    echo ""
    return 0
  fi
  # Strip KEY= and optional surrounding quotes / CR
  echo "${line#*=}" | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "$LOG_PREFIX ERROR: missing $ENV_FILE" >&2
  exit 1
fi

DB_ENGINE="$(get_env DB_ENGINE | tr '[:upper:]' '[:lower:]')"
DB_ENGINE="${DB_ENGINE:-mysql}"

if [[ "$DB_ENGINE" == "sqlite" ]]; then
  SRC="$APP_ROOT/db.sqlite3"
  OUT="$BACKUP_DIR/eazyudhar_sqlite_${STAMP}.sqlite3.gz"
  if [[ ! -f "$SRC" ]]; then
    echo "$LOG_PREFIX ERROR: sqlite file not found: $SRC" >&2
    exit 1
  fi
  gzip -c "$SRC" > "$OUT"
  echo "$LOG_PREFIX OK sqlite -> $OUT ($(du -h "$OUT" | awk '{print $1}'))"
else
  DB_NAME="$(get_env DB_NAME)"
  DB_USER="$(get_env DB_USER)"
  DB_PASSWORD="$(get_env DB_PASSWORD)"
  DB_HOST="$(get_env DB_HOST)"
  DB_PORT="$(get_env DB_PORT)"
  DB_NAME="${DB_NAME:-eazyudhar}"
  DB_USER="${DB_USER:-eazyudhar}"
  DB_HOST="${DB_HOST:-127.0.0.1}"
  DB_PORT="${DB_PORT:-3306}"

  if [[ -z "$DB_PASSWORD" ]]; then
    echo "$LOG_PREFIX ERROR: DB_PASSWORD empty in $ENV_FILE" >&2
    exit 1
  fi

  if ! command -v mysqldump >/dev/null 2>&1; then
    echo "$LOG_PREFIX ERROR: mysqldump not found in PATH" >&2
    exit 1
  fi

  OUT="$BACKUP_DIR/eazyudhar_mysql_${STAMP}.sql.gz"
  CNF="$(mktemp)"
  chmod 600 "$CNF"
  # shellcheck disable=SC2064
  trap "rm -f '$CNF'" EXIT

  # Quote values — passwords with # or ; are otherwise treated as comments in option files.
  python3 - "$CNF" "$DB_USER" "$DB_PASSWORD" "$DB_HOST" "$DB_PORT" <<'PY'
import sys
path, user, password, host, port = sys.argv[1:6]

def q(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

with open(path, "w", encoding="utf-8") as handle:
    handle.write("[client]\n")
    handle.write(f"user={q(user)}\n")
    handle.write(f"password={q(password)}\n")
    handle.write(f"host={q(host)}\n")
    handle.write(f"port={q(port)}\n")
PY

  mysqldump \
    --defaults-extra-file="$CNF" \
    --single-transaction \
    --routines \
    --triggers \
    --events \
    --hex-blob \
    --default-character-set=utf8mb4 \
    "$DB_NAME" | gzip -c > "$OUT"

  echo "$LOG_PREFIX OK mysql:$DB_NAME -> $OUT ($(du -h "$OUT" | awk '{print $1}'))"
fi

# Drop backups older than KEEP_DAYS
find "$BACKUP_DIR" -type f \( -name 'eazyudhar_mysql_*.sql.gz' -o -name 'eazyudhar_sqlite_*.sqlite3.gz' \) -mtime +"$KEEP_DAYS" -print -delete | while read -r old; do
  echo "$LOG_PREFIX deleted old backup: $old"
done

echo "$LOG_PREFIX done (keeping last ${KEEP_DAYS} days in $BACKUP_DIR)"
