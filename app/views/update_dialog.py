"""Polished, non-blocking update journey for signed LAGSHIFT releases."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from app.app_info import APP_VERSION
from app.views.brand import RoutePrismWidget, load_brand_fonts


class UpdateDialog(QDialog):
    download_requested = Signal()
    cancel_requested = Signal()
    install_requested = Signal(bool)

    def __init__(self, manifest: dict, parent=None):
        super().__init__(parent)
        load_brand_fonts()
        self.manifest = dict(manifest)
        self._phase = "available"
        self._publisher_signed = False
        self.setWindowTitle("آپدیت امن LAGSHIFT")
        self.setModal(False)
        self.setMinimumSize(610, 520)
        self.resize(690, 570)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(self._style())
        self._build_ui()

    @staticmethod
    def _style() -> str:
        return """
        QDialog { background:#061015; color:#F2FBFF; font-family:'Vazirmatn'; }
        QFrame#hero { background:#0A1921; border:1px solid #1C4655; border-radius:22px; }
        QFrame#trust { background:#091820; border:1px solid #173846; border-radius:15px; }
        QLabel#title { color:#F2FBFF; font-size:25px; font-weight:800; }
        QLabel#version { color:#55E3FA; font-size:15px; font-weight:700; }
        QLabel#muted { color:#8EAFBC; }
        QLabel#status { color:#CFF8FF; font-size:15px; font-weight:700; }
        QLabel#trustChip { color:#9FF3CF; background:#0D2A24; border:1px solid #216B55;
                           border-radius:10px; padding:7px 10px; }
        QPlainTextEdit#releaseNotes { color:#D6EAF2; background:#07141B;
            border:1px solid #173846; border-radius:14px; padding:10px; font-size:13px; }
        QProgressBar { background:#0B202A; border:1px solid #214957; border-radius:10px;
                       height:17px; text-align:center; color:#F2FBFF; font-weight:700; }
        QProgressBar::chunk { border-radius:9px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #20D9F5,stop:1 #8A38F5); }
        QPushButton { background:#0E2029; border:1px solid #315260; border-radius:12px;
                      padding:11px 18px; color:#EAF8FF; font-weight:700; }
        QPushButton:hover:!disabled { border-color:#55E3FA; background:#12303B; }
        QPushButton#primary { border:1px solid #62E7FA; color:#061015; font-size:14px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3CDAF4,stop:1 #7A62FF); }
        QPushButton#primary:disabled { color:#75909A; background:#172A32; border-color:#29434E; }
        QCheckBox { color:#FFD8A8; spacing:9px; }
        """

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 20)
        root.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        self.mark = RoutePrismWidget()
        self.mark.setFixedSize(70, 70)
        hero_layout.addWidget(self.mark)
        title_box = QVBoxLayout()
        title = QLabel("نسخهٔ تازه آماده است")
        title.setObjectName("title")
        version = str(self.manifest.get("version", "جدید"))
        version_label = QLabel(f"LAGSHIFT {APP_VERSION}  ←  نسخهٔ {version}")
        version_label.setObjectName("version")
        subtitle = QLabel("دانلود از کانال رسمی و کنترل کامل فایل پیش از نصب")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(version_label)
        title_box.addWidget(subtitle)
        hero_layout.addLayout(title_box, 1)
        root.addWidget(hero)

        trust = QFrame()
        trust.setObjectName("trust")
        trust_layout = QHBoxLayout(trust)
        trust_layout.setContentsMargins(12, 10, 12, 10)
        for text in ("✓ مانیفست Ed25519", "✓ کنترل SHA-256", "↻ ادامهٔ دانلود"):
            chip = QLabel(text)
            chip.setObjectName("trustChip")
            chip.setAlignment(Qt.AlignCenter)
            trust_layout.addWidget(chip)
        root.addWidget(trust)

        notes_title = QLabel("تغییرات این نسخه")
        notes_title.setStyleSheet("font-size:15px; font-weight:800; color:#DDF9FF;")
        root.addWidget(notes_title)
        notes_text = str(
            self.manifest.get("notes") or "بهبود پایداری و امنیت به‌روزرسانی."
        )
        notes = QPlainTextEdit(notes_text)
        notes.setObjectName("releaseNotes")
        notes.setReadOnly(True)
        notes.setMaximumHeight(150)
        notes_palette = notes.palette()
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            notes_palette.setColor(group, QPalette.Text, QColor("#D6EAF2"))
            notes_palette.setColor(group, QPalette.Base, QColor("#07141B"))
        notes.setPalette(notes_palette)
        notes.viewport().setPalette(notes_palette)
        root.addWidget(notes)

        self.status_label = QLabel("برای دریافت نسخهٔ تأییدشده آماده است")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("آماده")
        root.addWidget(self.progress)
        self.progress_detail = QLabel("فایل فقط از آدرس امضاشدهٔ انتشار دریافت می‌شود.")
        self.progress_detail.setObjectName("muted")
        self.progress_detail.setWordWrap(True)
        root.addWidget(self.progress_detail)

        self.unsigned_acceptance = QCheckBox(
            "می‌دانم این نسخه Authenticode ندارد و ممکن است Windows پیام Unknown publisher نشان دهد."
        )
        self.unsigned_acceptance.hide()
        self.unsigned_acceptance.toggled.connect(self._sync_install_button)
        root.addWidget(self.unsigned_acceptance)

        actions = QHBoxLayout()
        self.primary_button = QPushButton("دانلود امن آپدیت")
        self.primary_button.setObjectName("primary")
        self.primary_button.clicked.connect(self._primary_clicked)
        self.secondary_button = QPushButton("بعداً")
        self.secondary_button.clicked.connect(self._secondary_clicked)
        actions.addWidget(self.primary_button, 1)
        actions.addWidget(self.secondary_button)
        root.addLayout(actions)

    def _primary_clicked(self) -> None:
        if self._phase in {"available", "error", "paused"}:
            self.set_downloading()
            self.download_requested.emit()
        elif self._phase == "ready":
            self.set_installing()
            self.install_requested.emit(not self._publisher_signed)

    def _secondary_clicked(self) -> None:
        if self._phase == "downloading":
            self.cancel_requested.emit()
            self.set_paused()
        else:
            self.reject()

    def set_downloading(self) -> None:
        self._phase = "downloading"
        self.mark.set_busy(True)
        self.status_label.setText("در حال دریافت نسخه از GitHub…")
        self.progress.setFormat("در حال شروع…")
        self.primary_button.setEnabled(False)
        self.primary_button.setText("در حال دانلود")
        self.secondary_button.setText("توقف و ادامه بعداً")
        self.unsigned_acceptance.hide()

    def set_progress(self, received: int, total: int) -> None:
        if self._phase != "downloading":
            return
        total = max(1, int(total))
        received = max(0, min(int(received), total))
        percent = int(received * 100 / total)
        self.progress.setValue(percent)
        self.progress.setFormat(f"٪{percent}")
        self.progress_detail.setText(
            f"{received / 1048576:.1f} از {total / 1048576:.1f} مگابایت · بررسی هم‌زمان اندازه و هش"
        )

    def set_ready(self, publisher_signed: bool) -> None:
        self._phase = "ready"
        self._publisher_signed = bool(publisher_signed)
        self.mark.set_busy(False)
        self.progress.setValue(100)
        self.progress.setFormat("تأیید شد ✓")
        self.status_label.setText("دانلود کامل شد؛ امضا و SHA-256 دوباره بررسی می‌شوند")
        self.primary_button.setText("نصب و راه‌اندازی مجدد")
        self.secondary_button.setText("نصب در فرصت بعد")
        if publisher_signed:
            self.progress_detail.setText("امضای ناشر ویندوز نیز معتبر است؛ آمادهٔ نصب.")
            self.primary_button.setEnabled(True)
        else:
            self.progress_detail.setText(
                "کانال OMNIARC و محتوای فایل تأیید شده‌اند؛ این نسخه امضای پولی ویندوز ندارد."
            )
            self.unsigned_acceptance.setChecked(False)
            self.unsigned_acceptance.show()
            self.primary_button.setEnabled(False)

    def set_error(self, message: str) -> None:
        self._phase = "error"
        self.mark.set_busy(False)
        self.status_label.setText("دانلود امن کامل نشد")
        self.progress.setValue(0)
        self.progress.setFormat("نیاز به تلاش دوباره")
        self.progress_detail.setText(message)
        self.primary_button.setText("تلاش دوباره")
        self.primary_button.setEnabled(True)
        self.secondary_button.setText("بستن")

    def set_paused(self) -> None:
        self._phase = "paused"
        self.mark.set_busy(False)
        self.status_label.setText("دانلود متوقف شد")
        self.progress_detail.setText("بخش دریافت‌شده امن نگه داشته شد و دفعهٔ بعد ادامه پیدا می‌کند.")
        self.primary_button.setText("ادامهٔ دانلود")
        self.primary_button.setEnabled(True)
        self.secondary_button.setText("بستن")

    def set_installing(self) -> None:
        self._phase = "installing"
        self.mark.set_busy(True)
        self.status_label.setText("در حال تحویل امن به نصب‌کننده…")
        self.primary_button.setText("در حال اجرا")
        self.primary_button.setEnabled(False)
        self.secondary_button.setEnabled(False)

    def restore_ready_after_install_error(self, message: str) -> None:
        self.set_ready(self._publisher_signed)
        self.progress_detail.setText(message)

    def _sync_install_button(self) -> None:
        if self._phase == "ready" and not self._publisher_signed:
            self.primary_button.setEnabled(self.unsigned_acceptance.isChecked())

    def closeEvent(self, event) -> None:
        if self._phase == "downloading":
            self.cancel_requested.emit()
        self.mark.set_busy(False)
        super().closeEvent(event)
