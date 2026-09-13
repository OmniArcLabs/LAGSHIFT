"""
سرویس اجرای خودکار برنامه با بالا اومدن ویندوز، از طریق کلید رجیستری
HKCU\\...\\Run — نیازی به دسترسی ادمین یا نصب سرویس جدا نداره.
"""
import sys
import os
import plistlib
import subprocess
from pathlib import Path

from app.app_info import APP_NAME, LEGACY_DATA_FOLDER_NAME


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None  # روی غیر ویندوز (محیط توسعه) در دسترس نیست


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _macos_plist().is_file()
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            winreg.QueryValueEx(key, LEGACY_DATA_FOLDER_NAME)
            return True
    except Exception:
        return False


def set_enabled(enabled: bool) -> bool:
    """فعال/غیرفعال کردن اجرای خودکار. برمی‌گردونه: موفقیت"""
    if sys.platform == "darwin":
        return _set_macos_enabled(enabled)
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        if enabled:
            # مسیر main.py یا exe نهایی؛ فعلاً چون از سورس پایتون اجرا می‌شه،
            # مسیر python.exe + main.py رو ثبت می‌کنیم. بعد از build نهایی با
            # PyInstaller/Nuitka باید این به مسیر exe عوض بشه.
            exe = sys.executable
            script = str(Path(__file__).resolve().parent.parent.parent / "main.py")
            command = f'"{exe}" "{script}" --minimized'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _macos_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.omniarc.lagshift.plist"


def _macos_arguments() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--minimized"]
    script = Path(__file__).resolve().parents[2] / "main.py"
    return [str(Path(sys.executable).resolve()), str(script), "--minimized"]


def _set_macos_enabled(enabled: bool) -> bool:
    path = _macos_plist()
    domain = f"gui/{os.getuid()}"
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            with temporary.open("wb") as output:
                plistlib.dump({
                    "Label": "com.omniarc.lagshift",
                    "ProgramArguments": _macos_arguments(),
                    "RunAtLoad": True,
                    "ProcessType": "Interactive",
                }, output, sort_keys=True)
            os.replace(temporary, path)
            subprocess.run(
                ["/bin/launchctl", "bootout", domain, str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6,
            )
            result = subprocess.run(
                ["/bin/launchctl", "bootstrap", domain, str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
            )
            return result.returncode == 0
        subprocess.run(
            ["/bin/launchctl", "bootout", domain, str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
        )
        path.unlink(missing_ok=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
