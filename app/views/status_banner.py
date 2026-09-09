"""Bounded, deduplicated status notifications for the main window."""
import time

from PySide6.QtCore import QPropertyAnimation, QTimer, Qt, QEasingCurve
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect


COLORS = {
    "success": ("#1B3B2A", "#4CAF50"),
    "error": ("#3A1E1E", "#EF5350"),
    "warning": ("#3B301A", "#FFB74D"),
    "info": ("#1A2733", "#4FC3F7"),
}

BASE_DURATION_MS = {
    "success": 4500,
    "info": 5500,
    "warning": 7500,
    "error": 9000,
}
MIN_DURATION_MS = 2500
MAX_DURATION_MS = 12000
REPEAT_COOLDOWN_MS = 20000
RECENT_MESSAGE_LIMIT = 12


class StatusBanner(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setFixedHeight(0)
        self.setStyleSheet("border-radius: 8px; padding: 0px;")

        self._effect = None
        self._fade_anim = None
        self._install_effect(0.0)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        # A second bounded watchdog is deliberate.  A visual effect must never
        # be able to turn an ordinary notification into a permanent banner.
        self._expiry_watchdog = QTimer(self)
        self._expiry_watchdog.setInterval(400)
        self._expiry_watchdog.timeout.connect(self._check_expiry)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._collapse_current)

        self._message_generation = 0
        self._deadline = 0.0
        self._current_kind = "info"
        self._fading_out = False
        self._recent_messages: dict[tuple[str, str], float] = {}
        self._reduce_motion = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("برای بستن پیام کلیک کن")

    def _install_effect(self, opacity: float):
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(self._on_fade_finished)
        self._effect = effect
        self._fade_anim = animation

    def _ensure_effect(self):
        if self.graphicsEffect() is self._effect:
            return
        # Another page animation may have replaced and deleted the native Qt
        # object.  Recreate the banner-owned effect instead of leaving a shown
        # message without an expiry timer.
        self._install_effect(1.0 if self.height() > 0 else 0.0)

    @staticmethod
    def recommended_duration(text: str, kind: str) -> int:
        """Allow enough reading time while guaranteeing eventual dismissal."""
        level = kind if kind in BASE_DURATION_MS else "info"
        reading_time = 2500 + min(len(text), 220) * 38
        return max(
            MIN_DURATION_MS,
            min(MAX_DURATION_MS, max(BASE_DURATION_MS[level], reading_time)),
        )

    @staticmethod
    def is_recent_duplicate(recent_messages: dict, fingerprint: tuple[str, str], now: float) -> bool:
        return float(recent_messages.get(fingerprint, 0.0)) > float(now)

    def show_message(self, text: str, kind: str = "info", duration_ms: int | None = None):
        text = " ".join(str(text).split())
        if not text:
            self.dismiss(immediate=True)
            return
        kind = kind if kind in COLORS else "info"
        now = time.monotonic()
        fingerprint = (kind, text)
        # Background monitors can report the same state repeatedly.  Keeping
        # the original deadline prevents duplicate signals from pinning the
        # banner on screen forever.
        if text == self.text() and kind == self._current_kind and self.height() > 0:
            if self._fading_out or now < self._deadline:
                return
            self._fade_out()
            return
        self._recent_messages = {
            item: until for item, until in self._recent_messages.items()
            if until > now
        }
        if self.height() <= 0 and self.is_recent_duplicate(
            self._recent_messages, fingerprint, now
        ):
            return
        self._message_generation += 1
        self._fading_out = False
        # A newer message owns the banner.  Stop both the previous timeout and
        # fade so an older completion cannot leave the new message stuck/open.
        self._hide_timer.stop()
        self._collapse_timer.stop()
        self._ensure_effect()
        self._fade_anim.stop()
        bg, border = COLORS.get(kind, COLORS["info"])
        self.setStyleSheet(
            f"background-color:{bg}; color:#FFFFFF; border:1px solid {border}; "
            f"border-radius:8px; padding:10px;"
        )
        self.setText(text)
        self._current_kind = kind
        self.setFixedHeight(42)

        if self._reduce_motion:
            self._effect.setOpacity(1.0)
        else:
            self._fade_anim.setStartValue(self._effect.opacity())
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

        duration = (
            self.recommended_duration(text, kind)
            if duration_ms is None else
            max(MIN_DURATION_MS, min(MAX_DURATION_MS, int(duration_ms)))
        )
        self._deadline = now + duration / 1000.0
        self._recent_messages[fingerprint] = self._deadline + REPEAT_COOLDOWN_MS / 1000.0
        while len(self._recent_messages) > RECENT_MESSAGE_LIMIT:
            self._recent_messages.pop(next(iter(self._recent_messages)))
        self._hide_timer.start(duration)
        if not self._expiry_watchdog.isActive():
            self._expiry_watchdog.start()

    def _check_expiry(self):
        if self.height() <= 0:
            self._expiry_watchdog.stop()
            return
        if self._deadline and time.monotonic() >= self._deadline:
            self._fade_out()

    def _fade_out(self):
        if self.height() <= 0:
            self._expiry_watchdog.stop()
            return
        if self._fading_out:
            return
        self._fading_out = True
        generation = self._message_generation
        self._hide_timer.stop()
        self._ensure_effect()
        if self._reduce_motion:
            self._effect.setOpacity(0.0)
            self._collapse(generation)
            return
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()
        # Some graphics drivers do not reliably deliver animation.finished.
        self._collapse_timer.start(self._fade_anim.duration() + 100)

    def set_reduce_motion(self, enabled: bool):
        self._reduce_motion = bool(enabled)
        if enabled:
            self._ensure_effect()
            self._fade_anim.stop()
            self._effect.setOpacity(1.0 if self.height() > 0 else 0.0)

    def dismiss(self, immediate: bool = False):
        self._hide_timer.stop()
        if immediate:
            self._collapse(self._message_generation)
        else:
            self._fade_out()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.height() > 0:
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def _collapse(self, generation: int):
        if generation != self._message_generation:
            return
        self._hide_timer.stop()
        self._collapse_timer.stop()
        self._expiry_watchdog.stop()
        self._ensure_effect()
        self._fade_anim.stop()
        self._effect.setOpacity(0.0)
        self.setFixedHeight(0)
        self.clear()
        self._deadline = 0.0
        self._fading_out = False

    def _collapse_current(self):
        self._collapse(self._message_generation)

    def _on_fade_finished(self):
        # QGraphicsOpacityEffect only makes the label transparent; collapsing
        # its height is what actually removes the empty strip from the layout.
        self._ensure_effect()
        if not self._hide_timer.isActive() and self._effect.opacity() <= 0.01:
            self._collapse(self._message_generation)
