"""
سرویس مدیریت لیست بازی‌های دلخواه کاربر.
ذخیره‌سازی ساده در یک فایل JSON کنار برنامه (بدون نیاز به دیتابیس).
"""
import json
from pathlib import Path
from typing import List

from app.models.game import Game
from app.services import app_paths

# فایل ذخیره‌سازی در پوشه‌ی داده‌ی کاربر (AppData روی ویندوز)
def _data_file() -> Path:
    return app_paths.migrated_file("games.json")


# چند بازی معروف به عنوان پیش‌فرض
DEFAULT_GAMES = [
    Game("Valorant", "VALORANT-Win64-Shipping.exe"),
    Game("Dota 2", "dota2.exe"),
    Game("PUBG", "TslGame.exe"),
    Game("Counter-Strike 2", "cs2.exe"),
    Game("Fortnite", "FortniteClient-Win64-Shipping.exe"),
]


def load_games() -> List[Game]:
    """خوندن لیست بازی‌ها از فایل. اگه فایل نبود، لیست پیش‌فرض رو برمی‌گردونه و ذخیره می‌کنه."""
    path = _data_file()
    if not path.exists():
        save_games(DEFAULT_GAMES)
        return list(DEFAULT_GAMES)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Game(**item) for item in raw]
    except Exception:
        return list(DEFAULT_GAMES)


def save_games(games: List[Game]) -> None:
    """ذخیره‌ی کل لیست بازی‌ها روی دیسک"""
    path = _data_file()
    data = [
        {
            "name": g.name, "process_name": g.process_name, "notes": g.notes,
            "preferred_dns_name": g.preferred_dns_name,
            "preferred_tunnel_id": g.preferred_tunnel_id,
            "connection_mode": g.connection_mode,
            "connection_strategy": g.connection_strategy,
            "route_mode": getattr(g, "route_mode", "process"),
            "auto_connect": g.auto_connect,
            "route_profile": g.route_profile,
        }
        for g in games
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_game(games: List[Game], name: str, process_name: str = "", notes: str = "") -> List[Game]:
    """افزودن یک بازی جدید به لیست و ذخیره‌ی فوری"""
    games = list(games)
    games.append(Game(name=name.strip(), process_name=process_name.strip(), notes=notes.strip()))
    save_games(games)
    return games


def remove_game(games: List[Game], name: str) -> List[Game]:
    """حذف یک بازی از لیست بر اساس نام"""
    games = [g for g in games if g.name != name]
    save_games(games)
    return games
