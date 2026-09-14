"""Native Cocoa smoke checks for controls that source-only tests cannot cover."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models.network_adapter import NetworkAdapter
from app.viewmodels.main_viewmodel import MainViewModel
from app.views.main_window import MainWindow


@unittest.skipUnless(sys.platform == "darwin", "native macOS UI check")
class MacOSUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
        cls.app = QApplication.instance() or QApplication([])

    def test_tabs_and_primary_controls_accept_input(self):
        with (
            patch.object(MainViewModel, "refresh_adapters"),
            patch.object(MainViewModel, "refresh_official_warp_status"),
            patch.object(MainWindow, "_build_tray", lambda window: setattr(window, "tray_icon", None)),
        ):
            window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        bar = window.tabs.tabBar()
        for index in range(window.tabs.count()):
            QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(index).center())
            self.app.processEvents()
            self.assertEqual(window.tabs.currentIndex(), index)

        adapter = NetworkAdapter(
            name="Wi-Fi", description="macOS smoke service", is_enabled=True,
        )
        window._on_adapters_changed([adapter])
        self.assertTrue(window.toggle_btn.isEnabled())
        self.assertEqual(window.apps_tab.adapter_combo.currentData(), "Wi-Fi")

        window.tabs.setCurrentWidget(window.tools_tab)
        QTest.mouseClick(window.tools_tab.analyze_btn, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(window.tools_tab.result_title.text(), "بررسی کامل نشد")

        window.tabs.setCurrentWidget(window.settings_tab)
        self.assertTrue(window.check_update_btn.isEnabled())
        self.assertIn("macOS", window.check_update_btn.text())


if __name__ == "__main__":
    unittest.main()
