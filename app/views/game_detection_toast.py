"""Non-activating top notification for games running in full-screen mode."""
import ctypes

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class GameDetectionToast(QWidget):
    quick_requested = Signal(object)
    details_requested = Signal(object)
    dismissed = Signal(object)

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("بازی شناسایی شد")
        self._payload = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(15000)
        self._hide_timer.timeout.connect(self._dismiss)
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(300)
        self._topmost_timer.timeout.connect(self._force_windows_topmost)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background:#10242D; border:1px solid #4FC3F7; border-radius:14px; }"
            "QLabel { border:none; color:#E6E6E6; background:transparent; }"
            "QPushButton { background:#193742; color:#E6E6E6; border:1px solid #2D6478; "
            "border-radius:8px; padding:7px 12px; }"
            "QPushButton:hover { border-color:#81D4FA; }"
            "QPushButton#quick { background:#4FC3F7; color:#0E0E0E; font-weight:bold; border:none; }"
        )
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 11, 15, 11)
        layout.setSpacing(7)

        self.title = QLabel("🎮 بازی شناسایی شد")
        self.title.setStyleSheet("font-size:15px; font-weight:bold; color:#81D4FA;")
        layout.addWidget(self.title)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setStyleSheet("color:#B0BEC5;")
        layout.addWidget(self.description)

        buttons = QHBoxLayout()
        self.quick_button = QPushButton("✨ بهینه‌سازی هوشمند")
        self.quick_button.setObjectName("quick")
        self.details_button = QPushButton("⚙️ انتخاب جزئیات")
        self.later_button = QPushButton("فعلاً نه")
        self.quick_button.setToolTip("در بازی‌های Exclusive می‌توانی Ctrl+Alt+G را بزنی")
        buttons.addWidget(self.quick_button)
        buttons.addWidget(self.details_button)
        buttons.addWidget(self.later_button)
        layout.addLayout(buttons)

        self.quick_button.clicked.connect(self._quick)
        self.details_button.clicked.connect(self._details)
        self.later_button.clicked.connect(self._dismiss)

    def show_game(self, payload, name: str, confidence: int = 100):
        self._payload = payload
        self.title.setText(f"🎮 «{name}» شناسایی شد")
        self.description.setText(
            f"اطمینان تشخیص {confidence}٪ · بررسی هوشمند DNS، کیفیت مسیر و ترافیک مشاهده‌شدهٔ بازی. "
            "اگر پنجره در Full Screen دیده نشد، برای تأیید سریع Ctrl+Alt+G را بزن."
        )
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(620, max(360, area.width() - 32))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + 18)
        self.show()
        self.raise_()
        self._hide_timer.start()
        self._topmost_timer.start()
        QTimer.singleShot(0, self._force_windows_topmost)

    def _force_windows_topmost(self):
        """Strengthen Qt's topmost hint without activating or stealing game focus."""
        if not hasattr(ctypes, "windll"):
            return
        try:
            hwnd = int(self.winId())
            get_style = getattr(ctypes.windll.user32, "GetWindowLongPtrW", ctypes.windll.user32.GetWindowLongW)
            set_style = getattr(ctypes.windll.user32, "SetWindowLongPtrW", ctypes.windll.user32.SetWindowLongW)
            ex_style = get_style(hwnd, -20)
            # WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            set_style(hwnd, -20, ex_style | 0x00000008 | 0x00000080 | 0x08000000)
            hwnd_topmost = -1
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            area = screen.availableGeometry()
            x = area.x() + (area.width() - self.width()) // 2
            y = area.y() + 18
            # SWP_NOACTIVATE | SWP_SHOWWINDOW; re-apply position after resolution switches.
            ctypes.windll.user32.SetWindowPos(
                hwnd, hwnd_topmost, x, y, self.width(), self.height(), 0x0010 | 0x0040
            )
        except Exception:
            pass

    def _quick(self):
        payload = self._payload
        self._hide_timer.stop()
        self._topmost_timer.stop()
        self.hide()
        self.quick_requested.emit(payload)

    def _details(self):
        payload = self._payload
        self._hide_timer.stop()
        self._topmost_timer.stop()
        self.hide()
        self.details_requested.emit(payload)

    def _dismiss(self):
        payload = self._payload
        self._hide_timer.stop()
        self._topmost_timer.stop()
        self.hide()
        self.dismissed.emit(payload)
