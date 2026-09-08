"""Deterministic off-screen RTL, keyboard-focus and reduced-motion smoke test."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sandbox = tempfile.TemporaryDirectory(prefix="lagshift-a11y-")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["APPDATA"] = sandbox.name
    os.environ["LOCALAPPDATA"] = sandbox.name

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QAbstractButton
    from app.views.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    if window.layoutDirection() != Qt.RightToLeft:
        raise SystemExit("Main window is not RTL")
    buttons = [item for item in window.findChildren(QAbstractButton) if item.isEnabled()]
    unreachable = [item.objectName() or item.text() for item in buttons
                   if (item.objectName() or item.text())
                   and not (item.focusPolicy() & Qt.TabFocus)]
    if unreachable:
        raise SystemExit("Keyboard-unreachable controls: " + ", ".join(unreachable[:8]))
    window._on_reduce_motion_changed(True)
    if not window.home_orb._reduce_motion or not window.brand_mark._reduce_motion:
        raise SystemExit("Reduced motion did not reach animated brand controls")
    if not window.banner._reduce_motion:
        raise SystemExit("Reduced motion did not reach status banners")
    window.close()
    sandbox.cleanup()
    print(f"Accessibility smoke passed: {len(buttons)} keyboard controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
