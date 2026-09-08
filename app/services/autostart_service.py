"""
سرویس اجرای خودکار برنامه با بالا اومدن ویندوز، از طریق کلید رجیستری
HKCU\\...\\Run — نیازی به دسترسی ادمین یا نصب سرویس جدا نداره.
"""
import sys
from pathlib import Path

from app.app_info import APP_NAME, LEGACY_DATA_FOLDER_NAME


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None  # روی غیر ویندوز (محیط توسعه) در دسترس نیست


def is_enabled() -> bool:
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
