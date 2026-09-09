"""Render the real update dialog off-screen for visual release QA."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from app.views.update_dialog import UpdateDialog


def main() -> int:
    output = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(tempfile.gettempdir()) / "lagshift-update-dialog-preview.png"
    )
    app = QApplication([])
    dialog = UpdateDialog({
        "version": "1.0.2",
        "notes": (
            "• انتخاب مسیر پایدارتر برای برنامه‌های پشتیبانی‌شده\n"
            "• بهبود بازیابی خودکار تنظیمات شبکه\n"
            "• رفع چند ایراد ظاهری و افزایش امنیت آپدیت"
        ),
    })
    dialog.show()
    dialog.set_downloading()
    dialog.set_progress(37 * 1024 * 1024, 112 * 1024 * 1024)
    app.processEvents()
    if not dialog.grab().save(str(output), "PNG"):
        raise SystemExit("Could not render update dialog preview")
    dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
