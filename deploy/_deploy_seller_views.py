import paramiko
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOCAL = Path(r"D:\khata backend\easyudhar\sellerapp\views\seller_views.py")
REMOTE = "/home/deveazy/easyudhar/sellerapp/views/seller_views.py"

local = LOCAL.read_text(encoding="utf-8")
if "'id': 'online'" in local or "'id': 'payment_link'" in local:
    print("WARN: local still has online/payment_link — abort")
    raise SystemExit(1)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("193.180.212.163", username="deveazy", password="Eazy@2026#", timeout=30)

# backup + upload
_i, o, e = c.exec_command(
    f"cp {REMOTE} {REMOTE}.bak_payment_methods_$(date +%Y%m%d_%H%M%S) && echo bak_ok"
)
print(o.read().decode().strip())

sftp = c.open_sftp()
sftp.put(str(LOCAL), REMOTE)
sftp.close()

_i, o, e = c.exec_command(
    "python3 -m py_compile /home/deveazy/easyudhar/sellerapp/views/seller_views.py && echo COMPILE_OK; "
    "grep -n \"'id': 'online'\\|'id': 'payment_link'\\|UPI / Card\" "
    "/home/deveazy/easyudhar/sellerapp/views/seller_views.py || echo REMOVED_OK; "
    # reload workers
    "kill -HUP $(pgrep -f 'gunicorn -c deploy/gunicorn.conf.py' | head -1) 2>/dev/null || "
    "pkill -HUP -f '/home/deveazy/venv/bin/gunicorn' || true; "
    "sleep 1; "
    "curl -s -o /dev/null -w 'api:%{http_code}\\n' http://127.0.0.1:8099/capp/ || true"
)
print(o.read().decode())
err = e.read().decode()
if err.strip():
    print("ERR:", err[-800:])
c.close()
