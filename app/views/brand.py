"""LAGSHIFT visual identity and lightweight startup motion."""
from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPointF, QRectF, Qt, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget


CYAN = QColor("#20D9F5")
VIOLET = QColor("#8A38F5")
INK = QColor("#050A0E")
WHITE = QColor("#F2FBFF")


def load_brand_fonts() -> None:
    """Load the bundled font before the splash is shown, including frozen builds."""
    from pathlib import Path
    font_dir = Path(__file__).resolve().parent.parent / "resources" / "fonts"
    for name in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
        path = font_dir / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def _stroke_path(painter: QPainter, points: list[tuple[float, float]], color: QColor,
                 width: float, progress: float = 1.0) -> None:
    """Draw a short polyline progressively without needing SVG at runtime."""
    if len(points) < 2 or progress <= 0:
        return
    progress = max(0.0, min(1.0, progress))
    lengths = []
    total = 0.0
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        lengths.append(length)
        total += length
    remaining = total * progress
    path = QPainterPath()
    path.moveTo(*points[0])
    for index, length in enumerate(lengths):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        if remaining >= length:
            path.lineTo(x2, y2)
            remaining -= length
            continue
        if length > 0 and remaining > 0:
            ratio = remaining / length
            path.lineTo(x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio)
        break
    pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)


def draw_route_prism(painter: QPainter, rect: QRectF, progress: float = 1.0,
                     monochrome: bool = False, glow: bool = False) -> None:
    """Draw the Route Prism mark: candidate routes become one selected route."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    size = min(rect.width(), rect.height())
    x = rect.center().x() - size / 2
    y = rect.center().y() - size / 2
    sx = lambda value: x + size * value
    sy = lambda value: y + size * value
    line = max(2.0, size * 0.075)
    cyan = WHITE if monochrome else CYAN
    violet = WHITE if monochrome else VIOLET
    gate = WHITE

    incoming = max(0.0, min(1.0, progress / 0.42))
    gate_in = max(0.0, min(1.0, (progress - 0.20) / 0.38))
    outgoing = max(0.0, min(1.0, (progress - 0.52) / 0.34))
    losing_alpha = 1.0 if progress < 0.72 else max(0.28, 1.0 - (progress - 0.72) / 0.28 * 0.72)

    if glow and progress > 0.08:
        glow_color = QColor(cyan)
        glow_color.setAlpha(28)
        for extra in (line * 2.2, line * 1.25):
            _stroke_path(
                painter,
                [(sx(.08), sy(.30)), (sx(.32), sy(.30)), (sx(.48), sy(.46))],
                glow_color, line + extra, incoming,
            )

    for lane_y, target_y in ((.30, .46), (.50, .50), (.70, .54)):
        color = QColor(cyan)
        if lane_y != .50:
            color.setAlphaF(losing_alpha)
        _stroke_path(
            painter,
            [(sx(.08), sy(lane_y)), (sx(.31), sy(lane_y)), (sx(.48), sy(target_y))],
            color, line, incoming,
        )

    gate_color = QColor(gate)
    gate_color.setAlphaF(gate_in)
    _stroke_path(
        painter,
        [(sx(.46), sy(.13)), (sx(.69), sy(.28)), (sx(.69), sy(.39))],
        gate_color, line * .72, gate_in,
    )
    _stroke_path(
        painter,
        [(sx(.46), sy(.87)), (sx(.69), sy(.72)), (sx(.69), sy(.61))],
        gate_color, line * .72, gate_in,
    )

    _stroke_path(
        painter,
        [(sx(.48), sy(.50)), (sx(.69), sy(.50)), (sx(.91), sy(.50))],
        violet, line, outgoing,
    )

    if 0.30 < progress < 0.76 and not monochrome:
        scan = (progress - .30) / .46
        scan_color = QColor("#BFF7FF")
        scan_color.setAlpha(210)
        painter.setPen(QPen(scan_color, max(1.0, line * .20), Qt.SolidLine, Qt.RoundCap))
        scan_y = sy(.22 + .56 * scan)
        painter.drawLine(sx(.435), scan_y, sx(.725), scan_y)
    painter.restore()


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(INK)
        radius = max(3.0, size * .21)
        painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
        draw_route_prism(painter, QRectF(size * .06, size * .06, size * .88, size * .88))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class RoutePrismWidget(QWidget):
    """Small animated brand mark used in the app header."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self._progress = 1.0
        self._busy = False
        self._phase = 0.0
        self._reduce_motion = False
        self._timer = QTimer(self)
        self._timer.setInterval(42)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._phase = (self._phase + .055) % 1.0
        self._progress = .28 + self._phase * .72
        self.update()

    def set_busy(self, busy: bool):
        self._busy = bool(busy)
        if self._busy and not self._reduce_motion:
            self._timer.start()
        else:
            self._timer.stop()
            self._progress = 1.0
            self.update()

    def set_reduce_motion(self, value: bool):
        self._reduce_motion = bool(value)
        self.set_busy(self._busy)

    def play_once(self):
        """Run one short scan after the startup hand-off, then become completely idle."""
        if self._reduce_motion:
            return
        self.set_busy(True)
        QTimer.singleShot(720, lambda: self.set_busy(False))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#09161D"))
        painter.drawRoundedRect(QRectF(1, 1, 46, 46), 13, 13)
        draw_route_prism(painter, QRectF(3, 3, 42, 42), self._progress)


