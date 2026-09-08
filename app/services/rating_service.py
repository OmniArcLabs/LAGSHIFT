"""
ذخیره‌ی امتیاز شخصی کاربر برای هر کانفیگ تانل (۱ تا ۵ ستاره).

⚠️ صادقانه: این یه سیستم امتیازدهی *محلی/شخصی* هست، نه کامیونیتی واقعی.
برای امتیازدهی مشترک بین همه‌ی کاربرا، نیاز به یه سرور بک‌اند مرکزی
برای جمع‌آوری و نمایش امتیاز جمعی هست — که یه پروژه‌ی جدا و بزرگ‌تره
(فاز ۵+). فعلاً این فقط به خود کاربر کمک می‌کنه یادش بمونه کدوم
کانفیگ‌ها قبلاً براش خوب بودن.
"""
import json
from typing import Dict

from app.services import app_paths


def _ratings_file():
    return app_paths.migrated_file("ratings.json")


def load_ratings() -> Dict[str, int]:
    """دیکشنری {config_id: امتیاز ۱ تا ۵}"""
    path = _ratings_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_rating(config_id: str, stars: int) -> None:
    ratings = load_ratings()
    ratings[config_id] = max(1, min(5, stars))
    _ratings_file().write_text(json.dumps(ratings, ensure_ascii=False, indent=2), encoding="utf-8")


def get_rating(config_id: str) -> int:
    return load_ratings().get(config_id, 0)
