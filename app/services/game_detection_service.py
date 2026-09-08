"""Conservative, privacy-preserving local game process detection."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import ctypes
import re

from app.models.game import Game

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass(frozen=True)
class GameCandidate:
    name: str
    process_name: str
    executable_path: str
    confidence: int
    evidence: tuple[str, ...]


_NEVER_GAMES = {
    "system", "registry", "explorer.exe", "dwm.exe", "taskmgr.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "applicationframehost.exe", "shellexperiencehost.exe",
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "discord.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "riotclientservices.exe",
    "battle.net.exe", "upc.exe", "eadesktop.exe", "goggalaxy.exe", "gamebar.exe",
    "xray.exe", "sing-box.exe", "gamedns.exe", "python.exe", "pythonw.exe",
}
_GAME_PATH_MARKERS = (
    "\\steamapps\\common\\", "\\epic games\\", "\\riot games\\",
    "\\xboxgames\\", "\\gog galaxy\\games\\", "\\ea games\\",
    "\\ubisoft game launcher\\games\\", "\\battle.net\\",
)
_GAME_NAME_MARKERS = ("win64-shipping", "win32-shipping", "-shipping", "game-win64")
_HELPER_NAME_MARKERS = (
    "launcher", "crashreport", "crashpad", "anticheat", "easyanticheat",
    "battleye", "unins", "updater", "bootstrapper",
)


def _foreground_pid() -> int:
    if not hasattr(ctypes, "windll"):
        return 0
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _friendly_name(process_name: str) -> str:
    stem = Path(process_name).stem
    stem = re.sub(r"(?i)([-_ ]?(win32|win64)?[-_ ]?shipping)$", "", stem)
    stem = re.sub(r"[-_]+", " ", stem).strip()
    return stem or Path(process_name).stem


def detect_running_game(games: List[Game]) -> Optional[Game]:
    """
    اگه یکی از بازی‌های لیست کاربر در حال اجرا باشه، همون Game رو برمی‌گردونه.
    اگه هیچ‌کدوم اجرا نبود یا psutil در دسترس نبود، None برمی‌گردونه.
    """
    if not PSUTIL_AVAILABLE:
        return None

    process_map = {g.process_name.lower(): g for g in games if g.process_name.strip()}
    if not process_map:
        return None

    try:
        for proc in psutil.process_iter(attrs=["name"]):
            try:
                pname = (proc.info.get("name") or "").lower()
            except Exception:
                continue
            if pname in process_map:
                return process_map[pname]
    except Exception:
        pass
    return None


def detect_unregistered_game(games: List[Game], ignored_processes=None) -> Optional[GameCandidate]:
    """Return only a high-confidence unknown game; never uploads the process list."""
    if not PSUTIL_AVAILABLE:
        return None
    known = {g.process_name.lower() for g in games if g.process_name.strip()}
    ignored = {str(name).lower() for name in (ignored_processes or [])}
    foreground = _foreground_pid()
    candidates = []
    try:
        processes = psutil.process_iter(attrs=["pid", "name", "exe"])
        for proc in processes:
            info = proc.info
            name = (info.get("name") or "").strip()
            lower_name = name.lower()
            if (not name or lower_name in known or lower_name in ignored
                    or lower_name in _NEVER_GAMES
                    or any(marker in lower_name for marker in _HELPER_NAME_MARKERS)):
                continue
            exe = (info.get("exe") or "").strip()
            lower_path = exe.lower()
            score = 0
            evidence = []
            if any(marker in lower_path for marker in _GAME_PATH_MARKERS):
                score += 55
                evidence.append("مسیر نصب شناخته‌شده بازی")
            if any(marker in lower_name for marker in _GAME_NAME_MARKERS):
                score += 40
                evidence.append("الگوی اجرایی مخصوص بازی")
            if info.get("pid") == foreground:
                score += 20
                evidence.append("اکنون پنجره فعال ویندوز است")
            try:
                if exe and Path(exe).is_file() and Path(exe).stat().st_size >= 40 * 1024 * 1024:
                    score += 15
                    evidence.append("فایل اجرایی بزرگ")
            except (OSError, PermissionError):
                pass
            if score >= 55:
                candidates.append(GameCandidate(
                    _friendly_name(name), name, exe, min(score, 100), tuple(evidence)
                ))
    except Exception:
        return None
    return max(candidates, key=lambda item: item.confidence, default=None)
