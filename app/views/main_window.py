"""پنجره‌ی اصلی برنامه — طراحی مینیمال، تیره، راست‌چین، با پشتیبانی Tray"""
import sys
import math
import ctypes
import ctypes.wintypes
import winsound
from pathlib import Path

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF, QSize, QTimer, QTime, QEvent, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QPen, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QStatusBar, QCheckBox, QTabWidget, QLineEdit, QMessageBox,
    QSystemTrayIcon, QMenu, QGraphicsOpacityEffect, QDialog, QDialogButtonBox,
    QScrollArea, QFrame, QGridLayout, QProgressBar, QFileDialog, QSpinBox,
    QPlainTextEdit
)

from app.viewmodels.main_viewmodel import MainViewModel
from app.app_info import (
    ALLOW_CUSTOM_TUNNELS, ALLOW_GAMELINK, ALLOW_REMOTE_BACKEND,
    APP_DISPLAY_NAME, APP_VERSION, BUILD_NUMBER, EDITION,
    BRAND_PUBLISHER, LEGAL_PUBLISHER_NAME, SUPPORT_EMAIL, SUPPORT_URL,
    TERMS_VERSION, PRIVACY_VERSION,
)
from app.services import (
    settings_service, quality_service, game_route_profile_service,
    official_warp_service, crash_service, route_dna_service, recovery_service,
)
from app.views.status_banner import StatusBanner
from app.views.ping_history_chart import PingHistoryChart
from app.views.ping_overlay import PingOverlay
from app.views.game_detection_toast import GameDetectionToast
from app.views.brand import RoutePrismWidget, make_app_icon
from app.views.terms_dialog import TermsDialog
from app.views.app_access import AppAccessWidget


DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #071014;
    color: #EAF8FF;
    font-family: "Vazirmatn";
    font-size: 13px;
}
QLabel, QCheckBox {
    background: transparent;
}
QLabel#title {
    font-size: 21px;
    font-weight: bold;
    color: #75E7FF;
}
QLabel#subtitle {
    color: #8A8A8A;
}
QComboBox, QLineEdit {
    background-color: #0C1921;
    border: 1px solid #1C3440;
    border-radius: 11px;
    padding: 9px 12px 9px 40px;
    min-height: 22px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: left top;
    width: 34px;
    border: none;
    border-right: 1px solid #1C3440;
    background-color: #10232C;
    border-top-left-radius: 10px;
    border-bottom-left-radius: 10px;
}
QComboBox::down-arrow {
    image: url("__COMBO_ARROW__");
    width: 10px;
    height: 7px;
}
QPushButton {
    background-color: #0E1C25;
    border: 1px solid #203944;
    border-radius: 11px;
    padding: 10px 15px;
}
QPushButton:hover:!disabled {
    border: 1px solid #4FC3F7;
}
QPushButton#iconButton {
    padding: 0;
    min-width: 42px;
    max-width: 42px;
    min-height: 42px;
    max-height: 42px;
    font-size: 16px;
}
QPushButton:disabled {
    color: #555;
}
QPushButton#primary {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #55DFFF,stop:1 #6F70FF);
    color: #041116;
    font-weight: bold;
    border: none;
}
QPushButton#primary:hover:!disabled {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #80EAFF,stop:1 #8A86FF);
}
QPushButton#danger {
    background-color: transparent;
    border: 1px solid #C62828;
    color: #EF9A9A;
}
QPushButton#connected {
    background-color: transparent;
    border: 1px solid #EF5350;
    color: #EF9A9A;
    font-weight: bold;
}
QPushButton#connected:hover:!disabled {
    background-color: #2A1414;
    border: 1px solid #EF5350;
}
QListWidget {
    background-color: #0A151C;
    border-radius: 12px;
    border: 1px solid #1A303A;
    outline: none;
}
QListWidget::item {
    padding: 12px;
    border-bottom: 1px solid #132831;
}
QListWidget::item:selected {
    background-color: #14313D;
    color: #4FC3F7;
    border-right: 3px solid #4FC3F7;
}
QStatusBar {
    background-color: #081219;
    color: #7A7A7A;
    border-top: 1px solid #2B2B2B;
}
QScrollBar:vertical {
    background: transparent;
    width: 7px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #294653;
    border-radius: 3px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: #3F7285; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: 7px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #294653;
    border-radius: 3px;
    min-width: 32px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
    background: transparent;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QTabWidget::pane {
    border: 1px solid #172D37;
    border-radius: 16px;
    top: 6px;
    background:#081218;
}
QTabBar::tab {
    background-color: transparent;
    color: #78909C;
    padding: 10px 17px;
    margin:2px;
    border-radius:10px;
}
QTabBar::tab:selected {
    color: #DFF9FF;
    background:#102833;
    border-bottom: 2px solid #59DFFF;
}
QCheckBox {
    spacing: 8px;
    padding: 4px;
}
QFrame#gameHero {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #102A35,stop:1 #101827);
    border: 1px solid #28586B;
    border-radius: 18px;
}
QLabel#gameHeroTitle {
    color: #81D4FA;
    font-size: 17px;
    font-weight: bold;
}
QLabel#stepDone { color: #81C784; }
QLabel#stepActive { color: #4FC3F7; }
QFrame#topHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #09151C,stop:1 #0D1724);
    border:1px solid #172E3A;
    border-radius:16px;
}
QFrame#homeFocus {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #102B36,stop:0.55 #0C1B25,stop:1 #13162A);
    border:1px solid #2A5A6B;
    border-radius:22px;
}
QFrame#homeStat {
    background:#0B1820;
    border:1px solid #1A3440;
    border-radius:15px;
}
QLabel#homeHeroTitle { font-size:21px; font-weight:bold; color:#EAFBFF; }
QLabel#homeStateTitle { font-size:18px; font-weight:bold; color:#8EEAFF; }
"""

_combo_arrow_path = (
    Path(__file__).resolve().parent.parent / "resources" / "branding" / "chevron-down.svg"
).as_posix()
DARK_STYLE = DARK_STYLE.replace("__COMBO_ARROW__", _combo_arrow_path)


class ConnectionGauge(QWidget):
    """A low-cost route gauge: scans without inventing a score, then shows measured quality."""
    def __init__(self, reduce_motion=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 176)
        self._state = "idle"
        self._phase = 0
        self._score = None
        self._target_score = None
        self._settle_frames = 0
        self._reduce_motion = reduce_motion
        self._paused = False
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        if self._state == "testing":
            self._phase = (self._phase + 3) % 142
        elif self._target_score is not None:
            current = float(self._score or 0)
            delta = self._target_score - current
            if abs(delta) >= .35:
                self._score = current + delta * .14
            elif self._score != self._target_score:
                self._score = self._target_score
                self._settle_frames = 18
            elif self._settle_frames > 0:
                self._settle_frames -= 1
            else:
                self._timer.stop()
        self.update()

    def _sync_timer(self):
        should_run = (
            not self._reduce_motion and not self._paused and
            (self._state == "testing" or (
                self._target_score is not None and self._score != self._target_score
            ) or self._settle_frames > 0)
        )
        if should_run:
            self._timer.start()
        else:
            self._timer.stop()

    def set_reduce_motion(self, value: bool):
        self._reduce_motion = bool(value)
        if self._reduce_motion:
            if self._target_score is not None:
                self._score = self._target_score
            self._timer.stop()
        else:
            self._sync_timer()
        self.update()

    def set_paused(self, value: bool):
        self._paused = bool(value)
        self._sync_timer()

    def set_state(self, state: str):
        self._state = state
        if state in ("idle", "detected", "error"):
            self._score = None
            self._target_score = None
        self._sync_timer()
        self.update()

    def set_score(self, score: int, label: str = "امتیاز مسیر"):
        self._state = "connected"
        self._target_score = max(0, min(100, int(score)))
        self._settle_frames = 0
        self._score_label = label
        if self._score is None or self._reduce_motion:
            self._score = self._target_score if self._reduce_motion else 0.0
        self._sync_timer()
        self.update()

    def paintEvent(self, _event):
        if self._state == "testing":
            bright = QColor("#FFD166")
        elif self._state == "error":
            bright = QColor("#FF7D8B")
        elif self._score is not None:
            bright = QColor(
                "#79F2BE" if self._score >= 85 else
                "#65E5FF" if self._score >= 65 else
                "#FFD166" if self._score >= 45 else "#FF7D8B"
            )
        elif self._state == "detected":
            bright = QColor("#65E5FF")
        else:
            bright = QColor("#647985")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy, radius = self.width() // 2, 120, 98
        arc_rect = (cx - radius, cy - radius, radius * 2, radius * 2)

        pulse = int(18 * math.sin(self._settle_frames / 18 * math.pi)) if self._settle_frames else 0
        for extra, alpha in ((13, 22 + pulse), (7, 34 + pulse)):
            glow = QPen(QColor(bright.red(), bright.green(), bright.blue(), alpha), 5)
            glow.setCapStyle(Qt.RoundCap)
            painter.setPen(glow)
            painter.drawArc(cx - radius - extra, cy - radius - extra,
                            (radius + extra) * 2, (radius + extra) * 2, 0, 180 * 16)

        base_pen = QPen(QColor("#203743"), 13)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(*arc_rect, 0, 180 * 16)

        for tick in range(11):
            angle = math.pi - math.pi * tick / 10
            outer = radius - 15
            inner = outer - (9 if tick % 5 == 0 else 5)
            pen = QPen(QColor("#79909B"), 2 if tick % 5 == 0 else 1)
            painter.setPen(pen)
            painter.drawLine(
                int(cx + inner * math.cos(angle)), int(cy - inner * math.sin(angle)),
                int(cx + outer * math.cos(angle)), int(cy - outer * math.sin(angle)),
            )

        meter_pen = QPen(bright, 13)
        meter_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(meter_pen)
        if self._state == "testing":
            painter.drawArc(*arc_rect, (180 - self._phase) * 16, -38 * 16)
            needle_value = (self._phase + 19) / 180 * 100
        elif self._score is not None:
            painter.drawArc(*arc_rect, 180 * 16, -int(float(self._score) * 1.8 * 16))
            needle_value = float(self._score)
        else:
            needle_value = 0

        angle = math.pi - math.pi * needle_value / 100
        needle_radius = 66
        painter.setPen(QPen(QColor("#EAF8FF"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(cx, cy, int(cx + needle_radius * math.cos(angle)),
                         int(cy - needle_radius * math.sin(angle)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(bright)
        painter.drawEllipse(cx - 8, cy - 8, 16, 16)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        # Keep the endpoint labels inside the quiet area of the gauge.  Drawing
        # them directly on the arc made them low-contrast and easy to miss.
        base_badge = QRectF(27, 91, 62, 23)
        turbo_badge = QRectF(self.width() - 89, 91, 62, 23)
        painter.setPen(QPen(QColor("#29414C"), 1))
        painter.setBrush(QColor("#0A171E"))
        painter.drawRoundedRect(base_badge, 9, 9)
        painter.setPen(QPen(QColor("#267188"), 1))
        painter.setBrush(QColor("#0A1C24"))
        painter.drawRoundedRect(turbo_badge, 9, 9)
        painter.setPen(QColor("#B5C8D1"))
        painter.drawText(base_badge, Qt.AlignCenter, "پایه")
        painter.setPen(QColor("#72E8FF"))
        painter.drawText(turbo_badge, Qt.AlignCenter, "توربو")

        painter.setPen(QColor("#EAF8FF"))
        font.setBold(True)
        font.setPointSize(17)
        painter.setFont(font)
        value_text = (
            "در حال سنجش" if self._state == "testing" else
            str(int(round(self._score))) if self._score is not None else
            "فعال" if self._state == "connected" else
            "آماده"
        )
        painter.drawText(25, 130, self.width() - 50, 28, Qt.AlignCenter, value_text)
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        caption = (
            getattr(self, "_score_label", "امتیاز واقعی مسیر")
            if self._score is not None else
            "بدون عدد تخمینی" if self._state == "testing" else
            "منتظر سنجش واقعی" if self._state == "connected" else
            "امتیاز واقعی مسیر"
        )
        painter.setPen(QColor("#8FA5AF"))
        painter.drawText(20, 155, self.width() - 40, 18, Qt.AlignCenter, caption)


def _load_fonts():
    """لود فونت وزیرمتن از پوشه‌ی resources تا رابط فارسی درست و بدون باگ نمایش داده بشه"""
    from PySide6.QtGui import QFontDatabase
    import os
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "fonts")
    for fname in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
        path = os.path.join(base, fname)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        _load_fonts()
        self.vm = MainViewModel()
        self.settings = settings_service.load_settings()
        self.app_icon = make_app_icon()
        self._running_game_name = ""
        self._optimized_game_name = ""
        self._pending_game_payload = None
        self._official_warp_active = False
        self._official_warp_owned = False
        self._warp_operation_busy = False
        self._latest_dns_quality = {}

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(self.app_icon)
        self.resize(720, 540)
        self.setMinimumSize(430, 390)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(DARK_STYLE)

        self._build_ui()
        self._build_tray()
        self._connect_signals()
        self.vm.refresh_adapters()
        self._render_games(self.vm.games)
        self._render_tunnel_configs(self.vm.tunnel_configs)

        self.ping_overlay = PingOverlay(self._get_overlay_target)
        self.game_detection_toast = GameDetectionToast()
        self.game_detection_toast.quick_requested.connect(self._on_game_toast_quick)
        self.game_detection_toast.details_requested.connect(self._on_game_toast_details)
        self.game_detection_toast.dismissed.connect(self._on_game_toast_dismissed)
        self._hotkey_id = 0x4744
        self._hotkey_registered = self._register_global_hotkey()
        if self.settings.get("automatic_update_checks", True):
            QTimer.singleShot(2800, lambda: self.vm.check_for_updates(manual=False))
        QTimer.singleShot(900, self.vm.refresh_official_warp_status)

    # ---------------- ساخت رابط ----------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        self.main_root_layout = root
        root.setContentsMargins(22, 20, 22, 14)
        root.setSpacing(12)

        self.header_frame = QFrame()
        self.header_frame.setObjectName("topHeader")
        header = QHBoxLayout(self.header_frame)
        header.setContentsMargins(16, 12, 16, 12)
        self.brand_mark = RoutePrismWidget()
        self.brand_mark.set_reduce_motion(self.settings.get("reduce_motion", False))
        header.addWidget(self.brand_mark)
        title_box = QVBoxLayout()
        title = QLabel("LAGSHIFT  ·  لگ‌شیفت")
        title.setObjectName("title")
        subtitle = QLabel("بهینه‌ساز اتصال برای گیمرها")
        self.header_subtitle = subtitle
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.connection_badge = QLabel("⭕ قطع")
        self.connection_badge.setStyleSheet(
            "color:#A9BAC4; font-weight:bold; background:#0A151C;"
            "border:1px solid #203944; border-radius:12px; padding:8px 12px;"
        )
        header.addWidget(self.connection_badge)
        root.addWidget(self.header_frame)

        self.banner = StatusBanner()
        self.banner.set_reduce_motion(self.settings.get("reduce_motion", False))
        root.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.home_tab = self._build_home_tab()
        self.games_tab = self._build_games_tab()
        self.apps_tab = AppAccessWidget(self.vm)
        self.dns_tab = self._build_dns_tab()
        self.tunnel_tab = self._build_tunnel_tab()
        self.settings_tab = self._build_settings_tab()
        self.tabs.addTab(self.home_tab, "⌂ خانه")
        self.tabs.addTab(self.games_tab, "🎮 بازی‌ها")
        self.tabs.addTab(self.apps_tab, "🧩 برنامه‌ها")
        self.tabs.addTab(self.dns_tab, "🌐 DNS")
        self.tabs.addTab(self.tunnel_tab, "🛡 اتصال")
        self.tabs.addTab(self.settings_tab, "⚙ تنظیمات")
        root.addWidget(self.tabs, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_home_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        focus = QFrame()
        focus.setObjectName("homeFocus")
        focus_layout = QHBoxLayout(focus)
        focus_layout.setContentsMargins(24, 20, 24, 20)
        copy = QVBoxLayout()
        eyebrow = QLabel("پیشنهاد هوشمند برای همین لحظه")
        eyebrow.setStyleSheet("color:#72DFF8; font-weight:bold;")
        copy.addWidget(eyebrow)
        self.home_game_title = QLabel("منتظر اجرای بازی")
        self.home_game_title.setObjectName("homeHeroTitle")
        self.home_game_title.setWordWrap(True)
        copy.addWidget(self.home_game_title)
        self.home_game_subtitle = QLabel(
            "بازی را باز کن؛ لگ‌شیفت آن را محلی تشخیص می‌دهد و قبل از هر تغییری تأیید می‌گیرد."
        )
        self.home_game_subtitle.setWordWrap(True)
        self.home_game_subtitle.setStyleSheet("color:#A9BAC4;")
        copy.addWidget(self.home_game_subtitle)
        copy.addSpacing(8)
        self.home_state_title = QLabel("آمادهٔ شناسایی")
        self.home_state_title.setObjectName("homeStateTitle")
        copy.addWidget(self.home_state_title)
        self.home_state_copy = QLabel("هیچ بهینه‌سازی فعالی وجود ندارد.")
        self.home_state_copy.setWordWrap(True)
        self.home_state_copy.setStyleSheet("color:#93A8B3;")
        copy.addWidget(self.home_state_copy)
        steps_row = QHBoxLayout()
        steps_row.setSpacing(5)
        self.home_steps = []
        for text in ("۱ شناسایی", "۲ بررسی", "۳ انتخاب مسیر", "۴ آماده"):
            step = QLabel(text)
            step.setAlignment(Qt.AlignCenter)
            step.setStyleSheet(
                "color:#607985; background:#0A161D; border-radius:8px; padding:6px 5px;"
            )
            steps_row.addWidget(step)
            self.home_steps.append(step)
        copy.addLayout(steps_row)
        self.home_primary_btn = QPushButton("🎮 رفتن به بازی‌های من")
        self.home_primary_btn.setObjectName("primary")
        self.home_primary_btn.setMinimumHeight(45)
        copy.addWidget(self.home_primary_btn)
        focus_layout.addLayout(copy, 1)
        self.home_orb = ConnectionGauge(self.settings.get("reduce_motion", False))
        focus_layout.addWidget(self.home_orb, 0, Qt.AlignCenter)
        layout.addWidget(focus)

        stats = QGridLayout()
        stats.setHorizontalSpacing(10)
        stat_specs = (
            ("home_dns_value", "DNS", "بدون تغییر"),
            ("home_route_value", "مسیر اتصال", "مستقیم"),
            ("home_ping_value", "پینگ زنده", "—"),
        )
        for column, (attr, caption, value) in enumerate(stat_specs):
            card = QFrame()
            card.setObjectName("homeStat")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 12, 14, 12)
            heading = QLabel(caption)
            heading.setStyleSheet("color:#7896A4; font-size:11px;")
            metric = QLabel(value)
            metric.setWordWrap(True)
            metric.setStyleSheet("color:#DFF9FF; font-size:15px; font-weight:bold;")
            setattr(self, attr, metric)
            box.addWidget(heading)
            box.addWidget(metric)
            stats.addWidget(card, 0, column)
        layout.addLayout(stats)

        quick_title = QLabel("دسترسی سریع")
        quick_title.setStyleSheet("font-size:15px; font-weight:bold; color:#DFF9FF;")
        layout.addWidget(quick_title)
        quick = QGridLayout()
        self.home_games_btn = QPushButton("🎮 مدیریت بازی‌ها")
        self.home_dns_btn = QPushButton("🌐 انتخاب DNS")
        self.home_tunnel_btn = QPushButton("🛡 مسیرهای اتصال")
        quick.addWidget(self.home_games_btn, 0, 0)
        quick.addWidget(self.home_dns_btn, 0, 1)
        quick.addWidget(self.home_tunnel_btn, 0, 2)
        layout.addLayout(quick)
        privacy = QLabel(
            "🔒 تشخیص بازی و تحلیل مسیر روی همین دستگاه انجام می‌شود؛ هیچ تغییری بدون انتخاب تو اعمال نمی‌شود."
        )
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color:#7896A4; padding:6px;")
        layout.addWidget(privacy)
        layout.addStretch()
        return tab

    def _build_dns_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        adapter_row = QHBoxLayout()
        adapter_row.addWidget(QLabel("آداپتور:"))
        self.adapter_combo = QComboBox()
        adapter_row.addWidget(self.adapter_combo, 1)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setObjectName("iconButton")
        self.refresh_btn.setFixedSize(42, 42)
        self.refresh_btn.setToolTip("به‌روزرسانی فهرست کارت‌های شبکه")
        adapter_row.addWidget(self.refresh_btn)
        layout.addLayout(adapter_row)

        self.dns_score_frame = QFrame()
        self.dns_score_frame.setObjectName("dnsScoreCard")
        self.dns_score_frame.setStyleSheet(
            "QFrame#dnsScoreCard { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            "stop:0 #10242D, stop:1 #142F3A); border:1px solid #2D6478; border-radius:14px; }"
            "QLabel { border:none; background:transparent; }"
        )
        score_row = QHBoxLayout(self.dns_score_frame)
        score_row.setContentsMargins(16, 13, 16, 13)
        self.dns_score_big = QLabel("— / 100")
        self.dns_score_big.setAlignment(Qt.AlignCenter)
        self.dns_score_big.setMinimumWidth(155)
        self.dns_score_big.setStyleSheet("font-size:27px; font-weight:bold; color:#4FC3F7;")
        score_row.addWidget(self.dns_score_big)
        score_info = QVBoxLayout()
        self.dns_score_title = QLabel("🧠 DNS Intelligence")
        self.dns_score_title.setStyleSheet("font-size:16px; font-weight:bold; color:#81D4FA;")
        score_info.addWidget(self.dns_score_title)
        self.dns_score_metrics = QLabel(
            "آماده برای تحلیل چندمرحله‌ای · میانه · نوسان · پایداری · DoH"
        )
        self.dns_score_metrics.setWordWrap(True)
        self.dns_score_metrics.setStyleSheet("color:#B0BEC5;")
        score_info.addWidget(self.dns_score_metrics)
        self.dns_benchmark_bar = QProgressBar()
        self.dns_benchmark_bar.setRange(0, len(self.vm.dns_profiles))
        self.dns_benchmark_bar.setValue(0)
        self.dns_benchmark_bar.setTextVisible(False)
        self.dns_benchmark_bar.setFixedHeight(7)
        self.dns_benchmark_bar.setStyleSheet(
            "QProgressBar { background:#0D171C; border:none; border-radius:3px; }"
            "QProgressBar::chunk { background:#4FC3F7; border-radius:3px; }"
        )
        score_info.addWidget(self.dns_benchmark_bar)
        self.dns_benchmark_status = QLabel("برای شروع، «انتخاب هوشمند» را وصل کن")
        self.dns_benchmark_status.setStyleSheet("color:#80CBC4; font-size:11px;")
        score_info.addWidget(self.dns_benchmark_status)
        self.dns_explain_btn = QPushButton("چرا این مسیر انتخاب شد؟")
        self.dns_explain_btn.setEnabled(False)
        self.dns_explain_btn.setToolTip("دلیل انتخاب و میزان اطمینان RouteDNA را نشان می‌دهد")
        score_info.addWidget(self.dns_explain_btn)
        score_row.addLayout(score_info, 1)
        layout.addWidget(self.dns_score_frame)

        goal_card = QFrame()
        goal_card.setObjectName("dnsGoalCard")
        goal_card.setStyleSheet(
            "QFrame#dnsGoalCard { background:#171D20; border:1px solid #31505D; "
            "border-radius:12px; } QLabel { border:none; background:transparent; }"
        )
        goal_layout = QVBoxLayout(goal_card)
        goal_layout.setContentsMargins(14, 11, 14, 11)
        goal_title = QLabel("🎯 DNS را برای چه کاری می‌خواهی؟")
        goal_title.setStyleSheet("font-size:15px; font-weight:bold; color:#FFD180;")
        goal_layout.addWidget(goal_title)
        self.dns_goal_combo = QComboBox()
        self.dns_goal_combo.addItem("🎮 باز کردن بازی‌های تحریم‌شده · DNS ایرانی", "anti_sanction")
        self.dns_goal_combo.addItem("🌍 پاسخ سریع‌تر سایت و شروع دانلود · DNS جهانی", "speed")
        self.dns_goal_combo.addItem("🤖 انتخاب خودکار از بین همه DNSها", "balanced")
        goal_index = self.dns_goal_combo.findData(
            self.settings.get("dns_usage_goal", "balanced")
        )
        self.dns_goal_combo.setCurrentIndex(max(0, goal_index))
        goal_layout.addWidget(self.dns_goal_combo)
        goal_hint = QLabel(
            "سرعت واقعی خط تغییر نمی‌کند؛ حالت سرعت، پاسخ DNS و انتخاب CDN را بهینه می‌کند."
        )
        goal_hint.setWordWrap(True)
        goal_hint.setStyleSheet("color:#90A4AE; font-size:11px;")
        goal_layout.addWidget(goal_hint)
        layout.addWidget(goal_card)

        selection_row = QGridLayout()
        selection_label = QLabel("هنگام تست، اولویت با:")
        selection_label.setToolTip("این گزینه فقط روش امتیازدهی و انتخاب بهترین DNS را تغییر می‌دهد")
        selection_row.addWidget(selection_label, 0, 0)
        self.dns_preference_combo = QComboBox()
        self.dns_preference_combo.addItem("⚖️ متعادل · سریع و پایدار", "balanced")
        self.dns_preference_combo.addItem("⚡ سرعت پاسخ · انتخاب سریع‌ترین", "fastest")
        self.dns_preference_combo.addItem("🛡️ پایداری اتصال · نوسان کمتر", "stable")
        self.dns_preference_combo.setToolTip(
            "مشخص می‌کند LAGSHIFT در نتایج تست به سرعت پاسخ یا پایداری وزن بیشتری بدهد"
        )
        preference_index = self.dns_preference_combo.findData(
            self.settings.get("dns_selection_mode", "balanced")
        )
        self.dns_preference_combo.setCurrentIndex(max(0, preference_index))
        selection_row.addWidget(self.dns_preference_combo, 0, 1)
        self.dns_retest_btn = QPushButton("🧠 تست هوشمند مجدد و انتخاب بهترین")
        self.dns_retest_btn.setEnabled(False)
        selection_row.addWidget(self.dns_retest_btn, 1, 0, 1, 2)
        layout.addLayout(selection_row)

        layout.addWidget(QLabel("سرور DNS:"))
        self.profile_list = QListWidget()
        smart_item = QListWidgetItem("⚡ انتخاب هوشمند سریع‌ترین DNS سالم")
        smart_item.setData(Qt.UserRole, None)
        self.profile_list.addItem(smart_item)
        for p in self.vm.dns_profiles:
            item = QListWidgetItem(self._dns_profile_text(p))
            item.setData(Qt.UserRole, p)
            self._style_dns_profile_item(item, p)
            self.profile_list.addItem(item)
        self.profile_list.setCurrentRow(0)
        layout.addWidget(self.profile_list, 1)

        self.kill_switch_check = QCheckBox("محافظ DNS — بازیابی تنظیم قبلی اگر اتصال قطع شود")
        layout.addWidget(self.kill_switch_check)

        self.dns_state_label = QLabel("وضعیت DNS: تغییری توسط برنامه اعمال نشده")
        self.dns_state_label.setWordWrap(True)
        self.dns_state_label.setStyleSheet(
            "background:#171717; border:1px solid #2B2B2B; border-radius:8px; padding:9px; color:#B0BEC5;"
        )
        layout.addWidget(self.dns_state_label)

        action_row = QHBoxLayout()
        self.toggle_btn = QPushButton("اتصال")
        self.toggle_btn.setObjectName("primary")
        action_row.addWidget(self.toggle_btn)
        self.switch_dns_btn = QPushButton("🔁 تعویض مستقیم به DNS انتخاب‌شده")
        self.switch_dns_btn.setEnabled(False)
        self.switch_dns_btn.setToolTip("بدون نیاز به قطع دستی، DNS فعال را با انتخاب فعلی عوض می‌کند")
        action_row.addWidget(self.switch_dns_btn)
        layout.addLayout(action_row)

        return tab

    def _build_tunnel_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        import_title = QLabel("افزودن مسیر اتصال شخصی یا اشتراک:")
        import_row = QHBoxLayout()
        self.tunnel_link_input = QLineEdit()
        self.tunnel_link_input.setPlaceholderText("لینک مسیر را اینجا وارد کن…")
        import_row.addWidget(self.tunnel_link_input, 1)
        self.import_tunnel_btn = QPushButton("➕ افزودن")
        self.import_tunnel_btn.setObjectName("primary")
        import_row.addWidget(self.import_tunnel_btn)
        if ALLOW_CUSTOM_TUNNELS:
            layout.addWidget(import_title)
            layout.addLayout(import_row)
        else:
            import_title.hide()
            self.tunnel_link_input.hide()
            self.import_tunnel_btn.hide()
            public_note = QLabel(
                "🛡 اتصال اختیاری فقط با کلاینت رسمی Cloudflare انجام می‌شود. در حالت WARP ممکن است "
                "تمام ترافیک دستگاه موقتاً عبور کند؛ نسخه عمومی کانفیگ ناشناس دریافت نمی‌کند."
            )
            public_note.setWordWrap(True)
            public_note.setStyleSheet(
                "background:#0D2028; border:1px solid #28586B; border-radius:12px; "
                "padding:12px; color:#BDEFFF;"
            )
            layout.addWidget(public_note)

        warp_panel = QFrame()
        warp_panel.setStyleSheet(
            "QFrame { background:#0B1820; border:1px solid #285064; border-radius:14px; }"
            "QLabel { border:none; background:transparent; }"
        )
        warp_box = QVBoxLayout(warp_panel)
        warp_box.setContentsMargins(14, 12, 14, 12)
        warp_title = QLabel("☁ WARP Bridge رسمی · BETA")
        warp_title.setStyleSheet("font-size:15px; font-weight:bold; color:#79E6FF;")
        warp_box.addWidget(warp_title)
        self.warp_state_label = QLabel("در حال شناسایی کلاینت رسمی Cloudflare…")
        self.warp_state_label.setWordWrap(True)
        self.warp_state_label.setStyleSheet("color:#9BB2BC;")
        warp_box.addWidget(self.warp_state_label)
        warp_mode_row = QHBoxLayout()
        warp_mode_row.addWidget(QLabel("روش اتصال:"))
        self.warp_mode_combo = QComboBox()
        self.warp_mode_combo.addItem("پیشنهادی · انتخاب خودکار مسیر کامل", "smart")
        self.warp_mode_combo.addItem("حالت نجات · آزمایش هر ۶ روش رسمی", "rescue")
        self.warp_mode_combo.addItem("فقط DNS امن · انتخاب خودکار", "dns_smart")
        self.warp_mode_combo.addItem("فقط DNS امن (HTTPS)", "doh")
        self.warp_mode_combo.addItem("فقط DNS امن (TLS)", "dot")
        self.warp_mode_combo.addItem("ترافیک و DNS (UDP)", "warp")
        self.warp_mode_combo.addItem("ترافیک و DNS (HTTPS)", "warp+doh")
        self.warp_mode_combo.addItem("ترافیک و DNS (TLS)", "warp+dot")
        self.warp_mode_combo.addItem("فقط ترافیک", "tunnel_only")
        warp_mode_row.addWidget(self.warp_mode_combo, 1)
        warp_box.addLayout(warp_mode_row)
        warp_controls = QHBoxLayout()
        warp_controls.addWidget(QLabel("موتور انتقال:"))
        self.warp_protocol_combo = QComboBox()
        self.warp_protocol_combo.addItem("هوشمند · MASQUE سپس WireGuard", "auto")
        self.warp_protocol_combo.addItem("MASQUE", "masque")
        self.warp_protocol_combo.addItem("WireGuard", "wireguard")
        warp_controls.addWidget(self.warp_protocol_combo, 1)
        self.warp_refresh_btn = QPushButton("بررسی دوباره")
        warp_controls.addWidget(self.warp_refresh_btn)
        self.warp_install_btn = QPushButton("دریافت کلاینت رسمی")
        self.warp_install_btn.setObjectName("primary")
        self.warp_install_btn.setVisible(False)
        warp_controls.addWidget(self.warp_install_btn)
        self.warp_btn = QPushButton("اتصال و تأیید WARP رسمی")
        self.warp_btn.setObjectName("primary")
        self.warp_btn.setEnabled(False)
        warp_controls.addWidget(self.warp_btn)
        warp_box.addLayout(warp_controls)
        warp_warning = QLabel(
            "LAGSHIFT فایل Cloudflare را بازتوزیع نمی‌کند؛ فقط کلاینت رسمیِ دارای امضای معتبر را کنترل می‌کند."
        )
        warp_warning.setWordWrap(True)
        warp_warning.setStyleSheet("color:#6F8D99; font-size:11px;")
        warp_box.addWidget(warp_warning)
        layout.addWidget(warp_panel)

        layout.addWidget(QLabel("مسیرهای ذخیره‌شده:"))
        self.tunnel_list = QListWidget()
        layout.addWidget(self.tunnel_list, 1)

        row2 = QGridLayout()
        self.ping_test_btn = QPushButton("📶 تست پینگ")
        self.trial_btn = QPushButton("🧪 آزمایش ۳۰ ثانیه‌ای")
        self.rate_config_btn = QPushButton("⭐ امتیاز شخصی")
        self.remove_tunnel_btn = QPushButton("🗑️ حذف")
        self.remove_tunnel_btn.setObjectName("danger")
        row2.addWidget(self.ping_test_btn, 0, 0)
        row2.addWidget(self.trial_btn, 0, 1)
        row2.addWidget(self.rate_config_btn, 1, 0)
        row2.addWidget(self.remove_tunnel_btn, 1, 1)
        layout.addLayout(row2)

        self.tunnel_toggle_btn = QPushButton("اتصال هوشمند")
        self.tunnel_toggle_btn.setObjectName("primary")
        layout.addWidget(self.tunnel_toggle_btn)

        self.tunnel_scope_label = QLabel("محدوده اتصال: غیرفعال")
        self.tunnel_scope_label.setWordWrap(True)
        self.tunnel_scope_label.setStyleSheet("color:#80CBC4; padding:4px;")
        layout.addWidget(self.tunnel_scope_label)

        self.route_quality_label = QLabel("Game Score: هنوز مسیری ارزیابی نشده")
        self.route_quality_label.setWordWrap(True)
        self.route_quality_label.setStyleSheet(
            "background:#171717; border:1px solid #2B2B2B; border-radius:8px; "
            "padding:9px; color:#B0BEC5;"
        )
        layout.addWidget(self.route_quality_label)

        layout.addWidget(QLabel("تاریخچه‌ی پینگ (وقتی تانل وصله):"))
        self.ping_chart = PingHistoryChart()
        layout.addWidget(self.ping_chart)

        self.speed_test_btn = QPushButton("⚡ سنجش واقعی مسیر فعال")
        layout.addWidget(self.speed_test_btn)
        self.speed_test_result = QLabel("")
        self.speed_test_result.setStyleSheet("color:#B0BEC5; font-size:12px;")
        self.speed_test_result.setWordWrap(True)
        layout.addWidget(self.speed_test_result)

        note = QLabel(
            "WARP فقط پس از آزمون واقعی مسیر فعال می‌شود. در نسخه عمومی، اتصال به "
            "بازی در حال اجرا محدود است و با بسته‌شدن بازی خاتمه پیدا می‌کند."
            if not ALLOW_CUSTOM_TUNNELS else
            "اتصال هوشمند مسیرها را با عبور واقعی ترافیک بررسی می‌کند و بهترین مسیر سالم را فعال می‌کند."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8A8A8A;")
        layout.addWidget(note)

        self.usage_label = QLabel("زمان اتصال امروز: —")
        self.usage_label.setStyleSheet("color:#8A8A8A; font-size:12px;")
        layout.addWidget(self.usage_label)
        self.traffic_label = QLabel("مصرف محلی امروز: —")
        self.traffic_label.setStyleSheet("color:#8A8A8A; font-size:12px;")
        layout.addWidget(self.traffic_label)

        if ALLOW_CUSTOM_TUNNELS:
            public_title = QLabel("منابع کانفیگ عمومی (کامیونیتی، نه سرور اختصاصی این اپ):")
            public_title.setStyleSheet("margin-top:8px;")
            layout.addWidget(public_title)
            for src in self.vm.public_config_sources:
                row = QHBoxLayout()
                label = QLabel(f"🔗 {src.name} — {src.description}")
                label.setStyleSheet("color:#B0BEC5; font-size:12px;")
                label.setWordWrap(True)
                row.addWidget(label, 1)
                layout.addLayout(row)

        return tab

    def _build_games_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.games_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        hero = QFrame()
        hero.setObjectName("gameHero")
        hero_layout = QVBoxLayout(hero)
        hero_title = QLabel("🎮 بازی‌های من")
        hero_title.setObjectName("gameHeroTitle")
        hero_layout.addWidget(hero_title)
        hero_text = QLabel(
            "بازی را اجرا کن؛ برنامه آن را پیدا می‌کند و قبل از هر تغییری از تو اجازه می‌گیرد. "
            "برای استفاده معمولی فقط دکمه آبی را بزن."
        )
        hero_text.setWordWrap(True)
        hero_text.setStyleSheet("color:#B0BEC5;")
        hero_layout.addWidget(hero_text)
        steps = QLabel("① اجرای بازی     ② تأیید پیشنهاد     ③ بهینه‌سازی خودکار")
        steps.setWordWrap(True)
        steps.setStyleSheet(
            "background:#0E1A20; border-radius:8px; padding:9px; color:#80CBC4; font-weight:bold;"
        )
        hero_layout.addWidget(steps)
        self.game_detection_check = QCheckBox("تشخیص خودکار بازی‌های در حال اجرا")
        self.game_detection_check.setChecked(self.settings.get("game_detection_enabled", True))
        detection_options = QHBoxLayout()
        detection_options.addWidget(self.game_detection_check)
        self.game_detection_sound_check = QCheckBox("با صدا خبرم کن")
        self.game_detection_sound_check.setChecked(self.settings.get("game_detection_sound", True))
        self.game_detection_sound_check.toggled.connect(
            lambda value: self._set_setting("game_detection_sound", value)
        )
        detection_options.addWidget(self.game_detection_sound_check)
        detection_options.addStretch()
        hero_layout.addLayout(detection_options)
        shortcut_note = QLabel("داخل بازی تمام‌صفحه: Ctrl + Alt + G پیشنهاد را باز می‌کند")
        shortcut_note.setStyleSheet("color:#FFD180;")
        hero_layout.addWidget(shortcut_note)
        self.detected_game_label = QLabel("🔎 منتظر اجرای بازی…")
        self.detected_game_label.setStyleSheet("color:#80CBC4; font-size:14px; font-weight:bold;")
        hero_layout.addWidget(self.detected_game_label)
        self.review_detected_game_btn = QPushButton("✨ دیدن پیشنهاد و بهینه‌سازی")
        self.review_detected_game_btn.setObjectName("primary")
        self.review_detected_game_btn.hide()
        self.review_detected_game_btn.clicked.connect(self._on_review_pending_game)
        hero_layout.addWidget(self.review_detected_game_btn)
        layout.addWidget(hero)

        games_card = QFrame()
        games_card.setObjectName("dnsScoreCard")
        games_layout = QVBoxLayout(games_card)
        games_title = QLabel("بازی‌های شما")
        games_title.setStyleSheet("font-size:15px; font-weight:bold; color:#E0E0E0;")
        games_layout.addWidget(games_title)
        games_hint = QLabel("یک بازی را انتخاب کن؛ اگر در حال اجرا باشد، برنامه خودش آن را علامت می‌زند.")
        games_hint.setWordWrap(True)
        games_hint.setStyleSheet("color:#90A4AE;")
        games_layout.addWidget(games_hint)
        self.quick_game_action_btn = QPushButton("✨ بهینه‌سازی بازی انتخاب‌شده")
        self.quick_game_action_btn.setObjectName("primary")
        self.quick_game_action_btn.setEnabled(False)
        games_layout.addWidget(self.quick_game_action_btn)
        self.games_list = QListWidget()
        self.games_list.setMinimumHeight(115)
        self.games_list.setMaximumHeight(155)
        games_layout.addWidget(self.games_list)

        self.game_manage_toggle = QPushButton("➕ مدیریت فهرست بازی‌ها")
        self.game_manage_toggle.setCheckable(True)
        games_layout.addWidget(self.game_manage_toggle)
        self.game_manage_frame = QFrame()
        game_manage_layout = QVBoxLayout(self.game_manage_frame)

        manage_row = QGridLayout()
        self.game_name_input = QLineEdit()
        self.game_name_input.setPlaceholderText("نام بازی جدید")
        manage_row.addWidget(self.game_name_input, 0, 0)
        self.game_process_input = QLineEdit()
        self.game_process_input.setPlaceholderText("نام فایل بازی؛ مثل game.exe")
        manage_row.addWidget(self.game_process_input, 0, 1)
        self.add_game_btn = QPushButton("➕ افزودن بازی")
        manage_row.addWidget(self.add_game_btn, 1, 0)
        self.set_game_profile_btn = QPushButton("⚙️ تنظیم این بازی")
        manage_row.addWidget(self.set_game_profile_btn, 1, 1)
        game_manage_layout.addLayout(manage_row)
        self.remove_game_btn = QPushButton("🗑️ حذف بازی انتخاب‌شده")
        self.remove_game_btn.setObjectName("danger")
        game_manage_layout.addWidget(self.remove_game_btn)
        self.game_manage_frame.hide()
        games_layout.addWidget(self.game_manage_frame)
        layout.addWidget(games_card)

        status_title = QLabel("وضعیت همین الان")
        status_title.setStyleSheet("font-size:15px; font-weight:bold;")
        layout.addWidget(status_title)
        self.optimization_details_label = QLabel(
            "هنوز بهینه‌سازی بازی شروع نشده است.\nبازی را اجرا و پیشنهاد برنامه را تأیید کن."
        )
        self.optimization_details_label.setWordWrap(True)
        self.optimization_details_label.setStyleSheet(
            "background:#101C22; border:1px solid #29434E; border-radius:10px; padding:12px; color:#CFD8DC;"
        )
        layout.addWidget(self.optimization_details_label)

        self.game_advanced_toggle = QPushButton("🔧 نمایش جزئیات فنی و ابزارهای آزمایشی")
        self.game_advanced_toggle.setCheckable(True)
        layout.addWidget(self.game_advanced_toggle)
        self.game_advanced_frame = QFrame()
        advanced_layout = QVBoxLayout(self.game_advanced_frame)
        advanced_note = QLabel(
            "این بخش برای بررسی تخصصی است؛ استفاده عادی از برنامه به هیچ‌کدام از گزینه‌های زیر نیاز ندارد."
        )
        advanced_note.setWordWrap(True)
        advanced_note.setStyleSheet("color:#FFD180; padding:6px;")
        advanced_layout.addWidget(advanced_note)

        self.optimization_technical_label = QLabel("جزئیات اتصال فعلی هنوز آماده نیست")
        self.optimization_technical_label.setWordWrap(True)
        self.optimization_technical_label.setStyleSheet("color:#90A4AE; padding:6px;")
        advanced_layout.addWidget(self.optimization_technical_label)

        route_card = QFrame()
        route_card.setObjectName("gameHero")
        route_layout = QVBoxLayout(route_card)
        route_title = QLabel("🧭 شناخت مسیر بازی · آزمایشی")
        route_title.setObjectName("gameHeroTitle")
        route_layout.addWidget(route_title)
        route_hint = QLabel(
            "برنامه مقصدها و کیفیت مسیر این بازی را روی همین دستگاه یاد می‌گیرد. "
            "اطلاعات کم‌اعتماد روی اتصال اعمال نمی‌شود."
        )
        route_hint.setWordWrap(True)
        route_hint.setStyleSheet("color:#B0BEC5; font-size:11px;")
        route_layout.addWidget(route_hint)
        self.game_route_profile_label = QLabel("یک بازی در حال اجرا یا از فهرست انتخاب کن")
        self.game_route_profile_label.setWordWrap(True)
        self.game_route_profile_label.setStyleSheet(
            "background:#0E1A20; border:1px solid #2D6478; border-radius:8px; padding:10px; color:#B2EBF2;"
        )
        route_layout.addWidget(self.game_route_profile_label)
        self.network_lab_label = QLabel(
            "بررسی کیفیت مسیر: منتظر اجرای آزمایش"
        )
        self.network_lab_label.setWordWrap(True)
        self.network_lab_label.setStyleSheet(
            "background:#111820; border:1px solid #394B59; border-radius:8px; padding:10px; color:#B0BEC5;"
        )
        route_layout.addWidget(self.network_lab_label)
        self.adapter_monitor_label = QLabel("📡 وضعیت اینترنت: پس از شروع بهینه‌سازی نمایش داده می‌شود")
        self.adapter_monitor_label.setWordWrap(True)
        self.adapter_monitor_label.setStyleSheet("color:#80CBC4; padding:4px;")
        route_layout.addWidget(self.adapter_monitor_label)
        route_actions = QGridLayout()
        self.learn_game_route_btn = QPushButton("🧪 بررسی کامل مسیر بازی")
        self.learn_game_route_btn.setObjectName("primary")
        self.clear_game_route_btn = QPushButton("↩ پاک‌کردن اطلاعات یادگرفته‌شده")
        self.export_game_route_btn = QPushButton("📤 پشتیبان‌گیری از اطلاعات مسیر")
        self.import_game_route_btn = QPushButton("📥 بازیابی اطلاعات مسیر")
        route_actions.addWidget(self.learn_game_route_btn, 0, 0)
        route_actions.addWidget(self.clear_game_route_btn, 0, 1)
        route_actions.addWidget(self.export_game_route_btn, 1, 0)
        route_actions.addWidget(self.import_game_route_btn, 1, 1)
        route_layout.addLayout(route_actions)
        self.route_auto_rollback_check = QCheckBox(
            "محافظ اتصال: اگر نتیجه معتبر بود و اتصال بدتر شد، خودکار برگرد"
        )
        self.route_auto_rollback_check.setChecked(
            self.settings.get("route_auto_rollback", False)
        )
        route_layout.addWidget(self.route_auto_rollback_check)
        advanced_layout.addWidget(route_card)

        probe_card = QFrame()
        probe_card.setObjectName("dnsScoreCard")
        probe_layout = QVBoxLayout(probe_card)
        probe_title = QLabel("📊 مقایسه کیفیت قبل و بعد · آزمایشی")
        probe_title.setStyleSheet("font-size:15px; font-weight:bold; color:#CE93D8;")
        probe_layout.addWidget(probe_title)
        probe_note = QLabel(
            "یک بار قبل از اتصال و یک بار بعد از اتصال اندازه بگیر تا برنامه بگوید تغییر واقعاً مفید بوده یا نه."
        )
        probe_note.setWordWrap(True)
        probe_note.setStyleSheet("color:#B0BEC5; font-size:11px;")
        probe_layout.addWidget(probe_note)
        self.game_probe_result = QLabel("هنوز خط مبنایی ثبت نشده است")
        self.game_probe_result.setWordWrap(True)
        self.game_probe_result.setStyleSheet(
            "background:#151018; border:1px solid #4A3150; border-radius:8px; padding:10px; color:#E1BEE7;"
        )
        probe_layout.addWidget(self.game_probe_result)
        probe_actions = QHBoxLayout()
        self.game_probe_baseline_btn = QPushButton("① اندازه‌گیری قبل از اتصال")
        self.game_probe_compare_btn = QPushButton("② بررسی نتیجه بعد از اتصال")
        probe_actions.addWidget(self.game_probe_baseline_btn)
        probe_actions.addWidget(self.game_probe_compare_btn)
        probe_layout.addLayout(probe_actions)
        advanced_layout.addWidget(probe_card)

        advanced_layout.addWidget(QLabel("گزارش مرحله‌به‌مرحله:"))
        self.game_activity_list = QListWidget()
        self.game_activity_list.setMaximumHeight(105)
        self.game_activity_list.addItem("• منتظر اجرای بازی")
        advanced_layout.addWidget(self.game_activity_list)
        self.game_advanced_frame.hide()
        layout.addWidget(self.game_advanced_frame)
        layout.addStretch()

        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.tray_check = QCheckBox("موقع بستن پنجره، برنامه بره تو Tray به‌جای بسته شدن کامل")
        self.tray_check.setChecked(self.settings.get("minimize_to_tray", True))
        layout.addWidget(self.tray_check)

        note = QLabel(
            "وقتی این گزینه فعاله، با زدن ضربدر پنجره، برنامه فقط مخفی می‌شه و از "
            "آیکون کنار ساعت ویندوز در دسترسه. برای بستن کامل، از همون‌جا «خروج» رو بزن."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8A8A8A;")
        layout.addWidget(note)

        self.autostart_check = QCheckBox("اجرای خودکار برنامه با بالا اومدن ویندوز")
        self.autostart_check.setChecked(self.vm.is_autostart_enabled())
        layout.addWidget(self.autostart_check)

        self.overlay_check = QCheckBox("نمایش اورلی شناور پینگ روی صفحه (وقتی تانل وصله)")
        self.overlay_check.setChecked(self.settings.get("overlay_enabled", False))
        layout.addWidget(self.overlay_check)

        self.reduce_motion_check = QCheckBox("حرکت‌های رابط کمتر شود")
        self.reduce_motion_check.setChecked(self.settings.get("reduce_motion", False))
        self.reduce_motion_check.setToolTip("برای تمرکز بیشتر، حرکت گوی وضعیت و محوشدن نشان اتصال را کم می‌کند")
        layout.addWidget(self.reduce_motion_check)

        self.startup_animation_check = QCheckBox("نمایش لوگوموشن هنگام اجرای برنامه")
        self.startup_animation_check.setChecked(self.settings.get("startup_animation_enabled", True))
        self.startup_animation_check.setToolTip("با کلیک یا کلید Esc می‌توانی لوگوموشن را سریع رد کنی")
        layout.addWidget(self.startup_animation_check)

        self.network_advanced_toggle = QPushButton("⚙ تنظیمات حرفه‌ای شبکه")
        self.network_advanced_toggle.setCheckable(True)
        self.network_advanced_toggle.setToolTip("RouteDNA محلی، بازیابی مسیر و QoS بازی")
        layout.addWidget(self.network_advanced_toggle)
        self.network_advanced_frame = QFrame()
        self.network_advanced_frame.setObjectName("homeStat")
        advanced_layout = QVBoxLayout(self.network_advanced_frame)
        advanced_layout.setContentsMargins(14, 12, 14, 12)

        self.failover_check = QCheckBox("بازیابی خودکار و انتقال به مسیر پشتیبان")
        self.failover_check.setChecked(self.settings.get("auto_failover", True))
        advanced_layout.addWidget(self.failover_check)

        self.emergency_check = QCheckBox("حالت نجات وقتی UDP یا مسیر اصلی بسته است")
        self.emergency_check.setChecked(self.settings.get("emergency_mode", True))
        advanced_layout.addWidget(self.emergency_check)

        self.turbo_check = QCheckBox("Turbo دو‌مسیره و FEC (پس از اتصال سرور GameLink)")
        self.turbo_check.setChecked(self.settings.get("turbo_mode", False))
        self.turbo_check.setToolTip("برای جلوگیری از دو IP متفاوت، این قابلیت فقط با سرور مشترک GameLink فعال می‌شود")
        advanced_layout.addWidget(self.turbo_check)
        self.turbo_check.setVisible(ALLOW_GAMELINK)

        self.air_lite_check = QCheckBox("AIR Lite: دنبال‌کردن تغییر مقصد بازی در لحظه")
        self.air_lite_check.setChecked(self.settings.get("air_lite_enabled", True))
        self.air_lite_check.setToolTip("مقصدهای تازه را محلی تشخیص می‌دهد؛ نیاز به ارسال اطلاعات ندارد")
        advanced_layout.addWidget(self.air_lite_check)

        self.game_qos_check = QCheckBox("QoS موقت بازی (DSCP 46؛ بازگشت خودکار)")
        self.game_qos_check.setChecked(self.settings.get("game_qos_enabled", False))
        self.game_qos_check.setToolTip("فقط برای پروسه بازی و ActiveStore ویندوز؛ ممکن است روتر DSCP را نادیده بگیرد")
        advanced_layout.addWidget(self.game_qos_check)

        self.route_dna_check = QCheckBox(
            "★ پیشنهادی برای بهترین اتصال — RouteDNA محلی و شخصی‌سازی مسیر"
        )
        self.route_dna_check.setChecked(self.settings.get("route_dna_enabled", True))
        self.route_dna_check.setToolTip(
            "اثر انگشت شبکه هش می‌شود؛ IP عمومی، نام Wi‑Fi و مقصدهای شخصی ذخیره یا ارسال نمی‌شوند"
        )
        advanced_layout.addWidget(self.route_dna_check)
        dna_row = QHBoxLayout()
        dna_row.addWidget(QLabel("عمق آزمایش RouteDNA:"))
        self.route_dna_mode_combo = QComboBox()
        self.route_dna_mode_combo.addItem("سبک · مناسب بازی و مصرف کم", "light")
        self.route_dna_mode_combo.addItem("استاندارد · بررسی دقیق‌تر", "standard")
        self.route_dna_mode_combo.addItem("دقیق · فقط وقتی شبکه خلوت است", "deep")
        dna_index = self.route_dna_mode_combo.findData(
            self.settings.get("route_dna_probe_mode", "light")
        )
        self.route_dna_mode_combo.setCurrentIndex(max(0, dna_index))
        dna_row.addWidget(self.route_dna_mode_combo, 1)
        advanced_layout.addLayout(dna_row)
        dna_budget_row = QHBoxLayout()
        dna_budget_row.addWidget(QLabel("سقف مصرف روزانه تست‌های RouteDNA:"))
        self.route_dna_budget_spin = QSpinBox()
        self.route_dna_budget_spin.setRange(1, 100)
        self.route_dna_budget_spin.setSuffix(" MB")
        self.route_dna_budget_spin.setValue(
            int(self.settings.get("route_dna_daily_budget_mb", 25))
        )
        self.route_dna_budget_spin.setToolTip(
            "این عدد سقف تخمینی دادهٔ تست‌هاست؛ با پرشدن بودجه، تست سنگین خودکار اجرا نمی‌شود"
        )
        dna_budget_row.addWidget(self.route_dna_budget_spin)
        dna_budget_row.addStretch(1)
        advanced_layout.addLayout(dna_budget_row)
        dna_note = QLabel(
            "<b>با روشن‌بودن چه چیزی بررسی می‌شود؟</b> نوع اتصال، IPv4/IPv6، MTU، "
            "ظرفیت کارت شبکه، فشار لحظه‌ای و نتیجه واقعی تست مسیرها.<br>"
            "<b>چه چیزی نگه‌داری می‌شود؟</b> یک شناسه هش‌شده و ناشناس به‌همراه نتیجه مسیر، "
            "حداکثر ۳۰ روز و فقط روی همین دستگاه.<br>"
            "<b>چه چیزی خوانده یا ارسال نمی‌شود؟</b> IP عمومی، نام Wi‑Fi، تاریخچه مرور، "
            "محتوای ترافیک، حساب کاربری و موقعیت دقیق. ارسال اطلاعات خاموش است.<br>"
            "<b>اثر روشن‌بودن:</b> انتخاب شخصی‌تر و دقیق‌تر، با چند تست کوتاه و مصرف بسیار کم. "
            "هنگام بازی یا ترافیک سنگین خودکار تست سبک اجرا می‌شود.<br>"
            "<b>اگر خاموش باشد:</b> اتصال عادی و تست زنده کار می‌کند، اما حافظه و پیشنهاد "
            "اختصاصی همان شبکه در تصمیم‌گیری استفاده نمی‌شود.<br>"
            "ASN، اپراتور و منطقه فقط با رضایت جداگانه و Backend تنظیم‌شده دریافت می‌شوند."
        )
        dna_note.setWordWrap(True)
        dna_note.setStyleSheet("color:#8FAAB5;")
        advanced_layout.addWidget(dna_note)

        self.route_dna_geo_check = QCheckBox(
            "دریافت اختیاری منطقه، ASN و نام اپراتور از Backend لبه‌ای"
        )
        self.route_dna_geo_check.setChecked(
            self.settings.get("route_dna_remote_geo", False)
        )
        self.route_dna_geo_check.setToolTip(
            "Backend به‌طور طبیعی IP درخواست را می‌بیند، اما LAGSHIFT آن را در Payload، "
            "تاریخچه یا گزارش خطا ذخیره نمی‌کند؛ فقط منطقه تقریبی، ASN و اپراتور برمی‌گردند"
        )
        advanced_layout.addWidget(self.route_dna_geo_check)
        self.route_dna_geo_check.setVisible(ALLOW_REMOTE_BACKEND)
        geo_note = QLabel(
            "رضایت جداگانه و خاموش به‌صورت پیش‌فرض · برای کارکردن، آدرس GameLink باید "
            "تنظیم شده باشد. خاموش‌کردن، درخواست‌های جغرافیایی بعدی را متوقف می‌کند."
        )
        geo_note.setWordWrap(True)
        geo_note.setStyleSheet("color:#7895A1;")
        advanced_layout.addWidget(geo_note)
        geo_note.setVisible(ALLOW_REMOTE_BACKEND)

        dna_test_row = QHBoxLayout()
        self.route_dna_test_btn = QPushButton("اجرای بررسی کامل RouteDNA")
        self.route_dna_test_result = QLabel("هنوز بررسی دستی اجرا نشده است")
        self.route_dna_test_result.setWordWrap(True)
        self.route_dna_test_result.setStyleSheet("color:#8FAAB5;")
        dna_test_row.addWidget(self.route_dna_test_btn)
        dna_test_row.addWidget(self.route_dna_test_result, 1)
        advanced_layout.addLayout(dna_test_row)

        tuning_row = QHBoxLayout()
        tuning_row.addWidget(QLabel("بودجه پینگ مسیر:"))
        self.latency_budget_spin = QSpinBox()
        self.latency_budget_spin.setRange(30, 500)
        self.latency_budget_spin.setSuffix(" ms")
        self.latency_budget_spin.setValue(int(self.settings.get("route_latency_budget_ms", 160)))
        tuning_row.addWidget(self.latency_budget_spin)
        tuning_row.addWidget(QLabel("مسیر آماده:"))
        self.standby_count_spin = QSpinBox()
        self.standby_count_spin.setRange(0, 3)
        self.standby_count_spin.setValue(int(self.settings.get("route_standby_count", 2)))
        tuning_row.addWidget(self.standby_count_spin)
        advanced_layout.addLayout(tuning_row)

        server_features = QLabel(
            "🔒 Multipath هم‌زمان، UDP Redundancy و جابه‌جایی بدون قطع اینترنت: آماده اتصال به GameLink؛ "
            "تا زمان وجود رله واقعی فعال نمایش داده نمی‌شوند."
        )
        server_features.setWordWrap(True)
        server_features.setStyleSheet("color:#FFD180; background:#241D12; border-radius:8px; padding:9px;")
        advanced_layout.addWidget(server_features)
        server_features.setVisible(ALLOW_GAMELINK)

        self.radar_check = QCheckBox("مشارکت کاملاً اختیاری در رادار ناشناس کیفیت مسیر")
        self.radar_check.setChecked(self.settings.get("anonymous_radar", False))
        self.radar_check.setToolTip(
            "فقط امتیاز، پینگ، جیتر، پکت‌لاس، نوع مسیر، سیستم‌عامل و بازهٔ ساعت؛ "
            "بدون IP، نام شبکه، دامنه، آدرس سرور، شناسه دستگاه یا حساب کاربری"
        )
        advanced_layout.addWidget(self.radar_check)
        self.radar_check.setVisible(ALLOW_REMOTE_BACKEND)
        radar_note = QLabel(
            "خاموش به‌صورت پیش‌فرض · روشن‌کردن این گزینه فقط پس از تنظیم سرور GameLink، "
            "نمونه‌های تجمیعی بالا را ارسال می‌کند؛ خاموش‌کردن آن فوراً ارسال را متوقف می‌کند."
        )
        radar_note.setWordWrap(True)
        radar_note.setStyleSheet("color:#7895A1;")
        advanced_layout.addWidget(radar_note)
        radar_note.setVisible(ALLOW_REMOTE_BACKEND)

        gamelink_label = QLabel("آدرس سرور GameLink (وقتی زیرساخت آماده شد):")
        advanced_layout.addWidget(gamelink_label)
        self.gamelink_url_input = QLineEdit(self.settings.get("gamelink_api_url", ""))
        self.gamelink_url_input.setPlaceholderText("https://api.example.com")
        advanced_layout.addWidget(self.gamelink_url_input)
        gamelink_label.setVisible(ALLOW_GAMELINK)
        self.gamelink_url_input.setVisible(ALLOW_GAMELINK)
        self.network_advanced_frame.hide()
        layout.addWidget(self.network_advanced_frame)

        self.safe_report_btn = QPushButton("🧰 ساخت گزارش امن برای پشتیبانی")
        layout.addWidget(self.safe_report_btn)

        blackbox_card = QFrame()
        blackbox_card.setObjectName("homeStat")
        blackbox_layout = QVBoxLayout(blackbox_card)
        blackbox_layout.setContentsMargins(14, 12, 14, 12)
        blackbox_title = QLabel("جعبه‌سیاه و بازیابی خطا")
        blackbox_title.setStyleSheet("font-weight:bold; color:#CFF7FF;")
        blackbox_layout.addWidget(blackbox_title)
        blackbox_note = QLabel(
            "خطا و آخرین مراحل فنی فقط روی همین دستگاه نگه‌داری می‌شوند. "
            "هیچ گزارشی بدون انتخاب تو ارسال نمی‌شود."
        )
        blackbox_note.setWordWrap(True)
        blackbox_note.setStyleSheet("color:#8FAAB5;")
        blackbox_layout.addWidget(blackbox_note)
        self.blackbox_check = QCheckBox("ثبت محلی خطا و تشخیص هنگ روشن باشد")
        self.blackbox_check.setChecked(self.settings.get("blackbox_enabled", True))
        blackbox_layout.addWidget(self.blackbox_check)
        self.blackbox_status_label = QLabel()
        self.blackbox_status_label.setStyleSheet("color:#79EDB5;")
        blackbox_layout.addWidget(self.blackbox_status_label)
        blackbox_actions = QHBoxLayout()
        self.blackbox_export_btn = QPushButton("ساخت فایل برای ارسال دستی")
        self.blackbox_clear_btn = QPushButton("پاک‌کردن گزارش‌های محلی")
        blackbox_actions.addWidget(self.blackbox_export_btn)
        blackbox_actions.addWidget(self.blackbox_clear_btn)
        blackbox_layout.addLayout(blackbox_actions)
        layout.addWidget(blackbox_card)
        self._refresh_blackbox_status()

        security_card = QFrame()
        security_card.setObjectName("homeStat")
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(14, 12, 14, 12)
        security_title = QLabel("🛡 سپر امنیت و بازیابی")
        security_title.setStyleSheet("font-weight:bold; color:#CFF7FF;")
        security_layout.addWidget(security_title)
        self.security_status_label = QLabel(
            "سلامت فایل‌های بسته، امضای ناشر، اعتماد آپدیت و وضعیت بازیابی DNS را بررسی کن."
        )
        self.security_status_label.setWordWrap(True)
        self.security_status_label.setStyleSheet("color:#8FAAB5;")
        security_layout.addWidget(self.security_status_label)
        security_actions = QGridLayout()
        self.security_quick_btn = QPushButton("بررسی سریع امنیت")
        self.security_full_btn = QPushButton("بررسی کامل همه فایل‌ها")
        self.emergency_reset_btn = QPushButton("بازگردانی اضطراری شبکه")
        self.recovery_receipt_btn = QPushButton("رسید بازیابی")
        self.emergency_reset_btn.setStyleSheet(
            "border-color:#A45151; color:#FFD4D4;"
        )
        security_actions.addWidget(self.security_quick_btn, 0, 0)
        security_actions.addWidget(self.security_full_btn, 0, 1)
        security_actions.addWidget(self.recovery_receipt_btn, 1, 0)
        security_actions.addWidget(self.emergency_reset_btn, 1, 1)
        security_layout.addLayout(security_actions)
        layout.addWidget(security_card)

        update_card = QFrame()
        update_card.setObjectName("homeStat")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(14, 12, 14, 12)
        update_layout.addWidget(QLabel("آپدیت امن LAGSHIFT"))
        self.auto_update_check = QCheckBox("بررسی خودکار و بی‌صدا هنگام شروع برنامه")
        self.auto_update_check.setChecked(self.settings.get("automatic_update_checks", True))
        update_layout.addWidget(self.auto_update_check)
        update_channel_row = QHBoxLayout()
        update_channel_row.addWidget(QLabel("کانال انتشار:"))
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItem("پایدار · پیشنهادشده", "stable")
        self.update_channel_combo.addItem("آزمایشی · دریافت زودتر قابلیت‌ها", "beta")
        selected_channel = self.update_channel_combo.findData(
            self.settings.get("update_channel", "stable")
        )
        self.update_channel_combo.setCurrentIndex(max(0, selected_channel))
        update_channel_row.addWidget(self.update_channel_combo, 1)
        update_layout.addLayout(update_channel_row)
        self.update_status_label = QLabel(
            f"نسخه نصب‌شده: {APP_VERSION} · کانال "
            f"{'پایدار' if self.settings.get('update_channel', 'stable') == 'stable' else 'آزمایشی'}"
        )
        self.update_status_label.setWordWrap(True)
        self.update_status_label.setStyleSheet("color:#9FC2D0;")
        update_layout.addWidget(self.update_status_label)
        update_actions = QHBoxLayout()
        self.check_update_btn = QPushButton("🔄 بررسی آپدیت")
        self.download_update_btn = QPushButton("⬇ دریافت نسخه تأییدشده")
        self.download_update_btn.setObjectName("primary")
        self.download_update_btn.hide()
        update_actions.addWidget(self.check_update_btn)
        update_actions.addWidget(self.download_update_btn)
        update_layout.addLayout(update_actions)
        layout.addWidget(update_card)

        product_card = QFrame()
        product_card.setObjectName("homeStat")
        product_layout = QVBoxLayout(product_card)
        product_layout.setContentsMargins(14, 12, 14, 12)
        product_layout.addWidget(QLabel("درباره و شفافیت محصول"))
        product_actions = QHBoxLayout()
        self.terms_review_btn = QPushButton("📜 شرایط استفاده و حریم خصوصی")
        self.about_btn = QPushButton("ℹ درباره LAGSHIFT")
        product_actions.addWidget(self.terms_review_btn)
        product_actions.addWidget(self.about_btn)
        product_layout.addLayout(product_actions)
        layout.addWidget(product_card)

        layout.addStretch()
        return tab

    def _build_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("LAGSHIFT — لگ‌شیفت")

        menu = QMenu()
        show_action = QAction("نمایش برنامه", self)
        show_action.triggered.connect(self._restore_from_tray)
        quit_action = QAction("خروج کامل", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    # ---------------- سیگنال‌ها ----------------

    def _connect_signals(self):
        self.vm.adapters_changed.connect(self._on_adapters_changed)
        self.vm.status_message.connect(self._on_status_message)
        self.vm.games_changed.connect(self._render_games)
        self.vm.kill_switch_triggered.connect(self._on_kill_switch_triggered)
        self.vm.busy_changed.connect(self._on_busy_changed)
        self.vm.connection_changed.connect(self._on_connection_changed)
        self.vm.dns_benchmark_progress.connect(self._on_dns_benchmark_progress)
        self.vm.dns_quality_ready.connect(self._on_dns_quality_ready)
        self.vm.tunnel_configs_changed.connect(self._render_tunnel_configs)
        self.vm.tunnel_status_changed.connect(self._on_tunnel_status_changed)
        self.vm.tunnel_busy_changed.connect(self._on_tunnel_busy_changed)
        self.vm.ping_result_ready.connect(self._on_ping_result)
        self.vm.game_detected.connect(self._on_game_detected)
        self.vm.game_candidate_detected.connect(self._on_game_candidate_detected)
        self.vm.game_optimization_progress.connect(self._on_game_optimization_progress)
        self.vm.game_runtime_changed.connect(self._on_game_runtime_changed)
        self.vm.game_session_report_ready.connect(self._on_game_session_report_ready)
        self.vm.optimization_state_changed.connect(self._on_optimization_state_changed)
        self.vm.game_server_probe_ready.connect(self._on_game_server_probe_ready)
        self.vm.game_route_profile_ready.connect(self._on_game_route_profile_ready)
        self.vm.network_lab_ready.connect(self._on_network_lab_ready)
        self.vm.network_monitor_ready.connect(self._on_network_monitor_ready)
        self.vm.air_profile_updated.connect(self._on_air_profile_updated)
        self.vm.usage_updated.connect(self._on_usage_updated)
        self.vm.live_ping_ready.connect(self._on_live_ping)
        self.vm.speed_test_ready.connect(self._on_speed_test_ready)
        self.vm.route_dna_diagnostic_ready.connect(self._on_route_dna_diagnostic_ready)
        self.vm.security_audit_ready.connect(self._on_security_audit_ready)
        self.vm.emergency_reset_ready.connect(self._on_emergency_reset_ready)
        self.vm.warp_busy_changed.connect(self._on_warp_busy_changed)
        self.vm.warp_state_changed.connect(self._on_warp_state_changed)
        self.vm.route_quality_ready.connect(self._on_route_quality_ready)
        self.vm.failover_changed.connect(self._on_failover_changed)
        self.vm.trial_ready.connect(self._on_trial_ready)
        self.vm.diagnostic_report_ready.connect(self._on_diagnostic_report_ready)
        self.vm.traffic_usage_updated.connect(self._on_traffic_usage_updated)
        self.vm.update_check_ready.connect(self._on_update_check_ready)
        self.vm.update_download_ready.connect(self._on_update_download_ready)

        self.refresh_btn.clicked.connect(self.vm.refresh_adapters)
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        self.switch_dns_btn.clicked.connect(self._on_switch_dns_clicked)
        self.profile_list.itemDoubleClicked.connect(
            lambda _item: self._on_switch_dns_clicked() if self.vm.is_connected else None
        )
        self.dns_retest_btn.clicked.connect(self._on_retest_dns_clicked)
        self.dns_explain_btn.clicked.connect(self._show_dns_explanation)
        self.dns_goal_combo.currentIndexChanged.connect(
            lambda: self._set_setting(
                "dns_usage_goal", self.dns_goal_combo.currentData() or "balanced"
            )
        )
        self.dns_preference_combo.currentIndexChanged.connect(
            lambda: self._set_setting(
                "dns_selection_mode", self.dns_preference_combo.currentData() or "balanced"
            )
        )
        self.kill_switch_check.toggled.connect(self.vm.set_kill_switch_enabled)

        self.add_game_btn.clicked.connect(self._on_add_game_clicked)
        self.remove_game_btn.clicked.connect(self._on_remove_game_clicked)
        self.set_game_profile_btn.clicked.connect(self._on_set_game_profile_clicked)
        self.quick_game_action_btn.clicked.connect(self._on_quick_game_action)
        self.game_advanced_toggle.toggled.connect(self._toggle_game_advanced)
        self.game_manage_toggle.toggled.connect(self._toggle_game_manage)
        self.learn_game_route_btn.clicked.connect(self._on_learn_game_route_clicked)
        self.clear_game_route_btn.clicked.connect(self._on_clear_game_route_clicked)
        self.export_game_route_btn.clicked.connect(self._on_export_game_route_clicked)
        self.import_game_route_btn.clicked.connect(self._on_import_game_route_clicked)
        self.route_auto_rollback_check.toggled.connect(
            lambda value: self._set_setting("route_auto_rollback", value)
        )
        self.games_list.currentItemChanged.connect(self._on_game_selection_changed)
        self.game_probe_baseline_btn.clicked.connect(
            lambda: self._start_game_server_probe("baseline")
        )
        self.game_probe_compare_btn.clicked.connect(
            lambda: self._start_game_server_probe("current")
        )
        self.game_detection_check.toggled.connect(self._on_game_detection_setting_changed)

        self.import_tunnel_btn.clicked.connect(self._on_import_tunnel_clicked)
        self.remove_tunnel_btn.clicked.connect(self._on_remove_tunnel_clicked)
        self.ping_test_btn.clicked.connect(self._on_ping_test_clicked)
        self.trial_btn.clicked.connect(self._on_trial_clicked)
        self.tunnel_toggle_btn.clicked.connect(self._on_tunnel_toggle_clicked)
        self.warp_btn.clicked.connect(self._on_warp_clicked)
        self.warp_refresh_btn.clicked.connect(self.vm.refresh_official_warp_status)
        self.warp_install_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(official_warp_service.DOWNLOAD_URL))
        )
        self.rate_config_btn.clicked.connect(self._on_rate_config_clicked)
        self.speed_test_btn.clicked.connect(self.vm.run_speed_comparison)

        self.tray_check.toggled.connect(self._on_tray_setting_changed)
        self.autostart_check.toggled.connect(self.vm.set_autostart_enabled)
        self.overlay_check.toggled.connect(self._on_overlay_setting_changed)
        self.failover_check.toggled.connect(
            lambda value: self._set_setting("auto_failover", value)
        )
        self.emergency_check.toggled.connect(
            lambda value: self._set_setting("emergency_mode", value)
        )
        self.turbo_check.toggled.connect(self._on_turbo_setting_changed)
        self.air_lite_check.toggled.connect(
            lambda value: self._set_setting("air_lite_enabled", value)
        )
        self.game_qos_check.toggled.connect(
            lambda value: self._set_setting("game_qos_enabled", value)
        )
        self.route_dna_check.toggled.connect(
            lambda value: self._set_setting("route_dna_enabled", value)
        )
        self.route_dna_mode_combo.currentIndexChanged.connect(
            lambda _index: self._set_setting(
                "route_dna_probe_mode", self.route_dna_mode_combo.currentData()
            )
        )
        self.route_dna_budget_spin.valueChanged.connect(
            lambda value: self._set_setting("route_dna_daily_budget_mb", value)
        )
        self.route_dna_geo_check.toggled.connect(self._on_route_dna_geo_toggled)
        self.route_dna_test_btn.clicked.connect(self._run_route_dna_diagnostic)
        self.latency_budget_spin.valueChanged.connect(
            lambda value: self._set_setting("route_latency_budget_ms", value)
        )
        self.standby_count_spin.valueChanged.connect(
            lambda value: self._set_setting("route_standby_count", value)
        )
        self.radar_check.toggled.connect(
            lambda value: self._set_setting("anonymous_radar", value)
        )
        self.gamelink_url_input.editingFinished.connect(
            lambda: self._set_setting("gamelink_api_url", self.gamelink_url_input.text().strip())
        )
        self.safe_report_btn.clicked.connect(self.vm.create_safe_report)
        self.blackbox_check.toggled.connect(self._on_blackbox_toggled)
        self.blackbox_export_btn.clicked.connect(self._export_blackbox_reports)
        self.blackbox_clear_btn.clicked.connect(self._clear_blackbox_reports)
        self.security_quick_btn.clicked.connect(lambda: self._start_security_audit(False))
        self.security_full_btn.clicked.connect(lambda: self._start_security_audit(True))
        self.emergency_reset_btn.clicked.connect(self._confirm_emergency_reset)
        self.recovery_receipt_btn.clicked.connect(self._show_recovery_receipt)
        self.auto_update_check.toggled.connect(
            lambda value: self._set_setting("automatic_update_checks", value)
        )
        self.update_channel_combo.currentIndexChanged.connect(
            self._on_update_channel_changed
        )
        self.check_update_btn.clicked.connect(lambda: self._start_update_check(True))
        self.download_update_btn.clicked.connect(self._download_pending_update)
        self.terms_review_btn.clicked.connect(
            lambda: TermsDialog(self, review_only=True).exec()
        )
        self.about_btn.clicked.connect(self._show_about)
        self.network_advanced_toggle.toggled.connect(self.network_advanced_frame.setVisible)
        self.home_primary_btn.clicked.connect(self._on_home_primary)
        self.home_games_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.games_tab))
        self.home_dns_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.dns_tab))
        self.home_tunnel_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.tunnel_tab))
        self.reduce_motion_check.toggled.connect(self._on_reduce_motion_changed)
        self.startup_animation_check.toggled.connect(
            lambda value: self._set_setting("startup_animation_enabled", value)
        )

    def _on_home_primary(self):
        if self._pending_game_payload:
            self._on_review_pending_game()
            return
        game = self._selected_or_running_game()
        if game:
            self.tabs.setCurrentWidget(self.games_tab)
            self._show_game_optimizer(game=game)
            return
        self.tabs.setCurrentWidget(self.games_tab)
        self.banner.show_message("بازی را اجرا کن یا از فهرست انتخابش کن", "info")

    def _show_about(self):
        edition_name = "نسخه عمومی" if EDITION == "public" else "نسخه توسعه‌دهنده"
        publisher = LEGAL_PUBLISHER_NAME or BRAND_PUBLISHER
        support = SUPPORT_EMAIL or SUPPORT_URL or "راه ارتباط عمومی هنوز تعیین نشده"
        QMessageBox.information(
            self,
            "درباره LAGSHIFT",
            "LAGSHIFT — مسیر هوشمندتر برای بازی روان‌تر\n\n"
            f"نسخه {APP_VERSION} · ساخت {BUILD_NUMBER}\n"
            f"{edition_name}\n\n"
            f"ناشر: {publisher}\n"
            f"پشتیبانی: {support}\n\n"
            "محصول مستقل بررسی و بهینه‌سازی اتصال بازی‌ها و برنامه‌های پشتیبانی‌شده.\n"
            "LAGSHIFT سرویس VPN عمومی نیست و کاهش قطعی پینگ را تضمین نمی‌کند.\n\n"
            f"شرایط استفاده {TERMS_VERSION} · حریم خصوصی {PRIVACY_VERSION}\n"
            "گزارش اختیاری و اطلاعات جغرافیایی به‌صورت پیش‌فرض خاموش‌اند.\n\n"
            "LAGSHIFT by OMNIARC\n"
            "© 2026 OMNIARC. تمامی حقوق محفوظ است.\n"
            "Privacy، Security، SBOM و مجوز اجزای متن‌باز همراه بسته نصب هستند.",
        )

    def _start_security_audit(self, full: bool):
        self.security_quick_btn.setEnabled(False)
        self.security_full_btn.setEnabled(False)
        self.security_status_label.setText(
            "در حال تطبیق همه فایل‌ها…" if full else "در حال بررسی فایل‌های حیاتی…"
        )
        self.vm.run_security_audit(full)

    def _on_security_audit_ready(self, report: dict):
        self.security_quick_btn.setEnabled(True)
        self.security_full_btn.setEnabled(True)
        integrity = report.get("integrity") or {}
        if report.get("development_mode"):
            integrity_text = "حالت توسعه؛ کاتالوگ بسته پس از Build ساخته می‌شود"
        elif not integrity.get("available"):
            integrity_text = "کاتالوگ سلامت پیدا نشد"
        elif integrity.get("healthy"):
            integrity_text = (
                f"{integrity.get('checked', 0)} فایل بررسی شد و تغییری دیده نشد"
            )
        else:
            integrity_text = (
                f"هشدار: {len(integrity.get('failures') or [])} فایل ناسازگار است"
            )
        publisher = "امضای ناشر معتبر است" if report.get("publisher_signed") else (
            "نسخه فعلی هنوز امضای ناشر ندارد"
        )
        updater = "اعتماد آپدیت تنظیم شده" if report.get("update_trust_configured") else (
            "کانال تولیدی آپدیت هنوز تنظیم نشده"
        )
        acl = report.get("package_acl") or {}
        acl_text = (
            "دسترسی فایل‌های نصب محدود است" if acl.get("safe")
            else "حالت توسعه؛ ACL بسته پس از نصب بررسی می‌شود" if not acl.get("available")
            else "هشدار: کاربران عادی اجازه نوشتن در پوشه برنامه دارند"
        )
        pending = report.get("pending_recovery") or {}
        pending_kinds = []
        if report.get("pending_dns_restore") or pending.get("pending_dns"):
            pending_kinds.append("DNS")
        if pending.get("pending_qos"):
            pending_kinds.append("QoS")
        if pending.get("pending_warp"):
            pending_kinds.append("WARP")
        recovery = (
            f"بازیابی {'، '.join(pending_kinds)} در انتظار است"
            if pending_kinds else "تغییر شبکه بازیابی‌نشده‌ای وجود ندارد"
        )
        hijack = report.get("dns_hijack")
        if not hijack:
            dns_security = "برای تست دستکاری DNS ابتدا یک پروفایل را وصل کن"
        elif hijack.get("hijacked"):
            dns_security = "هشدار: پاسخ مصنوعی DNS مشاهده شد"
        elif hijack.get("conclusive"):
            dns_security = "تست ضد دستکاری DNS سالم است"
        else:
            dns_security = "تست دستکاری DNS قطعی نبود"
        doh = report.get("doh_policy")
        doh_text = (
            " · DoH بدون Downgrade تأیید شد" if doh and doh.get("no_downgrade")
            else " · سیاست No-Downgrade تأیید نشد" if doh else ""
        )
        scope = report.get("internet_scope") or {}
        scope_text = f"\n{scope.get('message')}" if scope.get("message") else ""
        ipv6 = report.get("ipv6_exposure") or {}
        ipv6_text = f"\n{ipv6.get('message')}" if ipv6.get("message") else ""
        self.security_status_label.setText(
            f"{integrity_text}\n{publisher} · {updater} · {recovery}\n{acl_text}\n"
            f"{dns_security}{doh_text}{scope_text}{ipv6_text}\n"
            "کاتالوگ هش تا زمان Code Signing ریشه اعتماد انتشار محسوب نمی‌شود."
        )
        level = "success" if (
            integrity.get("healthy") and report.get("publisher_signed")
            and report.get("update_trust_configured")
        ) else "info"
        self.banner.show_message("بررسی سپر امنیت کامل شد", level, 5000)

    def _confirm_emergency_reset(self):
        answer = QMessageBox.question(
            self, "بازگردانی اضطراری شبکه",
            "DNS قبلی و تمام QoSهای موقت متعلق به LAGSHIFT بازگردانده شوند؟\n"
            "این عملیات به تنظیمات برنامه‌های دیگر دست نمی‌زند و یک‌بار اجازه ویندوز می‌خواهد.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.emergency_reset_btn.setEnabled(False)
        self.security_status_label.setText("در حال اجرای دستور بازیابی محدود…")
        self.vm.emergency_network_reset()

    def _on_emergency_reset_ready(self, ok: bool, message: str):
        self.emergency_reset_btn.setEnabled(True)
        self.security_status_label.setText(message)
        self.banner.show_message(message, "success" if ok else "error", 7000)

    def _show_recovery_receipt(self):
        receipt = recovery_service.receipt(12)
        labels = {
            "dns-change": "تغییر DNS", "dns-restore": "بازگردانی DNS",
            "qos-change": "اعمال QoS", "qos-restore": "پاک‌سازی QoS",
            "warp-connect": "اتصال WARP", "warp-restore": "بازگردانی WARP",
            "emergency-reset": "بازیابی اضطراری",
        }
        outcomes = {
            "started": "شروع شد", "success": "موفق", "failed": "ناموفق",
            "partial": "نیمه‌کامل",
        }
        rows = []
        for event in receipt.get("events") or []:
            when = str(event.get("at", "")).replace("T", " ").replace("+00:00", " UTC")
            rows.append(
                f"{when} — {labels.get(event.get('action'), 'رویداد')} — "
                f"{outcomes.get(event.get('outcome'), 'نامشخص')}"
            )
        text = "\n".join(rows) if rows else "هنوز رویداد بازیابی ثبت نشده است."
        text += (
            "\n\nوضعیت: بازگردانی DNS لازم است."
            if receipt.get("pending_dns") else "\n\nوضعیت: تغییر DNS بازیابی‌نشده‌ای ثبت نشده است."
        )
        if receipt.get("pending_qos"):
            text += "\nوضعیت: پاک‌سازی QoS موقت لازم است."
        if receipt.get("pending_warp"):
            text += "\nوضعیت: بازگردانی نشست WARP متعلق به LAGSHIFT لازم است."
        text += "\nنام شبکه، IP، مقصد و اطلاعات حساب در این رسید ذخیره نمی‌شوند."
        QMessageBox.information(self, "رسید بازیابی LAGSHIFT", text)

    def _start_update_check(self, manual: bool):
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("در حال بررسی امضا...")
        self.update_status_label.setText("در حال بررسی کانال امن انتشار…")
        self.vm.check_for_updates(manual=manual)

    def _on_update_channel_changed(self):
        channel = self.update_channel_combo.currentData() or "stable"
        self._set_setting("update_channel", channel)
        label = "پایدار" if channel == "stable" else "آزمایشی"
        self.update_status_label.setText(
            f"نسخه نصب‌شده: {APP_VERSION} · کانال {label} · هنوز بررسی نشده"
        )

    def _on_update_check_ready(self, result: dict):
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("🔄 بررسی آپدیت")
        self.update_status_label.setText(result.get("message", "نتیجه‌ای دریافت نشد"))
        self._pending_update_manifest = result.get("manifest") or {}
        self.download_update_btn.setVisible(bool(result.get("available")))
        if result.get("available"):
            self.banner.show_message(result["message"], "success", 7000)
        elif result.get("manual"):
            level = "info" if not result.get("configured") else "error"
            self.banner.show_message(result.get("message", "بررسی ناموفق بود"), level, 6500)

    def _download_pending_update(self):
        manifest = getattr(self, "_pending_update_manifest", {})
        if not manifest:
            return
        self.download_update_btn.setEnabled(False)
        self.download_update_btn.setText("در حال دریافت و تطبیق هش…")
        self.vm.download_update(manifest)

    def _on_update_download_ready(self, path: str, error: str):
        self.download_update_btn.setEnabled(True)
        self.download_update_btn.setText("⬇ دریافت نسخه تأییدشده")
        if error or not path:
            self.banner.show_message(f"دانلود امن متوقف شد: {error}", "error", 7000)
            return
        answer = QMessageBox.question(
            self, "آپدیت آماده نصب است",
            "فایل با هش و امضای مانیفست تأیید شد. اکنون امضای ناشر ویندوز "
            "بررسی و نصب‌کننده اجرا شود؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            self.update_status_label.setText("آپدیت دانلود و برای نصب بعدی نگهداری شد")
            return
        ok, message = self.vm.install_downloaded_update(path)
        self.banner.show_message(message, "success" if ok else "error", 7000)

    def play_startup_reveal(self):
        """Brief staggered hand-off from the Route Prism splash into the real UI."""
        if self.settings.get("reduce_motion", False):
            return
        self.brand_mark.play_once()
        self._startup_panel_animations = []
        for widget, delay, duration in (
            (self.header_frame, 0, 260),
            (self.banner, 65, 280),
            (self.tabs, 125, 340),
        ):
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(duration)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self._startup_panel_animations.append((effect, animation))
            QTimer.singleShot(delay, animation.start)

        def release_effects():
            for widget in (self.header_frame, self.banner, self.tabs):
                widget.setGraphicsEffect(None)
            self._startup_panel_animations = []

        QTimer.singleShot(560, release_effects)

    def _set_home_state(self, state: str, title: str, detail: str, step: int | None = None):
        if not hasattr(self, "home_orb"):
            return
        self.home_orb.set_state(state)
        self.home_state_title.setText(title)
        self.home_state_copy.setText(detail)
        if step is None:
            step = {"idle": -1, "detected": 0, "testing": 1, "connected": 3, "error": 2}.get(state, -1)
        for index, label in enumerate(self.home_steps):
            if index < step:
                style = "color:#79F2BE; background:#0B241E; border-radius:8px; padding:6px 5px;"
                prefix = "✓ "
            elif index == step:
                style = "color:#071014; background:#65E5FF; border-radius:8px; padding:6px 5px; font-weight:bold;"
                prefix = "● "
            else:
                style = "color:#607985; background:#0A161D; border-radius:8px; padding:6px 5px;"
                prefix = ""
            base = ("شناسایی", "بررسی", "انتخاب مسیر", "آماده")[index]
            label.setText(f"{prefix}{index + 1} {base}")
            label.setStyleSheet(style)

    def _on_reduce_motion_changed(self, checked: bool):
        self._set_setting("reduce_motion", checked)
        self.home_orb.set_reduce_motion(checked)
        self.brand_mark.set_reduce_motion(checked)
        self.banner.set_reduce_motion(checked)

    def _on_adapters_changed(self, adapters):
        self.adapter_combo.clear()
        for a in adapters:
            self.adapter_combo.addItem(a.name, userData=a)
        self.apps_tab.set_adapters(adapters)

    @staticmethod
    def _dns_profile_text(profile, include_address: bool = True) -> str:
        if profile.region == "iran":
            badge = "🇮🇷 رفع تحریم"
        else:
            badge = "🌍 جهانی"
        address = f"   ·   {profile.primary}" if include_address else ""
        return f"{badge}   |   {profile.name}{address}"

    @staticmethod
    def _style_dns_profile_item(item, profile):
        color = "#FFD180" if profile.region == "iran" else "#81D4FA"
        item.setForeground(QColor(color))
        group = "ایرانی · تخصصی رفع تحریم" if profile.region == "iran" else "جهانی · عمومی"
        item.setToolTip(f"{group}\n{profile.description}")

    def _on_switch_dns_clicked(self):
        if not self.vm.is_connected:
            self.banner.show_message("ابتدا یک اتصال DNS برقرار کن", "info")
            return
        adapter_name = self.vm.active_adapter_name
        profile_item = self.profile_list.currentItem()
        if not adapter_name or not profile_item:
            self.banner.show_message("یک DNS از لیست انتخاب کن", "error")
            return
        profile = profile_item.data(Qt.UserRole)
        if profile is None:
            self.vm.apply_best_dns(
                adapter_name, self.dns_preference_combo.currentData() or "balanced",
                self.dns_goal_combo.currentData() or "balanced",
            )
            return
        if profile.name == self.vm.active_profile_name:
            self.banner.show_message("همین DNS الان فعال است؛ برای ارزیابی تازه، تست هوشمند مجدد را بزن", "info")
            return
        self.vm.apply_dns_profile(
            adapter_name, profile.name, profile.primary, profile.secondary, profile.doh_url
        )

    def _on_toggle_clicked(self):
        if self.vm.is_connected:
            self.vm.disconnect_dns()
            return
        adapter = self.adapter_combo.currentData()
        profile_item = self.profile_list.currentItem()
        if not adapter or not profile_item:
            self.banner.show_message("یک آداپتور و یک سرور DNS انتخاب کن", "error")
            return
        profile = profile_item.data(Qt.UserRole)
        if profile is None:
            self.vm.apply_best_dns(
                adapter.name, self.dns_preference_combo.currentData() or "balanced",
                self.dns_goal_combo.currentData() or "balanced",
            )
            return
        self.vm.apply_dns_profile(
            adapter.name, profile.name, profile.primary, profile.secondary, profile.doh_url
        )

    def _on_busy_changed(self, busy: bool):
        # جلوگیری از کلیک مکرر که باعث کرش می‌شد
        self.brand_mark.set_busy(busy)
        self.toggle_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.dns_preference_combo.setEnabled(not busy)
        self.dns_goal_combo.setEnabled(not busy)
        self.dns_retest_btn.setEnabled(not busy and self.vm.is_connected)
        self.switch_dns_btn.setEnabled(not busy and self.vm.is_connected)
        if busy:
            self.toggle_btn.setText("در حال اتصال...")
        else:
            self.toggle_btn.setText("قطع اتصال" if self.vm.is_connected else "اتصال")

    def _on_connection_changed(self, connected: bool, label: str):
        if connected:
            self.connection_badge.setText(f"🟢 وصل به {label}")
            self.connection_badge.setStyleSheet(
                "color:#79F2BE; font-weight:bold; background:#0B201B;"
                "border:1px solid #216B52; border-radius:12px; padding:8px 12px;"
            )
            self.home_dns_value.setText(label)
            self.toggle_btn.setText("قطع اتصال")
            self.toggle_btn.setObjectName("connected")
            self.dns_retest_btn.setEnabled(True)
            self.switch_dns_btn.setEnabled(True)
            source = (
                f"برای بازی «{self._optimized_game_name}»" if self._optimized_game_name else "به‌صورت دستی"
            )
            self.dns_state_label.setText(
                f"🟢 DNS فعال: {label}\nمنبع تغییر: {source}\n"
                "اثر: بهبود Resolve و دسترسی دامنه‌ها؛ DNS به‌تنهایی مسیر پکت‌های بازی را کوتاه نمی‌کند."
            )
            if not self._running_game_name:
                self._set_home_state(
                    "connected", "DNS هوشمند فعال است",
                    "نتیجهٔ چندمرحله‌ای DNS روی کیلومترشمار نمایش داده می‌شود.", 3,
                )
            for row in range(self.profile_list.count()):
                item = self.profile_list.item(row)
                profile = item.data(Qt.UserRole)
                if profile and label.startswith(profile.name):
                    self.profile_list.setCurrentRow(row)
                    break
            self._schedule_safety_gate_probe()
        else:
            self.connection_badge.setText("⭕ قطع")
            self.connection_badge.setStyleSheet(
                "color:#A9BAC4; font-weight:bold; background:#0A151C;"
                "border:1px solid #203944; border-radius:12px; padding:8px 12px;"
            )
            self.home_dns_value.setText("بدون تغییر")
            self.toggle_btn.setText("اتصال")
            self.toggle_btn.setObjectName("primary")
            self.dns_retest_btn.setEnabled(False)
            self.switch_dns_btn.setEnabled(False)
            self.dns_state_label.setText("وضعیت DNS: تغییری توسط برنامه اعمال نشده")
            self._reset_dns_quality_display()
            if not self.vm.tunnel_connected and not self._running_game_name:
                self._set_home_state("idle", "آمادهٔ شناسایی", "هیچ بهینه‌سازی فعالی وجود ندارد.", -1)
        # برای اینکه تغییر QSS بر اساس objectName جدید واقعاً اعمال بشه
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)
        self._animate_badge()

    def _on_dns_benchmark_progress(self, progress: dict):
        completed = int(progress.get("completed", 0))
        total = int(progress.get("total", len(self.vm.dns_profiles)))
        self.dns_benchmark_bar.setRange(0, max(1, total))
        self.dns_benchmark_bar.setValue(completed)
        if completed == 0:
            self._reset_dns_quality_display(
                "تست قبلی پاک شد؛ در حال ساخت امتیاز تازه…",
                reset_selection=False,
            )
            self.dns_benchmark_bar.setRange(0, max(1, total))
            self.dns_benchmark_bar.setValue(0)
        self.dns_score_big.setText(f"{completed} / {total}")
        self.toggle_btn.setText("🧠 در حال تحلیل DNSها…")
        if completed == 0:
            self.dns_benchmark_status.setText(
                "🔥 گرم‌کردن کش، ارسال چندین پرس‌وجو به ۵ دامنه و بررسی DNS پشتیبان/DoH…"
            )
        else:
            self.dns_benchmark_status.setText(
                f"🔍 «{progress.get('name', 'DNS')}» تحلیل شد · در حال سنجش بقیه…"
            )

    def _on_dns_quality_ready(self, result: dict):
        if result.get("error"):
            self._latest_dns_quality = {}
            self.dns_explain_btn.setEnabled(False)
            self.dns_score_big.setText("×")
            self.dns_score_big.setStyleSheet("font-size:36px; font-weight:bold; color:#EF5350;")
            self.dns_score_title.setText("هیچ DNS سالمی پیدا نشد")
            self.dns_score_title.setStyleSheet("font-size:16px; font-weight:bold; color:#EF5350;")
            self.dns_score_metrics.setText(result["error"])
            self.dns_benchmark_bar.setRange(0, 100)
            self.dns_benchmark_bar.setValue(0)
            self.dns_benchmark_status.setText(
                "اتصالی اعمال نشد؛ مسیر قبلی سیستم حفظ شد."
            )
            return
        self._latest_dns_quality = dict(result)
        self.dns_explain_btn.setEnabled(True)
        score = int(result.get("score", 0))
        color = "#66BB6A" if score >= 85 else "#4FC3F7" if score >= 70 else "#FFB74D" if score >= 50 else "#EF5350"
        self.dns_score_big.setText(f"{score} / 100")
        self.dns_score_big.setStyleSheet(
            f"font-size:29px; font-weight:bold; color:{color};"
        )
        doh = (
            f"DoH {'سالم' if result.get('doh_ok') else 'در این شبکه ناموفق'}"
            if result.get("doh_supported") else "DoH ندارد"
        )
        secondary = "پشتیبان سالم" if result.get("secondary_ok") else "پشتیبان ناپایدار"
        preference_labels = {
            "balanced": "انتخاب متعادل", "fastest": "سریع‌ترین پاسخ",
            "stable": "پایدارترین مسیر",
        }
        preference_label = preference_labels.get(result.get("preference", "balanced"), "تحلیل اختصاصی")
        goal_labels = {
            "anti_sanction": "رفع تحریم", "speed": "سرعت وب و CDN",
            "balanced": "ترکیبی",
        }
        goal_label = goal_labels.get(result.get("goal", "balanced"), "ترکیبی")
        self.dns_score_title.setText(
            f"🏆 {result.get('name')} · {result.get('label')} · {goal_label} · {preference_label}"
        )
        self.dns_score_title.setStyleSheet(f"font-size:16px; font-weight:bold; color:{color};")
        self.dns_score_metrics.setText(
            f"پاسخ معمول {result.get('median_ms')}ms · نوسان {result.get('jitter_ms')}ms · "
            f"موفقیت {result.get('success_rate'):g}٪ · {secondary} · {doh}"
        )
        self.dns_benchmark_bar.setRange(0, 100)
        self.dns_benchmark_bar.setValue(score)
        self.dns_benchmark_bar.setStyleSheet(
            "QProgressBar { background:#0D171C; border:none; border-radius:3px; }"
            f"QProgressBar::chunk {{ background:{color}; border-radius:3px; }}"
        )
        self.dns_benchmark_status.setText(
            "✅ انتخاب بر اساس چند دامنه و چند نمونه؛ این عدد پینگ سرور بازی نیست."
        )
        if not self._running_game_name and not self.vm.tunnel_connected:
            self.home_orb.set_score(score, "امتیاز واقعی DNS")
            self._set_home_state(
                "connected", "DNS هوشمند آماده است",
                f"امتیاز واقعی DNS: {score} از ۱۰۰ · این عدد پینگ سرور بازی نیست.", 3,
            )

        ranking = result.get("ranking", [])
        by_name = {item.get("name"): item for item in ranking}
        for row in range(1, self.profile_list.count()):
            item = self.profile_list.item(row)
            profile = item.data(Qt.UserRole)
            quality = by_name.get(profile.name) if profile else None
            if not quality:
                continue
            medal = "🥇" if quality is ranking[0] else "🟢" if quality["score"] >= 70 else "🟡" if quality["score"] >= 50 else "🔴"
            item.setText(
                f"{medal} {self._dns_profile_text(profile, include_address=False)} · {quality['score']}/100 · "
                f"میانه {quality['median_ms']}ms · موفقیت {quality['success_rate']:g}٪"
            )
            item.setToolTip(
                f"نوسان {quality['jitter_ms']}ms · "
                f"پشتیبان: {'سالم' if quality['secondary_ok'] else 'ناپایدار'} · "
                f"DoH: {'سالم' if quality['doh_ok'] else 'ناموفق/ناموجود'}"
            )

    def _reset_dns_quality_display(self, message: str = "برای شروع، اتصال هوشمند را بزن",
                                   reset_selection: bool = True):
        self._latest_dns_quality = {}
        self.dns_explain_btn.setEnabled(False)
        self.dns_score_big.setText("— / 100")
        self.dns_score_big.setStyleSheet("font-size:27px; font-weight:bold; color:#4FC3F7;")
        self.dns_score_title.setText("🧠 DNS Intelligence")
        self.dns_score_title.setStyleSheet("font-size:16px; font-weight:bold; color:#81D4FA;")
        self.dns_score_metrics.setText(
            "نتایج اتصال قبلی پاک شده است · میانه · نوسان · پایداری · DoH"
        )
        self.dns_benchmark_bar.setRange(0, 100)
        self.dns_benchmark_bar.setValue(0)
        self.dns_benchmark_status.setText(message)
        for row in range(1, self.profile_list.count()):
            item = self.profile_list.item(row)
            profile = item.data(Qt.UserRole)
            if profile:
                item.setText(self._dns_profile_text(profile))
                self._style_dns_profile_item(item, profile)
        if reset_selection:
            self.profile_list.setCurrentRow(0)

    def _show_dns_explanation(self):
        result = self._latest_dns_quality
        if not result:
            return
        route_context = result.get("route_dna") or {}
        explanation = result.get("route_dna_explanation") or result.get(
            "route_dna_summary"
        ) or "برنده با تست زندهٔ چند دامنه و مقایسهٔ پایداری انتخاب شد."
        QMessageBox.information(
            self, "چرا این مسیر انتخاب شد؟",
            f"DNS انتخاب‌شده: {result.get('name', '—')}\n\n"
            f"{explanation}\n\n"
            f"امتیاز زنده: {result.get('score', 0)}/100\n"
            f"پاسخ معمول: {result.get('median_ms', '—')}ms\n"
            f"نوسان: {result.get('jitter_ms', '—')}ms\n"
            f"موفقیت: {result.get('success_rate', '—')}٪\n\n"
            "سابقه فقط نقش کمکی دارد و برنده همیشه باید در تست همین دستگاه سالم باشد."
        )

    def _on_retest_dns_clicked(self):
        adapter = self.adapter_combo.currentData()
        adapter_name = self.vm.active_adapter_name or (adapter.name if adapter else "")
        if not adapter_name:
            self.banner.show_message("کارت شبکه فعال پیدا نشد", "error")
            return
        self.vm.apply_best_dns(
            adapter_name, self.dns_preference_combo.currentData() or "balanced",
            self.dns_goal_combo.currentData() or "balanced",
        )

    def _animate_badge(self):
        if self.settings.get("reduce_motion", False):
            self.connection_badge.setGraphicsEffect(None)
            return
        effect = QGraphicsOpacityEffect(self.connection_badge)
        self.connection_badge.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._badge_anim = anim  # جلوگیری از garbage collection زودهنگام

    def _on_status_message(self, text: str, kind: str):
        crash_service.add_breadcrumb("status", text, level=kind)
        self.status_bar.showMessage(text, 4000)
        self.banner.show_message(text, kind)

    def _on_kill_switch_triggered(self):
        QMessageBox.warning(
            self, "محافظ DNS فعال شد",
            "اتصال اینترنت قطع شد و DNS به‌صورت خودکار به حالت امن بازگردانده شد."
        )
        self.kill_switch_check.setChecked(False)

    def _render_games(self, games):
        selected_name = self.games_list.currentItem().data(Qt.UserRole) \
            if self.games_list.currentItem() else ""
        self.games_list.clear()
        for g in games:
            mode = quality_service.MODES.get(g.connection_mode, "متعادل")
            auto = " · خودکار" if g.auto_connect else ""
            learned = game_route_profile_service.summary(g.route_profile)
            route_badge = " · مسیر شناخته‌شده" if learned.get("endpoints") else ""
            if g.name == self._optimized_game_name:
                marker = "🚀 بهینه‌سازی فعال · "
            elif g.name == self._running_game_name:
                marker = "🎮 در حال اجرا · "
            else:
                marker = "🎮 "
            label = f"{marker}{g.name} · {mode}{auto}{route_badge}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, g.name)
            scope = "فقط خود بازی" if getattr(g, "route_mode", "process") == "process" else "کل سیستم"
            item.setToolTip(
                f"فایل بازی: {g.process_name or 'ثبت نشده'}\nدامنه اتصال: {scope}\n"
                f"اعتماد مسیر: {learned.get('confidence', 0)}٪"
            )
            self.games_list.addItem(item)
            if g.name == selected_name:
                self.games_list.setCurrentItem(item)

    def _toggle_game_advanced(self, checked: bool):
        self.game_advanced_frame.setVisible(checked)
        self.game_advanced_toggle.setText(
            "🔧 بستن جزئیات فنی" if checked else
            "🔧 نمایش جزئیات فنی و ابزارهای آزمایشی"
        )

    def _toggle_game_manage(self, checked: bool):
        self.game_manage_frame.setVisible(checked)
        self.game_manage_toggle.setText(
            "➖ بستن مدیریت بازی‌ها" if checked else "➕ مدیریت فهرست بازی‌ها"
        )

    def _on_game_selection_changed(self, current, _previous):
        self._refresh_game_route_profile()
        game = self._selected_or_running_game()
        self.quick_game_action_btn.setEnabled(bool(game))
        self.quick_game_action_btn.setText(
            f"✨ بررسی و بهینه‌سازی «{game.name}»" if game else
            "✨ بهینه‌سازی بازی انتخاب‌شده"
        )

    def _on_quick_game_action(self):
        game = self._selected_or_running_game()
        if not game:
            self.banner.show_message("ابتدا یک بازی را انتخاب یا اجرا کن", "info")
            return
        self._show_game_optimizer(game=game)

    def _selected_or_running_game(self):
        preferred_name = self._running_game_name or self._optimized_game_name
        if preferred_name:
            game = next((g for g in self.vm.games if g.name == preferred_name), None)
            if game:
                return game
        item = self.games_list.currentItem()
        if item:
            return next((g for g in self.vm.games if g.name == item.data(Qt.UserRole)), None)
        return None

    def _refresh_game_route_profile(self, game=None):
        game = game or self._selected_or_running_game()
        if not game:
            self.game_route_profile_label.setText("یک بازی در حال اجرا یا از فهرست انتخاب کن")
            self.clear_game_route_btn.setEnabled(False)
            return
        info = game_route_profile_service.summary(game.route_profile)
        if not info.get("available"):
            self.game_route_profile_label.setText(
                f"🎮 {game.name}\nهنوز چیزی یاد نگرفته‌ام؛ وارد بخش آنلاین بازی شو و یادگیری زنده را بزن."
            )
            self.clear_game_route_btn.setEnabled(False)
            return
        if info.get("lobby_waiting") and not info.get("endpoints"):
            self.game_route_profile_label.setText(
                f"🟡 {game.name} · Lobby Readiness فعال\n"
                "بازی و اینترنت شناسایی شده‌اند، اما ویندوز هنوز مقصد دورِ نشست بازی را نشان نمی‌دهد. "
                "این خطا نیست؛ پایش زنده روشن می‌ماند و با ساخته‌شدن Match/Session مقصد خودکار اضافه می‌شود.\n"
                f"UDP Capture پروسه: {len(info.get('local_udp_ports', []))} پورت محلی زیر نظر است · "
                f"MTU امن موقت: {info['mtu']} · ضدتقلب: "
                + ("، ".join(info.get("anti_cheat", [])) or "دیده نشد")
            )
            self.clear_game_route_btn.setEnabled(True)
            return
        state = "قدیمی؛ اعمال خودکار متوقف" if info["stale"] else "تازه و قابل استفاده"
        udp = "، ".join(map(str, info["udp_ports"][:8])) or "—"
        tcp = "، ".join(map(str, info["tcp_ports"][:8])) or "—"
        recommendation = info.get("recommendations", {})
        fec = "پیشنهاد می‌شود" if recommendation.get("fec") else "لازم نیست"
        drift = "⚠️ تغییر جدی مسیر دیده شد" if info.get("drift") else "مسیرها عادی‌اند"
        anti_cheat = "، ".join(info.get("anti_cheat", [])) or "دیده نشد"
        self.game_route_profile_label.setText(
            f"🎮 {game.name} · اعتماد {info['confidence']}٪ · {state}\n"
            f"{info['endpoints']} مقصد · {info['observations']} آزمایش · {info['contexts']} نوع اینترنت · "
            f"{info['distance_hint']} (نه تشخیص کشور)\n"
            f"UDP: {udp}   |   TCP: {tcp}\n"
            f"MTU امن: {info['mtu']} · Payload پیشنهادی: {recommendation.get('packet_payload', '—')} · "
            f"FEC: {fec}\n{drift} · نشانه لاگ: {info['log_hints']} · ضدتقلب: {anti_cheat}"
        )
        self.clear_game_route_btn.setEnabled(True)

    def _on_learn_game_route_clicked(self):
        game = self._selected_or_running_game()
        if not game:
            self.banner.show_message("ابتدا بازی را اجرا یا از فهرست انتخاب کن", "error")
            return
        self.learn_game_route_btn.setEnabled(False)
        self.game_route_profile_label.setText(
            f"🔍 Route Lab: اتصال زنده، لاگ‌های باز، پورت‌ها، کیفیت، تغییر مسیر، ضدتقلب و MTU «{game.name}»…"
        )
        self.vm.learn_game_route_profile(game)

    def _on_clear_game_route_clicked(self):
        game = self._selected_or_running_game()
        if not game or not game.route_profile:
            return
        reply = QMessageBox.question(
            self, "پاک‌کردن یادگیری محلی",
            f"پروفایل مسیر «{game.name}» پاک شود؟ تنظیمات امن پیش‌فرض جایگزین می‌شود.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.vm.clear_game_route_profile(game)
            self._refresh_game_route_profile(game)

    def _on_export_game_route_clicked(self):
        game = self._selected_or_running_game()
        if not game or not game.route_profile:
            self.banner.show_message("برای این بازی هنوز Route Profile ساخته نشده", "error")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره Route Recipe", f"{game.name}-route-recipe.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            text = game_route_profile_service.export_recipe(
                game.name, game.process_name, game.route_profile
            )
            Path(path).write_text(text, encoding="utf-8")
            self.banner.show_message("Route Recipe بدون کلید یا اطلاعات تانل ذخیره شد", "success")
        except OSError as exc:
            self.banner.show_message(f"ذخیره Route Recipe ناموفق بود: {exc}", "error")

    def _on_import_game_route_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "ورود Route Recipe", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            recipe_path = Path(path)
            if recipe_path.stat().st_size > 2_000_000:
                raise ValueError("فایل Route Recipe بیش از حد بزرگ است")
            game_name, process_name, profile = game_route_profile_service.import_recipe(
                recipe_path.read_text(encoding="utf-8")
            )
            game = self._selected_or_running_game()
            if not game:
                game = next(
                    (item for item in self.vm.games
                     if item.name == game_name or item.process_name.lower() == process_name.lower()),
                    None,
                )
            if not game:
                raise ValueError("ابتدا بازی مقصد را از فهرست انتخاب کن")
            self.vm.set_game_route_profile(game, profile)
            self._refresh_game_route_profile(game)
            self.banner.show_message(f"Route Recipe برای «{game.name}» وارد شد", "success")
        except (OSError, ValueError, TypeError) as exc:
            self.banner.show_message(f"Route Recipe پذیرفته نشد: {exc}", "error")

    def _on_game_route_profile_ready(self, game_name: str, profile: dict, error: str):
        self.learn_game_route_btn.setEnabled(True)
        game = next((item for item in self.vm.games if item.name == game_name), None)
        if error:
            self.game_route_profile_label.setText(f"⚠️ {error}\nوارد منوی آنلاین یا مسابقه شو و دوباره امتحان کن.")
            self.banner.show_message("یادگیری مسیر کامل نشد", "error")
            return
        self._refresh_game_route_profile(game)
        if profile:
            if profile.get("lobby_waiting") and not profile.get("endpoints"):
                self.banner.show_message(
                    f"Lobby Readiness «{game_name}» آماده شد؛ پایش مقصد بازی ادامه دارد", "success"
                )
                return
            changed = int(profile.get("changed_endpoints", 0))
            suffix = f" · {changed} مقصد تازه" if changed else " · مسیرهای قبلی تأیید شدند"
            self.banner.show_message(f"پروفایل مسیر «{game_name}» به‌روز شد{suffix}", "success")

    def _on_air_profile_updated(self, game_name: str, profile: dict, new_count: int):
        """AIR updates are intentionally quiet; the timeline reports meaningful transitions."""
        game = next((item for item in self.vm.games if item.name == game_name), None)
        self._refresh_game_route_profile(game)

    def _on_network_lab_ready(self, result: dict):
        if result.get("error"):
            self.network_lab_label.setText(f"⚠️ Network Lab: {result['error']}")
            return
        matrix, breakdown = result.get("matrix", {}), result.get("breakdown", {})
        def metric(name):
            row = matrix.get(name, {})
            return (f"{row.get('median_ms')}ms / نوسان {row.get('jitter_ms')} / افت {row.get('loss'):g}٪"
                    if row.get("available") else "بدون پاسخ قطعی")
        pressure = result.get("pressure", {}).get("active") or {}
        utilization = pressure.get("utilization_pct")
        load = f"{utilization:g}٪" if utilization is not None else "نامشخص"
        target_title = (
            "🟡 مرجع آمادگی لابی (سرور بازی نیست)" if result.get("lobby_mode") else
            f"🎯 مقصد مشاهده‌شده از ترافیک بازی / Relay {matrix.get('host')}:{matrix.get('port')}"
        )
        direct_text = (
            "منتظر نشست بازی" if result.get("lobby_mode") else
            f"{breakdown.get('destination_ms', -1)}ms"
        )
        self.network_lab_label.setText(
            f"{target_title} · IPv{matrix.get('ip_version')} · "
            f"ترافیک دیده‌شده: {str(matrix.get('observed_transport', '—')).upper()}\n"
            f"ICMP: {metric('icmp')}   |   TCP: {metric('tcp')}   |   UDP: {metric('udp')}\n"
            f"Gateway: {breakdown.get('gateway') or 'نامشخص'} ({breakdown.get('gateway_ms', -1)}ms) · "
            f"مقصد مستقیم: {direct_text} · Relay: "
            f"{breakdown.get('relay_ms', -1) if breakdown.get('relay_ms', -1) >= 0 else 'اندازه‌گیری نشد'}\n"
            f"کارت‌های سالم: {len(result.get('adapters', []))} · فشار لینک «{pressure.get('name', '—')}»: {load}\n"
            "Truth Engine: UDP بی‌پاسخ به‌تنهایی پکت‌لاس محسوب نمی‌شود؛ مسیر شتاب‌یافته فقط با پروب داخل GameLink قطعی است."
        )

    def _on_network_monitor_ready(self, result: dict):
        if result.get("error"):
            self.adapter_monitor_label.setText("📡 پایش کارت‌ها موقتاً در دسترس نیست")
            return
        adapters = result.get("adapters", [])
        pressure = result.get("pressure", {}).get("active") or {}
        utilization = pressure.get("utilization_pct")
        pressure_text = f"{utilization:g}٪" if utilization is not None else "نامشخص"
        names = "، ".join(item.get("name", "") for item in adapters[:3]) or "هیچ‌کدام"
        self.adapter_monitor_label.setText(
            f"📡 کارت‌های سالم ({len(adapters)}): {names} · مسیر پرترافیک: {pressure.get('name', '—')} · "
            f"↓ {pressure.get('down_mbps', 0):g} / ↑ {pressure.get('up_mbps', 0):g} Mbps · فشار {pressure_text}"
        )

    def _start_game_server_probe(self, phase: str):
        game = self._selected_or_running_game()
        if not game:
            self.banner.show_message("بازی در حال اجرا یا یک بازی انتخاب‌شده لازم است", "error")
            return
        self.game_probe_baseline_btn.setEnabled(False)
        self.game_probe_compare_btn.setEnabled(False)
        self.game_probe_result.setText(
            f"🔍 در حال پیدا کردن مقصدهای واقعی «{game.name}» و گرفتن چند نمونه…"
        )
        self.vm.probe_game_server(game, phase)

    def _on_game_server_probe_ready(self, result: dict):
        self.game_probe_baseline_btn.setEnabled(True)
        self.game_probe_compare_btn.setEnabled(True)
        if result.get("error"):
            self.game_probe_result.setText(f"⚠️ {result['error']}")
            return
        transport = result.get("transport", "").upper()
        current = (
            f"{result.get('connection')}\n"
            f"🎯 مقصد مشاهده‌شده از ترافیک بازی / Relay: {result.get('host')}:{result.get('port')} · "
            f"{transport} · {result.get('method')}\n"
            f"پینگ معمول: {result.get('latency_ms')}ms · جیتر: {result.get('jitter_ms')}ms · "
            f"افت: {result.get('loss'):g}٪ · Game Score: {result.get('score')}/100"
        )
        if result.get("phase") == "baseline":
            self.game_probe_result.setText(
                f"✅ خط مبنا ذخیره شد\n{current}\nحالا اتصال DNS/تانل را فعال کن و دکمه مقایسه را بزن."
            )
            return
        baseline = result.get("baseline")
        if not baseline:
            self.game_probe_result.setText(
                f"{current}\nℹ️ نتیجه فعلی ثبت شد، اما برای مقایسه ابتدا «ثبت قبل از اتصال» را بزن."
            )
            return
        delta = int(result.get("latency_delta", 0))
        comparison = (
            f"{abs(delta)}ms بهتر" if delta < 0 else
            f"{delta}ms بدتر" if delta > 0 else "بدون تغییر"
        )
        self.game_probe_result.setText(
            f"📊 مقایسه واقعی قبل و بعد\n"
            f"قبل: {baseline.get('latency_ms')}ms · {baseline.get('connection')}\n"
            f"بعد: {result.get('latency_ms')}ms · {result.get('connection')}\n"
            f"نتیجه پینگ: {comparison} · تغییر جیتر {result.get('jitter_delta'):+}ms · "
            f"تغییر افت {result.get('loss_delta'):+g}٪\n"
            f"مقصد یکسان: {result.get('host')}:{result.get('port')} · {transport}"
            + (f"\n⚠️ {result.get('scope_warning')}" if result.get("scope_warning") else "")
        )
        if result.get("rollback_recommended"):
            self.game_probe_result.setText(
                self.game_probe_result.text()
                + "\n🛟 Safety Gate: مسیر جدید به‌طور معنادار بدتر است."
            )
            if self.route_auto_rollback_check.isChecked():
                self.vm.rollback_active_route()
                self.game_probe_result.setText(
                    self.game_probe_result.text() + " بازگشت امن اجرا شد."
                )
        truth = result.get("truth") or {}
        if truth:
            labels = {"better": "بهتر شد", "worse": "بدتر شد", "same": "تفاوت معنادار ندارد",
                      "indirect": "مقایسه غیرمستقیم", "unknown": "نامشخص"}
            trust = "معتبر" if truth.get("trusted") else "غیرقطعی"
            self.game_probe_result.setText(
                self.game_probe_result.text()
                + f"\n🧠 Truth Engine: {labels.get(truth.get('verdict'), 'نامشخص')} · {trust} · "
                + truth.get("reason", "")
            )

    def _on_add_game_clicked(self):
        name = self.game_name_input.text().strip()
        process_name = self.game_process_input.text().strip()
        if not name:
            self.banner.show_message("نام بازی رو وارد کن", "error")
            return
        self.vm.add_game(name, process_name)
        self.game_name_input.clear()
        self.game_process_input.clear()

    def _on_remove_game_clicked(self):
        item = self.games_list.currentItem()
        if not item:
            self.banner.show_message("یک بازی رو از لیست انتخاب کن", "error")
            return
        self.vm.remove_game(item.data(Qt.UserRole))

    def _on_set_game_profile_clicked(self):
        item = self.games_list.currentItem()
        if not item:
            self.banner.show_message("یک بازی رو از لیست انتخاب کن", "error")
            return
        name = item.data(Qt.UserRole)
        game = next((g for g in self.vm.games if g.name == name), None)
        if not game:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"پروفایل ترجیحی — {game.name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dlg_layout = QVBoxLayout(dialog)

        dlg_layout.addWidget(QLabel("DNS ترجیحی:"))
        dns_combo = QComboBox()
        dns_combo.addItem("(بدون ترجیح)", userData="")
        for p in self.vm.dns_profiles:
            dns_combo.addItem(p.name, userData=p.name)
        if game.preferred_dns_name:
            idx = dns_combo.findData(game.preferred_dns_name)
            if idx >= 0:
                dns_combo.setCurrentIndex(idx)
        dlg_layout.addWidget(dns_combo)

        dlg_layout.addWidget(QLabel("کانفیگ تانل ترجیحی:"))
        tunnel_combo = QComboBox()
        tunnel_combo.addItem("(بدون ترجیح)", userData="")
        for c in self.vm.tunnel_configs:
            tunnel_combo.addItem(c.name, userData=c.id)
        if game.preferred_tunnel_id:
            idx = tunnel_combo.findData(game.preferred_tunnel_id)
            if idx >= 0:
                tunnel_combo.setCurrentIndex(idx)
        dlg_layout.addWidget(tunnel_combo)

        dlg_layout.addWidget(QLabel("اولویت اتصال برای این بازی:"))
        mode_combo = QComboBox()
        for key, label in quality_service.MODES.items():
            mode_combo.addItem(label, userData=key)
        mode_index = mode_combo.findData(game.connection_mode)
        if mode_index >= 0:
            mode_combo.setCurrentIndex(mode_index)
        dlg_layout.addWidget(mode_combo)

        dlg_layout.addWidget(QLabel("روش اتصال:"))
        strategy_combo = QComboBox()
        strategy_combo.addItem("هوشمند — انتخاب خودکار", userData="smart")
        strategy_combo.addItem("فقط DNS", userData="dns")
        strategy_combo.addItem("فقط تانل بازی", userData="tunnel")
        strategy_index = strategy_combo.findData(getattr(game, "connection_strategy", "smart"))
        if strategy_index >= 0:
            strategy_combo.setCurrentIndex(strategy_index)
        dlg_layout.addWidget(strategy_combo)

        dlg_layout.addWidget(QLabel("دامنه مسیردهی تانل:"))
        route_mode_combo = QComboBox()
        route_mode_combo.addItem("🎯 فقط پروسه بازی — Process Guard", userData="process")
        route_mode_combo.addItem("🌐 کل سیستم — برای بازی‌های ناسازگار", userData="system")
        route_mode_combo.setCurrentIndex(max(0, route_mode_combo.findData(
            getattr(game, "route_mode", "process")
        )))
        dlg_layout.addWidget(route_mode_combo)

        auto_connect_check = QCheckBox("بعد از شناسایی بازی، بدون پرسش اتصال مناسب را فعال کن")
        auto_connect_check.setChecked(game.auto_connect)
        dlg_layout.addWidget(auto_connect_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            self.vm.set_game_preferences(
                game.name, dns_combo.currentData() or "", tunnel_combo.currentData() or "",
                mode_combo.currentData() or "balanced", auto_connect_check.isChecked(),
                strategy_combo.currentData() or "smart", route_mode_combo.currentData() or "process",
            )

    def _on_game_detected(self, game):
        self.detected_game_label.setText(f"🟢 «{game.name}» در حال اجراست")
        self._show_game_notification(("game", game), game.name, 100)

    def _on_game_candidate_detected(self, candidate):
        self.detected_game_label.setText(
            f"🟡 بازی احتمالی: {candidate.name} · اطمینان {candidate.confidence}٪"
        )
        self._show_game_notification(("candidate", candidate), candidate.name, candidate.confidence)

    def _show_game_notification(self, payload, name: str, confidence: int):
        self._pending_game_payload = payload
        self.review_detected_game_btn.show()
        self.home_game_title.setText(name)
        self.home_game_subtitle.setText(
            f"بازی با اطمینان {confidence}٪ شناسایی شد؛ پیشنهاد آمادهٔ تأیید توست."
        )
        self.home_primary_btn.setText("✨ دیدن پیشنهاد بهینه‌سازی")
        self._set_home_state("detected", "پیشنهاد آماده است", "پیش از هر تغییر، جزئیات را می‌بینی و خودت تأیید می‌کنی.")
        self.game_detection_toast.show_game(payload, name, confidence)
        if settings_service.load_settings().get("game_detection_sound", True):
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except RuntimeError:
                pass
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "بازی شناسایی شد",
                f"«{name}» اجرا شد. پیشنهاد بهینه‌سازی آماده است.",
                QSystemTrayIcon.Information, 8000,
            )

    def _on_game_toast_quick(self, payload):
        if not payload:
            return
        kind, item = payload
        self.review_detected_game_btn.hide()
        self._pending_game_payload = None
        if kind == "candidate":
            self.vm.accept_game_candidate(item, "smart", "balanced", False)
        else:
            self.vm.apply_game_preferred_profile(item)

    def _on_game_toast_details(self, payload):
        if not payload:
            return
        kind, item = payload
        self.review_detected_game_btn.hide()
        self._pending_game_payload = None
        if kind == "candidate":
            self._show_game_optimizer(candidate=item)
        else:
            self._show_game_optimizer(game=item)

    def _on_game_toast_dismissed(self, payload):
        if payload:
            self._pending_game_payload = payload
            self.review_detected_game_btn.show()
            self.detected_game_label.setText(
                "🟡 بازی در حال اجراست · پیشنهاد بهینه‌سازی در برنامه منتظر است"
            )

    def _on_review_pending_game(self):
        if self._pending_game_payload:
            self._on_game_toast_details(self._pending_game_payload)

    def _register_global_hotkey(self) -> bool:
        """Register Ctrl+Alt+G without keyboard hooks or game-process injection."""
        try:
            # MOD_ALT | MOD_CONTROL | MOD_NOREPEAT, virtual-key G
            return bool(ctypes.windll.user32.RegisterHotKey(
                int(self.winId()), self._hotkey_id, 0x0001 | 0x0002 | 0x4000, 0x47
            ))
        except Exception:
            return False

    def _unregister_global_hotkey(self):
        if not getattr(self, "_hotkey_registered", False):
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._hotkey_id)
        except Exception:
            pass
        self._hotkey_registered = False

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and int(msg.wParam) == self._hotkey_id:  # WM_HOTKEY
                if self._pending_game_payload:
                    QTimer.singleShot(
                        0, lambda: self._on_game_toast_quick(self._pending_game_payload)
                    )
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def _show_game_optimizer(self, game=None, candidate=None):
        name = game.name if game else candidate.name
        process_name = game.process_name if game else candidate.process_name
        confidence = 100 if game else candidate.confidence
        evidence = ("این بازی قبلاً تأیید شده",) if game else candidate.evidence

        dialog = QDialog(self)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.setWindowTitle("پیشنهاد بهینه‌سازی بازی")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.setMinimumWidth(520)
        box = QVBoxLayout(dialog)
        title = QLabel(f"🎮 {name} شناسایی شد")
        title.setObjectName("gameHeroTitle")
        box.addWidget(title)
        details = QLabel(
            f"پروسه: {process_name}\nاطمینان تشخیص: {confidence}٪\n"
            + " · ".join(evidence)
        )
        details.setWordWrap(True)
        details.setStyleSheet("color:#90A4AE; padding:8px;")
        box.addWidget(details)

        plan = QLabel("")
        plan.setWordWrap(True)
        plan.setStyleSheet("background:#172B34; border-radius:10px; padding:12px; color:#CFD8DC;")
        box.addWidget(plan)

        row = QHBoxLayout()
        row.addWidget(QLabel("روش:"))
        strategy = QComboBox()
        strategy.addItem("✨ هوشمند (پیشنهادی)", "smart")
        strategy.addItem("🌐 فقط DNS", "dns")
        strategy.addItem("🛡️ فقط تانل بازی", "tunnel")
        if game:
            strategy.setCurrentIndex(max(0, strategy.findData(getattr(game, "connection_strategy", "smart"))))
        row.addWidget(strategy, 1)
        row.addWidget(QLabel("اولویت:"))
        mode = QComboBox()
        for key, label in quality_service.MODES.items():
            mode.addItem(label, key)
        if game:
            mode.setCurrentIndex(max(0, mode.findData(game.connection_mode)))
        row.addWidget(mode, 1)
        box.addLayout(row)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("دامنه تانل:"))
        route_mode = QComboBox()
        route_mode.addItem("🎯 فقط بازی (پیشنهادی)", "process")
        route_mode.addItem("🌐 کل سیستم (سازگاری)", "system")
        if game:
            route_mode.setCurrentIndex(max(0, route_mode.findData(getattr(game, "route_mode", "process"))))
        scope_row.addWidget(route_mode, 1)
        box.addLayout(scope_row)

        def update_explanation():
            selected = strategy.currentData()
            if selected == "dns":
                text = (
                    "🌐 DNS: همه DNSهای سالم با پرس‌وجوی واقعی سنجیده می‌شوند و سریع‌ترین مورد "
                    "روی کارت شبکه فعال می‌شود. این کار Resolve و دسترسی را بهتر می‌کند، اما مسیر "
                    "پکت‌های داخل مسابقه را تغییر نمی‌دهد و تضمین کاهش پینگ نیست."
                )
            elif selected == "tunnel":
                text = (
                    "🛡️ Tunnel: حداکثر ۸ کانفیگ با ترافیک HTTPS واقعی آزمایش می‌شوند؛ بر اساس "
                    "پینگ، نوسان، افت و پایداری امتیاز می‌گیرند. فقط پروسه بازی وارد بهترین مسیر می‌شود "
                    "و مسیر دوم سالم، اگر وجود داشته باشد، پشتیبان می‌ماند."
                )
            else:
                text = (
                    "✨ هوشمند: اگر کانفیگ تانل داری، ابتدا مسیرهای تانل را می‌سنجد و فقط بازی را از "
                    "بهترین مسیر عبور می‌دهد؛ اگر هیچ مسیر سالمی پیدا نشود، خودکار به بهترین DNS سالم "
                    "برمی‌گردد. Turbo فقط با data-plane واقعی GameLink فعال خواهد شد."
                )
            plan.setText(text)

        strategy.currentIndexChanged.connect(update_explanation)
        update_explanation()

        auto = QCheckBox("از دفعه بعد برای این بازی خودکار انجام بده")
        auto.setChecked(bool(game and game.auto_connect))
        box.addWidget(auto)

        buttons = QHBoxLayout()
        confirm = QPushButton("✨ تأیید و بهینه‌سازی")
        confirm.setObjectName("primary")
        later = QPushButton("فعلاً نه")
        buttons.addWidget(confirm)
        buttons.addWidget(later)
        ignore = None
        if candidate:
            ignore = QPushButton("این بازی نیست")
            buttons.addWidget(ignore)
        box.addLayout(buttons)
        confirm.clicked.connect(dialog.accept)
        later.clicked.connect(dialog.reject)
        if ignore:
            ignore.clicked.connect(lambda: dialog.setProperty("ignoreCandidate", True))
            ignore.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            if candidate:
                self.vm.accept_game_candidate(
                    candidate, strategy.currentData(), mode.currentData(), auto.isChecked()
                )
            else:
                self.vm.set_game_preferences(
                    game.name, game.preferred_dns_name, game.preferred_tunnel_id,
                    mode.currentData(), auto.isChecked(), strategy.currentData(), route_mode.currentData(),
                )
                game.connection_mode = mode.currentData()
                game.connection_strategy = strategy.currentData()
                game.route_mode = route_mode.currentData()
                self.vm.optimize_game_connection(game)
        elif candidate and dialog.property("ignoreCandidate"):
            self.vm.ignore_game_candidate(candidate.process_name)

    def _on_game_optimization_progress(self, game_name: str, state: str, message: str):
        icon = "❌" if state == "error" else "●"
        stamp = QTime.currentTime().toString("HH:mm:ss")
        self.game_activity_list.addItem(f"{stamp}  {icon} {game_name}: {message}")
        while self.game_activity_list.count() > 30:
            self.game_activity_list.takeItem(0)
        self.game_activity_list.scrollToBottom()

    def _on_game_runtime_changed(self, game_name: str, running: bool):
        self._running_game_name = game_name if running else ""
        if not running:
            self.game_detection_toast.hide()
            self._pending_game_payload = None
            self.review_detected_game_btn.hide()
            self._optimized_game_name = ""
            self.detected_game_label.setText("وضعیت: بازی بسته شد؛ در حال پایش محلی…")
            self.game_route_profile_label.setText(
                "بازی بسته شد؛ اطلاعات زنده این نشست پاک شد. پروفایل یادگرفته‌شده فقط برای اجرای بعدی ذخیره مانده است."
            )
            self.network_lab_label.setText(
                "Network Lab متوقف شد · برای مشاهده مقصد و سنجش تازه، بازی را دوباره اجرا کن"
            )
            self.adapter_monitor_label.setText("📡 پایش زنده کارت‌ها متوقف شد")
            self.game_probe_result.setText("نشست بازی بسته شد؛ نتیجهٔ زنده‌ای نمایش داده نمی‌شود")
            self.game_activity_list.clear()
            self.game_activity_list.addItem(
                f"{QTime.currentTime().toString('HH:mm:ss')}  ■ {game_name}: نشست بسته و اطلاعات زنده جمع شد"
            )
            self.clear_game_route_btn.setEnabled(False)
            self.quick_game_action_btn.setEnabled(False)
            self.quick_game_action_btn.setText("✨ بهینه‌سازی بازی انتخاب‌شده")
            self.optimization_technical_label.setText("نشست بازی بسته شد؛ جزئیات زنده پاک شدند")
            self.home_game_title.setText("منتظر اجرای بازی")
            self.home_game_subtitle.setText(
                "نشست قبلی جمع شد؛ بازی را دوباره اجرا کن تا بررسی تازه‌ای آغاز شود."
            )
            self.home_primary_btn.setText("🎮 رفتن به بازی‌های من")

            self.home_ping_value.setText("—")
            self._set_home_state("idle", "آمادهٔ شناسایی", "هیچ بهینه‌سازی فعالی وجود ندارد.")
        else:
            self.detected_game_label.setText(f"🟢 «{game_name}» پیدا شد و آماده بررسی است")
            self.quick_game_action_btn.setEnabled(True)
            self.quick_game_action_btn.setText(f"✨ بررسی و بهینه‌سازی «{game_name}»")
            self.home_game_title.setText(game_name)
            self.home_game_subtitle.setText("بازی شناسایی شد؛ انتخاب اتصال مناسب آمادهٔ بررسی توست.")
            self.home_primary_btn.setText("✨ بررسی و بهینه‌سازی")
            self._set_home_state("detected", "بازی پیدا شد", "برای دیدن پیشنهاد و تأیید تغییرات ادامه بده.")
        self._render_games(self.vm.games)
        if not running:
            self.games_list.clearSelection()
            self.games_list.setCurrentItem(None)

    def _on_game_session_report_ready(self, report: dict):
        duration = int(report.get("duration_s", 0))
        minutes, seconds = divmod(duration, 60)
        if report.get("conclusive"):
            metrics = (
                f"پینگ میانه {report.get('median_ms')}ms · بهترین {report.get('best_ms')}ms · "
                f"بدترین {report.get('worst_ms')}ms · جیتر {report.get('jitter_ms')}ms · "
                f"افت {report.get('loss_pct')}٪"
            )
        else:
            metrics = "نمونه کافی از مقصد واقعی بازی ثبت نشد؛ عدد ساختگی نمایش داده نمی‌شود"
        text = (
            f"📊 گزارش پایان نشست {report.get('game')} · {minutes}:{seconds:02d}\n"
            f"{metrics}\n"
            f"مسیر: {report.get('route')} · {report.get('samples', 0)} نمونه · "
            f"{report.get('route_events', 0)} رویداد مقصد؛ فقط خلاصه محلی و بدون IP"
        )
        self.game_probe_result.setText(text)
        self.game_activity_list.addItem(text.replace("\n", " · "))

    def _on_optimization_state_changed(self, state: dict):
        running = bool(state.get("running", False))
        stage = state.get("stage", "")
        self._optimized_game_name = state.get("game", "") if running and stage != "failed" else ""
        turbo_reason = state.get("turbo_reason", "")
        protocol = f" ({state.get('protocol')})" if state.get("protocol") else ""
        stage_label = {
            "testing": "در حال پیدا کردن بهترین اتصال",
            "applying_dns": "در حال فعال‌کردن DNS مناسب",
            "testing_tunnels": "در حال بررسی مسیرهای اتصال",
            "connected": "بهینه‌سازی فعال است",
            "failed": "بهینه‌سازی انجام نشد",
            "stopped": "بازی بسته شده است",
        }.get(stage, "در حال بررسی")
        connection = state.get("tunnel")
        if not connection or connection in ("در انتظار تصمیم", "استفاده نمی‌شود"):
            connection = state.get("dns", "هنوز انتخاب نشده")
        self.optimization_details_label.setText(
            f"🎮 {state.get('game', 'بازی')}\n"
            f"{'✅' if stage == 'connected' else '⏳' if running else '■'} {stage_label}\n"
            f"اتصال: {connection}\n"
            f"نتیجه: {state.get('effect', 'در حال ارزیابی…')}"
        )
        self.optimization_technical_label.setText(
            f"DNS: {state.get('dns', '—')}\n"
            f"تانل: {state.get('tunnel', '—')}{protocol}\n"
            f"دامنه مسیردهی: {state.get('routing', '—')}\n"
            f"بازیابی: {state.get('failover', '—')}\n"
            f"Turbo: {state.get('turbo', 'غیرفعال')} — {turbo_reason}"
        )
        home_state = {
            "testing": ("testing", "در حال سنجش مسیرها", 1),
            "applying_dns": ("testing", "در حال آماده‌سازی DNS", 2),
            "testing_tunnels": ("testing", "در حال بررسی مسیر اتصال", 2),
            "connected": ("connected", "بهینه‌سازی فعال است", 3),
            "failed": ("error", "اتصال مناسب پیدا نشد", 2),
            "stopped": ("idle", "نشست بازی پایان یافت", -1),
        }.get(stage, ("detected", "در حال بررسی", 0))
        self._set_home_state(
            home_state[0], home_state[1], state.get("effect", "در حال ارزیابی…"), home_state[2]
        )
        self.home_game_title.setText(state.get("game", self._running_game_name or "بازی"))
        self.home_primary_btn.setText(
            "✅ مشاهده وضعیت بازی" if stage == "connected" else "🎮 باز کردن مرکز بازی"
        )
        self._render_games(self.vm.games)
        QTimer.singleShot(0, lambda: self.games_scroll.verticalScrollBar().setValue(0))

    def _on_game_detection_setting_changed(self, checked: bool):
        self._set_setting("game_detection_enabled", checked)
        self.detected_game_label.setText(
            "🔎 منتظر اجرای بازی…" if checked else "⏸️ تشخیص خودکار خاموش است"
        )

    def _on_usage_updated(self, minutes_today: float, limit_mb: int):
        hours = int(minutes_today // 60)
        mins = int(minutes_today % 60)
        self.usage_label.setText(
            f"زمان اتصال امروز: {hours} ساعت و {mins} دقیقه"
        )

    def _on_traffic_usage_updated(self, total_bytes: int, quota_mb: int):
        used_mb = total_bytes / (1024 * 1024)
        percent = min(100.0, used_mb * 100.0 / max(1, quota_mb))
        self.traffic_label.setText(
            f"مصرف محلی امروز: {used_mb:.1f} MB از {quota_mb} MB ({percent:.1f}٪)"
        )

    # ---------------- تانل ----------------

    def _render_tunnel_configs(self, configs):
        self.tunnel_list.clear()
        for c in configs:
            label = f"{c.name}   ·   {c.protocol}   ·   {c.address}:{c.port}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, c)
            self.tunnel_list.addItem(item)

    def _on_import_tunnel_clicked(self):
        link = self.tunnel_link_input.text().strip()
        if not link:
            self.banner.show_message("لینک کانفیگ رو وارد کن", "error")
            return
        self.vm.import_tunnel_link(link)
        self.tunnel_link_input.clear()

    def _on_remove_tunnel_clicked(self):
        item = self.tunnel_list.currentItem()
        if not item:
            self.banner.show_message("یک کانفیگ رو انتخاب کن", "error")
            return
        config = item.data(Qt.UserRole)
        self.vm.remove_tunnel_config(config.id)

    def _on_ping_test_clicked(self):
        item = self.tunnel_list.currentItem()
        if not item:
            self.banner.show_message("یک کانفیگ رو برای تست پینگ انتخاب کن", "error")
            return
        config = item.data(Qt.UserRole)
        self.banner.show_message(f"در حال تست پینگ به {config.name}...", "info")
        self.vm.test_ping(config.name, config.address, config.port)

    def _on_ping_result(self, name: str, latency: int):
        if latency < 0:
            self.banner.show_message(f"«{name}»: پاسخ نداد ⚠️", "error")
        else:
            self.banner.show_message(f"«{name}»: {latency} میلی‌ثانیه 📶", "success")

    def _on_trial_clicked(self):
        item = self.tunnel_list.currentItem()
        if not item:
            self.banner.show_message("یک کانفیگ را برای آزمایش انتخاب کن", "error")
            return
        self.vm.run_config_trial(item.data(Qt.UserRole))

    def _on_trial_ready(self, result: dict):
        if not result.get("available"):
            self.speed_test_result.setText(
                f"آزمایش ۳۰ ثانیه‌ای «{result['name']}» ناموفق: {result.get('error', 'بدون پاسخ')}"
            )
            return
        self.speed_test_result.setText(
            f"آزمایش «{result['name']}» · Game Score {result['score']}/100 · "
            f"پینگ {result['latency']}ms · جیتر {result['jitter']}ms · "
            f"پکت‌لاس {result['loss']:g}% · {result['attempts']} نمونه"
        )

    def _on_tunnel_toggle_clicked(self):
        if self.vm.tunnel_connected:
            self.vm.disconnect_tunnel()
            return
        item = self.tunnel_list.currentItem()
        if not ALLOW_CUSTOM_TUNNELS and not self._running_game_name:
            self.banner.show_message(
                "برای WARP Game Mode ابتدا بازی را اجرا کن؛ اتصال عمومی کل سیستم در این نسخه فعال نیست.",
                "info", 5500,
            )
            return
        config = item.data(Qt.UserRole) if item else None
        game = None
        if not ALLOW_CUSTOM_TUNNELS:
            game = next((g for g in self.vm.games if g.name == self._running_game_name), None)
        self.vm.connect_tunnel(config, game)

    def _on_tunnel_busy_changed(self, busy: bool):
        self.brand_mark.set_busy(busy)
        self.tunnel_toggle_btn.setEnabled(not busy)
        self.import_tunnel_btn.setEnabled(not busy)
        self.trial_btn.setEnabled(not busy)
        if busy:
            self.tunnel_toggle_btn.setText("در حال انجام...")
        else:
            self.tunnel_toggle_btn.setText(
                "قطع اتصال تانل" if self.vm.tunnel_connected else "اتصال هوشمند"
            )

    def _on_tunnel_status_changed(self, connected: bool, name: str):
        if connected:
            self.tunnel_toggle_btn.setText("قطع اتصال تانل")
            self.tunnel_toggle_btn.setObjectName("connected")
            self.ping_chart.clear_history()
            if self.overlay_check.isChecked():
                self.ping_overlay.start()
        else:
            self.tunnel_toggle_btn.setText("اتصال هوشمند")
            self.tunnel_toggle_btn.setObjectName("primary")
            self.ping_overlay.stop()
        if connected:
            self.connection_badge.setText(f"🟢 مسیر هوشمند: {name}")
            self.connection_badge.setStyleSheet(
                "color:#79F2BE; font-weight:bold; background:#0B201B;"
                "border:1px solid #216B52; border-radius:12px; padding:8px 12px;"
            )
            self.home_route_value.setText(name)
            if not self._running_game_name:
                self._set_home_state(
                    "connected", "مسیر اتصال فعال است",
                    "اتصال برقرار شد؛ کیلومترشمار با رسیدن سنجش واقعی تکمیل می‌شود.", 3,
                )
            if self._optimized_game_name:
                self.tunnel_scope_label.setText(
                    f"🎯 محدوده اتصال: فقط بازی «{self._optimized_game_name}» — سایر برنامه‌ها مستقیم"
                )
            else:
                self.tunnel_scope_label.setText("🌐 محدوده اتصال: سراسری برای کل سیستم")
            for row in range(self.tunnel_list.count()):
                item = self.tunnel_list.item(row)
                config = item.data(Qt.UserRole)
                if config and config.name == name:
                    self.tunnel_list.setCurrentRow(row)
                    break
            self._schedule_safety_gate_probe()
        elif self.vm.is_connected:
            self.connection_badge.setText(f"🟢 وصل به {self.vm.active_profile_name}")
        else:
            self.connection_badge.setText("⭕ قطع")
            self.connection_badge.setStyleSheet(
                "color:#A9BAC4; font-weight:bold; background:#0A151C;"
                "border:1px solid #203944; border-radius:12px; padding:8px 12px;"
            )
        if not connected:
            self.tunnel_scope_label.setText("محدوده اتصال: غیرفعال")
            self.home_route_value.setText("مستقیم")
            if not self.vm.is_connected and not self._running_game_name:
                self._set_home_state("idle", "آمادهٔ شناسایی", "هیچ بهینه‌سازی فعالی وجود ندارد.", -1)
        self.tunnel_toggle_btn.style().unpolish(self.tunnel_toggle_btn)
        self.tunnel_toggle_btn.style().polish(self.tunnel_toggle_btn)

    def _schedule_safety_gate_probe(self):
        if not self.route_auto_rollback_check.isChecked():
            return
        game = self._selected_or_running_game()
        if not game or not self.vm.has_game_probe_baseline(game):
            return
        QTimer.singleShot(
            3500,
            lambda: self.vm.probe_game_server(game, "current")
            if (self.vm.is_connected or self.vm.tunnel_connected) else None,
        )

    def _get_overlay_target(self):
        """اورلی از این تابع می‌پرسه سرور فعلی چیه (برای نمایش وضعیت وصل/قطع)"""
        return self.vm.active_tunnel_name if self.vm.tunnel_connected else None

    def _on_live_ping(self, latency_ms: int):
        """پینگ دوره‌ی زنده (وقتی تانل وصله) — هم اورلی هم نمودار تاریخچه رو آپدیت می‌کنه"""
        self.ping_overlay.update_ping(latency_ms)
        self.ping_chart.add_value(latency_ms)
        self.home_ping_value.setText("بدون پاسخ" if latency_ms < 0 else f"{latency_ms} ms")

    def _on_route_quality_ready(self, result: dict):
        self.vm.record_route_quality(result)
        standby = f" · پشتیبان آماده: {result['standby']}" if result.get("standby") else ""
        self.route_quality_label.setText(
            f"Game Score: {result['score']}/100 ({result['label']}) · "
            f"پینگ {result['latency']}ms · جیتر {result['jitter']}ms · "
            f"پکت‌لاس {result['loss']:g}% · MTU {result.get('mtu', 1400)}{standby}"
        )
        self.ping_overlay.set_quality(result["score"], result["loss"])
        self.home_orb.set_score(int(result["score"]), "Game Score واقعی")
        self.home_ping_value.setText(f"{result['latency']} ms")
        self._set_home_state(
            "connected",
            "مسیر بازی آماده است",
            f"پینگ {result['latency']}ms · نوسان {result['jitter']}ms · پکت‌لاس {result['loss']:g}٪",
            3,
        )

    def _on_failover_changed(self, active: bool, detail: str):
        if active:
            self.route_quality_label.setText(f"🔄 بازیابی هوشمند: {detail}")

    def _on_diagnostic_report_ready(self, path: str):
        QMessageBox.information(
            self, "گزارش امن ساخته شد",
            f"گزارش در این مسیر ذخیره شد:\n{path}\n\nاین فایل شامل کلید، لینک یا آدرس سرور نیست.",
        )

    def _refresh_blackbox_status(self):
        count = crash_service.pending_count()
        self.blackbox_status_label.setText(
            "گزارش ذخیره‌شده‌ای وجود ندارد"
            if count == 0 else f"{count} گزارش محلی آماده بررسی است"
        )
        self.blackbox_export_btn.setEnabled(count > 0)
        self.blackbox_clear_btn.setEnabled(count > 0)

    def _on_blackbox_toggled(self, checked: bool):
        self.settings = settings_service.set_value("blackbox_enabled", checked)
        crash_service.set_enabled(checked)
        self.banner.show_message(
            "ثبت محلی خطا روشن شد" if checked else "ثبت خطا خاموش شد؛ گزارش‌های قبلی پاک نشده‌اند",
            "success" if checked else "info", 4500,
        )
        self._refresh_blackbox_status()

    def _export_blackbox_reports(self):
        if not crash_service.pending_count():
            self._refresh_blackbox_status()
            return
        try:
            import json
            payload = crash_service.preview_pending()
        except Exception as exc:
            self.banner.show_message(f"خواندن گزارش ممکن نشد: {exc}", "error")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("پیش‌نمایش کامل گزارش‌های پاک‌سازی‌شده")
        dialog.resize(820, 560)
        layout = QVBoxLayout(dialog)
        note = QLabel(
            "این دقیقاً همان محتوایی است که در فایل ذخیره می‌شود. چیزی خودکار ارسال نمی‌شود."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setLayoutDirection(Qt.LeftToRight)
        preview.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox()
        export_button = buttons.addButton("تأیید و ساخت فایل", QDialogButtonBox.AcceptRole)
        buttons.addButton("انصراف", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        export_button.setDefault(True)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            path = crash_service.export_pending()
        except Exception as exc:
            self.banner.show_message(f"ساخت فایل گزارش ممکن نشد: {exc}", "error")
            return
        QMessageBox.information(
            self, "فایل گزارش آماده شد",
            f"این فایل را می‌توانی دستی برای پشتیبانی بفرستی:\n{path}\n\n"
            "هیچ داده‌ای خودکار ارسال نشده است.",
        )

    def _clear_blackbox_reports(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("پاک‌کردن گزارش‌ها")
        box.setText("همه گزارش‌های خطای ذخیره‌شده روی این دستگاه پاک شوند؟")
        confirm = box.addButton("پاک‌کردن", QMessageBox.DestructiveRole)
        box.addButton("انصراف", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is confirm:
            removed = crash_service.clear_pending()
            self.banner.show_message(f"{removed} گزارش محلی پاک شد", "success")
            self._refresh_blackbox_status()

    def _on_overlay_setting_changed(self, checked: bool):
        self.settings = settings_service.set_value("overlay_enabled", checked)
        if checked and self.vm.tunnel_connected:
            self.ping_overlay.start()
        else:
            self.ping_overlay.stop()

    def _set_setting(self, key: str, value):
        self.settings = settings_service.set_value(key, value)

    def _on_turbo_setting_changed(self, checked: bool):
        if checked and not self.gamelink_url_input.text().strip():
            self.banner.show_message(
                "Turbo آماده است اما برای فعال‌شدن واقعی به سرور GameLink مشترک نیاز دارد",
                "info",
            )
        self._set_setting("turbo_mode", checked)

    def _on_warp_clicked(self):
        if self._warp_operation_busy:
            self.vm.cancel_official_warp_test()
            self.warp_btn.setEnabled(False)
            self.warp_btn.setText("در حال بازگردانی…")
            return
        if self._official_warp_active:
            if not self._official_warp_owned:
                self.banner.show_message(
                    "این اتصال قبل از LAGSHIFT فعال بوده؛ برای حفظ وضعیت کاربر آن را قطع نمی‌کنیم.",
                    "info", 6000,
                )
                return
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("قطع اتصال رسمی")
            box.setText("اتصال Cloudflare قطع و تنظیم قبلی برگردانده شود؟")
            confirm = box.addButton("قطع و بازگردانی", QMessageBox.AcceptRole)
            box.addButton("فعلاً نه", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is confirm:
                self.vm.disconnect_official_warp()
            return
        mode = self.warp_mode_combo.currentData() or "smart"
        dns_only = mode in {"doh", "dot", "dns_smart"}
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("فعال‌سازی اتصال رسمی")
        box.setText(
            "LAGSHIFT کلاینت رسمی Cloudflare را برای پیدا کردن یک مسیر سالم آزمایش می‌کند."
        )
        box.setInformativeText(
            "در حالت فقط DNS، ترافیک برنامه‌ها جابه‌جا نمی‌شود. در حالت‌های دیگر ممکن است "
            "تا زمان قطع اتصال، ترافیک دستگاه از Cloudflare عبور کند."
            if dns_only else
            "ممکن است تا زمان قطع اتصال، ترافیک دستگاه از Cloudflare عبور کند. "
            "اگر هیچ روشی سالم نبود، تنظیم قبلی خودکار برمی‌گردد."
        )
        confirm = box.addButton("ادامه", QMessageBox.AcceptRole)
        box.addButton("فعلاً نه", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is confirm:
            self.vm.import_warp_config(
                mode, self.warp_protocol_combo.currentData() or "auto",
            )

    def _on_warp_state_changed(self, result: dict):
        if result.get("operation") == "progress":
            self.warp_state_label.setText("◌ " + result.get("message", "در حال آزمایش…"))
            return
        installed = bool(result.get("installed", True))
        active = bool(result.get("active", False))
        if result.get("operation") == "connect" and result.get("ok"):
            self._official_warp_owned = bool(result.get("started_by_app"))
        elif result.get("operation") == "disconnect" and result.get("ok") and not active:
            self._official_warp_owned = False
        self._official_warp_active = active
        self.warp_install_btn.setVisible(not installed)
        self.warp_btn.setVisible(installed)
        signature_ok = bool(result.get("signature_valid", installed))
        if active:
            protocol = result.get("protocol", "مسیر رسمی")
            mode = result.get("mode", "")
            mode_label = result.get("mode_label") or official_warp_service.MODE_LABELS.get(mode, "اتصال رسمی")
            self.warp_state_label.setText(f"● {mode_label} فعال است · {protocol}")
            self.warp_state_label.setStyleSheet("color:#79EDB5;")
            self.warp_btn.setText(
                "قطع WARP و بازگشت" if self._official_warp_owned else "فعال خارج از LAGSHIFT"
            )
            self.warp_btn.setEnabled(self._official_warp_owned)
        elif not installed:
            self.warp_state_label.setText(
                "برای استفاده از این بخش، ابتدا کلاینت رسمی Cloudflare را دریافت و نصب کن؛ "
                "بعد به برنامه برگرد و «بررسی دوباره» را بزن."
            )
            self.warp_state_label.setStyleSheet("color:#FFD180;")
        elif not signature_ok:
            self.warp_state_label.setText("⚠ امضای Cloudflare تأیید نشد؛ اجرا برای امنیت مسدود شد.")
            self.warp_state_label.setStyleSheet("color:#FF8A80;")
            self.warp_btn.setText("فایل رسمی معتبر نیست")
            self.warp_btn.setEnabled(False)
        else:
            detail = result.get("message") or result.get("detail") or result.get("error")
            self.warp_state_label.setText("○ " + (detail or "کلاینت رسمی آماده‌ی آزمایش است."))
            self.warp_state_label.setToolTip(result.get("technical", ""))
            self.warp_state_label.setStyleSheet("color:#9BB2BC;")
            self.warp_btn.setText("اتصال و تأیید WARP رسمی")
            self.warp_btn.setEnabled(True)

    def _on_warp_busy_changed(self, busy: bool):
        self._warp_operation_busy = busy
        self.brand_mark.set_busy(busy)
        self.warp_btn.setEnabled(True)
        self.warp_refresh_btn.setEnabled(not busy)
        self.warp_protocol_combo.setEnabled(not busy and not self._official_warp_active)
        self.warp_mode_combo.setEnabled(not busy and not self._official_warp_active)
        self.warp_btn.setText(
            "لغو آزمایش و بازگردانی" if busy
            else ("قطع WARP و بازگشت" if self._official_warp_active and self._official_warp_owned
                  else "اتصال و تأیید WARP رسمی")
        )

    def _on_rate_config_clicked(self):
        item = self.tunnel_list.currentItem()
        if not item:
            self.banner.show_message("یک کانفیگ رو انتخاب کن", "error")
            return
        config = item.data(Qt.UserRole)
        current = self.vm.get_config_rating(config.id)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"امتیاز شخصی — {config.name}")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel("این کانفیگ رو از ۱ تا ۵ ستاره امتیاز بده (فقط برای خودت ذخیره می‌شه):"))
        stars_combo = QComboBox()
        for i in range(1, 6):
            stars_combo.addItem("⭐" * i, userData=i)
        if current:
            stars_combo.setCurrentIndex(current - 1)
        dlg_layout.addWidget(stars_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            self.vm.set_config_rating(config.id, stars_combo.currentData())

    def _on_speed_test_ready(self, result: dict):
        if not result.get("available"):
            self.speed_test_result.setText(
                f"مسیر فعال پاسخ نداد ({result.get('error') or 'timeout'})"
            )
            return
        route = "TUN هوشمند" if result.get("route") == "tunnel" else "اینترنت فعلی"
        self.speed_test_result.setText(
            f"{route} · پاسخ واقعی: {result['latency']} ms · نوسان: {result['jitter']} ms · "
            f"موفق: {result['successes']} از {result['attempts']}"
        )

    def _run_route_dna_diagnostic(self):
        deep = self.route_dna_mode_combo.currentData() == "deep"
        confirmed = False
        if deep:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("تأیید آزمایش دقیق")
            box.setText("آزمایش دقیق RouteDNA حداکثر ۴ مگابایت داده دریافت می‌کند.")
            box.setInformativeText(
                "اگر بازی یا دانلود سنگین فعال باشد، آزمایش خودکار متوقف یا سبک می‌شود."
            )
            accept = box.addButton("شروع آزمایش دقیق", QMessageBox.AcceptRole)
            box.addButton("انصراف", QMessageBox.RejectRole)
            box.exec()
            confirmed = box.clickedButton() is accept
            if not confirmed:
                return
        self.route_dna_test_btn.setEnabled(False)
        self.route_dna_test_result.setText("شبکه در حال بررسی است…")
        self.vm.run_route_dna_diagnostic(confirmed)

    def _on_route_dna_geo_toggled(self, enabled: bool):
        if enabled:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("اجازهٔ اطلاعات تقریبی شبکه")
            box.setText(
                "برای پیشنهاد دقیق‌تر، منطقهٔ تقریبی، ASN و نام اپراتور از Backend دریافت شود؟"
            )
            box.setInformativeText(
                "سرور اینترنتی هنگام درخواست طبیعتاً IP را می‌بیند؛ اما LAGSHIFT آن را در "
                "درخواست، حافظهٔ مسیر، گزارش خطا یا رابط ذخیره و نمایش نمی‌دهد. این گزینه "
                "اختیاری است و با خاموش‌کردن، درخواست بعدی متوقف می‌شود."
            )
            accept = box.addButton("اجازه می‌دهم", QMessageBox.AcceptRole)
            box.addButton("فعلاً نه", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not accept:
                self.route_dna_geo_check.blockSignals(True)
                self.route_dna_geo_check.setChecked(False)
                self.route_dna_geo_check.blockSignals(False)
                enabled = False
        self._set_setting("route_dna_remote_geo", enabled)

    def _on_route_dna_diagnostic_ready(self, result: dict):
        self.route_dna_test_btn.setEnabled(True)
        context = result.get("context") or {}
        gateway = context.get("gateway_quality") or {}
        bandwidth = result.get("bandwidth") or {}
        budget = result.get("budget") or {}
        parts = [route_dna_service.summarize(context)]
        if gateway.get("available"):
            parts.append(
                f"Gateway {gateway.get('median_ms')}ms · نوسان {gateway.get('jitter_ms')}ms"
            )
        if bandwidth.get("ok"):
            parts.append(f"سرعت دریافت کنترل‌شده {bandwidth.get('download_mbps')} Mbps")
        else:
            reasons = {
                "backend-unconfigured": "تست سرعت: Backend تنظیم نشده",
                "network-busy": "تست سرعت: شبکه شلوغ یا بازی فعال است",
                "confirmation-required": "تست دقیق تأیید نشد",
                "budget-exhausted": "بودجه امروز تمام شده",
                "incomplete": "دانلود آزمایشی کامل نشد",
            }
            parts.append(reasons.get(bandwidth.get("reason"), "تست سرعت در دسترس نبود"))
        parts.append(f"بودجه باقی‌مانده حدود {budget.get('remaining_kb', 0) // 1024} MB")
        self.route_dna_test_result.setText(" · ".join(parts))

    def resizeEvent(self, event):
        """Keep controls usable on compact windows instead of clipping them."""
        compact = event.size().width() < 620 or event.size().height() < 500
        margin = 10 if compact else 22
        spacing = 7 if compact else 12
        if hasattr(self, "main_root_layout"):
            self.main_root_layout.setContentsMargins(margin, margin, margin, 8)
            self.main_root_layout.setSpacing(spacing)
        if hasattr(self, "header_subtitle"):
            self.header_subtitle.setVisible(not compact)
        if hasattr(self, "home_orb"):
            self.home_orb.setVisible(not compact)
            self.home_orb.set_paused(compact or self.isMinimized() or not self.isActiveWindow())
        if hasattr(self, "game_activity_list"):
            self.game_activity_list.setMaximumHeight(75 if compact else 105)
        super().resizeEvent(event)

    def changeEvent(self, event):
        """Do not spend frames on decorative motion while the app is behind the game."""
        super().changeEvent(event)
        if event.type() in (QEvent.WindowStateChange, QEvent.ActivationChange) and hasattr(self, "home_orb"):
            QTimer.singleShot(
                0,
                lambda: self.home_orb.set_paused(
                    self.width() < 620 or self.isMinimized() or not self.isActiveWindow()
                ),
            )

    # ---------------- Tray ----------------

    def _on_tray_setting_changed(self, checked: bool):
        self.settings = settings_service.set_value("minimize_to_tray", checked)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _quit_app(self):
        self.vm.force_reset_on_exit()
        self.ping_overlay.stop()
        self.game_detection_toast.hide()
        self._unregister_global_hotkey()
        self.tray_icon.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        if self.settings.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "لگ‌شیفت هنوز فعاله",
                "برنامه در پس‌زمینه (Tray) در حال اجراست. برای خروج کامل از منوی آیکون استفاده کن.",
                self.app_icon,
                3000,
            )
        else:
            self.vm.force_reset_on_exit()
            self.ping_overlay.stop()
            self.game_detection_toast.hide()
            self._unregister_global_hotkey()
            self.tray_icon.hide()
            event.accept()
