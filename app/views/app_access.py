"""رابط App Access: پروفایل‌های آماده با نمایش صادقانه مسیر و تست واقعی."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QTimer, QSize, QFileInfo
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QProgressBar, QComboBox, QScrollArea, QSizePolicy,
    QBoxLayout, QToolButton, QFileIconProvider, QCheckBox,
)

from app.services import app_access_service


class AppRouteFlow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(138)
        self.app_name = "Discord"
        self.dns_name = "در حال انتخاب"
        self.warp_label = "فقط پایش"
        self.phase = 0
        self.verified = False
        self.route_kind = ""

    def set_route(self, *, app_name=None, dns_name=None, warp_label=None,
                  phase=None, verified=None, route_kind=None):
        if app_name is not None:
            self.app_name = app_name
        if dns_name is not None:
            self.dns_name = dns_name
        if warp_label is not None:
            self.warp_label = warp_label
        if phase is not None:
            self.phase = int(phase)
        if verified is not None:
            self.verified = bool(verified)
        if route_kind is not None:
            self.route_kind = str(route_kind)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        y = 46
        margin = 48
        usable = max(240, width - margin * 2)
        xs = [margin + usable * index / 3 for index in range(4)]
        active_color = QColor("#62DFFF")
        line_color = QColor("#23414D")
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(int(xs[0]), y, int(xs[-1]), y)
        if self.phase:
            end_index = 3 if self.verified else min(2, self.phase)
            painter.setPen(QPen(QColor("#79EDB5") if self.verified else active_color, 3))
            painter.drawLine(int(xs[0]), y, int(xs[end_index]), y)

        labels = (
            ("دستگاه تو", "Windows", "#62DFFF"),
            ("DNS هوشمند", self.dns_name, "#62DFFF"),
            ("WARP رسمی", self.warp_label, "#718894" if self.warp_label != "فعال و تأییدشده" else "#79EDB5"),
            (self.app_name, "سرویس مقصد", "#79EDB5" if self.verified else "#62DFFF"),
        )
        successful_nodes = {0, 3}
        if self.route_kind == "dns":
            successful_nodes.add(1)
        elif self.route_kind == "warp":
            successful_nodes.update({1, 2})
        for index, (title, detail, color) in enumerate(labels):
            if self.verified and index in successful_nodes:
                color = "#79EDB5"
            rect = QRectF(xs[index] - 23, y - 23, 46, 46)
            painter.setPen(QPen(QColor(color), 1.4))
            painter.setBrush(QColor("#10242D") if index != 2 else QColor("#111B21"))
            painter.drawRoundedRect(rect, 12, 12)
            painter.setPen(QColor(color))
            painter.setFont(QFont("Vazirmatn", 11, QFont.Bold))
            symbol = ("⌁", "DNS", "W", "✓" if self.verified else "APP")[index]
            painter.drawText(rect, Qt.AlignCenter, symbol)
            painter.setPen(QColor("#E8F8FD"))
            painter.setFont(QFont("Vazirmatn", 8, QFont.Bold))
            painter.drawText(QRectF(xs[index] - 65, y + 31, 130, 20), Qt.AlignCenter, title)
            painter.setPen(QColor("#78939E"))
            painter.setFont(QFont("Vazirmatn", 7))
            painter.drawText(QRectF(xs[index] - 70, y + 50, 140, 20), Qt.AlignCenter, detail)


class AppAccessWidget(QWidget):
    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.vm = view_model
        self._profile_list = app_access_service.available_profiles()
        self._profiles = {item.id: item for item in self._profile_list}
        self._profile_rows = {}
        self._buttons = {}
        self._selected_id = self._profile_list[0].id
        self._mission = "smart"
        self._columns = 0
        self._session_profile_id = ""
        self._first_catalog = True
        self._catalog_signature = None
        self._build_ui()
        self.badge_hide_timer = QTimer(self)
        self.badge_hide_timer.setSingleShot(True)
        self.badge_hide_timer.setInterval(4500)
        self.badge_hide_timer.timeout.connect(self.detected_badge.hide)
        self._connect()
        self._select_profile(self._selected_id)
        QTimer.singleShot(100, self.vm.refresh_app_catalog)
        self.catalog_timer = QTimer(self)
        self.catalog_timer.setInterval(4000)
        self.catalog_timer.timeout.connect(self._refresh_visible_catalog)
        self.catalog_timer.start()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self.content = QWidget()
        layout = QVBoxLayout(self.content)
        self.content_layout = layout
        layout.setContentsMargins(16, 16, 16, 18)
        layout.setSpacing(12)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

        hero = QFrame()
        hero.setStyleSheet(
            "QFrame { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #102A35,stop:1 #111827);"
            "border:1px solid #28586B; border-radius:16px; } QLabel { border:none; background:transparent; }"
        )
        self.hero_box = QBoxLayout(QBoxLayout.LeftToRight, hero)
        self.hero_box.setContentsMargins(18, 14, 18, 14)
        copy = QVBoxLayout()
        title = QLabel("🧩 دسترسی هوشمند برنامه‌ها  ·  BETA")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#DFF9FF;")
        copy.addWidget(title)
        subtitle = QLabel("ورود، دانلود و سرویس آنلاین هر برنامه با کمترین تغییر لازم")
        subtitle.setStyleSheet("color:#91AAB5;")
        subtitle.setWordWrap(True)
        copy.addWidget(subtitle)
        self.hero_box.addLayout(copy, 1)
        self.detected_badge = QLabel("در حال شناسایی برنامه‌های نصب‌شده…")
        self.detected_badge.setWordWrap(True)
        self.detected_badge.setTextFormat(Qt.PlainText)
        self.detected_badge.setLayoutDirection(Qt.RightToLeft)
        self.detected_badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.detected_badge.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detected_badge.setStyleSheet(
            "color:#77E8B3; background:#0C211B; border:1px solid #285342;"
            "border-radius:10px; padding:7px 10px;"
        )
        self.hero_box.addWidget(self.detected_badge)
        layout.addWidget(hero)

        self.workspace = QWidget()
        self.workspace_layout = QBoxLayout(QBoxLayout.LeftToRight, self.workspace)
        self.workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_layout.setSpacing(12)
        layout.addWidget(self.workspace)

        self.catalog_panel = QFrame()
        self.catalog_panel.setObjectName("appCatalogPanel")
        self.catalog_panel.setStyleSheet(
            "QFrame#appCatalogPanel { background:#09151B; border:1px solid #1D3540; border-radius:14px; }"
            "QLabel { border:none; background:transparent; }"
        )
        catalog_box = QVBoxLayout(self.catalog_panel)
        catalog_box.setContentsMargins(10, 11, 10, 11)
        catalog_box.setSpacing(9)
        catalog_title = QLabel("پروفایل‌های آماده")
        catalog_title.setStyleSheet("font-weight:bold; color:#D9F6FD; padding:2px 4px;")
        catalog_box.addWidget(catalog_title)

        tools = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔎 نام برنامه یا لانچر را جست‌وجو کن…")
        self.search_input.setClearButtonEnabled(True)
        tools.addWidget(self.search_input, 1)
        self.category_filter = QComboBox()
        for title, value in (
            ("همه", ""), ("لانچرها", "launcher"), ("هوش مصنوعی", "ai"),
            ("توسعه", "developer"), ("درایورها", "driver"),
            ("رسانه", "media"), ("ارتباط", "communication"),
        ):
            self.category_filter.addItem(title, value)
        self.category_filter.setToolTip("دسته‌بندی پروفایل‌ها")
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setObjectName("iconButton")
        self.refresh_button.setToolTip("شناسایی مجدد برنامه‌های نصب‌شده")
        tools.addWidget(self.refresh_button)
        catalog_box.addLayout(tools)
        catalog_box.addWidget(self.category_filter)

        self.apps_frame = QFrame()
        self.apps_frame.setStyleSheet(
            "QFrame { background:#09151B; border:1px solid #1D3540; border-radius:14px; }"
            "QToolButton { background:#0E1B22; border:1px solid #263E49; border-radius:11px;"
            "padding:7px; color:#91AAB5; font-size:11px; }"
            "QToolButton:hover { border-color:#4FC3F7; color:#DFF9FF; }"
            "QToolButton:checked { background:#12303B; border:1px solid #62DFFF;"
            "color:#EAFBFF; font-weight:bold; }"
        )
        self.apps_grid = QGridLayout(self.apps_frame)
        self.apps_grid.setContentsMargins(10, 10, 10, 10)
        self.apps_grid.setSpacing(8)
        for profile in self._profile_list:
            button = QToolButton()
            button.setText(profile.name)
            button.setIcon(self._profile_icon(profile))
            button.setIconSize(QSize(40, 40))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setMinimumHeight(82)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            button.setProperty("filteredOut", False)
            button.setToolTip(profile.description)
            button.clicked.connect(lambda _checked=False, key=profile.id: self._select_profile(key))
            self._buttons[profile.id] = button
        catalog_box.addWidget(self.apps_frame)
        catalog_box.addStretch()
        self.workspace_layout.addWidget(self.catalog_panel)
        self._reflow_apps(2)

        self.details_panel = QWidget()
        details_box = QVBoxLayout(self.details_panel)
        details_box.setContentsMargins(0, 0, 0, 0)
        details_box.setSpacing(10)
        self.workspace_layout.addWidget(self.details_panel, 1)

        selected = QFrame()
        selected.setStyleSheet(
            "QFrame { background:#0B171E; border:1px solid #294550; border-radius:14px; }"
            "QLabel { border:none; background:transparent; }"
        )
        selected_box = QVBoxLayout(selected)
        selected_box.setContentsMargins(16, 14, 16, 14)
        selected_box.setSpacing(10)
        self.selected_head = QBoxLayout(QBoxLayout.LeftToRight)
        self.selected_symbol = QLabel("DS")
        self.selected_symbol.setAlignment(Qt.AlignCenter)
        self.selected_symbol.setFixedSize(44, 44)
        self.selected_head.addWidget(self.selected_symbol)
        selected_copy = QVBoxLayout()
        self.selected_name = QLabel("Discord")
        self.selected_name.setStyleSheet("font-size:16px; font-weight:bold; color:#EAFBFF;")
        selected_copy.addWidget(self.selected_name)
        self.selected_detail = QLabel("ورود، API، CDN و Voice")
        self.selected_detail.setWordWrap(True)
        self.selected_detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.selected_detail.setStyleSheet("color:#8EA6B1;")
        selected_copy.addWidget(self.selected_detail)
        self.selected_head.addLayout(selected_copy, 1)
        self.app_state = QLabel("● هنوز آزمایش نشده")
        self.app_state.setWordWrap(True)
        self.app_state.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.app_state.setStyleSheet("color:#FFD180;")
        self.selected_head.addWidget(self.app_state)
        selected_box.addLayout(self.selected_head)

        mission_title = QLabel("چه مشکلی را حل کنیم؟")
        mission_title.setStyleSheet("font-weight:bold; color:#CFEFF8;")
        selected_box.addWidget(mission_title)
        self.mission_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.mission_buttons = {}
        specs = (
            ("smart", "✨ انتخاب هوشمند", "ورود، API و دانلود با هم بررسی می‌شوند"),
            ("login", "🔐 رفع مشکل ورود", "Login و Authentication"),
            ("download", "⬇ دانلود و آپدیت", "انتخاب DNS و CDN مناسب‌تر"),
        )
        for key, title_text, hint in specs:
            button = QPushButton(f"{title_text}\n{hint}")
            button.setCheckable(True)
            button.setMinimumHeight(55)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, value=key: self._select_mission(value))
            self.mission_layout.addWidget(button)
            self.mission_buttons[key] = button
        selected_box.addLayout(self.mission_layout)

        self.journey_panel = QFrame()
        self.journey_panel.setObjectName("journeyPanel")
        self.journey_panel.setStyleSheet(
            "QFrame#journeyPanel { background:#0D1D25; border:1px solid #244754; border-radius:11px; }"
            "QLabel { border:none; background:transparent; }"
        )
        journey_box = QVBoxLayout(self.journey_panel)
        journey_box.setContentsMargins(12, 9, 12, 9)
        journey_box.setSpacing(4)
        self.journey_title = QLabel("آماده برای شروع · ۴ بررسی کوتاه")
        self.journey_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.journey_title.setStyleSheet("color:#E9FAFF; font-weight:bold; font-size:13px;")
        self.journey_detail = QLabel(
            "اتصال فعلی، DNS، مسیر پشتیبان و مقصدهای برنامه به‌ترتیب بررسی می‌شوند."
        )
        self.journey_detail.setWordWrap(True)
        self.journey_detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.journey_detail.setStyleSheet("color:#89A8B4;")
        self.journey_steps = QLabel("۱ اتصال فعلی   ·   ۲ DNS هوشمند   ·   ۳ تأیید امن   ·   ۴ آماده‌سازی برنامه")
        self.journey_steps.setWordWrap(True)
        self.journey_steps.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.journey_steps.setStyleSheet("color:#607D89; font-size:11px;")
        journey_box.addWidget(self.journey_title)
        journey_box.addWidget(self.journey_detail)
        journey_box.addWidget(self.journey_steps)
        selected_box.addWidget(self.journey_panel)

        self.route_flow = AppRouteFlow()
        selected_box.addWidget(self.route_flow)

        self.truth_label = QLabel(
            "ℹ هنوز هیچ تغییری اعمال نشده؛ ابتدا مسیر فعلی و سپس DNSها روی مقصدهای همین برنامه آزمایش می‌شوند."
        )
        self.truth_label.setWordWrap(True)
        self.truth_label.setTextFormat(Qt.PlainText)
        self.truth_label.setLayoutDirection(Qt.RightToLeft)
        self.truth_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.truth_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.truth_label.setStyleSheet(
            "color:#A7C0CA; background:#101F27; border-radius:9px; padding:9px 11px;"
        )
        selected_box.addWidget(self.truth_label)

        self.metrics_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.metrics_layout.setSpacing(8)
        self.direct_metric = self._metric("مسیر فعلی", "—")
        self.active_metric = self._metric("مسیر انتخاب‌شده", "—")
        self.target_metric = self._metric("مقصد تأییدشده", "۰ از ۰")
        self.metrics_layout.addWidget(self.direct_metric[0])
        self.metrics_layout.addWidget(self.active_metric[0])
        self.metrics_layout.addWidget(self.target_metric[0])
        selected_box.addLayout(self.metrics_layout)

        self.progress_bar = QProgressBar()
        self.warp_fallback_check = QCheckBox(
            "اگر DNS کافی نبود، WARP رسمی را موقتاً آزمایش کن"
        )
        self.warp_fallback_check.setChecked(True)
        self.warp_fallback_check.setToolTip(
            "کلاینت رسمی Cloudflare باید نصب باشد. این حالت ممکن است هنگام آزمایش روی کل دستگاه اثر بگذارد."
        )
        self.warp_fallback_check.setStyleSheet(
            "QCheckBox { color:#A9C5CF; padding:4px; }"
            "QCheckBox::indicator { width:18px; height:18px; }"
        )
        selected_box.addWidget(self.warp_fallback_check)

        self.progress_bar.setRange(0, 4)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background:#172A33; border:none; border-radius:3px; }"
            "QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #62DFFF,stop:1 #78E8B0); border-radius:3px; }"
        )
        selected_box.addWidget(self.progress_bar)

        self.active_session_card = QFrame()
        self.active_session_card.setObjectName("activeAppSession")
        self.active_session_card.setStyleSheet(
            "QFrame#activeAppSession { background:#0D2A21; border:1px solid #42C982; border-radius:12px; }"
            "QLabel { border:none; background:transparent; }"
        )
        session_box = QHBoxLayout(self.active_session_card)
        session_box.setContentsMargins(13, 10, 13, 10)
        session_copy = QVBoxLayout()
        session_copy.setSpacing(2)
        self.session_title = QLabel("● پروفایل فعال است")
        self.session_title.setStyleSheet("color:#79EDB5; font-size:14px; font-weight:bold;")
        self.session_detail = QLabel("مسیر تأییدشده تا زمان قطع یا بسته‌شدن برنامه نگه داشته می‌شود.")
        self.session_detail.setWordWrap(True)
        self.session_detail.setStyleSheet("color:#A9D8C3;")
        session_copy.addWidget(self.session_title)
        session_copy.addWidget(self.session_detail)
        session_box.addLayout(session_copy, 1)
        self.disconnect_button = QPushButton("قطع اتصال و بازگردانی")
        self.disconnect_button.setObjectName("disconnectAppAccess")
        self.disconnect_button.setMinimumHeight(42)
        self.disconnect_button.setStyleSheet(
            "QPushButton { color:#FFE8EB; background:#381921; border:1px solid #FF6680;"
            "border-radius:10px; padding:8px 15px; font-weight:bold; }"
            "QPushButton:hover { background:#51202B; border-color:#FF8A9D; }"
            "QPushButton:pressed { background:#2A1117; }"
            "QPushButton:disabled { color:#866A70; background:#21171A; border-color:#4B3037; }"
        )
        session_box.addWidget(self.disconnect_button)
        self.active_session_card.hide()
        # Keep the active state above the diagnostic details so connection and
        # disconnect are visible immediately, even on shorter windows.
        selected_box.insertWidget(1, self.active_session_card)
        self.selected_panel = selected
        details_box.addWidget(selected)

        self.actions_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.actions_layout.addWidget(QLabel("کارت شبکه:"))
        self.adapter_combo = QComboBox()
        self.adapter_combo.setMinimumWidth(150)
        self.actions_layout.addWidget(self.adapter_combo)
        self.restore_note = QLabel("بازگشت خودکار بعد از بسته‌شدن برنامه روشن است")
        self.restore_note.setStyleSheet("color:#7897A4;")
        self.restore_note.setWordWrap(True)
        self.restore_note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.actions_layout.addWidget(self.restore_note, 1)
        self.connect_button = QPushButton("آزمایش و رفع مشکل Discord")
        self.connect_button.setObjectName("primary")
        self.connect_button.setMinimumHeight(45)
        self.connect_button.setMinimumWidth(215)
        self.connect_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.actions_layout.addWidget(self.connect_button)
        self.cancel_button = QPushButton("لغو بررسی و بازگردانی")
        self.cancel_button.setMinimumHeight(45)
        self.cancel_button.setStyleSheet("border-color:#A45151; color:#FFD4D4;")
        self.cancel_button.hide()
        self.actions_layout.addWidget(self.cancel_button)
        self.launch_button = QPushButton("باز کردن برنامه")
        self.launch_button.setMinimumHeight(45)
        self.launch_button.setEnabled(False)
        self.actions_layout.addWidget(self.launch_button)
        details_box.addLayout(self.actions_layout)

        honesty = QLabel(
            "🔒 LAGSHIFT محتوای رمزگذاری‌شده یا اطلاعات ورود را نمی‌خواند. موفقیت یعنی DNS، TCP و TLS "
            "مقصدهای ثبت‌شده تأیید شده‌اند؛ ورود حساب و عملکرد داخلی باید در خود برنامه بررسی شود."
        )
        honesty.setWordWrap(True)
        honesty.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        honesty.setStyleSheet("color:#7894A0; padding:4px;")
        details_box.addWidget(honesty)
        details_box.addStretch()
        layout.addStretch()

    @staticmethod
    def _metric(title: str, value: str):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background:#0D1B22; border:1px solid #203944; border-radius:10px; }"
            "QLabel { border:none; background:transparent; }"
        )
        box = QVBoxLayout(frame)
        box.setContentsMargins(10, 7, 10, 7)
        caption = QLabel(title)
        caption.setStyleSheet("color:#78939E; font-size:10px;")
        value_label = QLabel(value)
        value_label.setStyleSheet("color:#DDF8FF; font-weight:bold;")
        box.addWidget(caption)
        box.addWidget(value_label)
        return frame, value_label

    @staticmethod
    def _profile_icon(profile, file_path: str = "", installed: bool = False,
                      running: bool = False) -> QIcon:
        pixmap = QPixmap(46, 46)
        pixmap.fill(Qt.transparent)
        from pathlib import Path
        asset = (
            Path(__file__).resolve().parent.parent / "resources" /
            "app_icons" / f"{profile.id}.svg"
        )
        if asset.is_file():
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            background = "#252830" if profile.id == "epic" else profile.color
            painter.setBrush(QColor(background))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(1, 1, 44, 44), 13, 13)
            painter.end()
            logo = QPixmap(28, 28)
            logo.fill(Qt.transparent)
            logo_painter = QPainter(logo)
            QSvgRenderer(str(asset)).render(logo_painter, QRectF(1, 1, 26, 26))
            logo_painter.end()
            # Copilot's identity is its multicolour ribbon.  Keep the SVG's
            # original gradients instead of flattening it to a white glyph.
            if profile.id != "copilot":
                logo_painter = QPainter(logo)
                logo_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                logo_color = "#071014" if profile.id in {"spotify", "rockstar"} else "#FFFFFF"
                logo_painter.fillRect(logo.rect(), QColor(logo_color))
                logo_painter.end()
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(9, 9, logo)
            painter.end()
            file_path = "bundled"
        elif file_path:
            icon = QFileIconProvider().icon(QFileInfo(file_path))
            if not icon.isNull():
                source = icon.pixmap(QSize(42, 42))
                image = source.toImage()
                opaque = neutral_bright = 0
                for y in range(image.height()):
                    for x in range(image.width()):
                        color = image.pixelColor(x, y)
                        if color.alpha() > 40:
                            opaque += 1
                            if min(color.red(), color.green(), color.blue()) > 210 and (
                                max(color.red(), color.green(), color.blue())
                                - min(color.red(), color.green(), color.blue()) < 18
                            ):
                                neutral_bright += 1
                generic_document = opaque and neutral_bright / opaque > 0.28
                if not generic_document:
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.SmoothPixmapTransform)
                    painter.drawPixmap(2, 2, 42, 42, source)
                    painter.end()
                else:
                    file_path = ""
            else:
                file_path = ""
        if not file_path:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(profile.color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(2, 2, 42, 42), 11, 11)
            text_color = "#071014" if profile.color.upper() == "#FFFFFF" else "#FFFFFF"
            painter.setPen(QColor(text_color))
            painter.setFont(QFont("Vazirmatn", 9, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, profile.symbol)
            painter.end()
        if installed or running:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#79EDB5" if running else "#62DFFF"))
            painter.setPen(QPen(QColor("#071014"), 2))
            painter.drawEllipse(QRectF(31, 1, 14, 14))
            painter.setPen(QColor("#071014"))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(QRectF(31, 0, 14, 14), Qt.AlignCenter, "✓")
            painter.end()
        return QIcon(pixmap)

    def _set_truth(self, text: str):
        self.truth_label.setText("\u2067" + str(text) + "\u2069")

    def _connect(self):
        self.search_input.textChanged.connect(self._filter_apps)
        self.category_filter.currentIndexChanged.connect(
            lambda _index: self._filter_apps(self.search_input.text())
        )
        self.refresh_button.clicked.connect(lambda: self.vm.refresh_app_catalog(full=True))
        self.connect_button.clicked.connect(self._toggle_access)
        self.disconnect_button.clicked.connect(self._disconnect_access)
        self.cancel_button.clicked.connect(self.vm.cancel_app_access)
        self.launch_button.clicked.connect(self._launch_selected)
        self.vm.app_catalog_changed.connect(self._on_catalog_changed)
        self.vm.app_access_progress.connect(self._on_progress)
        self.vm.app_access_changed.connect(self._on_access_changed)

    def _refresh_visible_catalog(self):
        if self.isVisible():
            self.vm.refresh_app_catalog(full=False)

    def set_adapters(self, adapters):
        current = self.adapter_combo.currentData()
        self.adapter_combo.clear()
        for adapter in adapters:
            self.adapter_combo.addItem(adapter.name, adapter.name)
        if current:
            index = self.adapter_combo.findData(current)
            if index >= 0:
                self.adapter_combo.setCurrentIndex(index)

    def _select_profile(self, profile_id: str):
        if self._session_profile_id and profile_id != self._session_profile_id:
            self._set_truth("برای انتخاب برنامه‌ای دیگر، ابتدا دسترسی فعال را قطع و تنظیم قبلی را بازگردان.")
            return
        profile = self._profiles[profile_id]
        self._selected_id = profile_id
        for key, button in self._buttons.items():
            button.setChecked(key == profile_id)
        self.selected_name.setText(profile.name)
        self.selected_detail.setText(profile.description)
        self.selected_symbol.setText("")
        self.selected_symbol.setPixmap(self._profile_icon(profile).pixmap(QSize(42, 42)))
        self.selected_symbol.setStyleSheet("background:transparent; border:none;")
        row = self._profile_rows.get(profile_id, {})
        if row.get("running"):
            state = "● در حال اجرا"
            color = "#79EDB5"
        elif row.get("installed"):
            state = "● نصب‌شده · آماده آزمایش"
            color = "#81D4FA"
        elif profile.web_only:
            state = "◉ پروفایل وب · آماده آزمایش"
            color = "#81D4FA"
        else:
            state = "○ روی سیستم شناسایی نشد"
            color = "#90A4AE"
        if not self._session_profile_id:
            self.app_state.setText(state)
            self.app_state.setStyleSheet(f"color:{color};")
            self.connect_button.setText(f"آزمایش و رفع مشکل {profile.name}")
        self.launch_button.setText("باز کردن وب‌سرویس" if profile.launch_url else "اجرای برنامه")
        self.launch_button.setEnabled(bool(profile.launch_url or row.get("executable_path")))
        self.restore_note.setText(
            "برای پروفایل وب، پایان دسترسی را از همین صفحه بزن"
            if profile.web_only else "بازگشت خودکار بعد از بسته‌شدن برنامه روشن است"
        )
        if self._session_profile_id:
            return
        self.route_flow.set_route(
            app_name=profile.name, dns_name="در انتظار",
            warp_label="در صورت نیاز", phase=0, verified=False, route_kind="",
        )
        self.progress_bar.setValue(0)
        self.direct_metric[1].setText("—")
        self.active_metric[1].setText("—")
        self.target_metric[1].setText("۰ از ۰")
        self.journey_title.setText("آماده برای شروع · ۴ بررسی کوتاه")
        self.journey_detail.setText(
            "اتصال فعلی، DNS، مسیر پشتیبان و مقصدهای برنامه به‌ترتیب بررسی می‌شوند."
        )
        self.journey_steps.setText(
            "۱ اتصال فعلی   ·   ۲ DNS هوشمند   ·   ۳ تأیید امن   ·   ۴ آماده‌سازی برنامه"
        )
        self.truth_label.setStyleSheet(
            "color:#A7C0CA; background:#101F27; border-radius:9px; padding:9px 11px;"
        )
        self._set_truth(
            "هنوز تغییری اعمال نشده؛ ابتدا مسیر فعلی و سپس دی‌ان‌اس‌ها روی مقصدهای همین برنامه آزمایش می‌شوند."
        )

    def _select_mission(self, mission: str):
        if self._session_profile_id:
            return
        self._mission = mission
        for key, button in self.mission_buttons.items():
            button.setChecked(key == mission)
        descriptions = {
            "smart": "ورود، ارتباط سرویس و دانلود با هم سنجیده می‌شوند؛ فقط بهترین تغییر تأییدشده نگه داشته می‌شود.",
            "login": "فقط مقصدهای ورود و احراز هویت بررسی می‌شوند تا تغییر شبکه حداقلی بماند.",
            "download": "مسیر دی‌ان‌اس و دریافت محتوا با اولویت تعادل سرعت و پایداری سنجیده می‌شود.",
        }
        self._set_truth(descriptions.get(mission, descriptions["smart"]))

    def _filter_apps(self, text: str):
        query = text.strip().lower()
        category = self.category_filter.currentData() if hasattr(self, "category_filter") else ""
        for key, profile in self._profiles.items():
            filtered_out = bool(
                (query and query not in profile.name.lower())
                or (category and profile.category != category)
            )
            self._buttons[key].setProperty("filteredOut", filtered_out)
            self._buttons[key].setVisible(not filtered_out)
        self._reflow_apps(self._columns or 5)
        self._sync_catalog_height()

    def _sync_catalog_height(self):
        if self.width() >= 760:
            self.catalog_panel.setMinimumHeight(0)
            self.catalog_panel.setMaximumHeight(16777215)
            return
        columns = max(2, self._columns or (3 if self.width() >= 600 else 2))
        visible_count = sum(button.isVisible() for button in self._buttons.values())
        rows = max(1, (visible_count + columns - 1) // columns)
        catalog_height = 184 + rows * 90
        self.catalog_panel.setMinimumHeight(catalog_height)
        self.catalog_panel.setMaximumHeight(catalog_height)

    def _reflow_apps(self, columns: int):
        columns = max(2, columns)
        self._columns = columns
        while self.apps_grid.count():
            self.apps_grid.takeAt(0)
        visible = [
            button for button in self._buttons.values()
            if not bool(button.property("filteredOut"))
        ]
        for index, button in enumerate(visible):
            self.apps_grid.addWidget(button, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        wide = width >= 760
        self.workspace_layout.setDirection(
            QBoxLayout.RightToLeft if wide else QBoxLayout.TopToBottom
        )
        if wide:
            self.hero_box.setDirection(QBoxLayout.LeftToRight)
            self.detected_badge.setMinimumWidth(190)
            self.selected_head.setDirection(QBoxLayout.LeftToRight)
            self.mission_layout.setDirection(QBoxLayout.LeftToRight)
            self.metrics_layout.setDirection(QBoxLayout.LeftToRight)
            self.actions_layout.setDirection(QBoxLayout.LeftToRight)
            self.connect_button.setMinimumWidth(215)
            self.catalog_panel.setMinimumWidth(220)
            self.catalog_panel.setMaximumWidth(245)
            self.catalog_panel.setMinimumHeight(0)
            self.catalog_panel.setMaximumHeight(16777215)
            columns = 2
        else:
            self.hero_box.setDirection(QBoxLayout.TopToBottom)
            self.detected_badge.setMinimumWidth(0)
            self.selected_head.setDirection(QBoxLayout.TopToBottom)
            self.mission_layout.setDirection(QBoxLayout.TopToBottom)
            self.metrics_layout.setDirection(QBoxLayout.TopToBottom if width < 560 else QBoxLayout.LeftToRight)
            self.actions_layout.setDirection(QBoxLayout.TopToBottom)
            self.connect_button.setMinimumWidth(0)
            self.catalog_panel.setMinimumWidth(0)
            self.catalog_panel.setMaximumWidth(16777215)
            columns = 3 if width >= 600 else 2
        if columns != self._columns:
            self._reflow_apps(columns)
        self._sync_catalog_height()
        self.workspace_layout.invalidate()
        self.workspace_layout.activate()
        self.workspace.setMinimumWidth(0)
        self.workspace.setMinimumHeight(self.workspace_layout.sizeHint().height())
        self.content_layout.invalidate()
        self.content_layout.activate()
        self.content.setMinimumWidth(0)
        self.content.setMinimumHeight(self.content_layout.sizeHint().height())

    def _on_catalog_changed(self, rows: list):
        self._profile_rows = {row.get("id"): row for row in rows}
        installed = sum(bool(row.get("installed")) for row in rows)
        running = [row.get("name") for row in rows if row.get("running")]
        signature = (installed, tuple(running))
        if signature != self._catalog_signature:
            self._catalog_signature = signature
            if running:
                self.detected_badge.setText(f"در حال اجرا: {'، '.join(running[:2])}")
            else:
                self.detected_badge.setText(f"{installed} برنامه نصب‌شده شناسایی شد")
            self.detected_badge.show()
            self.badge_hide_timer.start()
        for key, button in self._buttons.items():
            row = self._profile_rows.get(key, {})
            profile = self._profiles[key]
            button.setText({
                "ubisoft": "Ubisoft", "rockstar": "Rockstar",
            }.get(key, profile.name))
            button.setIcon(self._profile_icon(
                profile, row.get("executable_path", ""),
                bool(row.get("installed")), bool(row.get("running")),
            ))
            button.setToolTip(
                profile.description + ("\nدر حال اجرا" if row.get("running") else "\nنصب‌شده" if row.get("installed") else "\nشناسایی نشده")
            )
        running_ids = [row.get("id") for row in rows if row.get("running")]
        if self._first_catalog and running_ids and not self._session_profile_id:
            self._selected_id = running_ids[0]
        self._first_catalog = False
        # A catalog refresh only updates detection/icons.  Re-selecting here
        # used to reset the successful route every four seconds.
        if not self._session_profile_id:
            self._select_profile(self._selected_id)

    def _toggle_access(self):
        session = getattr(self.vm, "_app_access_session", {})
        if session:
            self._set_truth("این پروفایل فعال است؛ برای پایان‌دادن از دکمهٔ قرمز «قطع اتصال و بازگردانی» استفاده کن.")
            return
        adapter = self.adapter_combo.currentData()
        if not adapter:
            self._set_truth("کارت شبکه فعالی برای اعمال دی‌ان‌اس پیدا نشد.")
            return
        self.connect_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.vm.start_app_access(
            self._selected_id, self._mission, adapter,
            allow_warp=self.warp_fallback_check.isChecked(),
        )

    def _disconnect_access(self):
        if not getattr(self.vm, "_app_access_session", {}):
            return
        self.disconnect_button.setEnabled(False)
        self.session_title.setText("◌ در حال قطع امن اتصال…")
        self.session_detail.setText("تنظیم قبلی شبکه در حال بازگردانی است؛ چند لحظه صبر کن.")
        self.vm.stop_app_access()

    def _launch_selected(self):
        ok, message = app_access_service.launch_profile(self._selected_id)
        self._set_truth(message)
        self.truth_label.setStyleSheet(
            ("color:#79EDB5; background:#0F261F;" if ok else
             "color:#FF9B91; background:#2A1719;")
            + " border-radius:9px; padding:9px 11px;"
        )

    def _on_progress(self, progress: dict):
        step = int(progress.get("step", 0))
        self.progress_bar.setRange(0, max(1, int(progress.get("total", 3))))
        self.progress_bar.setValue(step)
        self._set_truth(progress.get("message", "در حال بررسی…"))
        phase = progress.get("phase")
        stage_titles = {
            "baseline": "مرحله ۱ از ۴ · سنجش اتصال فعلی",
            "ranking": "مرحله ۲ از ۴ · پیدا کردن بهترین DNS",
            "verify": "مرحله ۳ از ۴ · تأیید امن مقصدهای برنامه",
            "warp": "مرحله ۴ از ۴ · آزمایش مسیر رسمی WARP",
            "restore": "بازگردانی امن تنظیمات شبکه",
        }
        self.journey_title.setText(stage_titles.get(phase, "در حال آماده‌سازی مسیر…"))
        self.journey_detail.setText(progress.get("message", "در حال بررسی…"))
        completed = max(0, min(4, step - 1))
        stage_names = ("اتصال فعلی", "DNS هوشمند", "تأیید امن", "آماده‌سازی برنامه")
        self.journey_steps.setText("   ·   ".join(
            ("✓ " if index < completed else "● " if index == completed else "○ ") + name
            for index, name in enumerate(stage_names)
        ))
        dns_name = "در حال آزمایش" if phase == "ranking" else "در حال تأیید" if phase == "verify" else "تنظیم فعلی"
        warp_label = "در حال آزمایش" if phase == "warp" else None
        self.route_flow.set_route(
            dns_name=dns_name, warp_label=warp_label, phase=step, verified=False
        )
        self.app_state.setText("◌ تحلیل مسیر در حال اجراست")
        self.app_state.setStyleSheet("color:#62DFFF;")
        self._set_controls_locked(True)
        self.active_session_card.hide()

    def _set_controls_locked(self, locked: bool):
        for button in self._buttons.values():
            button.setEnabled(not locked)
        for button in self.mission_buttons.values():
            button.setEnabled(not locked)
        self.search_input.setEnabled(not locked)
        self.refresh_button.setEnabled(not locked)
        self.category_filter.setEnabled(not locked)
        self.adapter_combo.setEnabled(not locked)
        self.warp_fallback_check.setEnabled(not locked)

    def _on_access_changed(self, result: dict):
        if result.get("operation") == "route_drift":
            drift = result.get("drift") or {}
            self.session_title.setText("◌ شبکه تغییر کرد؛ نتیجه قبلی دیگر مبنای انتخاب نیست")
            self.session_detail.setText(
                f"{drift.get('reason', 'مسیر ورودی تغییر کرده است')}؛ اتصال فعال حفظ شده و آزمون بعدی با شبکه تازه انجام می‌شود."
            )
            return
        if result.get("operation") == "evidence":
            evidence = result.get("evidence") or {}
            connections = int(evidence.get("connections", 0))
            self.app_state.setText(
                f"● در حال اجرا · {connections} ارتباط واقعی مشاهده شد"
                if connections else "● در حال اجرا · منتظر ارتباط سرویس"
            )
            self.app_state.setStyleSheet("color:#79EDB5;")
            if self._session_profile_id and self.active_session_card.isVisible():
                live_text = (
                    f"{connections} ارتباط واقعی همین برنامه دیده شد"
                    if connections else "پروفایل فعال است؛ منتظر اولین ارتباط سرویس"
                )
                self.session_detail.setText(live_text + " · مسیر تأییدشده همچنان برقرار است")
            return
        self.connect_button.setEnabled(True)
        self.cancel_button.hide()
        if result.get("operation") == "stop":
            if result.get("ok"):
                self._session_profile_id = ""
                self._set_controls_locked(False)
                self.app_state.setText("○ متوقف · تنظیم قبلی بازگردانی شد")
                self.app_state.setStyleSheet("color:#90A4AE;")
                self._set_truth("دسترسی برنامه متوقف شد و تغییر موقتی شبکه باقی نماند.")
                self.route_flow.set_route(dns_name="تنظیم قبلی", phase=0, verified=False)
                self.progress_bar.setValue(0)
                self.connect_button.setText(f"آزمایش و رفع مشکل {self._profiles[self._selected_id].name}")
                self.connect_button.show()
                self.active_session_card.hide()
                self.disconnect_button.setEnabled(True)
                self.journey_title.setText("اتصال با موفقیت قطع شد")
                self.journey_detail.setText("تنظیم قبلی شبکه بازگردانی شد و چیزی از پروفایل موقت باقی نماند.")
                self.journey_steps.setText("○ اتصال فعلی   ·   ○ DNS هوشمند   ·   ○ تأیید امن   ·   ○ برنامه")
            else:
                self._set_truth(result.get("error", "بازگردانی کامل نشد"))
                self._set_controls_locked(True)
                self.disconnect_button.setEnabled(True)
                self.session_title.setText("⚠ بازگردانی کامل نشد")
                self.session_detail.setText("یک‌بار دیگر دکمهٔ قطع را بزن یا برنامه را با دسترسی مدیر اجرا کن.")
            return
        if not result.get("ok"):
            self._session_profile_id = ""
            self._set_controls_locked(False)
            self.app_state.setText(
                "○ بررسی لغو شد" if result.get("cancelled") else "● مسیر تأیید نشد"
            )
            self.app_state.setStyleSheet("color:#FF8A80;")
            error = result.get("error", "مسیر قابل استفاده پیدا نشد")
            self._set_truth(error)
            self.route_flow.set_route(dns_name="بدون تغییر", phase=0, verified=False)
            self.progress_bar.setValue(0)
            self.connect_button.setText("تلاش دوباره")
            self.connect_button.show()
            self.active_session_card.hide()
            self.journey_title.setText("مسیر قابل استفاده پیدا نشد")
            probe = result.get("last_probe") or result.get("baseline") or {}
            attempted = int(probe.get("attempted", 0) or 0)
            tls_ok = int(probe.get("tls_ok", 0) or 0)
            tested = int(result.get("dns_candidates_tested", 0) or 0)
            baseline = result.get("baseline") or {}
            baseline_ms = int(baseline.get("median_ms", -1) or -1)
            self.direct_metric[1].setText(
                f"{baseline_ms} ms" if baseline_ms >= 0 else "مسدود"
            )
            self.active_metric[1].setText(
                f"{tested} DNS آزموده شد" if tested else "بدون مسیر سالم"
            )
            self.target_metric[1].setText(f"{tls_ok} از {attempted}")
            if probe.get("suspected_sinkhole"):
                self.journey_detail.setText(
                    "DNS مقصدها را به یک IP خصوصیِ بسته فرستاد؛ برای این شبکه مسیر ترافیکی سالم لازم است."
                )
            else:
                self.journey_detail.setText(
                    "همهٔ تغییرهای آزمایشی برگشت داده شدند و تنظیم شبکه دست‌نخورده است."
                )
            self.journey_steps.setText("✓ اتصال فعلی   ·   ✓ DNS بررسی شد   ·   × تأیید نشد   ·   ○ برنامه")
            return
        after = result.get("after") or {}
        baseline = result.get("baseline") or {}
        self._session_profile_id = result.get("profile_id", self._selected_id)
        self._selected_id = self._session_profile_id
        self._set_controls_locked(True)
        dns_name = result.get("dns_name", "تنظیم فعلی")
        route = result.get("route", "current")
        route_label = {
            "current": "مسیر مستقیم · بدون تغییر",
            "dns": f"DNS هوشمند · {dns_name}",
            "warp": result.get("warp_mode_label", "WARP رسمی"),
        }.get(route, dns_name)
        warp_label = "فعال و تأییدشده" if route == "warp" or result.get("warp_active") else "دست‌نخورده"
        self.app_state.setText("● آماده استفاده")
        self.app_state.setStyleSheet("color:#79EDB5;")
        self._set_truth(
            f"مسیر آماده شد — زمان پاسخ میانه: {after.get('median_ms', '—')} میلی‌ثانیه — "
            f"روش انتخابی: {route_label}. {result.get('message', '')}"
        )
        self.truth_label.setStyleSheet(
            "color:#79EDB5; background:#0F261F; border-radius:9px; padding:9px 11px;"
        )
        self.route_flow.set_route(
            dns_name=dns_name, warp_label=warp_label, phase=4, verified=True,
            route_kind=route,
        )
        self.progress_bar.setRange(0, 4)
        self.progress_bar.setValue(4)
        direct_ms = baseline.get("median_ms", -1)
        after_ms = after.get("median_ms", -1)
        self.direct_metric[1].setText(f"{direct_ms} ms" if direct_ms >= 0 else "ناموفق")
        self.active_metric[1].setText(f"{after_ms} ms" if after_ms >= 0 else "—")
        self.target_metric[1].setText(f"{after.get('tls_ok', 0)} از {after.get('attempted', 0)}")
        self.journey_title.setText("✓ مسیر آماده و در حال استفاده است")
        self.journey_detail.setText(
            f"بهترین مسیر برای {self._profiles[self._selected_id].name} پیدا شد: {route_label}. "
            "مقصدهای لازم هم با موفقیت پاسخ دادند."
            + (f" RouteDNA: {result.get('route_dna_explanation') or self._route_dna_summary(result.get('route_dna') or {})}."
               if result.get("route_dna") else "")
        )
        route_steps = {
            "current": "✓ اتصال فعلی سالم   ·   — DNS لازم نشد   ·   — WARP لازم نشد   ·   ✓ برنامه آماده",
            "dns": "✓ اتصال سنجیده شد   ·   ✓ DNS انتخاب شد   ·   ✓ مقصدها تأیید شد   ·   ✓ برنامه آماده",
            "warp": "✓ اتصال سنجیده شد   ·   ✓ DNS بررسی شد   ·   ✓ WARP تأیید شد   ·   ✓ برنامه آماده",
        }
        self.journey_steps.setText(route_steps.get(route, "✓ همهٔ بررسی‌های لازم کامل شد"))
        self.session_title.setText(f"● پروفایل {self._profiles[self._selected_id].name} فعال است")
        self.session_detail.setText(
            f"مسیر فعال: {route_label} · نتیجهٔ بررسی: "
            f"{after.get('tls_ok', 0)} از {after.get('attempted', 0)} مقصد آماده است"
        )
        self.disconnect_button.setEnabled(True)
        self.active_session_card.show()
        self.connect_button.hide()

    @staticmethod
    def _route_dna_summary(context: dict) -> str:
        labels = {"wifi": "Wi‑Fi", "ethernet": "کابل", "virtual": "کارت مجازی", "other": "شبکه"}
        kind = labels.get(context.get("adapter_kind"), "شبکه")
        pressure = "ترافیک بالا" if context.get("pressure") == "busy" else "فشار عادی"
        return f"{kind}، {pressure}، انتخاب بر پایه تست همین دستگاه"
