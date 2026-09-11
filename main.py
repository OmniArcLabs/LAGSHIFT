"""Application entry point with an unelevated UI and a narrow UAC helper."""
import sys
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QAbstractButton, QMessageBox

from app.services import settings_service, privileged_helper, crash_service
from app.app_info import APP_DISPLAY_NAME, APP_NAME
from app.views.brand import StartupSplash, load_brand_fonts, make_app_icon
from app.views.main_window import MainWindow
from app.views.terms_dialog import TermsDialog
from app.views.onboarding_dialog import OnboardingDialog


class NoDottedFocusStyle(QProxyStyle):
    """Keep keyboard focus working while removing Windows' dotted text rectangle."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)


class UiBreadcrumbFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and isinstance(watched, QAbstractButton):
            crash_service.add_breadcrumb(
                "ui", "button", widget=type(watched).__name__,
                label=(watched.text() or watched.objectName() or "unnamed").splitlines()[0],
            )
        return False


def main():
    if privileged_helper.HELPER_FLAG in sys.argv:
        index = sys.argv.index(privileged_helper.HELPER_FLAG)
        if len(sys.argv) != index + 3:
            raise SystemExit(2)
        raise SystemExit(privileged_helper.run_helper(sys.argv[index + 1], sys.argv[index + 2]))

    app = QApplication(sys.argv)
    app.setStyle(NoDottedFocusStyle(app.style()))
    load_brand_fonts()
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setWindowIcon(make_app_icon())
    app.setQuitOnLastWindowClosed(False)  # با بسته شدن پنجره (رفتن به Tray) اپ کامل نبنده
    app.setLayoutDirection(Qt.RightToLeft)  # پشتیبانی کامل RTL برای کل اپ

    minimized = "--minimized" in sys.argv
    settings = settings_service.load_settings()
    previous_unclean = crash_service.initialize(settings.get("blackbox_enabled", True))
    app.aboutToQuit.connect(crash_service.mark_clean_shutdown)
    breadcrumb_filter = UiBreadcrumbFilter(app)
    app.installEventFilter(breadcrumb_filter)
    heartbeat_timer = QTimer(app)
    heartbeat_timer.setInterval(1000)
    heartbeat_timer.timeout.connect(crash_service.heartbeat)
    heartbeat_timer.start()
    crash_service.start_watchdog()
    if not settings_service.has_current_legal_acceptance(settings):
        if TermsDialog().exec() != TermsDialog.Accepted:
            crash_service.mark_clean_shutdown()
            return
        settings = settings_service.load_settings()

    run_first_route_test = False
    if not minimized and not settings.get("onboarding_completed", False):
        accepted = OnboardingDialog().exec() == OnboardingDialog.Accepted
        settings = settings_service.load_settings()
        run_first_route_test = accepted and settings.get("onboarding_run_light_test", False)
        if run_first_route_test:
            settings_service.set_value("onboarding_run_light_test", False)

    show_intro = settings.get("startup_animation_enabled", True) and not minimized
    splash = None
    if show_intro:
        if settings.get("reduce_motion", False):
            duration = 320
        else:
            duration = 2600 if not settings.get("brand_intro_seen", False) else 1250
        splash = StartupSplash(duration)
        splash.show()
        app.processEvents()

    window = MainWindow()

    def start_first_route_test():
        if run_first_route_test:
            window._run_route_dna_diagnostic()

    def offer_crash_recovery():
        if not previous_unclean or not crash_service.pending_count():
            return
        box = QMessageBox(window)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("بازیابی اجرای قبلی")
        box.setText("اجرای قبلی درست بسته نشد؛ یک گزارش فنیِ بدون اطلاعات شخصی آماده شده است.")
        export_button = box.addButton("ساخت فایل گزارش", QMessageBox.AcceptRole)
        box.addButton("فعلاً نه", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is export_button:
            path = crash_service.export_pending()
            QMessageBox.information(
                window, "گزارش آماده شد",
                f"فایل گزارش برای ارسال دستی ساخته شد:\n{path}\n\nهیچ گزارشی خودکار ارسال نشده است.",
            )

    if not privileged_helper.is_admin() and sys.platform == "win32":
        window.banner.show_message(
            "حالت امن فعال است؛ فقط هنگام تغییر شبکه، ویندوز اجازه ادمین می‌خواهد.",
            "info", 6000
        )

    # اگه با فلگ --minimized اجرا شده باشه (مثلاً از طریق اجرای خودکار با ویندوز)،
    # مستقیم بره تو Tray به‌جای نمایش پنجره
    if minimized and window.tray_icon is not None:
        window.hide()
    elif splash is not None:
        def reveal_window():
            settings_service.set_value("brand_intro_seen", True)
            window.setWindowOpacity(0.0)
            window.show()
            if settings.get("reduce_motion", False):
                window.setWindowOpacity(1.0)
                return
            window.play_startup_reveal()
            animation = QPropertyAnimation(window, b"windowOpacity", window)
            animation.setDuration(430)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.start()
            window._startup_reveal_animation = animation
            QTimer.singleShot(600, offer_crash_recovery)
            QTimer.singleShot(1100, start_first_route_test)

        splash.finished.connect(reveal_window)
        splash.play()
    else:
        window.show()
        QTimer.singleShot(600, offer_crash_recovery)
        QTimer.singleShot(1100, start_first_route_test)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
