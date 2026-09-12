"""Non-technical UI for the domestic/full-tariff URL analyzer."""
from __future__ import annotations

import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.services import (
    linkirani_service, official_warp_service, operator_detection_service, settings_service,
    traffic_tariff_service,
)


class _TrafficSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class TrafficInsightWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _TrafficSignals(self)
        self._signals.completed.connect(self._show_result)
        self._signals.failed.connect(self._show_error)
        self._signals.progress.connect(self._show_progress)
        self._busy = False
        self._last_result = None
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
        title = QLabel("🧭 تشخیص تعرفهٔ داخلی")
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
        final_link_note = QLabel(
            "برای نتیجهٔ دقیق دانلود، لینک نهایی‌ای را وارد کن که IDM یا مرورگر واقعاً دریافت می‌کند؛ "
            "آدرس صفحهٔ سایت ممکن است روی سرور دیگری باشد."
        )
        final_link_note.setWordWrap(True)
        final_link_note.setStyleSheet("color:#FFD98A; font-size:11px;")
        hero_box.addWidget(final_link_note)
        source_row = QHBoxLayout()
        official_btn = QPushButton("استعلام رسمی ITO")
        official_btn.setToolTip("بازکردن مرجع رسمی تعرفهٔ داخلی در مرورگر")
        official_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            "https://eservices.ito.gov.ir/page/IPListSearch"
        )))
        complaint_btn = QPushButton("پیگیری از ۱۹۵")
        complaint_btn.setToolTip("برای گزارش اعمال‌نشدن تعرفهٔ داخلی")
        complaint_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://195.cra.ir")))
        source_row.addWidget(official_btn)
        source_row.addWidget(complaint_btn)
        source_row.addStretch()
        hero_box.addLayout(source_row)
        layout.addWidget(hero)

        options = QFrame()
        options.setObjectName("homeStat")
        options_box = QVBoxLayout(options)
        operator_row = QHBoxLayout()
        operator_row.addWidget(QLabel("اپراتور اینترنت:"))
        self.operator_combo = QComboBox()
        for label, value in (
            ("تشخیص خودکار (پیشنهادی)", "auto"), ("نامشخص", "نامشخص"),
            ("همراه اول", "همراه اول"), ("ایرانسل", "ایرانسل"),
            ("رایتل", "رایتل"), ("مخابرات", "مخابرات"),
            ("شاتل", "شاتل"), ("آسیاتک", "آسیاتک"),
            ("مبین‌نت", "مبین‌نت"), ("پارس‌آنلاین", "پارس‌آنلاین"),
            ("پیشگامان", "پیشگامان"), ("سایر", "سایر"),
        ):
            self.operator_combo.addItem(label, value)
        stored = settings_service.load_settings()
        wanted = "auto" if stored.get("traffic_operator_mode") == "auto" else str(
            stored.get("traffic_operator_manual", "نامشخص")
        )
        index = self.operator_combo.findData(wanted)
        self.operator_combo.setCurrentIndex(max(0, index))
        self.operator_combo.currentIndexChanged.connect(self._operator_changed)
        self.operator_combo.setToolTip(
            "انتخاب دستی همیشه بر تشخیص خودکار اولویت دارد"
        )
        operator_row.addWidget(self.operator_combo, 1)
        options_box.addLayout(operator_row)
        self.operator_note = QLabel(
            "تشخیص خودکار هنگام بررسی، یک درخواست کوچک به Cloudflare می‌فرستد. Cloudflare مانند هر "
            "سایت دیگری IP اتصال را می‌بیند؛ LAGSHIFT خود IP را نمایش، ذخیره یا وارد گزارش نمی‌کند."
        )
        self.operator_note.setWordWrap(True)
        self.operator_note.setStyleSheet("color:#79CDBE; font-size:11px;")
        self.operator_note.setVisible(self.operator_combo.currentData() == "auto")
        options_box.addWidget(self.operator_note)
        self.linkirani_check = QCheckBox("استعلام کمکی LinkIrani برای نتیجه دقیق‌تر")
        self.linkirani_check.setChecked(stored.get("traffic_linkirani_enabled", False))
        self.linkirani_check.setToolTip(
            "فقط آدرس میزبان نهایی بدون مسیر، query و token به LinkIrani فرستاده می‌شود"
        )
        self.linkirani_check.toggled.connect(self._linkirani_toggled)
        options_box.addWidget(self.linkirani_check)
        linkirani_note = QLabel(
            "در صورت روشن‌بودن، فقط نام میزبان نهایی به سرویس ثالث LinkIrani فرستاده می‌شود؛ "
            "پاسخ آن با برچسب «احتمالی» نمایش داده می‌شود و تضمین اپراتور نیست."
        )
        linkirani_note.setWordWrap(True)
        linkirani_note.setStyleSheet("color:#8FAAB5; font-size:11px;")
        options_box.addWidget(linkirani_note)
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
            "نتیجه می‌تواند «ثبت‌شده برای تعرفهٔ داخلی»، «مسیر ترکیبی» یا «قابل تأیید نیست» باشد."
        )
        self.result_summary.setWordWrap(True)
        self.result_summary.setStyleSheet("color:#9BB3BF;")
        result_box.addWidget(self.result_summary)
        self.result_details = QListWidget()
        self.result_details.setMaximumHeight(230)
        self.result_details.hide()
        result_box.addWidget(self.result_details)
        result_actions = QHBoxLayout()
        self.details_btn = QPushButton("نمایش جزئیات فنی")
        self.details_btn.setCheckable(True)
        self.details_btn.setDisabled(True)
        self.details_btn.toggled.connect(self._toggle_details)
        result_actions.addWidget(self.details_btn)
        self.copy_receipt_btn = QPushButton("کپی رسید بررسی")
        self.copy_receipt_btn.setToolTip("رسید فقط شامل میزبان و IP است؛ مسیر و توکن محرمانه حذف می‌شود")
        self.copy_receipt_btn.setDisabled(True)
        self.copy_receipt_btn.clicked.connect(self._copy_receipt)
        result_actions.addWidget(self.copy_receipt_btn)
        result_actions.addStretch()
        result_box.addLayout(result_actions)
        layout.addWidget(self.result_card)

        explain = QLabel(
            "نکته: «ثبت در فهرست تعرفهٔ داخلی» تضمین نمی‌کند دقیقاً نصف حجم کم شود؛ "
            "ضریب نهایی را اپراتور و نوع بسته تعیین می‌کنند. اگر نتیجه با صورتحساب فرق داشت، "
            "رسید بررسی را نگه دار و از مسیر ۱۹۵ پیگیری کن."
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
        self.operator_combo.setDisabled(busy)
        self.linkirani_check.setDisabled(busy)
        self.analyze_btn.setText("در حال بررسی مسیر…" if busy else "بررسی تعرفه و مسیر")

    def _operator_changed(self):
        value = self.operator_combo.currentData() or "نامشخص"
        if value == "auto":
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("اجازهٔ تشخیص خودکار اپراتور")
            box.setText("برای نتیجهٔ شخصی‌تر، اپراتور اینترنت به‌صورت خودکار تشخیص داده شود؟")
            box.setInformativeText(
                "یک درخواست کوچک به سرویس رسمی Cloudflare فرستاده می‌شود. Cloudflare مثل هر "
                "سایت دیگری IP اتصال را می‌بیند؛ LAGSHIFT خود IP را نمایش، ذخیره یا وارد "
                "گزارش نمی‌کند. هر زمان بخواهی می‌توانی اپراتور را دستی انتخاب کنی."
            )
            accept = box.addButton("فعال‌کردن تشخیص خودکار", QMessageBox.AcceptRole)
            box.addButton("فعلاً نه", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not accept:
                manual = settings_service.load_settings().get(
                    "traffic_operator_manual", "نامشخص"
                )
                index = self.operator_combo.findData(manual)
                self.operator_combo.blockSignals(True)
                self.operator_combo.setCurrentIndex(max(1, index))
                self.operator_combo.blockSignals(False)
                value = self.operator_combo.currentData() or "نامشخص"
        settings_service.set_value("traffic_operator_mode", "auto" if value == "auto" else "manual")
        if value != "auto":
            settings_service.set_value("traffic_operator_manual", value)
        self.operator_note.setVisible(value == "auto")

    def _linkirani_toggled(self, checked: bool):
        allowed = bool(checked)
        if allowed:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("اجازهٔ استعلام کمکی LinkIrani")
            box.setText("برای دقیق‌ترشدن نتیجه، میزبان نهایی لینک از LinkIrani پرسیده شود؟")
            box.setInformativeText(
                "فقط نام میزبان نهایی (مثل example.ir) ارسال می‌شود؛ مسیر فایل، عبارت جست‌وجو، "
                "توکن و محتوای دانلود روی دستگاه می‌مانند. پاسخ LinkIrani ثالث و غیرتضمینی است."
            )
            accept = box.addButton("اجازه می‌دهم", QMessageBox.AcceptRole)
            box.addButton("فعلاً نه", QMessageBox.RejectRole)
            box.exec()
            allowed = box.clickedButton() is accept
        if allowed != bool(checked):
            self.linkirani_check.blockSignals(True)
            self.linkirani_check.setChecked(allowed)
            self.linkirani_check.blockSignals(False)
        settings_service.set_value("traffic_linkirani_enabled", allowed)

    def _toggle_details(self, checked: bool):
        self.result_details.setVisible(bool(checked and self._last_result is not None))
        self.details_btn.setText("بستن جزئیات فنی" if checked else "نمایش جزئیات فنی")

    def _start(self):
        if self._busy:
            return
        value = self.url_input.text().strip()
        if not value:
            self._show_error("اول آدرس دقیق سایت یا فایل را وارد کن")
            return
        self._set_busy(True)
        self.copy_receipt_btn.setText("کپی رسید بررسی")
        self.copy_receipt_btn.setDisabled(True)
        self.result_title.setText("در حال دنبال‌کردن مسیر واقعی لینک…")
        self.result_summary.setText("DNS، تغییر مسیر و میزبان نهایی بدون دریافت محتوای فایل بررسی می‌شوند.")
        self.result_details.hide()
        self.details_btn.setChecked(False)
        self.details_btn.setDisabled(True)
        user_reports_vpn = self.vpn_check.isChecked()
        selected_operator = self.operator_combo.currentData() or "نامشخص"
        use_linkirani = self.linkirani_check.isChecked()

        def worker():
            try:
                self._signals.progress.emit(
                    "در حال شناخت اتصال و بررسی روشن‌بودن WARP/VPN…"
                )
                # Both lookups are read-only and independent. Running them in
                # parallel keeps automatic ISP detection from slowing the URL check.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    warp_future = pool.submit(
                        official_warp_service.trace_says_warp_on, 2.5
                    )
                    hint_future = (
                        pool.submit(operator_detection_service.detect, timeout_s=3.5)
                        if selected_operator == "auto" else None
                    )
                    warp_active = bool(warp_future.result())
                    detected_hint = hint_future.result() if hint_future is not None else None
                self._signals.progress.emit(
                    "اتصال شناخته شد؛ مسیرهای انتقال لینک تا میزبان نهایی دنبال می‌شوند…"
                )
                tunnel_active = bool(warp_active or user_reports_vpn)
                if selected_operator == "auto":
                    hint = (
                        operator_detection_service.OperatorHint(source="tunnel-active")
                        if tunnel_active else detected_hint
                    )
                    operator_name = hint.name
                    operator_source = hint.source
                    operator_confidence = hint.confidence
                else:
                    operator_name = selected_operator
                    operator_source = "manual"
                    operator_confidence = "انتخاب کاربر"
                result = traffic_tariff_service.analyze_url(
                    value,
                    traffic_tariff_service.load_trusted_catalog(),
                    warp_or_vpn_active=tunnel_active,
                    operator_name=operator_name,
                    operator_source=operator_source,
                    operator_confidence=operator_confidence,
                )
                if use_linkirani:
                    self._signals.progress.emit(
                        "میزبان نهایی پیدا شد؛ پاسخ کمکی LinkIrani در حال مقایسه است…"
                    )
                    evidence = linkirani_service.check(result.final_url)
                    result = traffic_tariff_service.merge_external_evidence(result, evidence)
                self._signals.completed.emit(result)
            except traffic_tariff_service.TariffAnalysisError as exc:
                self._signals.failed.emit(str(exc))
            except Exception:
                self._signals.failed.emit("بررسی لینک کامل نشد؛ اتصال اینترنت و خود لینک را دوباره بررسی کن")

        threading.Thread(target=worker, daemon=True).start()

    def _show_progress(self, message: str):
        if self._busy:
            self.result_title.setText("در حال بررسی تعرفه و مسیر…")
            self.result_summary.setText(message)

    def _show_result(self, result):
        self._set_busy(False)
        self._last_result = result
        self.copy_receipt_btn.setEnabled(True)
        self.details_btn.setEnabled(True)
        colors = {
            "domestic": "#67E8B2", "likely_domestic": "#8BE7C0",
            "mixed": "#FFD166", "unknown": "#FFB3BA",
        }
        self.result_title.setText(result.title)
        self.result_title.setStyleSheet(
            f"font-size:16px; font-weight:bold; color:{colors.get(result.classification, '#CFF7FF')};"
        )
        final_host = urllib.parse.urlsplit(result.final_url).hostname or "—"
        size = "نامشخص"
        if result.content_length is not None:
            size = f"{result.content_length / (1024 * 1024):.1f} مگابایت"
        operator_text = result.operator_name
        if result.operator_source == "tunnel-active":
            operator_text = "به‌علت VPN/WARP قابل تشخیص نیست"
        elif result.operator_source == "unavailable":
            operator_text = "خودکار ناموفق؛ می‌توانی دستی انتخاب کنی"
        source_summary = (
            f"\nمنبع کمکی: {result.external_source} · پاسخ احتمالی و غیرتضمینی"
            if result.external_checked else ""
        )
        self.result_summary.setText(
            f"{result.reasons[0] if result.reasons else result.title}\n"
            f"اپراتور: {operator_text} · اطمینان نتیجه: {result.confidence}"
            f"{source_summary}"
        )
        self.result_details.clear()
        for reason in result.reasons:
            self.result_details.addItem("• " + reason)
        for index, step in enumerate(result.steps, start=1):
            state = "ثبت‌شده" if step.registered else "تأییدنشده"
            evidence = f" ({' و '.join(step.evidence)})" if step.evidence else ""
            families = []
            if any(":" not in address for address in step.addresses):
                families.append("IPv4")
            if any(":" in address for address in step.addresses):
                families.append("IPv6")
            self.result_details.addItem(
                f"مسیر {index}: {step.host} · HTTP {step.status} · {state}{evidence} · "
                f"{'+'.join(families) or 'IP نامشخص'} · {', '.join(step.addresses)}"
            )
        if result.warning:
            self.result_details.addItem("⚠ " + result.warning)
        if result.external_checked:
            self.result_details.addItem(
                f"منبع کمکی: {result.external_source} · پاسخ ثالث و غیرتضمینی"
            )
        source_line = "منبع: " + result.catalog_source
        if result.catalog_revision:
            source_line += f" · نسخه {result.catalog_revision}"
        if result.catalog_updated_at:
            source_line += f" · بروزرسانی {result.catalog_updated_at}"
        self.result_details.addItem(source_line)
        self.result_details.setVisible(self.details_btn.isChecked())
        if self.history_check.isChecked():
            traffic_tariff_service.remember_result(result)
            self._render_history()

    def _show_error(self, message: str):
        self._set_busy(False)
        self._last_result = None
        self.copy_receipt_btn.setDisabled(True)
        self.details_btn.setChecked(False)
        self.details_btn.setDisabled(True)
        self.result_title.setText("بررسی کامل نشد")
        self.result_title.setStyleSheet("font-size:16px; font-weight:bold; color:#FF9AA5;")
        self.result_summary.setText(message)
        self.result_details.hide()

    def _render_history(self):
        labels = {
            "domestic": "ثبت‌شده", "likely_domestic": "احتمالاً داخلی",
            "mixed": "ترکیبی", "unknown": "تأییدنشده",
        }
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

    def _copy_receipt(self):
        result = self._last_result
        if result is None:
            return
        lines = [
            "رسید بررسی تعرفهٔ داخلی LAGSHIFT",
            f"نتیجه: {result.title}",
            f"اطمینان: {result.confidence}",
            f"زمان بررسی: {result.checked_at}",
            f"اپراتور انتخاب‌شده: {result.operator_name}",
            f"روش تشخیص اپراتور: {result.operator_source} | اطمینان: {result.operator_confidence}",
            f"میزبان مبدأ: {urllib.parse.urlsplit(result.requested_url).hostname or '—'}",
            f"میزبان نهایی: {urllib.parse.urlsplit(result.final_url).hostname or '—'}",
        ]
        for index, step in enumerate(result.steps, start=1):
            state = "ثبت‌شده" if step.registered else "تأییدنشده"
            lines.append(
                f"مسیر {index}: {step.host} | {', '.join(step.addresses)} | "
                f"HTTP {step.status} | {state}"
            )
        lines.append(f"فهرست: {result.catalog_source} | نسخه: {result.catalog_revision or 'نامشخص'}")
        if result.external_checked:
            lines.append(f"منبع کمکی: {result.external_source} | پاسخ ثالث و غیرتضمینی")
        if result.catalog_updated_at:
            lines.append("تاریخ فهرست: " + result.catalog_updated_at)
        if result.warning:
            lines.append("هشدار: " + result.warning)
        lines.append(
            "این نتیجه ثبت فنی مسیر است و ضریب نهایی مصرف بسته را تضمین نمی‌کند؛ "
            "رسیدگی به اعمال تعرفه با اپراتور و سامانه ۱۹۵ است."
        )
        QApplication.clipboard().setText("\n".join(lines))
        self.copy_receipt_btn.setText("رسید کپی شد ✓")
