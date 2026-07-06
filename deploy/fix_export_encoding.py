"""Fix Windows-1252 smart dashes in dumpdata JSON so loaddata accepts UTF-8."""
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "data_export.json")
data = path.read_bytes()
fixed = data.replace(b"\x97", "\u2013".encode("utf-8"))
if fixed != data:
    path.write_bytes(fixed)
    print(f"Fixed {data.count(b'\\x97')} Windows-1252 dash byte(s) in {path}")
else:
    print(f"No encoding fixes needed in {path}")
path.read_text(encoding="utf-8")
print("UTF-8 validation OK")
