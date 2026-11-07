"""Load simple KEY=VALUE settings from the project .env file."""
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent


def load_project_env(path: Path = ROOT / ".env") -> None:
    if not path.is_file():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            raise ValueError(f"Format .env tidak valid pada baris {line_number}.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def api_key_is_configured(value: str | None) -> bool:
    if value is None or len(value.strip()) < 32:
        return False
    normalized = value.strip().lower()
    return not any(marker in normalized for marker in ("contoh", "ganti", "rahasia-anda"))
