"""
اورلی شناور پینگ — یه پنجره‌ی کوچیک، بدون فریم، همیشه روی بقیه‌ی پنجره‌ها
(Always on Top)، که پینگ لحظه‌ای رو حین بازی نشون می‌ده.
"""
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtGui import QMouseEvent


class PingOverlay(QWidget):
    def __init__(self, get_target_fn):
        """
        get_target_fn: تابعی بدون آرگومان که (host, port) یا None برمی‌گردونه —
        این‌طوری اورلی خودش نمی‌دونه سرور فعلی چیه، از ویومدل می‌پرسه.
        """
        super().__init__()
        self._get_target = get_target_fn
        self._drag_offset = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(225, 58)
        self._score = None
        self._loss = None

        self.setStyleSheet("""
            QWidget#overlayRoot {
                background-color: rgba(18, 18, 18, 210);
                border-radius: 10px;
                border: 1px solid rgba(79, 195, 247, 120);
            }
            QLabel {
                color: #E0E0E0;
                font-size: 13px;
                font-weight: bold;
            }
        """)

        self.setObjectName("overlayRoot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self.label = QLabel("⚡ در انتظار اتصال...")
        self.label.setObjectName("")  # استایل جدا نگیره از QWidget#overlayRoot
        layout.addWidget(self.label)

        # موقعیت پیش‌فرض: گوشه‌ی بالا-راست صفحه
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 24, 24)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)

    def start(self):
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def update_ping(self, latency_ms: int):
        if latency_ms < 0:
            self.label.setText("⚠️ بدون پاسخ")
        elif latency_ms < 60:
            self.label.setText(self._format_value("🟢", latency_ms))
        elif latency_ms < 120:
            self.label.setText(self._format_value("🟡", latency_ms))
        else:
            self.label.setText(self._format_value("🔴", latency_ms))

    def set_quality(self, score: int, loss: float):
        self._score = score
        self._loss = loss

    def _format_value(self, icon: str, latency_ms: int) -> str:
        detail = f" · امتیاز {self._score}" if self._score is not None else ""
        if self._loss is not None:
            detail += f" · افت {self._loss:g}%"
        return f"{icon} {latency_ms} ms{detail}"

    def _refresh(self):
        target = self._get_target()
        if not target:
            self.label.setText("⭕ تانلی وصل نیست")
            return
        # تست واقعی تو ویومدل انجام می‌شه (ترد جدا)؛ این متد فقط UI رو آپدیت می‌کنه
        # از بیرون صدا زده می‌شه (به ping_result_ready وصل می‌شه)

    # --- قابلیت جابه‌جا کردن با درگ ماوس، چون پنجره فریم نداره ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_offset = None
