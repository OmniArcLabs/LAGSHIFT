"""ViewModel اصلی: پل بین UI و سرویس‌ها (الگوی MVVM)"""
import threading
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal, QTimer

from app.models.network_adapter import DEFAULT_DNS_PROFILES
from app.app_info import (
    ALLOW_CUSTOM_TUNNELS, ALLOW_LEGACY_WARP_REGISTRATION,
    UPDATE_MANIFEST_URL, UPDATE_PUBLIC_KEY_B64,
)
from app.services import (
    adapter_service, dns_service, games_service, connectivity_service,
    game_detection_service, usage_tracker_service,
    official_warp_service, autostart_service, rating_service,
    settings_service, diagnostics_service, radar_service, quality_service,
    game_server_probe_service,
    game_route_profile_service,
    network_lab_service, game_qos_service,
    update_service,
    app_access_service, app_route_service, app_profile_catalog_service,
    privileged_helper, route_dna_service, integrity_service,
    connection_state_service,
    game_session_report_service,
    recovery_service,
)
if ALLOW_CUSTOM_TUNNELS or ALLOW_LEGACY_WARP_REGISTRATION:
    from app.services import (
        config_parser, tunnel_service, tunnel_storage_service,
        warp_service, subscription_service,
    )
else:
    from app.services.public_tunnel_stubs import (
        config_parser, tunnel_service, tunnel_storage_service,
        warp_service, subscription_service,
    )
from app.services.public_configs import PUBLIC_CONFIG_SOURCES, SUGGESTED_DAILY_LIMIT_MB


