"""
ردیاب زمان اتصال روزانه. این مقدار عمداً «مصرف اینترنت» نامیده نمی‌شود،
چون مدت اتصال را نمی‌توان به حجم ترافیک تبدیل کرد.
"""
import json
from datetime import date
from pathlib import Path

from app.services import app_paths


def _usage_file() -> Path:
    return app_paths.migrated_file("usage.json")


def _load() -> dict:
    path = _usage_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _usage_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_connected_minutes(minutes: float) -> float:
    """اضافه کردن دقایق اتصال به مجموع امروز و برگردوندن مجموع جدید"""
    data = _load()
    today = str(date.today())
    data[today] = data.get(today, 0) + minutes
    _save(data)
    return data[today]


def get_today_minutes() -> float:
    data = _load()
    return data.get(str(date.today()), 0)


def add_traffic_bytes(byte_count: int) -> int:
    data = _load()
    key = str(date.today()) + ":bytes"
    data[key] = max(0, int(data.get(key, 0))) + max(0, int(byte_count))
    _save(data)
    return data[key]


def get_today_bytes() -> int:
    return int(_load().get(str(date.today()) + ":bytes", 0))


class TrafficMeter:
    """Local estimate; authoritative quota enforcement must happen server-side."""
    def __init__(self):
        self._last = None

    def start(self) -> None:
        self._last = self._read()

    def sample(self) -> int:
        current = self._read()
        if self._last is None:
            self._last = current
            return 0
        delta = max(0, current - self._last)
        self._last = current
        return delta

    @staticmethod
    def _read() -> int:
        try:
            import psutil
            counters = psutil.net_io_counters()
            return int(counters.bytes_sent + counters.bytes_recv)
        except Exception:
            return 0