class StartupSplash(QWidget):
    finished = Signal()

    def __init__(self, duration_ms: int = 1250, parent=None):
        super().__init__(parent, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        load_brand_fonts()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(680, 390)
        self._progress = 0.0
        self._finished = False
        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(max(260, int(duration_ms)))
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.finished.connect(self.finish)
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, value: float):
        self._progress = float(value)
        self.update()

    progress = Property(float, get_progress, set_progress)

    def play(self):
        self.show()
        self.raise_()
        self._animation.start()

    def finish(self):
        if self._finished:
            return
        self._finished = True
        self._animation.stop()
        self.close()
        self.finished.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.finish()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, _event):
        self.finish()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        card = QRectF(9, 9, self.width() - 18, self.height() - 18)
        painter.setPen(QPen(QColor(38, 84, 102, 150), 1))
        painter.setBrush(QColor(5, 12, 17, 248))
        painter.drawRoundedRect(card, 28, 28)

        # A restrained moving network field adds depth, but exists only during startup.
        field_alpha = int(34 * math.sin(min(1.0, self._progress / .28) * math.pi / 2))
        painter.setPen(QPen(QColor(32, 170, 205, field_alpha), 1))
        drift = self._progress * 34
        for row in range(5):
            yy = 68 + row * 55
            painter.drawLine(42 + drift, yy, self.width() - 42, yy)
        for column in range(8):
            xx = 58 + column * 82 - drift * .45
            painter.drawLine(xx, 34, xx + 54, self.height() - 44)

        for index in range(10):
            phase = (self._progress * 1.35 + index * .137) % 1.0
            px = 48 + phase * (self.width() - 96)
            py = 58 + ((index * 47) % 235)
            alpha = int(95 * math.sin(phase * math.pi))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(44, 220, 245, alpha))
            painter.drawEllipse(QPointF(px, py), 1.6, 1.6)

        mark_progress = min(1.0, self._progress / .76)
        handoff = max(0.0, min(1.0, (self._progress - .88) / .12))
        handoff = 1.0 - (1.0 - handoff) ** 3
        start_rect = QRectF(210, 45, 260, 200)
        end_rect = QRectF(524, 23, 104, 86)
        mark_rect = QRectF(
            start_rect.x() + (end_rect.x() - start_rect.x()) * handoff,
            start_rect.y() + (end_rect.y() - start_rect.y()) * handoff,
            start_rect.width() + (end_rect.width() - start_rect.width()) * handoff,
            start_rect.height() + (end_rect.height() - start_rect.height()) * handoff,
        )
        draw_route_prism(painter, mark_rect, mark_progress, glow=handoff < .25)

        # The selected route releases one clean energy ring instead of noisy particles.
        impact = max(0.0, min(1.0, (self._progress - .70) / .18))
        if 0.0 < impact < 1.0:
            radius = 26 + impact * 112
            alpha = int(150 * (1.0 - impact))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(138, 56, 245, alpha), 2.2))
            painter.drawEllipse(QPointF(340, 145), radius * 1.45, radius)

        text_reveal = max(0.0, min(1.0, (self._progress - .54) / .28))
        text_fade = 1.0 - handoff
        font = QFont("Vazirmatn", 29, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 3.4)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        word = "LAGSHIFT"
        advances = [metrics.horizontalAdvance(letter) for letter in word]
        cursor = (self.width() - sum(advances)) / 2
        baseline = 287.0
        for index, (letter, advance) in enumerate(zip(word, advances)):
            local = max(0.0, min(1.0, (text_reveal - index * .045) / .685))
            eased = 1.0 - (1.0 - local) ** 3
            alpha = int(255 * eased * text_fade)
            painter.setPen(QColor(235, 250, 255, alpha))
            offset = (-1 if index % 2 == 0 else 1) * (1.0 - eased) * 16
            painter.drawText(QPointF(cursor + offset, baseline), letter)
            cursor += advance

        text_alpha = int(255 * text_reveal * text_fade)
        caption_color = QColor(124, 158, 172, text_alpha)
        painter.setPen(caption_color)
        painter.setFont(QFont("Vazirmatn", 10))
        painter.drawText(QRectF(70, 302, 540, 30), Qt.AlignCenter, "مسیر بهتر، بازی روان‌تر")

        hint_alpha = int(145 * max(0.0, min(1.0, (self._progress - .72) / .2)))
        painter.setPen(QColor(105, 128, 138, hint_alpha))
        painter.setFont(QFont("Vazirmatn", 8))
        painter.drawText(QRectF(70, 344, 540, 20), Qt.AlignCenter, "برای ردکردن کلیک کن یا Esc بزن")
