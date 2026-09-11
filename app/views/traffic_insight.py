"""Non-technical UI for the domestic/full-tariff URL analyzer."""
from __future__ import annotations

import threading
import urllib.parse

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.services import official_warp_service, settings_service, traffic_tariff_service


class _TrafficSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class TrafficInsightWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _TrafficSignals(self)
        self._signals.completed.connect(self._show_result)
        self._signals.failed.connect(self._show_error)
        self._busy = False
        self._build()
        self._render_history()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(13)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        hero = QFrame()
        hero.setObjectName("homeFocus")
        hero_box = QVBoxLayout(hero)
        title = QLabel("🧭 راهنمای تعرفهٔ دانلود")
        title.setStyleSheet("font-size:19px; font-weight:bold; color:#DFF9FF;")
        hero_box.addWidget(title)
        note = QLabel(
            "آدرس دقیق صفحه یا فایل را وارد کن. لگ‌شیفت تغییر مسیر و میزبان نهایی دانلود را "
            "بررسی می‌کند و فقط با مدرک معتبر نتیجه می‌دهد."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9FC2D0;")
        hero_box.addWidget(note)
        input_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.ir/download/file.zip")
        self.url_input.setLayoutDirection(Qt.LeftToRight)
        self.url_input.returnPressed.connect(self._start)
        self.analyze_btn = QPushButton("بررسی تعرفه و مسیر")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self._start)
        input_row.addWidget(self.url_input, 1)
        input_row.addWidget(self.analyze_btn)
        hero_box.addLayout(input_row)
        privacy = QLabel(
            "🔒 محتوای دانلود خوانده نمی‌شود؛ توکن و عبارت بعد از ? یا # نه نمایش داده می‌شود و نه ذخیره."
        )
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color:#79CDBE; font-size:11px;")
        hero_box.addWidget(privacy)
        layout.addWidget(hero)

        options = QFrame()
        options.setObjectName("homeStat")
        options_box = QVBoxLayout(options)
        operator_row = QHBoxLayout()
        operator_row.addWidget(QLabel("اپراتور اینترنت:"))
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(("نامشخص", "همراه اول", "ایرانسل", "رایتل", "مخابرات", "شاتل", "آسیاتک", "سایر"))
        self.operator_combo.setToolTip("فعلاً برای توضیح نتیجه است؛ فهرست تعرفه هر اپراتور باید معتبر و به‌روز باشد")
        operator_row.addWidget(self.operator_combo, 1)
        options_box.addLayout(operator_row)
        self.vpn_check = QCheckBox("VPN یا فیلترشکن دیگری روشن است")
        self.vpn_check.setToolTip("در این حالت مسیر دیده‌شده ممکن است با مسیر صورتحساب اپراتور فرق کند")
        options_box.addWidget(self.vpn_check)
        self.history_check = QCheckBox("نتیجهٔ خلاصه و بدون آدرس محرمانه روی همین دستگاه بماند")
        self.history_check.setChecked(settings_service.load_settings().get("traffic_insight_history", False))
        self.history_check.toggled.connect(
            lambda checked: settings_service.set_value("traffic_insight_history", bool(checked))
        )
        options_box.addWidget(self.history_check)
        layout.addWidget(options)

        self.result_card = QFrame()
        self.result_card.setObjectName("homeStat")
        result_box = QVBoxLayout(self.result_card)
        self.result_title = QLabel("برای شروع، یک لینک وارد کن")
        self.result_title.setStyleSheet("font-size:16px; font-weight:bold; color:#CFF7FF;")
        self.result_title.setWordWrap(True)
        result_box.addWidget(self.result_title)
        self.result_summary = QLabel(
            "نتیجه می‌تواند «ثبت‌شده داخلی»، «ترکیبی» یا «قابل تأیید نیست» باشد."
        )
        self.result_summary.setWordWrap(True)
        self.result_summary.setStyleSheet("color:#9BB3BF;")
        result_box.addWidget(self.result_summary)
        self.result_details = QListWidget()
        self.result_details.setMaximumHeight(150)
        self.result_details.hide()
        result_box.addWidget(self.result_details)
        layout.addWidget(self.result_card)

        explain = QLabel(
            "نکته: نیم‌بها یا داخلی‌بودن در نهایت توسط اپراتور روی صورتحساب اعمال می‌شود. "
            "اگر نتیجه با صورتحساب فرق داشت، رسید دانلود را نگه دار و از مسیر شکایت ۱۹۵ پیگیری کن."
        )
        explain.setWordWrap(True)
        explain.setStyleSheet("color:#8FAAB5; padding:4px;")
        layout.addWidget(explain)

        history_card = QFrame()
        history_card.setObjectName("homeStat")
        history_box = QVBoxLayout(history_card)
        history_head = QHBoxLayout()
        history_head.addWidget(QLabel("تاریخچهٔ خصوصی همین دستگاه"))
        history_head.addStretch()
        clear_btn = QPushButton("پاک‌کردن")
        clear_btn.clicked.connect(self._clear_history)
        history_head.addWidget(clear_btn)
        history_box.addLayout(history_head)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(130)
        history_box.addWidget(self.history_list)
        layout.addWidget(history_card)
        layout.addStretch()

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.analyze_btn.setDisabled(busy)
        self.url_input.setDisabled(busy)
        self.analyze_btn.setText("در حال بررسی مسیر…" if busy else "بررسی تعرفه و مسیر")

    def _start(self):
        if self._busy:
            return
        value = self.url_input.text().strip()
        if not value:
            self._show_error("اول آدرس دقیق سایت یا فایل را وارد کن")
            return
        self._set_busy(True)
        self.result_title.setText("در حال دنبال‌کردن مسیر واقعی لینک…")
        self.result_summary.setText("DNS، تغییر مسیر و میزبان نهایی بدون دریافت محتوای فایل بررسی می‌شوند.")
        self.result_details.hide()
        user_reports_vpn = self.vpn_check.isChecked()

        def worker():
            try:
                warp = official_warp_service.inspect()
                result = traffic_tariff_service.analyze_url(
                    value,
                    traffic_tariff_service.load_trusted_catalog(),
                    warp_or_vpn_active=bool(warp.connected or user_reports_vpn),
                )
                self._signals.completed.emit(result)
            except traffic_tariff_service.TariffAnalysisError as exc:
                self._signals.failed.emit(str(exc))
            except Exception:
                self._signals.failed.emit("بررسی لینک کامل نشد؛ اتصال اینترنت و خود لینک را دوباره بررسی کن")

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result):
        self._set_busy(False)
        colors = {"domestic": "#67E8B2", "mixed": "#FFD166", "unknown": "#FFB3BA"}
        self.result_title.setText(result.title)
        self.result_title.setStyleSheet(
            f"font-size:16px; font-weight:bold; color:{colors.get(result.classification, '#CFF7FF')};"
        )
        final_host = urllib.parse.urlsplit(result.final_url).hostname or "—"
        size = "نامشخص"
        if result.content_length is not None:
            size = f"{result.content_length / (1024 * 1024):.1f} مگابایت"
        self.result_summary.setText(
            f"میزبان نهایی: {final_host}  ·  اطمینان: {result.confidence}  ·  "
            f"اندازهٔ اعلام‌شده: {size}  ·  {len(result.steps) - 1} تغییر مسیر"
        )
        self.result_details.clear()
        for reason in result.reasons:
            self.result_details.addItem("• " + reason)
        if result.warning:
            self.result_details.addItem("⚠ " + result.warning)
        self.result_details.addItem("منبع: " + result.catalog_source)
        self.result_details.show()
        if self.history_check.isChecked():
            traffic_tariff_service.remember_result(result)
            self._render_history()

    def _show_error(self, message: str):
        self._set_busy(False)
        self.result_title.setText("بررسی کامل نشد")
        self.result_title.setStyleSheet("font-size:16px; font-weight:bold; color:#FF9AA5;")
        self.result_summary.setText(message)
        self.result_details.hide()

    def _render_history(self):
        labels = {"domestic": "داخلی", "mixed": "ترکیبی", "unknown": "نامشخص"}
        self.history_list.clear()
        rows = traffic_tariff_service.load_history()
        if not rows:
            self.history_list.addItem("تاریخچه‌ای ذخیره نشده است")
            return
        for row in reversed(rows):
            suffix = f" · {row['extension']}" if row["extension"] else ""
            self.history_list.addItem(
                f"{row['host']}{suffix} — {labels.get(row['classification'], 'نامشخص')}"
            )

    def _clear_history(self):
        traffic_tariff_service.clear_history()
        self._render_history()
