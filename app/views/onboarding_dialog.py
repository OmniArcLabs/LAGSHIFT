"""Short, explicit first-run choices for new installations."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from app.services import settings_service
from app.views.brand import RoutePrismWidget


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("آماده‌سازی LAGSHIFT")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QDialog { background:#071014; color:#EAF8FF; font-size:13px; }
            QLabel { color:#DDF7FF; }
            QComboBox { min-height:28px; padding:7px 11px; background:#0C1921;
                border:1px solid #294958; border-radius:10px; }
            QCheckBox { padding:5px; spacing:8px; }
            QPushButton { min-height:38px; border-radius:10px; padding:7px 16px;
                background:#10232C; border:1px solid #294958; color:#EAF8FF; }
            QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #55DFFF,stop:1 #6F70FF); color:#041116; font-weight:bold; border:none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        head = QHBoxLayout()
        mark = RoutePrismWidget()
        mark.setFixedSize(72, 72)
        head.addWidget(mark)
        heading = QLabel(
            "<h2>اتصال را برای خودت تنظیم کن</h2>"
            "<p style='color:#9FC2D0'>سه انتخاب کوتاه؛ بعداً همه از تنظیمات قابل تغییرند.</p>"
        )
        head.addWidget(heading, 1)
        layout.addLayout(head)

        layout.addWidget(QLabel("بیشتر برای چه کاری از LAGSHIFT استفاده می‌کنی؟"))
        self.goal = QComboBox()
        self.goal.addItem("بازی آنلاین و لانچرها", "games")
        self.goal.addItem("برنامه‌ها، ورود و دانلود", "apps")
        self.goal.addItem("هر دو", "balanced")
        layout.addWidget(self.goal)

        layout.addWidget(QLabel("اینترنت اصلی این دستگاه چیست؟"))
        self.network = QComboBox()
        self.network.addItem("تشخیص خودکار", "auto")
        self.network.addItem("ثابت / Wi-Fi / فیبر", "fixed")
        self.network.addItem("همراه / Hotspot", "mobile")
        layout.addWidget(self.network)

        self.route_dna = QCheckBox("RouteDNA برای پیشنهاد شخصی همین شبکه روشن باشد")
        self.route_dna.setChecked(True)
        layout.addWidget(self.route_dna)
        disclosure = QLabel(
            "RouteDNA نوع اتصال، پینگ، نوسان، MTU و نتیجهٔ تست را بررسی می‌کند. شناسهٔ شبکه "
            "هش‌شده و محلی است؛ IP کامل، نام Wi‑Fi، تاریخچهٔ مرور و محتوای ترافیک ذخیره یا "
            "ارسال نمی‌شوند. اطلاعات تقریبی اپراتور نیز جداگانه و پیش‌فرض خاموش است."
        )
        disclosure.setWordWrap(True)
        disclosure.setStyleSheet(
            "color:#8FC6D4; background:#0B1A21; border:1px solid #1D3A47;"
            "border-radius:10px; padding:10px;"
        )
        layout.addWidget(disclosure)
        self.light_test = QCheckBox("پس از ورود، یک بررسی سبک و کم‌مصرف آماده باشد")
        self.light_test.setChecked(True)
        layout.addWidget(self.light_test)

        actions = QHBoxLayout()
        later = QPushButton("بعداً")
        later.clicked.connect(self.reject)
        finish = QPushButton("ذخیره و ورود به LAGSHIFT")
        finish.setObjectName("primary")
        finish.clicked.connect(self._save)
        actions.addWidget(later)
        actions.addWidget(finish, 1)
        layout.addLayout(actions)

    def _save(self):
        settings = settings_service.load_settings()
        settings.update({
            "onboarding_completed": True,
            "onboarding_primary_goal": self.goal.currentData() or "games",
            "onboarding_network_kind": self.network.currentData() or "auto",
            "onboarding_run_light_test": self.light_test.isChecked(),
            "route_dna_enabled": self.route_dna.isChecked(),
        })
        settings_service.save_settings(settings)
        self.accept()
