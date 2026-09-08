"""First-run, explicit acceptance for the product terms and privacy notice."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_info import PRIVACY_VERSION, TERMS_VERSION
from app.services import settings_service
from app.views.brand import RoutePrismWidget


TERMS_TEXT = """
<h2>استفاده مسئولانه از LAGSHIFT</h2>
<p>LAGSHIFT یک نرم‌افزار مستقل برای بررسی، مدیریت و بهینه‌سازی اتصال بازی‌های آنلاین و برنامه‌های پشتیبانی‌شده است که با تمرکز بر نیازهای کاربران ایرانی طراحی شده است.</p>
<h3>هدف محصول</h3>
<p>LAGSHIFT سرویس VPN عمومی یا ابزار دسترسی آزاد به تمام اینترنت نیست. قابلیت‌های DNS، AppRoute و WARP Bridge فقط برای بررسی و بهبود اتصال بازی‌ها، لانچرها و برنامه‌هایی ارائه می‌شوند که در کاتالوگ محصول مشخص شده‌اند.</p>
<h3>استفاده مجاز</h3>
<p>استفاده برای فعالیت غیرقانونی، آسیب‌رسان، نفوذ، ایجاد اختلال، دسترسی بدون مجوز یا عبور عمومی ترافیک نامرتبط با پروفایل انتخابی مجاز نیست. کاربر موظف است قوانین محل استفاده، شرایط سرویس مقصد و حقوق اشخاص ثالث را رعایت کند.</p>
<h3>WARP Bridge رسمی</h3>
<p>WARP Bridge یک قابلیت اختیاری و آزمایشی است که فقط کلاینت رسمی و دارای امضای Cloudflare را، پس از تأیید صریح کاربر، کنترل می‌کند. در حالت WARP ممکن است تمام ترافیک دستگاه موقتاً از شبکه Cloudflare عبور کند و این اتصال محدود به پردازش بازی نیست.</p>
<p>LAGSHIFT فایل اجرایی Cloudflare را بازتوزیع نمی‌کند، محصول Cloudflare نیست و دسترسی، کیفیت یا ادامه فعالیت این سرویس ثالث را تضمین نمی‌کند. نصب، پذیرش شرایط Cloudflare و نگهداری حساب برعهده کاربر است.</p>
<p>کاربر موظف است شرایط استفاده Cloudflare و قوانین محل استفاده خود را رعایت کند. LAGSHIFT کاهش قطعی پینگ، دسترسی بدون وقفه یا عملکرد یکسان روی همه ارائه‌دهندگان اینترنت را تضمین نمی‌کند.</p>
<h3>تغییرات شبکه</h3>
<p>برخی قابلیت‌ها برای تغییر DNS یا مسیر موقت WARP به مجوز ویندوز نیاز دارند. برنامه وضعیت قبلی را نگه می‌دارد و پس از قطع، خطا یا بازیابی اضطراری برای بازگرداندن آن تلاش می‌کند.</p>
<h3>حریم خصوصی</h3>
<p>ارسال داده‌های اختیاری مانند Radar بدون رضایت جداگانه انجام نمی‌شود. پذیرش این شرایط به‌معنای رضایت برای ارسال اطلاعات اختیاری نیست.</p>
<p>AppRoute فقط نتیجه فنی، روش اتصال و شناسه هش‌شده شبکه را به‌صورت محلی نگه می‌دارد. محتوای TLS، رمز عبور، پیام‌ها و داده ورود خوانده یا ذخیره نمی‌شوند. کاتالوگ آنلاین فقط در صورت پیکربندی کانال رسمی و تأیید امضای دیجیتال پذیرفته می‌شود.</p>
<p>جعبه‌سیاه محلی می‌تواند خطا، نسخه برنامه و آخرین مراحل فنیِ پاک‌سازی‌شده را فقط روی همین دستگاه نگه دارد. این گزارش شامل کلید اتصال، نشانی IP، نام کاربری یا محتوای شخصی نیست و بدون اقدام روشن کاربر برای سازنده ارسال نمی‌شود. ثبت محلی از تنظیمات قابل غیرفعال‌سازی و پاک‌کردن است.</p>
<h3>مسئولیت</h3>
<p>کاربر مسئول نحوه استفاده از نرم‌افزار است. سازنده، تا حدی که قوانین لازم‌الاجرا اجازه می‌دهند، مسئول استفاده برخلاف این شرایط یا اختلال و تغییرات سرویس Cloudflare WARP و سایر سرویس‌های ثالث نیست. حقوق قانونی غیرقابل‌سلب مصرف‌کننده محفوظ است.</p>
"""


class TermsDialog(QDialog):
    def __init__(self, parent=None, *, review_only: bool = False):
        super().__init__(parent)
        self.setWindowTitle("شروع امن LAGSHIFT")
        self.setMinimumSize(620, 600)
        self.resize(720, 680)
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QDialog { background:#071014; color:#EAF8FF; font-size:13px; }
            QLabel { color:#DDF7FF; }
            QScrollArea { background:#0A151C; border:1px solid #1D3A47; border-radius:14px; }
            QCheckBox { spacing:9px; padding:6px; color:#D8F5FF; }
            QPushButton { min-height:38px; border-radius:10px; padding:7px 16px; background:#10232C; border:1px solid #294958; color:#EAF8FF; }
            QPushButton#accept { min-height:48px; background:#102027; color:#60747D; border:1px solid #243942; font-size:14px; font-weight:bold; }
            QPushButton#accept[ready="true"] { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #35E47A,stop:1 #75F3A5); color:#03150B; border:1px solid #8CFFB4; }
            QPushButton:disabled { background:#102027; color:#60747D; }
        """)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        mark = RoutePrismWidget()
        mark.setFixedSize(74, 74)
        title = QLabel("<h1>LAGSHIFT</h1><p>قبل از شروع، استفاده مسئولانه را تأیید کن.</p>")
        header.addWidget(mark)
        header.addWidget(title, 1)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        text = QLabel(TERMS_TEXT)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setOpenExternalLinks(False)
        body_layout.addWidget(text)
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        self.terms_check = QCheckBox("شرایط استفاده را خوانده‌ام و می‌پذیرم.")
        self.privacy_check = QCheckBox("سیاست حریم خصوصی را مطالعه کرده‌ام.")
        self.scope_check = QCheckBox("می‌دانم LAGSHIFT سرویس VPN عمومی نیست و WARP فقط برای پروفایل بازی یا برنامه انتخاب‌شده آزمایش می‌شود.")
        for checkbox in (self.terms_check, self.privacy_check, self.scope_check):
            checkbox.toggled.connect(self._sync_accept_button)
            layout.addWidget(checkbox)

        actions = QHBoxLayout()
        decline = QPushButton("بستن" if review_only else "نمی‌پذیرم و خارج می‌شوم")
        decline.clicked.connect(self.reject)
        self.accept_button = QPushButton("می‌پذیرم و ادامه می‌دهم")
        self.accept_button.setObjectName("accept")
        self.accept_button.setProperty("ready", False)
        self.accept_button.setEnabled(False)
        self.accept_glow = QGraphicsDropShadowEffect(self.accept_button)
        self.accept_glow.setBlurRadius(30)
        self.accept_glow.setOffset(0, 0)
        self.accept_glow.setColor(QColor(53, 228, 122, 190))
        self.accept_glow.setEnabled(False)
        self.accept_button.setGraphicsEffect(self.accept_glow)
        self.accept_button.clicked.connect(self._accept_terms)
        actions.addWidget(decline)
        actions.addWidget(self.accept_button, 1)
        layout.addLayout(actions)
        if review_only:
            for checkbox in (self.terms_check, self.privacy_check, self.scope_check):
                checkbox.hide()
            self.accept_button.hide()

    def _sync_accept_button(self):
        ready = (
            self.terms_check.isChecked()
            and self.privacy_check.isChecked()
            and self.scope_check.isChecked()
        )
        self.accept_button.setEnabled(ready)
        self.accept_button.setProperty("ready", ready)
        self.accept_glow.setEnabled(ready)
        self.accept_button.style().unpolish(self.accept_button)
        self.accept_button.style().polish(self.accept_button)

    def _accept_terms(self):
        settings = settings_service.load_settings()
        settings.update({
            "terms_accepted_version": TERMS_VERSION,
            "privacy_acknowledged_version": PRIVACY_VERSION,
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
        })
        settings_service.save_settings(settings)
        self.accept()
