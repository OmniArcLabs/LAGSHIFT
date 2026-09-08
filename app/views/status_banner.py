"""یه بنر وضعیت با انیمیشن محو نرم (fade)، برای پیام‌های موفقیت/خطا/اطلاع"""
from PySide6.QtCore import QPropertyAnimation, QTimer, Qt, QEasingCurve
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect


COLORS = {
    "success": ("#1B3B2A", "#4CAF50"),
    "error": ("#3A1E1E", "#EF5350"),
    "info": ("#1A2733", "#4FC3F7"),
}


class StatusBanner(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setFixedHeight(0)
        self.setStyleSheet("border-radius: 8px; padding: 0px;")

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)

        self._fade_anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._message_generation = 0
        self._reduce_motion = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("برای بستن پیام کلیک کن")

    def show_message(self, text: str, kind: str = "info", duration_ms: int = 5000):
        text = str(text)
        # Background monitors can report the same state repeatedly.  Keeping
        # the original deadline prevents duplicate signals from pinning the
        # banner on screen forever.
        if text == self.text() and self.height() > 0 and self._hide_timer.isActive():
            return
        self._message_generation += 1
        # A newer message owns the banner.  Stop both the previous timeout and
        # fade so an older completion cannot leave the new message stuck/open.
        self._hide_timer.stop()
        self._fade_anim.stop()
        bg, border = COLORS.get(kind, COLORS["info"])
        self.setStyleSheet(
            f"background-color:{bg}; color:#FFFFFF; border:1px solid {border}; "
            f"border-radius:8px; padding:10px;"
        )
        self.setText(text)
        self.setFixedHeight(42)

        if self._reduce_motion:
            self._effect.setOpacity(1.0)
        else:
            self._fade_anim.setStartValue(self._effect.opacity())
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

        self._hide_timer.start(max(250, int(duration_ms)))

    def _fade_out(self):
        generation = self._message_generation
        if self._reduce_motion:
            self._effect.setOpacity(0.0)
            self._collapse(generation)
            return
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()
        # Some graphics drivers do not reliably deliver animation.finished
        # for opacity effects.  This is a guarded, deterministic fallback.
        QTimer.singleShot(
            self._fade_anim.duration() + 80,
            lambda: self._collapse(generation),
        )

    def set_reduce_motion(self, enabled: bool):
        self._reduce_motion = bool(enabled)
        if enabled:
            self._fade_anim.stop()

    def dismiss(self):
        self._hide_timer.stop()
        self._fade_out()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.height() > 0:
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def _collapse(self, generation: int):
        if generation != self._message_generation or self._hide_timer.isActive():
            return
        self._fade_anim.stop()
        self._effect.setOpacity(0.0)
        self.setFixedHeight(0)
        self.clear()

    def _on_fade_finished(self):
        # QGraphicsOpacityEffect only makes the label transparent; collapsing
        # its height is what actually removes the empty strip from the layout.
        if not self._hide_timer.isActive() and self._effect.opacity() <= 0.01:
            self._collapse(self._message_generation)