class MainViewModel(QObject):
    adapters_changed = Signal(list)
    status_message = Signal(str, str)   # (متن پیام, نوع: "success" | "error" | "info")
    games_changed = Signal(list)
    kill_switch_triggered = Signal()
    busy_changed = Signal(bool)         # برای غیرفعال‌سازی دکمه‌ها حین عملیات
    connection_changed = Signal(bool, str)  # (وصل/قطع, نام پروفایل یا آداپتور)
    dns_benchmark_progress = Signal(dict)
    dns_quality_ready = Signal(dict)

    tunnel_configs_changed = Signal(list)
    tunnel_status_changed = Signal(bool, str)  # (وصل/قطع, نام کانفیگ)
    tunnel_busy_changed = Signal(bool)
    ping_result_ready = Signal(str, int)  # (نام سرور/کانفیگ, لتنسی به میلی‌ثانیه یا -1)

    game_detected = Signal(object)      # یک شیء Game که تازه تشخیص داده شده
    game_candidate_detected = Signal(object)
    game_optimization_progress = Signal(str, str, str)  # game, state, message
    game_runtime_changed = Signal(str, bool)
    optimization_state_changed = Signal(dict)
    game_server_probe_ready = Signal(dict)
    game_route_profile_ready = Signal(str, dict, str)
    network_lab_ready = Signal(dict)
    network_monitor_ready = Signal(dict)
    air_profile_updated = Signal(str, dict, int)
    usage_updated = Signal(float, int)  # (دقایق امروز, سقف پیشنهادی مگابایت)

    live_ping_ready = Signal(int)       # پینگ دوره‌ای برای اورلی و نمودار تاریخچه (میلی‌ثانیه یا -1)
    speed_test_ready = Signal(dict)     # نتیجه‌ی مقایسه‌ی سرعت: {"direct": ms, "dns": ms, "tunnel": ms}
    warp_busy_changed = Signal(bool)
    warp_state_changed = Signal(dict)
    route_quality_ready = Signal(dict)
    failover_changed = Signal(bool, str)
    trial_ready = Signal(dict)
    diagnostic_report_ready = Signal(str)
    traffic_usage_updated = Signal(int, int)
    update_check_ready = Signal(dict)
    update_download_progress = Signal(int, int)
    update_download_ready = Signal(str, str)
    app_catalog_changed = Signal(list)
    app_access_progress = Signal(dict)
    app_access_changed = Signal(dict)
    route_dna_diagnostic_ready = Signal(dict)
    security_audit_ready = Signal(dict)
    emergency_reset_ready = Signal(bool, str)
    connection_flow_changed = Signal(dict)
    game_session_report_ready = Signal(dict)

    # Worker completion signals keep every QObject/QTimer mutation on the GUI thread.
    _dns_apply_completed = Signal(bool, str, str, str)
    _dns_disconnect_completed = Signal(bool)
    _tunnel_connect_completed = Signal(bool, str, str, object)
    _tunnel_disconnect_completed = Signal()
    _warp_completed = Signal(object, str)
    _official_warp_completed = Signal(dict)
    _kill_switch_checked = Signal(bool)
    _subscription_completed = Signal(object, str)
    _trial_completed = Signal(object, str, str)
    _app_catalog_completed = Signal(list)
    _app_access_completed = Signal(dict)
    _route_monitor_checked = Signal(dict)
    _game_preflight_completed = Signal(object, dict)

    def __init__(self):
        super().__init__()
        self.adapters = []
        self.dns_profiles = DEFAULT_DNS_PROFILES
        self.games = games_service.load_games()
        self.public_config_sources = PUBLIC_CONFIG_SOURCES

        self.active_adapter_name = None
        self.active_profile_name = None
        self.kill_switch_enabled = False
        self.is_connected = False
        self._busy = False  # جلوگیری از کلیک‌های همزمان/متعدد (رفع کرش)
        self._official_warp_session = {}
        self._warp_generation = 0
        self._pending_dns_quality = None
        self._active_route_context = {}
        self._pending_tunnel_route_context = {}
        self._route_monitor_busy = False
        self._route_bad_samples = 0
        self._app_access_session = {}
        self._app_access_generation = 0
        self._app_access_worker = None
        self._app_catalog_installed = []
        self._app_scan_busy = False
        self._connection_state = connection_state_service.ConnectionState()
        self._connection_generation = 0
        self._update_download_cancel = threading.Event()
        self._game_session_summary = {}
        self._match_route_locked = False

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(5000)
        self._watchdog_timer.timeout.connect(self._check_connectivity)

        # --- تانل ---
        stored_tunnels = tunnel_storage_service.load_configs()
        self.tunnel_configs = (
            stored_tunnels if ALLOW_CUSTOM_TUNNELS
            else [
                item for item in stored_tunnels
                if item.source == "warp" and item.extra.get("verified") is True
            ]
        )
        self._tunnel = tunnel_service.TunnelProcess()
        self.tunnel_connected = False
        self.active_tunnel_name = None
        self._tunnel_busy = False
        self._tunnel_connect_time = None  # برای محاسبه‌ی مدت اتصال (تخمین مصرف)
        self._active_tunnel_config = None
        self._standby_tunnel_config = None
        self._standby_tunnel_configs = []
        self._active_game_mode = "balanced"
        self._last_ranked_configs = []
        self._recovering_tunnel = False
        self._live_failures = 0
        self._last_quality = {}
        self._shadow_route_busy = False
        self._shadow_last_summary = ""
        self._active_process_names = []
        self._active_route_mtu = 1400
        self._traffic_meter = usage_tracker_service.TrafficMeter()

        # --- تشخیص خودکار بازی ---
        self._last_detected_game_name = None
        self._auto_connected_game_name = None
        self._seen_candidate_processes = set()
        self._optimizing_game = None
        self._route_learning_game = None
        self._game_started_dns = False
        self._game_started_tunnel = False
        self._pending_game_stop_dns = False
        self._pending_game_stop_tunnel = False
        self._game_probe_baselines = {}
        self._game_session_generation = 0
        self._game_scan_timer = QTimer(self)
        # Catch launch/splash processes before a game takes exclusive full-screen.
        self._game_scan_timer.setInterval(750)
        self._game_scan_timer.timeout.connect(self._scan_for_running_game)
        self._game_scan_timer.start()
        self._air_timer = QTimer(self)
        self._air_timer.setInterval(5000)
        self._air_timer.timeout.connect(self._air_lite_tick)
        self._air_busy = False
        self._air_last_notice = {}
        self._network_monitor_timer = QTimer(self)
        self._network_monitor_timer.setInterval(4000)
        self._network_monitor_timer.timeout.connect(self._network_monitor_tick)
        self._network_monitor_busy = False

        # --- مصرف روزانه (تخمینی) ---
        self._usage_timer = QTimer(self)
        self._usage_timer.setInterval(60000)  # هر یک دقیقه
        self._usage_timer.timeout.connect(self._tick_usage)

        # --- پینگ دوره‌ای برای اورلی/نمودار (فقط وقتی تانل وصله) ---
        self._live_ping_timer = QTimer(self)
        self._live_ping_timer.setInterval(2000)
        self._live_ping_timer.timeout.connect(self._tick_live_ping)
        self._live_ping_target = None  # (host, port) کانفیگ فعلی
        self._tunnel_watchdog_timer = QTimer(self)
        self._tunnel_watchdog_timer.setInterval(3000)
        self._tunnel_watchdog_timer.timeout.connect(self._check_tunnel_process)
        self._shadow_route_timer = QTimer(self)
        self._shadow_route_timer.setInterval(45000)
        self._shadow_route_timer.timeout.connect(self._shadow_route_tick)

        self._dns_apply_completed.connect(self._on_apply_finished)
        self._dns_disconnect_completed.connect(self._on_disconnect_finished)
        self._tunnel_connect_completed.connect(self._on_tunnel_connect_finished)
        self._tunnel_disconnect_completed.connect(self._on_tunnel_disconnect_finished)
        self._warp_completed.connect(self._on_warp_finished)
        self._official_warp_completed.connect(self._on_official_warp_finished)
        self._kill_switch_checked.connect(self._on_kill_switch_checked)
        self._subscription_completed.connect(self._on_subscription_finished)
        self.live_ping_ready.connect(self._on_live_health)
        self._trial_completed.connect(self._on_trial_finished)
        self._pending_dns_recovery_checked = False
        self._pending_recovery_notice_checked = False
        self._game_preflight_busy = False
        self._app_catalog_completed.connect(self._on_app_catalog_completed)
        self._app_access_completed.connect(self._on_app_access_completed)
        self.app_access_progress.connect(self._on_connection_progress)
        self._route_monitor_checked.connect(self._on_route_monitor_checked)
        self._game_preflight_completed.connect(self._on_game_preflight_completed)
        self._app_access_watch_timer = QTimer(self)
        self._app_access_watch_timer.setInterval(2200)
        self._app_access_watch_timer.timeout.connect(self._app_access_watch_tick)
        self._app_access_watch_timer.start()
        self._route_monitor_timer = QTimer(self)
        self._route_monitor_timer.setInterval(8000)
        self._route_monitor_timer.timeout.connect(self._route_dna_monitor_tick)
        self._route_monitor_timer.start()
        QTimer.singleShot(1800, self._refresh_app_profile_catalog)

    def _on_connection_progress(self, payload: dict):
        snapshot = self._connection_state.snapshot()
        if snapshot.get("scope") != "app" or snapshot.get("phase") in {
            "active", "failed", "idle", "restoring",
        }:
            return
        phase = {
            "baseline": "testing", "ranking": "testing", "verify": "verifying",
            "warp": "testing", "restore": "restoring",
        }.get(str(payload.get("phase")), "testing")
        self._connection_state.advance(
            self._connection_generation, phase, str(payload.get("message") or "")
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())

    # ---------- RouteDNA مشترک ----------

    @staticmethod
    def _route_dna_snapshot(adapter_name: str, purpose: str, settings: dict,
                            *, sample_pressure: bool = True,
                            sample_gateway: bool = False) -> dict:
        hint = route_dna_service.fetch_remote_hint(
            settings.get("gamelink_api_url", ""),
            bool(settings.get("route_dna_remote_geo", False)),
        )
        return route_dna_service.snapshot(
            adapter_name, purpose, sample_pressure=sample_pressure,
            remote_hint=hint, sample_gateway=sample_gateway,
        )

    def run_route_dna_diagnostic(self, deep_confirmed: bool = False):
        settings = settings_service.load_settings()
        if not settings.get("route_dna_enabled", True):
            self.status_message.emit("برای اجرای آزمایش، ابتدا RouteDNA را روشن کن", "info")
            return
        adapter_name = self.active_adapter_name or next(
            (item.name for item in self.adapters if getattr(item, "is_enabled", False)), ""
        )
        if not adapter_name:
            self.status_message.emit("کارت شبکه فعالی برای آزمایش پیدا نشد", "error")
            return
        self.status_message.emit("RouteDNA در حال بررسی Gateway، Wi‑Fi و ظرفیت مسیر است…", "info")

        def worker():
            context = self._route_dna_snapshot(
                adapter_name, "download", settings, sample_gateway=True,
            )
            policy = route_dna_service.probe_policy(
                context, game_running=bool(self._optimizing_game),
                requested=str(settings.get("route_dna_probe_mode", "light")),
            )
            daily_limit = int(settings.get("route_dna_daily_budget_mb", 25))
            budget = route_dna_service.probe_budget_status(daily_limit)
            backend_ready = bool(route_dna_service._public_https_base(
                settings.get("gamelink_api_url", "")
            ))
            blocked_by_load = (
                context.get("pressure") == "busy" or bool(self._optimizing_game)
            )
            bandwidth = {"ok": False, "skipped": True,
                         "reason": "backend-unconfigured", "mode": policy["mode"]}
            if blocked_by_load:
                bandwidth["reason"] = "network-busy"
            elif backend_ready:
                budget = route_dna_service.reserve_probe_budget(
                    route_dna_service.bandwidth_budget_kb(policy["mode"]), daily_limit,
                )
                if not budget["allowed"]:
                    bandwidth["reason"] = "budget-exhausted"
                else:
                    bandwidth = route_dna_service.measure_controlled_bandwidth(
                        settings.get("gamelink_api_url", ""), policy["mode"],
                        deep_confirmed=deep_confirmed, network_busy=False,
                    )
            self.route_dna_diagnostic_ready.emit({
                "context": context, "policy": policy,
                "budget": budget, "bandwidth": bandwidth,
            })

        threading.Thread(target=worker, daemon=True).start()

    def run_security_audit(self, full: bool = False):
        """Run package checks off the GUI thread; never mutate network state."""
        def worker():
            integrity = integrity_service.verify_catalog(full=full)
            package_acl = integrity_service.audit_package_acl()
            signed = (
                update_service.has_valid_authenticode(Path(sys.executable))
                if getattr(sys, "frozen", False) else False
            )
            profile = next((item for item in self.dns_profiles
                            if item.name == self.active_profile_name), None)
            dns_hijack = (
                connectivity_service.detect_dns_hijacking(profile.primary)
                if profile is not None else None
            )
            doh_policy = (
                dns_service.verify_doh_no_downgrade(profile.primary, profile.doh_url)
                if profile is not None and profile.doh_url else None
            )
            internet_scope = connectivity_service.detect_internet_scope()
            ipv6_exposure = connectivity_service.audit_ipv6_exposure(
                custom_ipv4_dns_active=profile is not None
            )
            self.security_audit_ready.emit({
                "integrity": integrity,
                "package_acl": package_acl,
                "publisher_signed": signed,
                "update_trust_configured": bool(
                    UPDATE_MANIFEST_URL and UPDATE_PUBLIC_KEY_B64
                ),
                "pending_dns_restore": dns_service.has_pending_restore(),
                "pending_recovery": recovery_service.receipt(1),
                "helper_scope": "dns-only-schema",
                "development_mode": not getattr(sys, "frozen", False),
                "dns_hijack": dns_hijack,
                "doh_policy": doh_policy,
                "internet_scope": internet_scope,
                "ipv6_exposure": ipv6_exposure,
            })

        threading.Thread(target=worker, daemon=True).start()

    def emergency_network_reset(self):
        """Run the fixed DNS/QoS recovery recipe in one UAC session."""
        def worker():
            warp_ok = True
            warp_session = dict(self._official_warp_session)
            if not warp_session:
                intent = recovery_service.warp_intent()
                if intent:
                    status = official_warp_service.inspect()
                    if (
                        status.connected and status.signature_valid
                        and status.mode.casefold() == intent.get("expected_mode", "")
                    ):
                        warp_session = {
                            "started_by_app": True,
                            "original_mode": intent.get("original_mode", ""),
                            "original_protocol": intent.get("original_protocol", ""),
                        }
                    else:
                        # Never disconnect a user-owned or ambiguous WARP session.
                        warp_ok = False
            if warp_session.get("started_by_app"):
                result = official_warp_service.disconnect_if_started(
                    True,
                    warp_session.get("original_mode", ""),
                    warp_session.get("original_protocol", ""),
                )
                warp_ok = bool(result.get("ok"))
                if warp_ok:
                    self._official_warp_session = {}
            ok, error = privileged_helper.request(
                "emergency_reset", "", timeout_s=35.0
            )
            ok = bool(ok and warp_ok)
            self.emergency_reset_ready.emit(
                ok, "DNS، QoS و مسیر WARP متعلق به LAGSHIFT بازیابی شدند" if ok
                else (error or "بازیابی مسیر WARP متعلق به برنامه کامل نشد")
            )

        threading.Thread(target=worker, daemon=True).start()

    def _route_dna_monitor_tick(self):
        if (self._route_monitor_busy or not self._active_route_context
                or not (self.is_connected or self.tunnel_connected)):
            return
        adapter = self.active_adapter_name or next(
            (item.name for item in self.adapters if getattr(item, "is_enabled", False)), ""
        )
        if not adapter:
            return
        self._route_monitor_busy = True
        previous = dict(self._active_route_context)
        active_profile = self.active_profile_name

        def worker():
            current = route_dna_service.snapshot(
                adapter, previous.get("purpose", "smart"), sample_pressure=False,
            )
            drift = route_dna_service.detect_drift(previous, current)
            dns_healthy = None
            if active_profile:
                profile = next(
                    (item for item in self.dns_profiles if item.name == active_profile), None
                )
                if profile is not None:
                    dns_healthy = connectivity_service.measure_dns_query_ms(
                        profile.primary, timeout_s=1.0
                    ) >= 0
            self._route_monitor_checked.emit({
                "adapter": adapter, "current": current, "drift": drift,
                "dns_healthy": dns_healthy,
            })

        threading.Thread(target=worker, daemon=True).start()

    def _on_route_monitor_checked(self, result: dict):
        self._route_monitor_busy = False
        drift = result.get("drift") or {}
        if drift.get("changed"):
            settings = settings_service.load_settings()
            self._active_route_context = self._route_dna_snapshot(
                result.get("adapter", ""),
                (result.get("current") or {}).get("purpose", "smart"),
                settings, sample_pressure=False,
            )
            self._pending_dns_quality = None
            self._route_bad_samples = 0
            self.status_message.emit(
                f"RouteDNA تغییر شبکه را تشخیص داد: {drift.get('reason')}. "
                "نتیجه قدیمی کنار گذاشته شد؛ اتصال سالم فعلی حفظ می‌شود.",
                "info",
            )
            return
        healthy = result.get("dns_healthy")
        if healthy is False:
            self._route_bad_samples += 1
        elif healthy is True:
            self._route_bad_samples = 0
        if self.is_connected and self._route_bad_samples == 3:
            self.status_message.emit(
                "RouteDNA سه پاسخ ناموفق متوالی دید؛ مسیر DNS نیاز به تست هوشمند مجدد دارد.",
                "error",
            )

    # ---------- دسترسی هوشمند برنامه‌ها ----------

    def _refresh_app_profile_catalog(self):
        def worker():
            try:
                changed = app_profile_catalog_service.refresh()
            except Exception:
                changed = False
            if changed:
                self.refresh_app_catalog(full=True)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_app_catalog(self, full: bool = False):
        if self._app_scan_busy:
            return
        self._app_scan_busy = True

        def worker():
            try:
                if full or not self._app_catalog_installed:
                    self._app_catalog_installed = app_access_service.installed_app_records()
                rows = app_access_service.catalog_status(
                    installed_names={row["name"] for row in self._app_catalog_installed},
                    installed_records=list(self._app_catalog_installed),
                )
            except Exception:
                rows = []
            self._app_catalog_completed.emit(rows)

        threading.Thread(target=worker, daemon=True).start()

    def _on_app_catalog_completed(self, rows: list):
        self._app_scan_busy = False
        self.app_catalog_changed.emit(rows)

    @staticmethod
    def _profile_payload(profile):
        if profile is None:
            return None
        return {
            "name": profile.name, "primary": profile.primary,
            "secondary": profile.secondary, "doh_url": profile.doh_url,
        }

    def start_app_access(self, profile_id: str, mission: str, adapter_name: str,
                         allow_warp: bool = True):
        if self._match_route_locked:
            self.app_access_changed.emit({
                "ok": False,
                "error": "نشست واقعی بازی فعال است؛ تغییر مسیر تا پایان بازی قفل شده است.",
            })
            return
        profile = app_access_service.get_profile(profile_id)
        if profile is None:
            self.app_access_changed.emit({"ok": False, "error": "پروفایل برنامه معتبر نیست"})
            return
        if not adapter_name:
            self.app_access_changed.emit({"ok": False, "error": "کارت شبکه فعالی انتخاب نشده است"})
            return
        if self._busy or self._tunnel_busy:
            self.app_access_changed.emit({"ok": False, "error": "یک عملیات اتصال دیگر در حال اجراست"})
            return
        if self.tunnel_connected:
            self.app_access_changed.emit({
                "ok": False,
                "error": "برای جلوگیری از مسیر مبهم، ابتدا اتصال Game Mode را قطع کن.",
            })
            return

        mission = mission if mission in {"smart", "login", "download"} else "smart"
        previous = next(
            (item for item in self.dns_profiles if item.name == self.active_profile_name), None
        ) if self.is_connected else None
        previous_payload = self._profile_payload(previous)
        previous_adapter = self.active_adapter_name
        self._busy = True
        self._connection_generation = self._connection_state.begin(
            "app", f"پیش‌بررسی {profile.name}", cancellable=True
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self._app_access_generation += 1
        operation_generation = self._app_access_generation
        self.busy_changed.emit(True)
        self.app_access_progress.emit({
            "phase": "baseline", "step": 1, "total": 4,
            "message": f"دسترسی فعلی {profile.name} بدون تغییر شبکه بررسی می‌شود…",
        })

        def restore_previous():
            if previous is not None and previous_adapter:
                return dns_service.set_dns(
                    previous_adapter, previous.primary, previous.secondary or None,
                    previous.doh_url,
                )
            return dns_service.restore_original_dns(adapter_name)

        def worker():
            temporary_dns_changed = False
            temporary_warp = None
            warp_attempted = False
            dns_candidates_tested = 0
            last_probe = None
            route_context = {}
            dna_rounds = 2

            def cancelled() -> bool:
                return operation_generation != self._app_access_generation

            def finish_cancelled():
                if temporary_warp:
                    official_warp_service.disconnect_if_started(
                        bool(temporary_warp.get("started_by_app")),
                        temporary_warp.get("original_mode", ""),
                        temporary_warp.get("original_protocol", ""),
                    )
                if temporary_dns_changed:
                    restore_previous()
                self._app_access_completed.emit({
                    "operation": "start", "ok": False, "cancelled": True,
                    "profile_id": profile.id, "app_name": profile.name,
                    "error": "بررسی لغو شد و تغییرهای موقت شبکه بازگردانده شدند.",
                })

            def remember(route_name: str, ok: bool, probe: dict | None = None):
                if not route_context:
                    return
                try:
                    evidence = probe or {}
                    route_dna_service.record(
                        route_context, target=profile.id, route=route_name, success=ok,
                        latency_ms=int(evidence.get("median_ms", -1) or -1),
                    )
                except Exception:
                    pass
            try:
                settings = settings_service.load_settings()
                if settings.get("route_dna_enabled", True):
                    try:
                        route_context = self._route_dna_snapshot(
                            adapter_name, mission, settings, sample_pressure=True
                        )
                        policy = route_dna_service.probe_policy(
                            route_context,
                            game_running=bool(self._last_detected_game_name),
                            requested=str(settings.get("route_dna_probe_mode", "light")),
                        )
                        route_context["probe_policy"] = policy
                        budget = route_dna_service.reserve_probe_budget(
                            policy["max_kb"], int(settings.get("route_dna_daily_budget_mb", 25))
                        )
                        route_context["data_budget"] = budget
                        dna_rounds = policy["rounds"] if budget["allowed"] else 1
                        self.app_access_progress.emit({
                            "phase": "baseline", "step": 1, "total": 4,
                            "message": (
                                f"RouteDNA: {route_dna_service.summarize(route_context)}؛ "
                                f"آزمایش {policy['mode']} برای {profile.name}."
                            ),
                            "route_dna": route_context,
                        })
                    except Exception:
                        route_context = {}
                else:
                    self.app_access_progress.emit({
                        "phase": "baseline", "step": 1, "total": 4,
                        "message": (
                            "RouteDNA خاموش است؛ تست زنده عادی ادامه دارد. برای انتخاب شخصی‌تر "
                            "و بهترین نتیجه روی همین شبکه، آن را از تنظیمات حرفه‌ای روشن کن."
                        ),
                        "route_dna_disabled": True,
                    })
                baseline = app_access_service.probe_profile(profile, mission)
                if cancelled():
                    finish_cancelled()
                    return
                last_probe = baseline
                baseline_diagnosis = app_route_service.diagnose(baseline)
                warp_before = official_warp_service.inspect()
                if baseline["healthy"]:
                    remember("direct", True, baseline)
                    evidence = app_access_service.profile_connection_evidence(profile)
                    app_route_service.record_outcome(
                        profile_id=profile.id, mission=mission, adapter_name=adapter_name,
                        route="current", ok=True, median_ms=baseline.get("median_ms", -1),
                        diagnosis=baseline_diagnosis["code"],
                    )
                    self._app_access_completed.emit({
                        "operation": "start", "ok": True, "profile_id": profile.id,
                        "app_name": profile.name, "mission": mission,
                        "route": "current", "dns_changed": False,
                        "dns_name": self.active_profile_name or "تنظیم فعلی ویندوز",
                        "adapter": self.active_adapter_name or adapter_name,
                        "baseline": baseline, "after": baseline,
                        "previous_profile": previous_payload,
                        "previous_adapter": previous_adapter,
                        "warp_active": warp_before.trace_active,
                        "diagnosis": baseline_diagnosis, "evidence": evidence,
                        "route_dna": route_dna_service.enrich_probe(route_context, baseline),
                        "route_dna_explanation": route_dna_service.explain_choice(
                            route_context, route="direct", probe=baseline, target=profile.id
                        ) if route_context else "",
                        "message": "مسیر فعلی سالم بود؛ هیچ تغییر شبکه‌ای لازم نشد. ورود هنوز باید داخل برنامه تأیید شود.",
                    })
                    return

                domains = profile.domains_for(mission)
                goal = "balanced" if mission == "download" else "anti_sanction"
                self.app_access_progress.emit({
                    "phase": "ranking", "step": 2, "total": 4,
                    "message": f"DNSها روی {len(domains)} مقصد واقعی {profile.name} آزمایش می‌شوند…",
                })
                ranking = connectivity_service.rank_dns_profiles(
                    self.dns_profiles,
                    progress=lambda row: self.app_access_progress.emit({
                        "phase": "ranking", "step": 2, "total": 4,
                        "completed": row.get("completed", 0), "count": row.get("total", 0),
                        "message": f"آزمایش DNS: {row.get('name', 'در حال بررسی')}",
                    }),
                    preference="stable" if mission == "login" else "balanced",
                    goal=goal, domains=domains, rounds=dna_rounds,
                )
                if cancelled():
                    finish_cancelled()
                    return
                if route_context:
                    ranking = route_dna_service.personalize_ranked_dns(
                        ranking, route_context, profile.id
                    )
                # Four pre-ranked candidates are enough for App Access.  A hard
                # cap prevents a degraded network from turning one click into
                # several minutes of retries.
                ranking = ranking[:4]
                dns_failure = "هیچ DNS مناسبی پاسخ معتبر نداد"
                if ranking and not privileged_helper.is_admin():
                    shortlisted = ranking[:4]
                    self.app_access_progress.emit({
                        "phase": "verify", "step": 3, "total": 4,
                        "message": (
                            "یک‌بار اجازه مدیر را تأیید کن؛ حداکثر ۴ DNS برتر داخل همان "
                            "پنجره و با سقف زمانی مشخص آزمایش می‌شوند."
                        ),
                    })
                    candidate_payload = [{
                        "name": row["profile"].name,
                        "servers": [
                            value for value in (
                                row["profile"].primary, row["profile"].secondary,
                            ) if value
                        ],
                        "doh_url": row["profile"].doh_url,
                    } for row in shortlisted]
                    batch = privileged_helper.select_dns(
                        adapter_name, candidate_payload, list(domains),
                        progress=lambda row: self.app_access_progress.emit({
                            "phase": "verify", "step": 3, "total": 4,
                            "candidate": row.get("index", 0),
                            "candidate_count": row.get("count", len(shortlisted)),
                            "message": (
                                f"نامزد {row.get('index', 0)} از {row.get('count', len(shortlisted))}: "
                                f"DNS «{row.get('name', 'در حال بررسی')}» در حال تأیید است…"
                            ),
                        }),
                    )
                    if cancelled():
                        temporary_dns_changed = bool(batch.get("ok"))
                        finish_cancelled()
                        return
                    dns_candidates_tested = int(batch.get("tested", 0) or 0)
                    last_probe = batch.get("last_probe") or last_probe
                    if batch.get("ok"):
                        selected = batch.get("selected") or {}
                        chosen = next(
                            (row for row in shortlisted
                             if row["profile"].name == selected.get("name")),
                            shortlisted[0],
                        )
                        dns_profile = chosen["profile"]
                        after = selected.get("probe") or {}
                        diagnosis = app_route_service.diagnose(after)
                        remember(f"dns:{dns_profile.name}", True, after)
                        evidence = app_access_service.profile_connection_evidence(profile)
                        candidate_index = int(selected.get("index", 1))
                        app_route_service.record_outcome(
                            profile_id=profile.id, mission=mission, adapter_name=adapter_name,
                            route="dns", ok=True, mode=dns_profile.name,
                            median_ms=after.get("median_ms", -1), diagnosis=diagnosis["code"],
                        )
                        self._app_access_completed.emit({
                            "operation": "start", "ok": True, "profile_id": profile.id,
                            "app_name": profile.name, "mission": mission,
                            "route": "dns", "dns_changed": True,
                            "dns_name": dns_profile.name, "adapter": adapter_name,
                            "dns_score": chosen.get("score", 0),
                            "dns_candidates_tested": candidate_index,
                            "baseline": baseline, "after": after,
                            "previous_profile": previous_payload,
                            "previous_adapter": previous_adapter,
                            "warp_active": warp_before.trace_active,
                            "diagnosis": diagnosis, "evidence": evidence,
                            "route_dna": route_dna_service.enrich_probe(route_context, after),
                            "route_dna_explanation": route_dna_service.explain_choice(
                                route_context, route=f"dns:{dns_profile.name}",
                                probe=after, target=profile.id,
                            ) if route_context else "",
                            "message": (
                                f"با یک اجازه مدیر، {candidate_index} نامزد بررسی شد و "
                                f"{after.get('tls_ok', 0)} از {after.get('attempted', 0)} مقصد تأیید شد."
                            ),
                        })
                        return
                    if not batch.get("restored", True):
                        raise RuntimeError("آزمایش DNS تمام شد اما بازگردانی تنظیم قبلی کامل نشد.")
                    dns_failure = batch.get("error", dns_failure)
                    ranking = []
                if ranking:
                    dns_failures = []
                    candidate_count = len(ranking)
                    for candidate_index, chosen in enumerate(ranking, start=1):
                        if cancelled():
                            finish_cancelled()
                            return
                        dns_profile = chosen["profile"]
                        self.app_access_progress.emit({
                            "phase": "verify", "step": 3, "total": 4,
                            "candidate": candidate_index, "candidate_count": candidate_count,
                            "message": (
                                f"نامزد {candidate_index} از {candidate_count}: DNS «{dns_profile.name}» "
                                "روی مقصدهای برنامه تأیید می‌شود…"
                            ),
                        })
                        changed = not (
                            self.is_connected and self.active_adapter_name == adapter_name
                            and self.active_profile_name == dns_profile.name
                        )
                        applied = not changed or dns_service.set_dns(
                            adapter_name, dns_profile.primary, dns_profile.secondary or None,
                            dns_profile.doh_url,
                        )
                        temporary_dns_changed = bool(temporary_dns_changed or (applied and changed))
                        if not applied:
                            dns_failures.append(
                                f"{dns_profile.name}: "
                                f"{dns_service.get_last_error() or 'ویندوز تغییر DNS را نپذیرفت'}"
                            )
                            continue
                        after = app_access_service.probe_profile(profile, mission)
                        if cancelled():
                            finish_cancelled()
                            return
                        last_probe = after
                        dns_candidates_tested = candidate_index
                        diagnosis = app_route_service.diagnose(after)
                        if not after["healthy"]:
                            remember(f"dns:{dns_profile.name}", False, after)
                            dns_failures.append(f"{dns_profile.name}: {diagnosis['title']}")
                            continue
                        evidence = app_access_service.profile_connection_evidence(profile)
                        remember(f"dns:{dns_profile.name}", True, after)
                        app_route_service.record_outcome(
                            profile_id=profile.id, mission=mission, adapter_name=adapter_name,
                            route="dns", ok=True, median_ms=after.get("median_ms", -1),
                            diagnosis=diagnosis["code"],
                        )
                        self._app_access_completed.emit({
                            "operation": "start", "ok": True, "profile_id": profile.id,
                            "app_name": profile.name, "mission": mission,
                            "route": "dns", "dns_changed": temporary_dns_changed,
                            "dns_name": dns_profile.name, "adapter": adapter_name,
                            "dns_score": chosen.get("score", 0),
                            "dns_candidates_tested": candidate_index,
                            "baseline": baseline, "after": after,
                            "previous_profile": previous_payload,
                            "previous_adapter": previous_adapter,
                            "warp_active": warp_before.trace_active,
                            "diagnosis": diagnosis, "evidence": evidence,
                            "route_dna": route_dna_service.enrich_probe(route_context, after),
                            "route_dna_explanation": route_dna_service.explain_choice(
                                route_context, route=f"dns:{dns_profile.name}",
                                probe=after, target=profile.id,
                            ) if route_context else "",
                            "message": (
                                f"پس از بررسی {candidate_index} نامزد، {after['tls_ok']} از "
                                f"{after['attempted']} مقصد با TLS تأیید شد. "
                                "عملکرد ورود باید داخل خود برنامه تأیید شود."
                            ),
                        })
                        return
                    if temporary_dns_changed:
                        restored = restore_previous()
                        if not restored:
                            raise RuntimeError(
                                "بازگردانی DNS قبلی کامل نشد؛ برای ایمنی آزمایش WARP شروع نشد."
                            )
                        temporary_dns_changed = False
                    if dns_failures:
                        dns_failure = " | ".join(dns_failures[-3:])

                warp_retry_allowed = app_route_service.warp_retry_allowed(
                    profile.id, mission, adapter_name
                )
                if (allow_warp and warp_before.installed and warp_before.signature_valid
                        and warp_retry_allowed):
                    if cancelled():
                        finish_cancelled()
                        return
                    self.app_access_progress.emit({
                        "phase": "warp", "step": 4, "total": 4,
                        "message": "DNS کافی نبود؛ حالت‌های امن کلاینت رسمی Cloudflare آزمایش می‌شوند…",
                    })
                    modes = app_route_service.preferred_warp_modes(
                        profile.id, mission, adapter_name
                    )
                    warp_attempted = True
                    warp_result = official_warp_service.connect_best(
                        modes=modes,
                        max_attempts=2,
                        total_budget_s=22,
                        verify_attempts=2,
                        progress=lambda message: self.app_access_progress.emit({
                            "phase": "warp", "step": 4, "total": 4,
                            "message": message,
                        }),
                    )
                    temporary_warp = warp_result if warp_result.get("ok") else None
                    if cancelled():
                        finish_cancelled()
                        return
                    if warp_result.get("ok"):
                        after = app_access_service.probe_profile(profile, mission)
                        last_probe = after
                        diagnosis = app_route_service.diagnose(after)
                        if after["healthy"]:
                            remember(f"warp:{warp_result.get('mode', '')}", True, after)
                            evidence = app_access_service.profile_connection_evidence(profile)
                            app_route_service.record_outcome(
                                profile_id=profile.id, mission=mission, adapter_name=adapter_name,
                                route="warp", ok=True, mode=warp_result.get("mode", ""),
                                median_ms=after.get("median_ms", -1), diagnosis=diagnosis["code"],
                            )
                            self._app_access_completed.emit({
                                "operation": "start", "ok": True, "profile_id": profile.id,
                                "app_name": profile.name, "mission": mission,
                                "route": "warp", "dns_changed": False,
                                "dns_name": "DNS داخل مسیر WARP", "adapter": adapter_name,
                                "baseline": baseline, "after": after,
                                "previous_profile": previous_payload,
                                "previous_adapter": previous_adapter,
                                "warp_active": True,
                                "warp_started_by_app": bool(warp_result.get("started_by_app")),
                                "warp_original_mode": warp_result.get("original_mode", ""),
                                "warp_original_protocol": warp_result.get("original_protocol", ""),
                                "warp_mode": warp_result.get("mode", ""),
                                "warp_mode_label": warp_result.get("mode_label", "مسیر رسمی Cloudflare"),
                                "diagnosis": diagnosis, "evidence": evidence,
                                "route_dna": route_dna_service.enrich_probe(route_context, after),
                                "route_dna_explanation": route_dna_service.explain_choice(
                                    route_context, route=f"warp:{warp_result.get('mode', '')}",
                                    probe=after, target=profile.id,
                                ) if route_context else "",
                                "message": (
                                    f"{after['tls_ok']} از {after['attempted']} مقصد پس از WARP تأیید شد. "
                                    "WARP ممکن است موقتاً روی کل دستگاه اثر بگذارد؛ ورود را داخل برنامه بررسی کن."
                                ),
                            })
                            return
                        official_warp_service.disconnect_if_started(
                            bool(warp_result.get("started_by_app")),
                            warp_result.get("original_mode", ""),
                            warp_result.get("original_protocol", ""),
                        )
                        temporary_warp = None
                        warp_failure = diagnosis["title"]
                    else:
                        warp_failure = warp_result.get("error", "WARP رسمی متصل نشد")
                elif allow_warp and not warp_retry_allowed:
                    warp_failure = (
                        "WARP اخیراً روی همین شبکه ناموفق بوده؛ برای جلوگیری از انتظار دوباره، "
                        "تا ۳۰ دقیقه آزمایش نشد"
                    )
                elif allow_warp and not warp_before.installed:
                    warp_failure = "کلاینت رسمی Cloudflare نصب نیست"
                elif allow_warp and not warp_before.signature_valid:
                    warp_failure = "امضای کلاینت Cloudflare تأیید نشد"
                else:
                    warp_failure = "آزمایش WARP توسط کاربر خاموش است"

                failure = app_route_service.diagnose(baseline)
                app_route_service.record_outcome(
                    profile_id=profile.id, mission=mission, adapter_name=adapter_name,
                    route="failed", ok=False,
                    mode="warp-unavailable" if warp_attempted else "",
                    diagnosis=failure["code"],
                )
                final_diagnosis = app_route_service.diagnose(last_probe or baseline)
                remember("failed", False, last_probe or baseline)
                if final_diagnosis["code"] == "dns-sinkhole":
                    error = (
                        f"{profile.name} به یک IP خصوصیِ غیرقابل‌دسترسی هدایت شد. "
                        "روی این اینترنت، DNS تنها کافی نیست و WARP رسمی هم مسیر سالمی پیدا نکرد. "
                        "تنظیمات شبکه به حالت قبل برگشت."
                    )
                else:
                    error = (
                        f"{failure['title']}. DNS: {dns_failure}. WARP: {warp_failure}. "
                        "هیچ تغییر شبکه‌ای باقی نماند."
                    )
                raise RuntimeError(error)
            except Exception as exc:
                if temporary_warp:
                    official_warp_service.disconnect_if_started(
                        bool(temporary_warp.get("started_by_app")),
                        temporary_warp.get("original_mode", ""),
                        temporary_warp.get("original_protocol", ""),
                    )
                if temporary_dns_changed:
                    restore_previous()
                self._app_access_completed.emit({
                    "operation": "start", "ok": False, "profile_id": profile.id,
                    "app_name": profile.name, "mission": mission,
                    "error": str(exc)[:500], "baseline": locals().get("baseline") or {},
                    "last_probe": last_probe or {},
                    "dns_candidates_tested": dns_candidates_tested,
                    "warp_attempted": warp_attempted,
                    "route_dna": route_dna_service.enrich_probe(route_context, last_probe),
                })

        self._app_access_worker = threading.Thread(
            target=worker, daemon=True, name=f"app-access-{operation_generation}"
        )
        self._app_access_worker.start()

    def wait_for_app_access(self, timeout: float = 5.0) -> bool:
        """Wait briefly for the current App Access worker to terminate."""
        worker = self._app_access_worker
        if worker is None or worker is threading.current_thread():
            return True
        worker.join(max(0.0, float(timeout)))
        return not worker.is_alive()

    def cancel_app_access(self):
        if not self._busy:
            return
        self._app_access_generation += 1
        self._connection_state.cancel(
            self._connection_generation, "لغو شد؛ شبکه در حال بازگردانی است"
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self.app_access_progress.emit({
            "phase": "restore", "step": 1, "total": 1,
            "message": "لغو ثبت شد؛ عملیات جاری در اولین نقطه امن متوقف و شبکه بازگردانده می‌شود…",
        })

    def stop_app_access(self):
        session = dict(self._app_access_session)
        if self._busy or not session:
            return
        self._busy = True
        self._connection_generation = self._connection_state.begin(
            "app", "بازگردانی پروفایل برنامه", cancellable=False
        )
        self._connection_state.advance(self._connection_generation, "restoring")
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self.busy_changed.emit(True)
        self.app_access_progress.emit({
            "phase": "restore", "step": 1, "total": 1,
            "message": "تنظیم شبکه قبل از App Access در حال بازگردانی است…",
        })

        def worker():
            try:
                previous = session.get("previous_profile") or {}
                previous_adapter = session.get("previous_adapter")
                warp_ok = True
                if session.get("route") == "warp":
                    warp_result = official_warp_service.disconnect_if_started(
                        bool(session.get("warp_started_by_app")),
                        session.get("warp_original_mode", ""),
                        session.get("warp_original_protocol", ""),
                    )
                    warp_ok = bool(warp_result.get("ok"))
                if session.get("dns_changed"):
                    if previous and previous_adapter:
                        ok = dns_service.set_dns(
                            previous_adapter, previous["primary"], previous.get("secondary") or None,
                            previous.get("doh_url", ""),
                        )
                    else:
                        ok = dns_service.restore_original_dns(session.get("adapter"))
                else:
                    ok = True
                self._app_access_completed.emit({
                    "operation": "stop", "ok": bool(ok and warp_ok),
                    "error": "" if ok and warp_ok else (
                        dns_service.get_last_error() or "بازگردانی مسیر شبکه کامل نشد"
                    ),
                    "previous_profile": previous,
                    "previous_adapter": previous_adapter,
                })
            except Exception as exc:
                self._app_access_completed.emit({"operation": "stop", "ok": False, "error": str(exc)[:500]})

        self._app_access_worker = threading.Thread(
            target=worker, daemon=True, name="app-access-restore"
        )
        self._app_access_worker.start()

    def _on_app_access_completed(self, result: dict):
        self._busy = False
        self.busy_changed.emit(False)
        operation = result.get("operation", "start")
        if result.get("ok") and operation == "start":
            self._connection_state.advance(
                self._connection_generation, "active", "پروفایل برنامه فعال است",
                owned_by_app=bool(result.get("dns_changed") or result.get("warp_started_by_app")),
            )
        elif result.get("ok") and operation == "stop":
            self._connection_state.reset("تنظیم قبلی شبکه بازگردانده شد")
        elif result.get("cancelled"):
            self._connection_state.reset("عملیات لغو و تغییر موقت بازگردانده شد")
        else:
            self._connection_state.advance(
                self._connection_generation, "failed", str(result.get("error") or "اتصال کامل نشد")
            )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        if operation == "stop":
            if result.get("ok"):
                previous = result.get("previous_profile") or {}
                self._app_access_session = {}
                if previous and result.get("previous_adapter"):
                    self.is_connected = True
                    self.active_adapter_name = result["previous_adapter"]
                    self.active_profile_name = previous.get("name")
                    self.connection_changed.emit(True, self.active_profile_name or "DNS")
                else:
                    self.is_connected = False
                    self.active_adapter_name = None
                    self.active_profile_name = None
                    self.connection_changed.emit(False, "")
                self.status_message.emit("App Access متوقف و تنظیم قبلی شبکه بازگردانی شد", "success")
            else:
                self.status_message.emit(result.get("error", "بازگردانی کامل نشد"), "error")
            self.app_access_changed.emit(result)
            self.refresh_adapters()
            return

        if result.get("ok"):
            self._app_access_session = dict(result)
            self._app_access_session["seen_running"] = False
            self._app_access_session["watch_ticks"] = 0
            if result.get("route") == "dns":
                self.is_connected = True
                self.active_adapter_name = result.get("adapter")
                self.active_profile_name = result.get("dns_name")
                self.connection_changed.emit(True, self.active_profile_name or "DNS")
            self.status_message.emit(f"پروفایل {result.get('app_name')} آماده شد ✅", "success")
        else:
            detail = str(result.get("error") or "مسیر قابل تأییدی پیدا نشد")
            self.status_message.emit(
                detail[:220],
                "error",
            )
        self.app_access_changed.emit(result)
        self.refresh_adapters()

    def _app_access_watch_tick(self):
        if not self._app_access_session or self._busy:
            return
        profile_id = self._app_access_session.get("profile_id")
        running = profile_id in app_access_service.active_profile_ids()
        if running:
            self._app_access_session["seen_running"] = True
            self._app_access_session["watch_ticks"] = int(
                self._app_access_session.get("watch_ticks", 0)
            ) + 1
            if self._app_access_session["watch_ticks"] % 3 == 0:
                profile = app_access_service.get_profile(profile_id)
                if profile is not None:
                    evidence = app_access_service.profile_connection_evidence(profile)
                    self._app_access_session["evidence"] = evidence
                    self.app_access_changed.emit({
                        "operation": "evidence", "ok": True,
                        "profile_id": profile_id, "evidence": evidence,
                    })
            if self._app_access_session["watch_ticks"] % 5 == 0:
                previous_context = self._app_access_session.get("route_dna") or {}
                adapter = self._app_access_session.get("adapter") or self.active_adapter_name
                if previous_context and adapter:
                    try:
                        current_context = route_dna_service.snapshot(
                            adapter, self._app_access_session.get("mission", "smart"),
                            sample_pressure=False,
                        )
                        drift = route_dna_service.detect_drift(previous_context, current_context)
                        if drift.get("changed"):
                            current_context = self._route_dna_snapshot(
                                adapter, self._app_access_session.get("mission", "smart"),
                                settings_service.load_settings(), sample_pressure=False,
                            )
                            self._app_access_session["route_dna"] = current_context
                            self.app_access_changed.emit({
                                "operation": "route_drift", "ok": True,
                                "profile_id": profile_id, "drift": drift,
                            })
                    except Exception:
                        pass
        elif self._app_access_session.get("seen_running"):
            self.app_access_progress.emit({
                "phase": "restore", "step": 1, "total": 1,
                "message": "برنامه بسته شد؛ تنظیم قبلی شبکه خودکار بازمی‌گردد…",
            })
            self.stop_app_access()

    # ---------- آپدیت امن ----------

    def check_for_updates(self, manual: bool = False):
        def worker():
            channel = str(settings_service.load_settings().get(
                "update_channel", "stable"
            ))
            result = update_service.check_for_update(channel=channel)
            settings_service.set_value(
                "last_update_check", datetime.now(timezone.utc).isoformat()
            )
            self.update_check_ready.emit({
                "configured": result.configured,
                "available": result.available,
                "message": result.message,
                "manifest": result.manifest or {},
                "manual": manual,
                "channel": channel,
            })

        threading.Thread(target=worker, daemon=True).start()

    def download_update(self, manifest: dict):
        if self._optimizing_game:
            self.update_download_ready.emit(
                "", "بازی در حال اجراست؛ دانلود آپدیت تا پایان Session قفل شد"
            )
            return
        self._update_download_cancel.clear()

        def worker():
            try:
                path = update_service.download_verified_installer(
                    manifest,
                    public_key_b64=UPDATE_PUBLIC_KEY_B64,
                    progress=lambda received, total: self.update_download_progress.emit(
                        int(received), int(total)
                    ),
                    cancelled=self._update_download_cancel.is_set,
                )
                self.update_download_ready.emit(str(path), "")
            except Exception as exc:
                self.update_download_ready.emit("", str(exc)[:400])

        threading.Thread(target=worker, daemon=True).start()

    def cancel_update_download(self):
        self._update_download_cancel.set()

    def downloaded_update_has_authenticode(self, path: str) -> bool:
        return update_service.has_valid_authenticode(Path(path))

    def install_downloaded_update(
        self, path: str, manifest: dict, allow_unsigned: bool = False
    ) -> tuple[bool, str]:
        if self._optimizing_game:
            return False, "بازی در حال اجراست؛ نصب آپدیت تا پایان Session قفل شد"
        return update_service.launch_verified_installer(
            Path(path), manifest,
            public_key_b64=UPDATE_PUBLIC_KEY_B64,
            allow_unsigned=allow_unsigned,
        )

    def probe_game_server(self, game, phase: str = "current"):
        """Measure an endpoint observed on the game process without blocking the UI."""
        if not game or not game.process_name.strip():
            self.game_server_probe_ready.emit({"error": "برای این بازی نام پروسه ثبت نشده است"})
            return
        process_key = game.process_name.strip().lower()
        connection = (
            (
                f"تانل اختصاصی بازی · {self.active_tunnel_name or 'فعال'}"
                if self._active_process_names else f"تانل سراسری · {self.active_tunnel_name or 'فعال'}"
            ) if self.tunnel_connected
            else f"DNS · {self.active_profile_name or 'فعال'}" if self.is_connected
            else "اینترنت مستقیم / تنظیم فعلی ویندوز"
        )

        def worker():
            baseline = self._game_probe_baselines.get(process_key)
            if phase == "current" and baseline:
                endpoint = {
                    "host": baseline["host"], "port": baseline["port"],
                    "transport": baseline["transport"], "priority": 0,
                }
                result = game_server_probe_service.benchmark_endpoint(
                    endpoint, mode=getattr(game, "connection_mode", "balanced")
                )
                if not result.get("available"):
                    result = {"error": "همان مقصد قبلی این بار پاسخ آزمایش را نداد"}
            else:
                result = game_server_probe_service.probe_game_server(
                    game.process_name, getattr(game, "connection_mode", "balanced")
                )
            result.update({
                "game": game.name, "process": game.process_name,
                "phase": phase, "connection": connection,
            })
            if not result.get("error") and phase == "baseline":
                self._game_probe_baselines[process_key] = dict(result)
            if not result.get("error") and phase == "current" and baseline:
                result["baseline"] = baseline
                result["latency_delta"] = result["latency_ms"] - baseline["latency_ms"]
                result["jitter_delta"] = result["jitter_ms"] - baseline["jitter_ms"]
                result["loss_delta"] = round(result["loss"] - baseline["loss"], 1)
                if self.tunnel_connected and self._active_process_names:
                    result["scope_warning"] = (
                        "تانل فقط پروسه بازی را عبور می‌دهد؛ پروب مستقل برنامه ممکن است مسیر مستقیم را بسنجد."
                    )
                trustworthy = not result.get("scope_warning") and str(
                    baseline.get("connection", "")
                ).startswith("اینترنت مستقیم")
                result["rollback_recommended"] = bool(
                    trustworthy and (
                        result["latency_delta"] >= 25 or result["loss_delta"] >= 5
                    )
                )
                result["truth"] = network_lab_service.truth_engine(
                    baseline, result, bool(self.tunnel_connected and self._active_process_names)
                )
            self.game_server_probe_ready.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def has_game_probe_baseline(self, game) -> bool:
        return bool(
            game and game.process_name.strip().lower() in self._game_probe_baselines
        )

    def learn_game_route_profile(self, game):
        if not game or not game.process_name.strip():
            self.game_route_profile_ready.emit("", {}, "برای بازی نام پروسه ثبت نشده است")
            return
        self.status_message.emit(f"یادگیری مسیرهای واقعی «{game.name}» شروع شد…", "info")
        self._route_learning_game = game
        if settings_service.load_settings().get("air_lite_enabled", True):
            self._air_timer.start()
        self._network_monitor_timer.start()
        session_generation = self._game_session_generation

        def worker():
            try:
                profile = game_route_profile_service.learn(
                    game.process_name, game.route_profile,
                    getattr(game, "connection_mode", "balanced"),
                    context=(
                        f"{self.active_adapter_name or (self.adapters[0].name if self.adapters else 'unknown')}|"
                        + ("tunnel" if self.tunnel_connected else "dns" if self.is_connected else "direct")
                    ),
                )
                if (session_generation != self._game_session_generation
                        or self._last_detected_game_name != game.name):
                    return
                if profile.get("error"):
                    self.game_route_profile_ready.emit(game.name, {}, profile["error"])
                    return
                game.route_profile = profile
                games_service.save_games(self.games)
                self.games_changed.emit(self.games)
                self.game_route_profile_ready.emit(game.name, profile, "")
                try:
                    relay_host = getattr(self._active_tunnel_config, "host", "") or ""
                    learned_endpoints = profile.get("endpoints", [])
                    lab = (
                        network_lab_service.run_for_endpoint(learned_endpoints[0], relay_host)
                        if learned_endpoints and not profile.get("lobby_waiting") else
                        network_lab_service.run(game.process_name, relay_host)
                    )
                    lab["game"] = game.name
                    self.network_lab_ready.emit(lab)
                except Exception as exc:
                    self.network_lab_ready.emit({"game": game.name, "error": str(exc)})
            except Exception as exc:
                self.game_route_profile_ready.emit(game.name, {}, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def clear_game_route_profile(self, game):
        if not game:
            return
        game.route_profile = {}
        games_service.save_games(self.games)
        self.games_changed.emit(self.games)
        self.game_route_profile_ready.emit(game.name, {}, "")
        self.status_message.emit(f"یادگیری محلی «{game.name}» پاک شد", "info")

    def set_game_route_profile(self, game, profile: dict):
        if not game:
            return
        game.route_profile = profile
        games_service.save_games(self.games)
        self.games_changed.emit(self.games)
        self.game_route_profile_ready.emit(game.name, profile, "")

    def rollback_active_route(self):
        if self.tunnel_connected:
            self.disconnect_tunnel()
        elif self.is_connected:
            self.disconnect_dns()

    # ---------- آداپتورها ----------

    def refresh_adapters(self):
        if not self._pending_recovery_notice_checked:
            self._pending_recovery_notice_checked = True
            pending = recovery_service.receipt(1)
            if pending.get("pending_qos") or pending.get("pending_warp"):
                self.status_message.emit(
                    "بازیابی امن از اجرای قبلی آماده است؛ از تنظیمات، بازنشانی اضطراری را اجرا کن",
                    "info",
                )
        if not self._pending_dns_recovery_checked:
            self._pending_dns_recovery_checked = True
            if dns_service.has_pending_restore():
                threading.Thread(target=self._recover_dns_after_crash, daemon=True).start()
        try:
            self.adapters = adapter_service.list_adapters()
            self.adapters_changed.emit(self.adapters)
        except Exception as e:
            self.status_message.emit(f"خطا در گرفتن آداپتورها: {e}", "error")

    def _recover_dns_after_crash(self):
        if dns_service.restore_original_dns():
            self.status_message.emit("تنظیم DNS باقی‌مانده از اجرای قبلی بازیابی شد", "info")

    def apply_dns_profile(self, adapter_name: str, profile_name: str, primary: str,
                          secondary: str = "", doh_url: str = ""):
        """اعمال DNS در یک ترد جدا تا UI فریز/کرش نکنه، با قفل busy برای جلوگیری از کلیک مکرر"""
        if self._match_route_locked:
            self.status_message.emit("Match Lock فعال است؛ DNS وسط نشست بازی تغییر نمی‌کند", "info")
            return
        if self._busy:
            return  # کلیک تکراری رو نادیده می‌گیریم به‌جای صف کردن عملیات
        self._busy = True
        self._connection_generation = self._connection_state.begin(
            "dns", f"پیش‌بررسی DNS {profile_name}", cancellable=False
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self._pending_dns_quality = None
        self.busy_changed.emit(True)
        self.status_message.emit("در حال تحلیل و اتصال…", "info")

        def worker():
            try:
                self._connection_state.advance(
                    self._connection_generation, "testing", "سنجش کیفیت DNS انتخابی"
                )
                self.connection_flow_changed.emit(self._connection_state.snapshot())
                profile = next(
                    (item for item in self.dns_profiles
                     if item.name == profile_name and item.primary == primary),
                    None,
                )
                if profile is not None:
                    self.dns_benchmark_progress.emit({
                        "completed": 0, "total": 1, "name": profile.name
                    })
                    quality = connectivity_service.benchmark_dns_profile(profile)
                    self.dns_benchmark_progress.emit({
                        "completed": 1, "total": 1, "name": profile.name
                    })
                    if quality["score"] <= 0:
                        self.dns_quality_ready.emit({
                            "error": f"DNS «{profile.name}» در آزمایش چندمرحله‌ای پاسخ معتبر نداد"
                        })
                        self._dns_apply_completed.emit(
                            False, adapter_name, profile_name, "DNS انتخابی پاسخ پایدار نداد"
                        )
                        return
                    self._pending_dns_quality = {**quality, "ranking": [quality]}
                ok = dns_service.set_dns(adapter_name, primary, secondary or None, doh_url)
                error = dns_service.get_last_error() if not ok else ""
            except Exception as exc:
                ok = False
                error = str(exc)
            self._dns_apply_completed.emit(ok, adapter_name, profile_name, error)

        threading.Thread(target=worker, daemon=True).start()

    def apply_best_dns(self, adapter_name: str, preference: str = "balanced",
                       goal: str = "balanced"):
        if self._match_route_locked:
            self.status_message.emit("Match Lock فعال است؛ انتخاب DNS تا پایان بازی متوقف شد", "info")
            return
        if self._busy:
            return
        self._busy = True
        self._connection_generation = self._connection_state.begin(
            "dns", "مسابقه DNS هوشمند", cancellable=False
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self._pending_dns_quality = None
        self.busy_changed.emit(True)
        if settings_service.load_settings().get("route_dna_enabled", True):
            self.status_message.emit("RouteDNA روشن است؛ انتخاب شخصی DNS شروع شد…", "info")
        else:
            self.status_message.emit(
                "RouteDNA خاموش است؛ DNS با تست زنده عمومی انتخاب می‌شود. برای بهترین انتخاب شخصی آن را روشن کن.",
                "info",
            )
        candidates = connectivity_service.profiles_for_goal(self.dns_profiles, goal)
        self.dns_benchmark_progress.emit({
            "completed": 0, "total": len(candidates), "name": "آماده‌سازی آزمایش‌ها"
        })

        def worker():
            self._connection_state.advance(
                self._connection_generation, "testing", "مقایسه نامزدهای DNS"
            )
            self.connection_flow_changed.emit(self._connection_state.snapshot())
            route_context = {}
            dna_rounds = 2
            try:
                if settings_service.load_settings().get("route_dna_enabled", True):
                    route_context = self._route_dna_snapshot(
                        adapter_name,
                        "download" if goal == "speed" else "smart",
                        settings_service.load_settings(), sample_pressure=True,
                    )
                    policy = route_dna_service.probe_policy(
                        route_context,
                        game_running=bool(self._last_detected_game_name),
                        requested=str(settings_service.load_settings().get(
                            "route_dna_probe_mode", "light"
                        )),
                    )
                    budget = route_dna_service.reserve_probe_budget(
                        policy["max_kb"], int(settings_service.load_settings().get(
                            "route_dna_daily_budget_mb", 25
                        )),
                    )
                    route_context.update({"probe_policy": policy, "data_budget": budget})
                    dna_rounds = policy["rounds"] if budget["allowed"] else 1
            except Exception:
                route_context = {}
            ranking = connectivity_service.rank_dns_profiles(
                self.dns_profiles, progress=self.dns_benchmark_progress.emit,
                preference=preference, goal=goal, rounds=dna_rounds,
            )
            if route_context:
                ranking = route_dna_service.personalize_ranked_dns(
                    ranking, route_context, f"dns-{goal}"
                )
            if not ranking:
                self.dns_quality_ready.emit({
                    "error": "هیچ DNSی در تمام آزمایش‌ها پاسخ معتبر نداد"
                })
                self._dns_apply_completed.emit(
                    False, adapter_name, "", "هیچ‌کدام از DNSها پاسخ معتبر ندادند"
                )
                return
            best = ranking[0]
            profile = best["profile"]
            ok = dns_service.set_dns(
                adapter_name, profile.primary, profile.secondary or None, profile.doh_url
            )
            self._pending_dns_quality = {
                **best, "ranking": ranking, "preference": preference, "goal": goal,
                "route_dna": route_context,
                "route_dna_summary": route_dna_service.summarize(route_context)
                if route_context else "",
                "route_dna_explanation": route_dna_service.explain_choice(
                    route_context, route=f"dns:{profile.name}",
                    probe={"median_ms": best.get("median_ms", -1)},
                    target=f"dns-{goal}",
                ) if route_context else "",
            }
            name = profile.name
            error = dns_service.get_last_error() if not ok else ""
            self._dns_apply_completed.emit(ok, adapter_name, name, error)

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, ok: bool, adapter_name: str, profile_name: str,
                           error: str = ""):
        self._busy = False
        self.busy_changed.emit(False)
        self._connection_state.advance(
            self._connection_generation, "active" if ok else "failed",
            f"DNS {profile_name} فعال است" if ok else (error or "اتصال DNS کامل نشد"),
            owned_by_app=ok,
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        if ok:
            self.active_adapter_name = adapter_name
            self.active_profile_name = profile_name
            self.is_connected = True
            self.status_message.emit(f"با موفقیت به «{profile_name}» وصل شدید ✅", "success")
            self.connection_changed.emit(True, profile_name)
            self._active_route_context = dict(
                (self._pending_dns_quality or {}).get("route_dna") or {}
            )
            self._route_bad_samples = 0
            if self.kill_switch_enabled:
                self._watchdog_timer.start()
            if self._pending_dns_quality:
                self.dns_quality_ready.emit(self._pending_dns_quality)
        else:
            detail = error or "ویندوز تغییر DNS را نپذیرفت"
            self.status_message.emit(f"اتصال DNS ناموفق بود: {detail} ⚠️", "error")
        if self._optimizing_game and self._game_started_dns:
            game_name = self._optimizing_game.name
            if ok:
                quality = self._pending_dns_quality or {}
                quality_text = (
                    f" · DNS Score {quality.get('score')}/100 · میانه {quality.get('median_ms')}ms"
                    if quality else ""
                )
                self.game_optimization_progress.emit(
                    game_name, "done",
                    f"۳. DNS «{profile_name}» روی «{adapter_name}» فعال شد{quality_text}"
                )
                self.optimization_state_changed.emit({
                    "game": game_name, "running": True, "stage": "connected",
                    "strategy": "dns", "dns": f"فعال: {profile_name}",
                    "tunnel": "خاموش", "routing": f"DNS کارت شبکه {adapter_name}",
                    "failover": "محافظ DNS" if self.kill_switch_enabled else "خاموش",
                    "turbo": "غیرفعال", "turbo_reason": "در اتصال DNS کاربردی ندارد",
                    "effect": (
                        f"DNS Score {quality.get('score', '—')}/100؛ پاسخ معمول "
                        f"{quality.get('median_ms', '—')}ms، نوسان {quality.get('jitter_ms', '—')}ms، "
                        f"موفقیت {quality.get('success_rate', '—')}٪. مسیر دیتای بازی تغییر نکرده است."
                    ),
                })
            else:
                self.game_optimization_progress.emit(game_name, "error", f"اعمال DNS شکست خورد: {detail}")
                self.optimization_state_changed.emit({
                    "game": game_name, "running": True, "stage": "failed",
                    "dns": "ناموفق", "tunnel": "خاموش", "routing": "بدون تغییر",
                    "failover": "غیرفعال", "turbo": "غیرفعال", "effect": detail,
                })
        self.refresh_adapters()
        if self._pending_game_stop_dns:
            self._pending_game_stop_dns = False
            if ok and self.is_connected:
                self.disconnect_dns()

    def disconnect_dns(self):
        """قطع اتصال و بازگردوندن DNS به حالت خودکار — فقط وقتی وصل باشیم فعاله"""
        if self._busy or not self.is_connected or not self.active_adapter_name:
            return
        self._busy = True
        self._connection_generation = self._connection_state.begin(
            "dns", "بازگردانی DNS قبلی", cancellable=False
        )
        self._connection_state.advance(self._connection_generation, "restoring")
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self.busy_changed.emit(True)
        adapter_name = self.active_adapter_name

        def worker():
            try:
                ok = dns_service.reset_dns_to_dhcp(adapter_name)
            except Exception:
                ok = False
            self._dns_disconnect_completed.emit(ok)

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnect_finished(self, ok: bool):
        self._busy = False
        self.busy_changed.emit(False)
        if ok:
            self._connection_state.reset("DNS قبلی بازگردانده شد")
        else:
            self._connection_state.advance(
                self._connection_generation, "failed", "بازگردانی DNS کامل نشد"
            )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self._watchdog_timer.stop()
        if ok:
            self.status_message.emit("اتصال قطع شد و DNS به حالت خودکار برگشت ✅", "success")
        else:
            self.status_message.emit("خطا در قطع اتصال ⚠️", "error")
        self.is_connected = False
        self.active_adapter_name = None
        self.active_profile_name = None
        if not self.tunnel_connected:
            self._active_route_context = {}
        self._route_bad_samples = 0
        self.connection_changed.emit(False, "")
        self.refresh_adapters()

    def force_reset_on_exit(self):
        """موقع بستن کامل اپ صدا زده می‌شه — بدون ترد، سریع و مطمئن DNS و تانل رو ریست می‌کنه"""
        if self.is_connected and self.active_adapter_name:
            try:
                dns_service.reset_dns_to_dhcp(self.active_adapter_name)
            except Exception:
                pass
        self.force_stop_tunnel_on_exit()
        if self._optimizing_game:
            game_qos_service.remove(self._optimizing_game.process_name)

    # ---------- Kill Switch ----------

    def set_kill_switch_enabled(self, enabled: bool):
        self.kill_switch_enabled = enabled
        if enabled and self.is_connected:
            self._watchdog_timer.start()
            self.status_message.emit("محافظ DNS فعال شد 🛡️", "info")
        else:
            self._watchdog_timer.stop()
            self.status_message.emit("محافظ DNS غیرفعال شد", "info")

    def _check_connectivity(self):
        if not self.kill_switch_enabled or not self.active_adapter_name:
            return

        def worker():
            connected = connectivity_service.is_connected()
            if not connected and self.active_adapter_name:
                dns_service.reset_dns_to_dhcp(self.active_adapter_name)
            self._kill_switch_checked.emit(connected)

        threading.Thread(target=worker, daemon=True).start()

    def _on_kill_switch_checked(self, connected: bool):
        if connected or not self.active_adapter_name:
            return
        self.kill_switch_triggered.emit()
        self._watchdog_timer.stop()
        self.is_connected = False
        self.connection_changed.emit(False, "")

    # ---------- بازی‌های دلخواه ----------

    def add_game(self, name: str, process_name: str = "",
                 preferred_dns_name: str = "", preferred_tunnel_id: str = ""):
        if not name.strip():
            return
        games = list(self.games)
        from app.models.game import Game
        games.append(Game(
            name=name.strip(), process_name=process_name.strip(),
            preferred_dns_name=preferred_dns_name, preferred_tunnel_id=preferred_tunnel_id,
        ))
        games_service.save_games(games)
        self.games = games
        self.games_changed.emit(self.games)
        self.status_message.emit(f"بازی «{name}» اضافه شد ✅", "success")

    def remove_game(self, name: str):
        self.games = games_service.remove_game(self.games, name)
        self.games_changed.emit(self.games)
        self.status_message.emit(f"بازی «{name}» حذف شد", "info")

    def set_game_preferences(self, name: str, preferred_dns_name: str, preferred_tunnel_id: str,
                             connection_mode: str = "balanced", auto_connect: bool = False,
                             connection_strategy: str = "smart", route_mode: str = "process"):
        """تنظیم پروفایل DNS/تانل ترجیحی برای یک بازی موجود"""
        updated = []
        for g in self.games:
            if g.name == name:
                g.preferred_dns_name = preferred_dns_name
                g.preferred_tunnel_id = preferred_tunnel_id
                g.connection_mode = connection_mode
                g.connection_strategy = connection_strategy
                g.route_mode = route_mode if route_mode in ("process", "system") else "process"
                g.auto_connect = auto_connect
            updated.append(g)
        self.games = updated
        games_service.save_games(self.games)
        self.games_changed.emit(self.games)
        self.status_message.emit(f"پروفایل ترجیحی «{name}» ذخیره شد ✅", "success")

    # ---------- تشخیص خودکار بازی ----------

    def _scan_for_running_game(self):
        detection_settings = settings_service.load_settings()
        if not detection_settings.get("game_detection_enabled", True):
            return
        game = game_detection_service.detect_running_game(self.games)
        current_name = game.name if game else None
        if current_name != self._last_detected_game_name:
            previous_name = self._last_detected_game_name
            self._last_detected_game_name = current_name
            if game:
                self._game_session_generation += 1
                self._match_route_locked = False
                self._game_session_summary = game_session_report_service.begin(game)
                self.game_runtime_changed.emit(game.name, True)
                if game.auto_connect:
                    self._auto_connected_game_name = game.name
                    self.status_message.emit(f"«{game.name}» شناسایی شد؛ خلبان خودکار فعال شد", "info")
                    self.apply_game_preferred_profile(game)
                else:
                    self.game_detected.emit(game)
            elif previous_name and self._auto_connected_game_name == previous_name:
                self._auto_connected_game_name = None
            if previous_name and not game:
                self._game_session_generation += 1
                self._match_route_locked = False
                session_report = None
                previous_game = next(
                    (item for item in self.games if item.name == previous_name), None
                )
                if previous_game is not None and self._game_session_summary:
                    route = (
                        "game-mode" if self._game_started_tunnel else
                        "dns" if self._game_started_dns else
                        "warp" if self._official_warp_session.get("active") else "direct"
                    )
                    session_report = game_session_report_service.finish(
                        previous_game, self._game_session_summary, route
                    )
                self._game_session_summary = {}
                self._air_timer.stop()
                self._network_monitor_timer.stop()
                if self._route_learning_game and self._route_learning_game.name == previous_name:
                    self._route_learning_game = None
                self.game_runtime_changed.emit(previous_name, False)
                if session_report is not None:
                    self.game_session_report_ready.emit(session_report)
                self.game_optimization_progress.emit(
                    previous_name, "done", "بازی بسته شد؛ تنظیمات مخصوص این نشست جمع‌آوری می‌شود"
                )
                if self._optimizing_game and self._optimizing_game.name == previous_name:
                    game_qos_service.remove(self._optimizing_game.process_name)
                    if self._game_started_tunnel and self.tunnel_connected:
                        self.disconnect_tunnel()
                    elif self._game_started_tunnel and self._tunnel_busy:
                        self._pending_game_stop_tunnel = True
                    if self._game_started_dns and self.is_connected:
                        self.disconnect_dns()
                    elif self._game_started_dns and self._busy:
                        self._pending_game_stop_dns = True
                    self._optimizing_game = None
                    self._game_started_dns = False
                    self._game_started_tunnel = False
                    self.optimization_state_changed.emit({
                        "game": previous_name, "running": False, "stage": "stopped",
                        "effect": "بازی بسته شد؛ بهینه‌سازی مخصوص بازی فعال نیست.",
                    })
        if not game:
            candidate = game_detection_service.detect_unregistered_game(
                self.games, detection_settings.get("ignored_game_processes", [])
            )
            if candidate and candidate.process_name.lower() not in self._seen_candidate_processes:
                self._seen_candidate_processes.add(candidate.process_name.lower())
                self.game_candidate_detected.emit(candidate)

    def ignore_game_candidate(self, process_name: str):
        settings = settings_service.load_settings()
        ignored = {str(item).lower(): str(item) for item in settings.get("ignored_game_processes", [])}
        ignored[process_name.lower()] = process_name
        settings_service.set_value("ignored_game_processes", list(ignored.values()))
        self.status_message.emit(f"«{process_name}» دیگر به‌عنوان بازی پیشنهاد نمی‌شود", "info")

    def accept_game_candidate(self, candidate, strategy="smart", mode="balanced",
                              auto_connect=False):
        from app.models.game import Game
        game = Game(
            name=candidate.name, process_name=candidate.process_name,
            notes="تشخیص خودکار محلی", connection_mode=mode,
            connection_strategy=strategy, auto_connect=auto_connect,
        )
        self.games.append(game)
        self._last_detected_game_name = game.name
        games_service.save_games(self.games)
        self.games_changed.emit(self.games)
        self.game_runtime_changed.emit(game.name, True)
        self.optimize_game_connection(game)

    def optimize_game_connection(self, game):
        """Verify lobby readiness before any DNS, QoS or route mutation."""
        if not game or self._game_preflight_busy:
            return
        if self._match_route_locked:
            self.status_message.emit(
                "Match Lock فعال است؛ تا پایان نشست مسیر بازی تغییر نمی‌کند", "info"
            )
            return
        self._game_preflight_busy = True
        self.game_optimization_progress.emit(
            game.name, "testing",
            "پیش‌بررسی لابی: کارت شبکه و دسترسی واقعی اینترنت بررسی می‌شوند…",
        )

        def worker():
            scope = connectivity_service.detect_internet_scope(timeout_s=2.0)
            fallback_online = bool(scope.get("online"))
            if not fallback_online and not scope.get("captive"):
                fallback_online = connectivity_service.is_connected(timeout_ms=850)
            active_adapter = self.active_adapter_name or next(
                (item.name for item in self.adapters if getattr(item, "is_enabled", False)), ""
            )
            self._game_preflight_completed.emit(game, {
                "scope": scope,
                "online": fallback_online,
                "adapter": active_adapter,
            })

        threading.Thread(target=worker, daemon=True).start()

    def _on_game_preflight_completed(self, game, result: dict):
        self._game_preflight_busy = False
        scope = result.get("scope") or {}
        decision = connectivity_service.evaluate_game_preflight(
            scope, bool(result.get("online")), str(result.get("adapter") or "")
        )
        if not decision["ready"]:
            self.game_optimization_progress.emit(game.name, "error", decision["message"])
            self.status_message.emit(decision["message"], "error")
            return
        self.game_optimization_progress.emit(
            game.name, "active",
            f"پیش‌بررسی لابی کامل شد · {result['adapter']} · {decision['message']}",
        )
        self._begin_game_optimization(game)

    def _begin_game_optimization(self, game):
        strategy = getattr(game, "connection_strategy", "smart")
        self._optimizing_game = game
        self._game_started_dns = False
        self._game_started_tunnel = False
        self._pending_game_stop_dns = False
        self._pending_game_stop_tunnel = False
        self._match_route_locked = False
        settings = settings_service.load_settings()
        if settings.get("air_lite_enabled", True):
            self._air_timer.start()
        self._network_monitor_timer.start()
        if settings.get("game_qos_enabled", False):
            def qos_worker():
                ok, detail = game_qos_service.apply(game.process_name)
                self.game_optimization_progress.emit(
                    game.name, "active" if ok else "error",
                    ("QoS بازی: " + detail) if ok else "QoS اعمال نشد؛ " + detail,
                )
            threading.Thread(target=qos_worker, daemon=True).start()
        turbo_requested = bool(settings.get("turbo_mode", False))
        snapshot = {
            "game": game.name, "process": game.process_name, "running": True,
            "stage": "testing", "strategy": strategy,
            "dns": "در انتظار تصمیم", "tunnel": "در انتظار تصمیم",
            "routing": "هنوز اعمال نشده", "failover": "هنوز ارزیابی نشده",
            "turbo": "غیرفعال",
            "turbo_reason": (
                "درخواست شده، اما تا اتصال data-plane سرور GameLink واقعاً فعال نمی‌شود"
                if turbo_requested else "در تنظیمات خاموش است"
            ),
        }
        self.optimization_state_changed.emit(snapshot)
        route_scope = "فقط پروسه بازی" if getattr(game, "route_mode", "process") == "process" else "کل سیستم"
        self.game_optimization_progress.emit(game.name, "active", f"۱. پروسه بازی تأیید شد · دامنه: {route_scope}")
        if strategy == "dns" or (strategy == "smart" and not self.tunnel_configs):
            if not self.adapters:
                self.game_optimization_progress.emit(game.name, "error", "۲. کارت شبکه فعال پیدا نشد")
                return
            self.game_optimization_progress.emit(
                game.name, "active",
                "۲. DNSها با پاسخ واقعی آزمایش می‌شوند؛ این کار رفع نام و دسترسی را بهتر می‌کند، نه مسیر پکت‌های داخل بازی را"
            )
            snapshot.update({
                "stage": "applying_dns", "dns": "آزمایش و انتخاب خودکار",
                "tunnel": "استفاده نمی‌شود", "routing": "تغییر DNS روی کارت شبکه",
                "failover": "محافظ DNS در صورت فعال‌بودن",
                "effect": "بهبود Resolve و دسترسی؛ ادعای کاهش مستقیم پینگ بازی ندارد.",
            })
            self.optimization_state_changed.emit(snapshot)
            self._game_started_dns = True
            preference = (
                "fastest" if getattr(game, "connection_mode", "balanced") == "competitive"
                else "stable" if getattr(game, "connection_mode", "balanced") == "stability"
                else "balanced"
            )
            self.apply_best_dns(
                self.active_adapter_name or self.adapters[0].name, preference,
                settings_service.load_settings().get("dns_usage_goal", "balanced"),
            )
            return
        self.game_optimization_progress.emit(
            game.name, "active", "۲. سنجش واقعی مسیرها: پینگ، جیتر، پکت‌لاس و پایداری"
        )
        self.game_optimization_progress.emit(
            game.name, "active", (
                f"۳. مسیر برگزیده فقط به پروسه {game.process_name} اختصاص می‌یابد"
                if getattr(game, "route_mode", "process") == "process" else
                "۳. مسیر برگزیده برای کل سیستم فعال می‌شود"
            )
        )
        snapshot.update({
            "stage": "testing_tunnels", "dns": "DNS اختصاصی تغییر نمی‌کند",
            "tunnel": "در حال آزمون حداکثر ۸ مسیر",
            "routing": f"پس از انتخاب، {route_scope}",
            "failover": "چند مسیر سالم در صورت وجود آماده می‌شوند",
            "effect": "تغییر مسیر ترافیک بازی؛ مسیرها با HTTPS سنجیده می‌شوند و مقصد آزمون الزاماً سرور خود بازی نیست.",
        })
        self.optimization_state_changed.emit(snapshot)
        self._game_started_tunnel = True
        self.connect_tunnel(game=game)

    def _air_lite_tick(self):
        """Notice live destination handoffs and refresh the local recipe without touching routes."""
        game = self._optimizing_game or self._route_learning_game
        if not game or not game.process_name.strip():
            self._air_timer.stop()
            return
        if self._air_busy:
            return
        self._air_busy = True
        session_generation = self._game_session_generation

        def worker():
            try:
                endpoints = game_server_probe_service.discover_game_endpoints(
                    game.process_name, limit=12
                )
                if not endpoints:
                    endpoints = game_server_probe_service.capture_game_udp_endpoints(
                        game.process_name, duration_s=1.3, limit=12
                    )
                if (session_generation != self._game_session_generation
                        or self._last_detected_game_name != game.name):
                    return
                known = set(game.route_profile.get("seen_keys", []))
                known.update(item.get("key") for item in game.route_profile.get("endpoints", []))
                fresh = [item for item in endpoints if
                         f"{item.get('host')}:{int(item.get('port', 0))}/{item.get('transport', 'tcp')}" not in known]
                if not fresh:
                    return
                if self._optimizing_game and self._optimizing_game.name == game.name:
                    first_lock = not self._match_route_locked
                    self._match_route_locked = True
                    if first_lock:
                        self.status_message.emit(
                            "ترافیک واقعی نشست بازی دیده شد؛ Match Lock تغییر مسیر را تا پایان بازی متوقف کرد",
                            "info",
                        )
                was_waiting = bool(game.route_profile.get("lobby_waiting", False))
                game.route_profile = game_route_profile_service.merge_observation(
                    game.route_profile, endpoints
                )
                game.route_profile["lobby_waiting"] = False
                game.route_profile["changed_endpoints"] = len(fresh)
                game.route_profile["air_last_handoff"] = game.route_profile.get("updated_at")
                games_service.save_games(self.games)
                self.games_changed.emit(self.games)
                self.air_profile_updated.emit(game.name, game.route_profile, len(fresh))
                try:
                    relay_host = getattr(self._active_tunnel_config, "host", "") or ""
                    lab = network_lab_service.run_for_endpoint(fresh[0], relay_host)
                    lab["game"] = game.name
                    self.network_lab_ready.emit(lab)
                except Exception:
                    pass
                now = time.monotonic()
                last_notice = float(self._air_last_notice.get(game.name, 0))
                if was_waiting or now - last_notice >= 60:
                    self._air_last_notice[game.name] = now
                    self.game_optimization_progress.emit(
                        game.name, "active",
                        f"AIR Lite: مقصد واقعی UDP شناسایی شد؛ {len(fresh)} مسیر تازه ثبت شد",
                    )
            finally:
                self._air_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _network_monitor_tick(self):
        if self._network_monitor_busy or not self._optimizing_game:
            return
        self._network_monitor_busy = True

        def worker():
            try:
                result = {
                    "adapters": network_lab_service.adapter_health(),
                    "pressure": network_lab_service.traffic_pressure(),
                }
            except Exception as exc:
                result = {"error": str(exc)}
            self._network_monitor_busy = False
            self.network_monitor_ready.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def apply_game_preferred_profile(self, game):
        """اعمال پروفایل DNS/تانل ترجیحی یک بازی (بعد از تأیید کاربر تو UI)"""
        strategy = getattr(game, "connection_strategy", "smart")
        if not game.preferred_dns_name and not game.preferred_tunnel_id:
            self.optimize_game_connection(game)
            return
        applied_anything = False

        if game.preferred_dns_name and strategy in ("smart", "dns"):
            profile = next((p for p in self.dns_profiles if p.name == game.preferred_dns_name), None)
            if profile and self.adapters:
                adapter_name = self.active_adapter_name or self.adapters[0].name
                self.apply_dns_profile(
                    adapter_name, profile.name, profile.primary, profile.secondary, profile.doh_url
                )
                applied_anything = True

        if game.preferred_tunnel_id and strategy in ("smart", "tunnel"):
            config = next((c for c in self.tunnel_configs if c.id == game.preferred_tunnel_id), None)
            if config:
                self.connect_tunnel(config, game)
                applied_anything = True

        if strategy != "dns" and not game.preferred_tunnel_id and self.tunnel_configs:
            self.connect_tunnel(game=game)
            applied_anything = True

        if not applied_anything:
            self.status_message.emit(
                f"برای «{game.name}» پروفایل ترجیحی تنظیم نشده — از تب بازی‌های من تنظیمش کن",
                "info",
            )

    # ---------- تانل (V2Ray/Xray/Shadowsocks) ----------

    def import_tunnel_link(self, link: str):
        if not ALLOW_CUSTOM_TUNNELS:
            self.status_message.emit(
                "نسخه عمومی فقط WARP Game Mode را می‌پذیرد و امکان ورود کانفیگ ندارد.",
                "error",
            )
            return
        """پارس کردن یه لینک vmess/vless/ss و افزودن به لیست کانفیگ‌ها"""
        if link.lower().startswith(("https://", "http://")):
            self._tunnel_busy = True
            self.tunnel_busy_changed.emit(True)
            self.status_message.emit("در حال دریافت اشتراک...", "info")

            def worker():
                try:
                    configs = subscription_service.fetch(link)
                    self._subscription_completed.emit(configs, "")
                except Exception as exc:
                    self._subscription_completed.emit([], str(exc))

            threading.Thread(target=worker, daemon=True).start()
            return
        try:
            config = config_parser.parse_link(link)
        except Exception as e:
            self.status_message.emit(f"خطا در خوندن لینک: {e}", "error")
            return
        self.tunnel_configs = tunnel_storage_service.add_config(self.tunnel_configs, config)
        self.tunnel_configs_changed.emit(self.tunnel_configs)
        self.status_message.emit(f"کانفیگ «{config.name}» اضافه شد ✅", "success")

    def _on_subscription_finished(self, configs, error: str):
        self._tunnel_busy = False
        self.tunnel_busy_changed.emit(False)
        if error:
            self.status_message.emit(f"دریافت اشتراک ناموفق بود: {error}", "error")
            return
        for config in configs:
            self.tunnel_configs = tunnel_storage_service.add_config(self.tunnel_configs, config)
        self.tunnel_configs_changed.emit(self.tunnel_configs)
        self.status_message.emit(f"{len(configs)} کانفیگ از اشتراک وارد شد ✅", "success")

    def remove_tunnel_config(self, config_id: str):
        self.tunnel_configs = tunnel_storage_service.remove_config(self.tunnel_configs, config_id)
        self.tunnel_configs_changed.emit(self.tunnel_configs)

    def connect_tunnel(self, config=None, game=None):
        """Probe candidates through real HTTPS, then start the best one in TUN mode."""
        if self._match_route_locked:
            self.status_message.emit("Match Lock فعال است؛ مسیر وسط نشست بازی عوض نمی‌شود", "info")
            return
        if self._tunnel_busy:
            return
        if not self.tunnel_configs:
            self.status_message.emit("ابتدا حداقل یک کانفیگ اضافه کن", "error")
            return
        self._tunnel_busy = True
        self.tunnel_busy_changed.emit(True)
        if settings_service.load_settings().get("route_dna_enabled", True):
            self.status_message.emit("RouteDNA روشن است؛ مسیرهای بازی برای همین شبکه بررسی می‌شوند…", "info")
        else:
            self.status_message.emit(
                "RouteDNA خاموش است؛ مسیرها بدون حافظه شخصی و فقط با تست همین لحظه بررسی می‌شوند.",
                "info",
            )
        mode = getattr(game, "connection_mode", "balanced") if game else "balanced"
        process_names = ([game.process_name] if game and game.process_name.strip()
                         and getattr(game, "route_mode", "process") == "process" else [])
        learned = game_route_profile_service.summary(game.route_profile) if game else {"available": False}
        route_mtu = (
            learned["mtu"] if learned.get("available") and not learned.get("stale")
            and learned.get("confidence", 0) >= 35 else 1400
        )
        self._active_game_mode = mode
        self._active_process_names = process_names
        self._active_route_mtu = route_mtu

        def worker():
            from app.services import quality_service
            route_context = {}
            route_target = game.name if game else "game-mode"
            try:
                settings = settings_service.load_settings()
                if settings.get("route_dna_enabled", True):
                    dna_adapter = self.active_adapter_name or (
                        self.adapters[0].name if self.adapters else "unknown"
                    )
                    route_context = self._route_dna_snapshot(
                        dna_adapter, "game" if game else "smart", settings,
                        sample_pressure=True,
                    )
            except Exception:
                route_context = {}
            ordered = list(self.tunnel_configs)
            if config is not None:
                ordered = [config] + [item for item in ordered if item.id != config.id]
            candidates = []
            errors = []
            checked = ordered[:8]
            with ThreadPoolExecutor(max_workers=min(3, len(checked) or 1)) as executor:
                jobs = {executor.submit(tunnel_service.probe_config, item): item for item in checked}
                for future in as_completed(jobs):
                    item = jobs[future]
                    self.status_message.emit(f"نتیجه مسیر «{item.name}» دریافت شد", "info")
                    try:
                        health = future.result()
                    except Exception as exc:
                        errors.append(f"{item.name}: {exc}")
                        continue
                    quality = quality_service.score_path(item, health, mode)
                    if health.available:
                        personal = rating_service.get_rating(item.id)
                        memory = route_dna_service.prior(
                            route_context, route_target, f"tunnel:{item.id}"
                        ) if route_context else {"samples": 0, "success_rate": 0}
                        dna_bonus = min(4, memory["samples"]) if memory["success_rate"] >= 70 else 0
                        candidates.append((quality.score + dna_bonus, personal,
                                           health.latency_ms, item, quality))
                    else:
                        if route_context:
                            try:
                                route_dna_service.record(
                                    route_context, target=route_target,
                                    route=f"tunnel:{item.id}", success=False,
                                )
                            except Exception:
                                pass
                        errors.append(f"{item.name}: {health.error}")
            if not candidates:
                detail = errors[0] if errors else "هیچ مسیر سالمی پیدا نشد"
                self._tunnel_connect_completed.emit(False, detail, "", None)
                return
            candidates.sort(key=lambda row: (-row[0], -row[1], row[2]))
            budget = int(settings_service.load_settings().get("route_latency_budget_ms", 160))
            within_budget = [row for row in candidates if row[2] <= budget]
            if within_budget:
                candidates = within_budget + [row for row in candidates if row not in within_budget]
            score, _, latency, selected, quality = candidates[0]
            udp_protocols = {"hysteria2", "tuic", "wireguard"}
            emergency = (
                bool(settings_service.load_settings().get("emergency_mode", True))
                and any(item.protocol in udp_protocols for item in checked)
                and not any(row[3].protocol in udp_protocols for row in candidates)
            )
            self._last_ranked_configs = [row[3] for row in candidates]
            standby_count = max(0, min(3, int(
                settings_service.load_settings().get("route_standby_count", 2)
            )))
            self._standby_tunnel_configs = [row[3] for row in candidates[1:1 + standby_count]]
            self._standby_tunnel_config = self._standby_tunnel_configs[0] if self._standby_tunnel_configs else None
            ok, message = self._tunnel.start(
                selected, mode="tun", process_names=process_names, mtu=route_mtu
            )
            if ok:
                self._pending_tunnel_route_context = dict(route_context)
                if route_context:
                    try:
                        route_dna_service.record(
                            route_context, target=route_target,
                            route=f"tunnel:{selected.id}", success=True,
                            latency_ms=latency, jitter_ms=quality.jitter_ms,
                            loss=quality.packet_loss_pct,
                        )
                    except Exception:
                        pass
                message = (
                    f"بهترین مسیر «{selected.name}» با RouteDNA Score {score}/100 "
                    f"و پینگ {latency}ms انتخاب شد — {message}"
                )
                if process_names:
                    message += f" · فقط ترافیک {game.name} از تانل عبور می‌کند · MTU {route_mtu}"
                if latency > budget:
                    message += f" · هشدار: بودجه {budget}ms رد شد اما این بهترین مسیر سالم بود"
                if emergency:
                    message = "حالت نجات TCP فعال شد · " + message
                self.route_quality_ready.emit({
                    "score": score, "label": quality.label, "latency": latency,
                    "jitter": quality.jitter_ms, "loss": quality.packet_loss_pct,
                    "mode": mode, "protocol": selected.protocol, "mtu": route_mtu,
                    "standby": self._standby_tunnel_config.name
                    if self._standby_tunnel_config else "",
                    "standby_count": len(self._standby_tunnel_configs),
                    "budget_ms": budget, "within_budget": latency <= budget,
                    "route_dna": route_context,
                    "route_dna_explanation": route_dna_service.explain_choice(
                        route_context, route=f"tunnel:{selected.id}",
                        probe={"median_ms": latency}, target=route_target,
                    ) if route_context else "",
                })
            self._tunnel_connect_completed.emit(ok, message, selected.name, selected)

        threading.Thread(target=worker, daemon=True).start()

    def _on_tunnel_connect_finished(self, ok: bool, message: str, name: str, config=None):
        was_recovering = self._recovering_tunnel
        self._recovering_tunnel = False
        self._tunnel_busy = False
        self.tunnel_busy_changed.emit(False)
        if ok:
            self.tunnel_connected = True
            self.active_tunnel_name = name
            self._active_tunnel_config = config
            self._active_route_context = dict(self._pending_tunnel_route_context)
            self._live_failures = 0
            self.status_message.emit(message, "success")
            self._tunnel_connect_time = time.monotonic()
            self._usage_timer.start()
            self._traffic_meter.start()
            self._tunnel_watchdog_timer.start()
            if config is not None:
                self._live_ping_target = ("1.1.1.1", 443)
                self._live_ping_timer.start()
            if self._standby_tunnel_config is not None:
                self._shadow_route_timer.start()
        else:
            self.status_message.emit(message, "error")
        if self._optimizing_game and self._game_started_tunnel:
            game = self._optimizing_game
            if ok:
                standby = (f"{len(self._standby_tunnel_configs)} مسیر آماده" if
                           self._standby_tunnel_configs else "ندارد")
                self.game_optimization_progress.emit(
                    game.name, "done",
                    f"۴. مسیر «{name}» فعال شد؛ دامنه: "
                    + (f"فقط {game.process_name}" if self._active_process_names else "کل سیستم")
                )
                self.optimization_state_changed.emit({
                    "game": game.name, "running": True, "stage": "connected",
                    "strategy": "tunnel", "dns": "DNS سیستم تغییر نکرده",
                    "tunnel": f"فعال: {name}", "protocol": getattr(config, "protocol", ""),
                    "routing": ((f"فقط پردازش {game.process_name}" if self._active_process_names else "کل سیستم")
                                + f" · MTU {self._active_route_mtu}"),
                    "failover": f"پشتیبان: {standby}", "turbo": "غیرفعال",
                    "turbo_reason": "data-plane سرور GameLink هنوز متصل نیست",
                    "effect": "مسیر ترافیک بازی تغییر کرده؛ سایر برنامه‌ها از اینترنت عادی استفاده می‌کنند.",
                })
            elif getattr(game, "connection_strategy", "smart") == "smart" and self.adapters:
                self._game_started_tunnel = False
                self._game_started_dns = True
                self.game_optimization_progress.emit(
                    game.name, "active", "هیچ تانل سالمی نبود؛ حالت هوشمند به DNS سالم برمی‌گردد"
                )
                preference = (
                    "fastest" if getattr(game, "connection_mode", "balanced") == "competitive"
                    else "stable" if getattr(game, "connection_mode", "balanced") == "stability"
                    else "balanced"
                )
                self.apply_best_dns(
                    self.active_adapter_name or self.adapters[0].name, preference,
                    settings_service.load_settings().get("dns_usage_goal", "balanced"),
                )
            else:
                self._game_started_tunnel = False
                self.game_optimization_progress.emit(game.name, "error", f"اتصال تانل ناموفق بود: {message}")
                self.optimization_state_changed.emit({
                    "game": game.name, "running": True, "stage": "failed",
                    "dns": "بدون تغییر", "tunnel": "ناموفق", "routing": "اعمال نشد",
                    "failover": "مسیر سالمی نبود", "turbo": "غیرفعال", "effect": message,
                })
        if was_recovering:
            self.failover_changed.emit(False, name if ok else "")
        self.tunnel_status_changed.emit(self.tunnel_connected, name if ok else "")
        if self._pending_game_stop_tunnel:
            self._pending_game_stop_tunnel = False
            if ok and self.tunnel_connected:
                self.disconnect_tunnel()

    def disconnect_tunnel(self):
        if self._tunnel_busy or not self.tunnel_connected:
            return
        self._tunnel_busy = True
        self.tunnel_busy_changed.emit(True)

        def worker():
            self._tunnel.stop()
            self._tunnel_disconnect_completed.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_tunnel_disconnect_finished(self):
        self._tunnel_busy = False
        self.tunnel_busy_changed.emit(False)
        self.tunnel_connected = False
        self.active_tunnel_name = None
        self._active_tunnel_config = None
        self._pending_tunnel_route_context = {}
        if not self.is_connected:
            self._active_route_context = {}
        self._usage_timer.stop()
        self._tunnel_watchdog_timer.stop()
        self._live_ping_timer.stop()
        self._shadow_route_timer.stop()
        self._live_ping_target = None
        self._finalize_usage_tick()
        self.status_message.emit("تانل قطع شد", "info")
        self.tunnel_status_changed.emit(False, "")

    def _shadow_route_tick(self):
        """Probe one standby endpoint without starting it or touching active routes."""
        standby = self._standby_tunnel_config
        if (
            self._shadow_route_busy or not self.tunnel_connected
            or standby is None or self._tunnel_busy
        ):
            return
        self._shadow_route_busy = True

        def worker():
            try:
                health = tunnel_service.probe_config(standby)
                if health.available:
                    summary = (
                        f"Shadow Route: مسیر پشتیبان «{standby.name}» بدون تعویض مسیر "
                        f"با پاسخ {health.latency_ms}ms آماده است"
                    )
                else:
                    summary = (
                        f"Shadow Route: مسیر پشتیبان «{standby.name}» فعلاً پاسخ معتبر نداد؛ "
                        "مسیر فعال دست‌نخورده ماند"
                    )
                if summary != self._shadow_last_summary:
                    self._shadow_last_summary = summary
                    game = self._optimizing_game
                    if game:
                        self.game_optimization_progress.emit(game.name, "active", summary)
            except Exception:
                # Shadow measurement is observational and must never disturb play.
                pass
            finally:
                self._shadow_route_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _check_tunnel_process(self):
        if not self.tunnel_connected or self._tunnel.is_running():
            return
        self._trigger_fast_failover("هسته مسیر فعال متوقف شد")

    def _on_live_health(self, latency_ms: int):
        if not self.tunnel_connected or self._recovering_tunnel:
            return
        if latency_ms < 0:
            self._live_failures += 1
        else:
            self._live_failures = 0
        if self._live_failures >= 3:
            self._trigger_fast_failover("مسیر فعال سه بار پیاپی پاسخ نداد")

    def _trigger_fast_failover(self, reason: str):
        """Start the pre-tested standby before falling back to a full rescan."""
        if self._recovering_tunnel or self._tunnel_busy:
            return
        if not settings_service.load_settings().get("auto_failover", True):
            self._tunnel_watchdog_timer.stop()
            self._usage_timer.stop()
            self._live_ping_timer.stop()
            self._finalize_usage_tick()
            self.tunnel_connected = False
            self.active_tunnel_name = None
            self._active_tunnel_config = None
            self.tunnel_status_changed.emit(False, "")
            self.status_message.emit(f"{reason}؛ بازیابی خودکار در تنظیمات خاموش است", "error")
            return
        self._recovering_tunnel = True
        self._tunnel_busy = True
        self.tunnel_busy_changed.emit(True)
        self.failover_changed.emit(True, reason)
        self._tunnel_watchdog_timer.stop()
        self._usage_timer.stop()
        self._live_ping_timer.stop()
        self._finalize_usage_tick()
        self.tunnel_connected = False
        previous = self._active_tunnel_config
        standby = self._standby_tunnel_config
        self.active_tunnel_name = None
        self._active_tunnel_config = None
        self.tunnel_status_changed.emit(False, "")
        self.status_message.emit(f"{reason}؛ در حال انتقال خودکار به مسیر پشتیبان...", "info")

        def worker():
            ordered = []
            if standby is not None and (previous is None or standby.id != previous.id):
                ordered.append(standby)
            ordered.extend(item for item in self._last_ranked_configs
                           if (previous is None or item.id != previous.id)
                           and all(item.id != seen.id for seen in ordered))
            errors = []
            for item in ordered[:3]:
                ok, message = self._tunnel.start(
                    item, mode="tun", process_names=self._active_process_names,
                    mtu=self._active_route_mtu,
                )
                if ok:
                    self._standby_tunnel_configs = [candidate for candidate in ordered
                                                    if candidate.id != item.id][:3]
                    self._standby_tunnel_config = (self._standby_tunnel_configs[0]
                                                   if self._standby_tunnel_configs else None)
                    self._tunnel_connect_completed.emit(
                        True, f"بدون دخالت کاربر به مسیر پشتیبان «{item.name}» منتقل شد — {message}",
                        item.name, item,
                    )
                    return
                errors.append(f"{item.name}: {message}")
            detail = errors[0] if errors else "مسیر پشتیبان آماده‌ای وجود ندارد"
            self._tunnel_connect_completed.emit(False, f"بازیابی خودکار ناموفق بود: {detail}", "", None)

        threading.Thread(target=worker, daemon=True).start()

    def _tick_live_ping(self):
        if not self._live_ping_target:
            return

        def worker():
            health = tunnel_service.measure_http_path(
                proxy_port=tunnel_service.HTTP_PORT, attempts=1, timeout_s=2.0
            )
            self.live_ping_ready.emit(health.latency_ms if health.available else -1)

        threading.Thread(target=worker, daemon=True).start()

    def _tick_usage(self):
        """هر یک دقیقه که تانل وصله، مصرف تخمینی امروز رو آپدیت می‌کنه"""
        if not self._tunnel_connect_time:
            return
        elapsed_min = (time.monotonic() - self._tunnel_connect_time) / 60.0
        self._tunnel_connect_time = time.monotonic()
        total_today = usage_tracker_service.add_connected_minutes(elapsed_min)
        self.usage_updated.emit(total_today, SUGGESTED_DAILY_LIMIT_MB)
        total_bytes = usage_tracker_service.add_traffic_bytes(self._traffic_meter.sample())
        quota_mb = int(settings_service.load_settings().get("local_quota_mb", 20480))
        self.traffic_usage_updated.emit(total_bytes, quota_mb)

    def _finalize_usage_tick(self):
        if not self._tunnel_connect_time:
            return
        elapsed_min = (time.monotonic() - self._tunnel_connect_time) / 60.0
        self._tunnel_connect_time = None
        total_today = usage_tracker_service.add_connected_minutes(elapsed_min)
        self.usage_updated.emit(total_today, SUGGESTED_DAILY_LIMIT_MB)
        total_bytes = usage_tracker_service.add_traffic_bytes(self._traffic_meter.sample())
        quota_mb = int(settings_service.load_settings().get("local_quota_mb", 20480))
        self.traffic_usage_updated.emit(total_bytes, quota_mb)

    def run_config_trial(self, config):
        if self._tunnel_busy or self.tunnel_connected:
            self.status_message.emit("برای تست ۳۰ ثانیه‌ای ابتدا تانل فعال را قطع کن", "info")
            return
        self._tunnel_busy = True
        self.tunnel_busy_changed.emit(True)
        self.status_message.emit(f"آزمایش ۳۰ ثانیه‌ای «{config.name}» شروع شد...", "info")

        def worker():
            try:
                health = tunnel_service.trial_config(config, duration_s=30.0)
                self._trial_completed.emit(health, config.name, "")
            except Exception as exc:
                self._trial_completed.emit(None, config.name, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_trial_finished(self, health, name: str, error: str):
        self._tunnel_busy = False
        self.tunnel_busy_changed.emit(False)
        if error or health is None or not health.available:
            detail = error or (health.error if health else "بدون پاسخ")
            self.status_message.emit(f"آزمایش «{name}» ناموفق بود: {detail}", "error")
            self.trial_ready.emit({"available": False, "name": name, "error": detail})
            return
        quality = quality_service.calculate_game_quality(
            health.latency_ms, health.jitter_ms, health.successes, health.attempts,
            self._active_game_mode,
        )
        result = {
            "available": True, "name": name, "score": quality.score,
            "latency": quality.latency_ms, "jitter": quality.jitter_ms,
            "loss": quality.packet_loss_pct, "attempts": health.attempts,
        }
        self.trial_ready.emit(result)
        self.status_message.emit(f"آزمایش «{name}» کامل شد؛ امتیاز {quality.score}/100", "success")

    def record_route_quality(self, result: dict):
        self._last_quality = dict(result)
        settings = settings_service.load_settings()
        enabled = bool(settings.get("anonymous_radar", False))
        radar_service.record_sample(result, enabled)
        if enabled and settings.get("gamelink_api_url"):
            threading.Thread(
                target=radar_service.flush,
                args=(settings.get("gamelink_api_url", ""), True),
                daemon=True,
            ).start()

    def create_safe_report(self):
        try:
            path = diagnostics_service.build_report(self.tunnel_configs, self._last_quality)
            self.diagnostic_report_ready.emit(str(path))
            self.status_message.emit("گزارش امن ساخته شد؛ هیچ کلید یا آدرس سروری داخلش نیست", "success")
        except Exception as exc:
            self.status_message.emit(f"ساخت گزارش ناموفق بود: {exc}", "error")

    def test_ping(self, name: str, host: str, port: int):
        """تست لتنسی TCP به یه آدرس/پورت مشخص، در ترد جدا"""
        def worker():
            latency = connectivity_service.measure_latency_ms(host, port)
            self.ping_result_ready.emit(name, latency)

        threading.Thread(target=worker, daemon=True).start()

    def force_stop_tunnel_on_exit(self):
        """موقع بستن کامل اپ صدا زده می‌شه تا تانل هم پاک بسته بشه"""
        try:
            self._finalize_usage_tick()
        except Exception:
            pass
        try:
            self._tunnel.stop()
        except Exception:
            pass
        if self._official_warp_session.get("started_by_app"):
            try:
                official_warp_service.disconnect_if_started(
                    True,
                    self._official_warp_session.get("original_mode", ""),
                    self._official_warp_session.get("original_protocol", ""),
                )
            except Exception:
                pass

    # ---------- Warp رایگان خودکار ----------

    @staticmethod
    def _official_warp_payload(status):
        return {
            "operation": "status", "ok": True, "installed": status.installed,
            "active": status.connected, "trace_active": status.trace_active,
            "service_running": status.service_running,
            "signature_valid": status.signature_valid,
            "detail": status.detail, "cli_status": status.cli_status,
            "mode": status.mode, "protocol": status.protocol,
        }

    def refresh_official_warp_status(self):
        def worker():
            self._official_warp_completed.emit(
                self._official_warp_payload(official_warp_service.inspect())
            )
        threading.Thread(target=worker, daemon=True).start()

    def import_warp_config(self, mode_selection: str = "smart", protocol: str = "auto"):
        """Connect through the signed official client and verify the public path."""
        if self._match_route_locked:
            self.status_message.emit("Match Lock فعال است؛ WARP وسط نشست بازی تغییر نمی‌کند", "info")
            return
        self.warp_busy_changed.emit(True)
        self._warp_generation += 1
        operation_generation = self._warp_generation
        self._connection_generation = self._connection_state.begin(
            "warp", "آزمایش مسیرهای رسمی Cloudflare", cancellable=True
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self.status_message.emit("WARP رسمی در حال آزمایش و تأیید مسیر واقعی است…", "info")

        def worker():
            self._connection_state.advance(
                self._connection_generation, "testing", "سنجش حالت‌های رسمی Cloudflare"
            )
            self.connection_flow_changed.emit(self._connection_state.snapshot())
            if not ALLOW_LEGACY_WARP_REGISTRATION:
                protocols = {
                    "auto": ("MASQUE", "WireGuard"),
                    "masque": ("MASQUE",),
                    "wireguard": ("WireGuard",),
                }.get(protocol, ("MASQUE", "WireGuard"))
                modes = {
                    "smart": ("warp+doh", "warp+dot", "warp"),
                    "rescue": ("warp+doh", "warp+dot", "warp", "tunnel_only", "doh", "dot"),
                    "dns_smart": ("doh", "dot"),
                    "doh": ("doh",), "dot": ("dot",), "warp": ("warp",),
                    "warp+doh": ("warp+doh",), "warp+dot": ("warp+dot",),
                    "tunnel_only": ("tunnel_only",),
                }.get(mode_selection, ("warp+doh", "warp+dot", "warp"))
                result = official_warp_service.connect_best(
                    modes=modes,
                    protocols=protocols,
                    progress=lambda message: self.warp_state_changed.emit({
                        "operation": "progress", "message": message,
                    }),
                    cancelled=lambda: operation_generation != self._warp_generation,
                )
                result["operation"] = "connect"
                self._official_warp_completed.emit(result)
                return
            try:
                config = warp_service.register_warp_account()
            except Exception as e:
                self._warp_completed.emit(None, str(e))
                return
            default_port = config.port
            failures = []
            for port in warp_service.WIREGUARD_PORTS:
                config.port = port
                health = tunnel_service.probe_config(config, attempts=1, timeout_s=4.0)
                if health.available:
                    config.extra["last_probe_ms"] = health.latency_ms
                    config.extra["tested_ports"] = list(warp_service.WIREGUARD_PORTS)
                    config.extra["verified"] = True
                    self._warp_completed.emit(config, "")
                    return
                failures.append(f"{port}: {health.error}")
            config.port = default_port
            self._warp_completed.emit(
                None,
                "هیچ‌کدام از چهار پورت آزمایشی WARP پاسخ معتبر ندادند؛ پروفایل خراب "
                "ذخیره نشد "
                f"({'; '.join(failures)})",
            )

        threading.Thread(target=worker, daemon=True).start()

    def cancel_official_warp_test(self):
        snapshot = self._connection_state.snapshot()
        if snapshot.get("scope") != "warp" or not snapshot.get("cancellable"):
            return
        self._warp_generation += 1
        self._connection_state.cancel(
            self._connection_generation, "لغو شد؛ تنظیم قبلی Cloudflare در حال بازگشت است"
        )
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        self.warp_state_changed.emit({
            "operation": "progress",
            "message": "لغو دریافت شد؛ تنظیم قبلی Cloudflare در حال بازگشت است…",
        })

    def disconnect_official_warp(self):
        self.warp_busy_changed.emit(True)
        self._connection_generation = self._connection_state.begin(
            "warp", "بازگردانی WARP متعلق به برنامه", cancellable=False
        )
        self._connection_state.advance(self._connection_generation, "restoring")
        self.connection_flow_changed.emit(self._connection_state.snapshot())
        started_by_app = bool(self._official_warp_session.get("started_by_app"))
        original_mode = self._official_warp_session.get("original_mode", "")
        original_protocol = self._official_warp_session.get("original_protocol", "")

        def worker():
            result = official_warp_service.disconnect_if_started(
                started_by_app, original_mode, original_protocol,
            )
            result["operation"] = "disconnect"
            self._official_warp_completed.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_official_warp_finished(self, result: dict):
        operation = result.get("operation")
        if operation != "status":
            self.warp_busy_changed.emit(False)
            if result.get("cancelled"):
                self._connection_state.reset("آزمایش WARP لغو شد؛ تنظیم قبلی بازگشت")
            elif operation == "disconnect" and result.get("ok") and not result.get("active"):
                self._connection_state.reset("WARP متعلق به برنامه بازگردانده شد")
            else:
                self._connection_state.advance(
                    self._connection_generation,
                    "active" if result.get("ok") and result.get("active") else "failed",
                    str(result.get("message") or result.get("error") or "وضعیت WARP به‌روزرسانی شد"),
                    owned_by_app=bool(result.get("started_by_app")),
                )
            self.connection_flow_changed.emit(self._connection_state.snapshot())
        if operation == "connect" and result.get("ok"):
            self._official_warp_session = dict(result)
        elif operation == "disconnect" and result.get("ok") and not result.get("active"):
            self._official_warp_session = {}
        self.warp_state_changed.emit(result)
        if operation in {"connect", "disconnect"}:
            message = result.get("message") or result.get("error") or "وضعیت WARP به‌روزرسانی شد"
            self.status_message.emit(message, "success" if result.get("ok") else "error")

    def _on_warp_finished(self, config, error: str):
        self.warp_busy_changed.emit(False)
        if config is None:
            self.status_message.emit(error, "error")
            return
        self.tunnel_configs = tunnel_storage_service.add_config(self.tunnel_configs, config)
        self.tunnel_configs_changed.emit(self.tunnel_configs)
        if error:
            self.status_message.emit(error, "error")
        else:
            self.status_message.emit(
                f"WARP با تست واقعی وصل شد ({config.extra.get('last_probe_ms', 0)}ms) ✅",
                "success",
            )

    # ---------- اجرای خودکار با ویندوز ----------

    def is_autostart_enabled(self) -> bool:
        return autostart_service.is_enabled()

    def set_autostart_enabled(self, enabled: bool):
        ok = autostart_service.set_enabled(enabled)
        if ok:
            msg = "اجرای خودکار با ویندوز فعال شد ✅" if enabled else "اجرای خودکار غیرفعال شد"
            self.status_message.emit(msg, "success" if enabled else "info")
        else:
            self.status_message.emit("تغییر تنظیم اجرای خودکار ممکن نشد ⚠️", "error")

    # ---------- امتیاز شخصی کانفیگ‌ها ----------

    def get_config_rating(self, config_id: str) -> int:
        return rating_service.get_rating(config_id)

    def set_config_rating(self, config_id: str, stars: int):
        rating_service.set_rating(config_id, stars)
        self.status_message.emit(f"امتیاز {stars}⭐ ذخیره شد", "success")

    # ---------- تست سرعت مقایسه‌ای ----------

    def run_speed_comparison(self):
        """Measure actual HTTPS bytes on the currently active system route."""
        self.status_message.emit("در حال سنجش واقعی مسیر فعال...", "info")

        def worker():
            health = tunnel_service.measure_http_path(attempts=3, timeout_s=5.0)
            result = {
                "route": "tunnel" if self.tunnel_connected else "direct",
                "available": health.available,
                "latency": health.latency_ms,
                "jitter": health.jitter_ms,
                "successes": health.successes,
                "attempts": health.attempts,
                "error": health.error,
            }
            self.speed_test_ready.emit(result)

        threading.Thread(target=worker, daemon=True).start()
