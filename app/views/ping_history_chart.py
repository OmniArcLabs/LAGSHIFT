"""
یه نمودار خطی سبک برای تاریخچه‌ی پینگ/جیتر، با QPainter خام رسم می‌شه
(بدون نیاز به کتابخونه‌ی خارجی مثل pyqtgraph/matplotlib، برای سبک موندن اپ).
"""
from collections import deque
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QLinearGradient, QPainterPath
from PySide6.QtWidgets import QWidget


class PingHistoryChart(QWidget):
    def __init__(self, max_points: int = 60, parent=None):
        super().__init__(parent)
        self.max_points = max_points
        self.values = deque(maxlen=max_points)  # لتنسی به میلی‌ثانیه، -1 برای بدون پاسخ
        self.setMinimumHeight(140)

    def add_value(self, latency_ms: int):
        self.values.append(latency_ms)
        self.update()

    def clear_history(self):
        self.values.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(self.rect(), QColor("#1A1A1A"))

        if len(self.values) < 2:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "هنوز داده‌ای برای نمودار نیست")
            painter.end()
            return

        valid_values = [v for v in self.values if v >= 0]
        max_val = max(valid_values) if valid_values else 100
        max_val = max(max_val, 50) * 1.15  # کمی حاشیه بالای نمودار

        step_x = rect.width() / max(1, (self.max_points - 1))
        points = []
        for i, v in enumerate(self.values):
            x = rect.left() + i * step_x
            if v < 0:
                points.append(None)
                continue
            y = rect.bottom() - (v / max_val) * rect.height()
            points.append((x, y))

        painter.setPen(QPen(QColor("#2A2A2A"), 1))
        for frac in (0.25, 0.5, 0.75):
            y = rect.bottom() - frac * rect.height()
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

        path = QPainterPath()
        started = False
        for p in points:
            if p is None:
                started = False
                continue
            if not started:
                path.moveTo(*p)
                started = True
            else:
                path.lineTo(*p)

        painter.setPen(QPen(QColor("#4FC3F7"), 2))
        painter.drawPath(path)

        last_valid = next((v for v in reversed(self.values) if v >= 0), None)
        if last_valid is not None:
            painter.setPen(QColor("#E0E0E0"))
            painter.drawText(
                QRectF(rect.left(), rect.top(), rect.width(), 20),
                Qt.AlignLeft | Qt.AlignTop,
                f"آخرین: {last_valid} ms",
            )

        painter.end()
