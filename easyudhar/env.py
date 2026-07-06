"""Load .env and read configuration helpers."""

import os
from pathlib import Path


def load_env_file(base_dir: Path) -> None:
    """Load DJANGO_ENV_FILE, project .env, or parent .env (e.g. /home/deveazy/.env)."""
    candidates = []
    env_override = os.environ.get('DJANGO_ENV_FILE', '').strip()
    if env_override:
        candidates.append(env_override)
    candidates.append(str(base_dir / '.env'))
    candidates.append(str(base_dir.parent / '.env'))

    for env_path in candidates:
        if not os.path.isfile(env_path):
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=True)
        except ImportError:
            _load_env_manual(env_path)
        return


def _load_env_manual(path: str) -> None:
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip().strip('\r')
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def env(key: str, default: str = '') -> str:
    return os.environ.get(key, default).strip().strip('\r')


def env_bool(key: str, default: str = 'false') -> bool:
    return env(key, default).lower() in ('1', 'true', 'yes', 'on')


def env_int(key: str, default: str = '0') -> int:
    raw = env(key, default)
    return int(raw) if raw else 0


def env_list(key: str, default: str = '') -> list[str]:
    raw = env(key, default)
    if not raw:
        return []
    return [item.strip() for item in raw.split(',') if item.strip()]
