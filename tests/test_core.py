import base64
import hashlib
import json
import os
import socket
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app import app_info
from app.models.network_adapter import DnsProfile
from app.models.app_access import DEFAULT_APP_ACCESS_PROFILES
from app.models.tunnel_config import TunnelConfig
from app.services import app_paths, config_parser, connectivity_service, crash_service, diagnostics_service, dns_service, game_detection_service, game_route_profile_service, game_server_probe_service, gamelink_service, quality_service, settings_service, subscription_service, tunnel_storage_service, warp_service, official_warp_service, privileged_helper, update_service, network_lab_service, game_qos_service, app_access_service, app_route_service, app_profile_catalog_service, route_dna_service, radar_service, integrity_service, recovery_service, connection_state_service, game_session_report_service
from app.services.tunnel_service import build_sing_box_config, build_xray_config, engine_for
from app.views.status_banner import StatusBanner


UUID = "11111111-1111-1111-1111-111111111111"


class ConnectionStateTests(unittest.TestCase):
    def test_stale_worker_cannot_overwrite_new_connection(self):
        state = connection_state_service.ConnectionState()
        old = state.begin("dns", "old")
        new = state.begin("app", "new")
        self.assertFalse(state.advance(old, "active", "stale", True))
        self.assertTrue(state.advance(new, "testing", "current"))
        self.assertEqual(state.snapshot()["scope"], "app")
        self.assertEqual(state.snapshot()["message"], "current")

    def test_cancel_enters_non_cancellable_restore_and_reset_clears_owner(self):
        state = connection_state_service.ConnectionState()
        generation = state.begin("warp", "start")
        state.advance(generation, "applying", owned_by_app=True)
        self.assertTrue(state.cancel(generation, "restore"))
        self.assertEqual(state.snapshot()["phase"], "restoring")
        self.assertFalse(state.snapshot()["cancellable"])
        state.reset("done")
        self.assertEqual(state.snapshot()["phase"], "idle")
        self.assertFalse(state.snapshot()["owned_by_app"])

    def test_post_session_report_aggregates_without_endpoints(self):
        game = MagicMock()
        game.name = "Test Game"
        game.route_profile = {"history": [
            {"latency_ms": 80, "jitter_ms": 5, "loss": 0, "new_endpoints": 2},
            {"latency_ms": 100, "jitter_ms": 7, "loss": 2, "new_endpoints": 1},
        ]}
        report = game_session_report_service.finish(
            game, {"game": "Test Game", "started_at": "2026-09-08T00:00:00+00:00", "history_index": 0},
            "dns",
        )
        self.assertEqual(report["median_ms"], 90)
        self.assertEqual(report["route_events"], 3)
        self.assertNotIn("endpoints", report)
        self.assertNotIn("host", report)


class PackageAclTests(unittest.TestCase):
    @patch("app.services.integrity_service._read_acl")
    def test_acl_rejects_broad_user_modify_permission(self, read_acl):
        read_acl.return_value = {
            "owner": "BUILTIN\\Administrators",
            "rules": [{"identity": "BUILTIN\\Users", "rights": "Modify, Synchronize", "type": "Allow"}],
        }
        with patch("app.services.integrity_service.os.name", "nt"):
            result = integrity_service.audit_package_acl(Path("C:/Program Files/LAGSHIFT"))
        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "broad-write-access")

    @patch("app.services.integrity_service._read_acl")
    def test_acl_accepts_read_execute_for_users(self, read_acl):
        read_acl.return_value = {
            "owner": "BUILTIN\\Administrators",
            "rules": [{"identity": "BUILTIN\\Users", "rights": "ReadAndExecute, Synchronize", "type": "Allow"}],
        }
        with patch("app.services.integrity_service.os.name", "nt"):
            result = integrity_service.audit_package_acl(Path("C:/Program Files/LAGSHIFT"))
        self.assertTrue(result["safe"])


class StatusBannerTests(unittest.TestCase):
    def test_finished_fade_collapses_banner_and_clears_text(self):
        banner = MagicMock()
        banner._hide_timer.isActive.return_value = False
        banner._effect.opacity.return_value = 0.0
        banner._message_generation = 3
        banner._collapse = lambda generation: StatusBanner._collapse(banner, generation)
        StatusBanner._on_fade_finished(banner)
        banner.setFixedHeight.assert_called_once_with(0)
        banner.clear.assert_called_once_with()

    def test_active_replacement_message_is_not_collapsed(self):
        banner = MagicMock()
        banner._hide_timer.isActive.return_value = True
        banner._effect.opacity.return_value = 0.0
        StatusBanner._on_fade_finished(banner)
        banner.setFixedHeight.assert_not_called()
        banner.clear.assert_not_called()

    def test_stale_banner_timeout_cannot_hide_newer_message(self):
        banner = MagicMock()
        banner._message_generation = 4
        banner._hide_timer.isActive.return_value = False
        StatusBanner._collapse(banner, 3)
        banner.setFixedHeight.assert_not_called()
        banner.clear.assert_not_called()


class AppAccessTests(unittest.TestCase):
    def test_every_app_profile_has_a_bundled_vector_icon(self):
        icon_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "app_icons"
        missing = [
            profile.id for profile in DEFAULT_APP_ACCESS_PROFILES
            if not (icon_dir / f"{profile.id}.svg").is_file()
        ]
        self.assertEqual(missing, [])
        for profile in DEFAULT_APP_ACCESS_PROFILES:
            text = (icon_dir / f"{profile.id}.svg").read_text(encoding="utf-8")
            self.assertIn("<svg", text)
            self.assertIn("viewBox=", text)
            self.assertLess(len(text), 64 * 1024)

    def test_presets_have_real_mission_targets_and_unique_ids(self):
        ids = [profile.id for profile in DEFAULT_APP_ACCESS_PROFILES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 20)
        for profile in DEFAULT_APP_ACCESS_PROFILES:
            if not profile.web_only:
                self.assertTrue(profile.process_names)
            self.assertTrue(profile.domains_for("smart"))
            for domain in profile.domains_for("smart"):
                self.assertIn(".", domain)
                self.assertNotIn("/", domain)

    def test_catalog_distinguishes_installed_and_running(self):
        rows = app_access_service.catalog_status(
            installed_names={"steam", "discord"}, process_names={"discord.exe"}
        )
        by_id = {row["id"]: row for row in rows}
        self.assertTrue(by_id["discord"]["installed"])
        self.assertTrue(by_id["discord"]["running"])
        self.assertTrue(by_id["steam"]["installed"])
        self.assertFalse(by_id["steam"]["running"])

    def test_generic_background_processes_do_not_trigger_app_profiles(self):
        active = app_access_service.active_profile_ids({
            "update.exe", "agent.exe", "gamingservices.exe", "launcher.exe",
        })
        self.assertFalse(active)

    def test_missions_use_only_their_relevant_domains(self):
        discord = next(profile for profile in DEFAULT_APP_ACCESS_PROFILES if profile.id == "discord")
        self.assertEqual(discord.domains_for("login"), discord.login_domains)
        self.assertEqual(discord.domains_for("download"), discord.download_domains)
        self.assertGreater(len(discord.domains_for("smart")), len(discord.domains_for("login")))

    @patch("app.services.app_access_service.ssl.create_default_context")
    @patch("app.services.app_access_service.socket.create_connection")
    @patch("app.services.app_access_service.socket.getaddrinfo")
    def test_probe_requires_real_resolution_and_tcp_handshake(self, getaddrinfo, connect, tls_context):
        getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 443))]
        connect.return_value = MagicMock()
        tls_context.return_value.wrap_socket.return_value = MagicMock()
        result = app_access_service.probe_domains(["example.com"])
        self.assertTrue(result["healthy"])
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["reachable"], 1)
        self.assertEqual(result["tls_ok"], 1)
        connect.assert_called_once_with(("example.com", 443), timeout=1.4)
        tls_context.return_value.wrap_socket.assert_called_once()

    @patch("app.services.app_access_service.ssl.create_default_context")
    @patch("app.services.app_access_service.socket.create_connection")
    @patch("app.services.app_access_service.socket.getaddrinfo")
    def test_probe_marks_dead_private_dns_sinkhole(self, getaddrinfo, connect, _tls_context):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.10.34.35", 443))
        ]
        connect.side_effect = OSError("blocked")
        result = app_access_service.probe_domains(["discord.com", "gateway.discord.gg"])
        self.assertTrue(result["suspected_sinkhole"])
        self.assertEqual(result["unique_addresses"], ["10.10.34.35"])
        self.assertEqual(app_route_service.diagnose(result)["code"], "dns-sinkhole")

    def test_local_route_diagnosis_distinguishes_dns_transport_and_tls(self):
        self.assertEqual(app_route_service.diagnose({"attempted": 2})["code"], "dns")
        self.assertEqual(app_route_service.diagnose({
            "attempted": 2, "resolved": 2, "reachable": 0,
        })["code"], "transport")
        self.assertEqual(app_route_service.diagnose({
            "attempted": 2, "resolved": 2, "reachable": 2, "tls_ok": 0,
        })["code"], "tls")
        self.assertEqual(app_route_service.diagnose({
            "attempted": 2, "resolved": 2, "reachable": 2, "tls_ok": 2,
        })["code"], "healthy")

    def test_route_learning_is_local_bounded_and_hides_adapter_name(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            app_route_service.record_outcome(
                profile_id="discord", mission="login", adapter_name="Private Wi-Fi Name",
                route="warp", ok=True, mode="warp+dot", median_ms=42,
                diagnosis="healthy",
            )
            raw = app_route_service._history_path().read_text(encoding="utf-8")
            self.assertNotIn("Private Wi-Fi Name", raw)
            self.assertEqual(
                app_route_service.preferred_warp_modes("discord", "login", "Private Wi-Fi Name")[0],
                "warp+dot",
            )


class RouteDnaTests(unittest.TestCase):
    def test_history_keeps_only_hashed_network_and_bounded_metrics(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            context = {
                "network": "a" * 20, "purpose": "voice",
                "public_ip": "203.0.113.42", "operator": "Private ISP",
            }
            route_dna_service.record(
                context, target="discord", route="dns:Electro",
                success=True, latency_ms=72, jitter_ms=4, loss=0,
            )
            raw = route_dna_service._history_path().read_text(encoding="utf-8")
            self.assertNotIn("203.0.113.42", raw)
            self.assertNotIn("Private ISP", raw)
            self.assertEqual(route_dna_service.prior(
                context, "discord", "dns:Electro"
            )["samples"], 1)

    def test_operator_prior_is_hashed_and_only_a_low_confidence_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            first = {"network": "home", "purpose": "voice", "asn": "AS44244",
                     "operator": "Private ISP", "geo": {"country": "IR"},
                     "adapter_kind": "mobile"}
            second = {**first, "network": "another-cell"}
            route_dna_service.record(
                first, target="discord", route="dns:Electro", success=True,
                latency_ms=70,
            )
            raw = route_dna_service._history_path().read_text(encoding="utf-8")
            self.assertNotIn("Private ISP", raw)
            self.assertNotIn("AS44244", raw)
            memory = route_dna_service.prior(second, "discord", "dns:Electro")
            self.assertEqual(memory["scope"], "operator-group")
            self.assertEqual(memory["confidence"], "experimental")

    def test_public_stable_never_queues_anonymous_radar(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            radar_service.record_sample({
                "score": 88, "latency": 60, "public_ip": "203.0.113.7",
                "route_dna": {
                    "asn": "AS44244", "operator": "Private ISP",
                    "adapter_kind": "mobile", "purpose": "voice",
                    "geo": {"country": "IR"},
                },
            }, True)
            self.assertFalse(radar_service._queue_file().exists())
            self.assertFalse(app_info.ALLOW_REMOTE_BACKEND)

    def test_live_result_dominates_route_dna_memory(self):
        fast = {"profile": DnsProfile("Fast", "1.1.1.1"), "score": 90}
        slow = {"profile": DnsProfile("Slow", "8.8.8.8"), "score": 70}
        ranked = route_dna_service.personalize_ranked_dns(
            [fast, slow], {"network": "n", "purpose": "smart"}, "dns"
        )
        self.assertEqual(ranked[0]["profile"].name, "Fast")

    def test_hysteresis_requires_gain_and_repeated_bad_samples(self):
        self.assertFalse(route_dna_service.should_switch(70, 90, 1))
        self.assertFalse(route_dna_service.should_switch(70, 76, 3))
        self.assertTrue(route_dna_service.should_switch(70, 82, 2))

    def test_busy_or_gaming_network_forces_light_probe_budget(self):
        policy = route_dna_service.probe_policy(
            {"pressure": "busy"}, game_running=False, requested="deep"
        )
        self.assertEqual(policy["mode"], "light")
        self.assertLessEqual(policy["max_kb"], 96)

    def test_route_drift_invalidates_changed_network(self):
        previous = {"network": "old", "adapter_kind": "wifi", "ipv4": True, "ipv6": False}
        current = {"network": "new", "adapter_kind": "wifi", "ipv4": True, "ipv6": False}
        self.assertTrue(route_dna_service.detect_drift(previous, current)["changed"])

    def test_candidate_registry_exposes_only_available_route_families(self):
        rows = route_dna_service.candidate_registry(
            dns_names=("Electro", "Cloudflare"), warp_available=False
        )
        self.assertEqual([row["kind"] for row in rows], ["direct", "dns", "dns"])
        self.assertFalse(any(row["kind"] == "warp" for row in rows))

    def test_explanation_is_based_on_probe_and_local_samples(self):
        context = {"network": "none", "purpose": "login"}
        text = route_dna_service.explain_choice(
            context, route="direct", target="discord",
            probe={"tls_ok": 2, "median_ms": 81},
        )
        self.assertIn("2 مقصد", text)
        self.assertIn("81ms", text)

    def test_daily_probe_budget_is_bounded_and_resets_by_storage_day(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            first = route_dna_service.reserve_probe_budget(900, daily_limit_mb=1)
            second = route_dna_service.reserve_probe_budget(900, daily_limit_mb=1)
            self.assertTrue(first["allowed"])
            self.assertFalse(second["allowed"])
            self.assertGreaterEqual(second["remaining_kb"], 0)

    def test_remote_hint_is_coarse_and_drops_ip_fields(self):
        hint = route_dna_service.sanitize_remote_hint({
            "country": "ir", "region": "Tehran", "city": "Tehran",
            "asn": 44244, "operator": "Example ISP", "ip": "203.0.113.9",
        })
        self.assertEqual(hint["asn"], "AS44244")
        self.assertEqual(hint["geo"]["country"], "IR")
        self.assertNotIn("ip", hint)

    def test_shared_tournament_scores_each_purpose_differently(self):
        fast = {"id": "fast", "available": True, "latency_ms": 30,
                "jitter_ms": 2, "loss": 0, "success_rate": 100,
                "download_mbps": 3}
        download = {"id": "download", "available": True, "latency_ms": 80,
                    "jitter_ms": 5, "loss": 0, "success_rate": 100,
                    "download_mbps": 22}
        self.assertEqual(
            route_dna_service.tournament([fast, download], "game")["winner"]["id"],
            "fast",
        )
        self.assertEqual(
            route_dna_service.tournament([fast, download], "download")["winner"]["id"],
            "download",
        )

    def test_deep_bandwidth_probe_requires_explicit_confirmation(self):
        result = route_dna_service.measure_controlled_bandwidth(
            "https://edge.example", "deep", deep_confirmed=False
        )
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "confirmation-required")

    def test_mobile_adapter_is_not_mislabeled_as_other(self):
        self.assertEqual(route_dna_service._adapter_kind("Intel 5G WWAN"), "mobile")

    def test_cgnat_hint_requires_carrier_range_evidence(self):
        self.assertEqual(
            network_lab_service._cgnat_from_hops(["192.168.1.1", "100.70.2.4"]),
            "probable",
        )
        self.assertEqual(
            network_lab_service._cgnat_from_hops(["192.168.1.1", "8.8.8.8"]),
            "unknown",
        )

    def test_recent_failed_warp_uses_network_scoped_cooldown(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            app_route_service.record_outcome(
                profile_id="discord", mission="smart", adapter_name="Wi-Fi",
                route="failed", ok=False, mode="warp-unavailable", diagnosis="transport",
            )
            self.assertFalse(app_route_service.warp_retry_allowed("discord", "smart", "Wi-Fi"))
            self.assertTrue(app_route_service.warp_retry_allowed("spotify", "smart", "Wi-Fi"))
            self.assertTrue(app_route_service.warp_retry_allowed("discord", "smart", "Ethernet"))

    def test_new_application_batch_is_complete(self):
        ids = {profile.id for profile in DEFAULT_APP_ACCESS_PROFILES}
        self.assertTrue({
            "soundcloud", "vscode", "unity", "amd", "nvidia",
            "chatgpt", "claude", "gemini", "copilot", "perplexity",
        }.issubset(ids))

    @patch("app.services.app_access_service.subprocess.Popen")
    @patch("app.services.app_access_service.catalog_status")
    def test_launcher_runs_only_discovered_executable(self, catalog, popen):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "Code.exe"
            executable.touch()
            catalog.return_value = [{"id": "vscode", "executable_path": str(executable)}]
            ok, _message = app_access_service.launch_profile("vscode")
            self.assertTrue(ok)
            popen.assert_called_once()

    @patch("app.services.app_access_service.os.startfile", create=True)
    @patch("app.services.app_access_service.catalog_status", return_value=[])
    def test_web_profile_opens_only_bundled_https_target(self, _catalog, startfile):
        ok, _message = app_access_service.launch_profile("gemini")
        self.assertTrue(ok)
        startfile.assert_called_once_with("https://gemini.google.com/")

    def test_viewmodel_uses_official_warp_after_dns_candidates_fail(self):
        from PySide6.QtCore import QCoreApplication
        from app.viewmodels.main_viewmodel import MainViewModel

        qt_app = QCoreApplication.instance() or QCoreApplication([])
        baseline = {
            "healthy": False, "attempted": 2, "resolved": 2,
            "reachable": 0, "tls_ok": 0, "median_ms": -1,
        }
        after = {
            "healthy": True, "attempted": 2, "resolved": 2,
            "reachable": 2, "tls_ok": 2, "median_ms": 55,
        }
        status = official_warp_service.OfficialWarpStatus(
            installed=True, signature_valid=True, connected=False,
        )
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ), patch("app.services.app_access_service.probe_profile", side_effect=[baseline, after]), \
                patch("app.services.connectivity_service.rank_dns_profiles", return_value=[]), \
                patch("app.services.official_warp_service.inspect", return_value=status), \
                patch("app.services.official_warp_service.connect_best", return_value={
                    "ok": True, "started_by_app": True, "mode": "warp+doh",
                    "mode_label": "ترافیک و DNS (HTTPS)", "original_mode": "warp",
                    "original_protocol": "MASQUE",
                }) as connect_best, \
                patch("app.services.app_access_service.profile_connection_evidence", return_value={
                    "running": False, "connections": 0, "has_session_evidence": False,
                }):
            vm = MainViewModel()
            vm.dns_profiles = []
            results = []
            vm.app_access_changed.connect(results.append)
            vm.start_app_access("discord", "login", "Wi-Fi", allow_warp=True)
            deadline = time.time() + 3
            while not results and time.time() < deadline:
                qt_app.processEvents()
                time.sleep(0.01)
            self.assertTrue(vm.wait_for_app_access())
            qt_app.processEvents()
            self.assertTrue(results)
            self.assertTrue(results[-1]["ok"])
            self.assertEqual(results[-1]["route"], "warp")
            connect_best.assert_called_once()
            for timer in vm.findChildren(type(vm._app_access_watch_timer)):
                timer.stop()

    def test_app_access_verifies_more_than_the_first_ranked_dns(self):
        from PySide6.QtCore import QCoreApplication
        from app.viewmodels.main_viewmodel import MainViewModel

        qt_app = QCoreApplication.instance() or QCoreApplication([])
        baseline = {
            "healthy": False, "attempted": 2, "resolved": 2,
            "reachable": 0, "tls_ok": 0, "median_ms": -1,
        }
        first_failed = {
            "healthy": False, "attempted": 2, "resolved": 2,
            "reachable": 0, "tls_ok": 0, "median_ms": -1,
        }
        second_healthy = {
            "healthy": True, "attempted": 2, "resolved": 2,
            "reachable": 2, "tls_ok": 2, "median_ms": 48,
        }
        first = DnsProfile("First", "1.1.1.1", region="iran", purpose="anti_sanction")
        second = DnsProfile("Second", "8.8.8.8", region="iran", purpose="anti_sanction")
        ranking = [
            {"profile": first, "score": 95},
            {"profile": second, "score": 90},
        ]
        status = official_warp_service.OfficialWarpStatus(
            installed=False, signature_valid=False, connected=False,
        )
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ), patch(
            "app.services.app_access_service.probe_profile",
            side_effect=[baseline, first_failed, second_healthy],
        ), patch(
            "app.services.connectivity_service.rank_dns_profiles", return_value=ranking,
        ), patch(
            "app.services.official_warp_service.inspect", return_value=status,
        ), patch(
            "app.services.privileged_helper.is_admin", return_value=True,
        ), patch(
            "app.services.dns_service.set_dns", return_value=True,
        ) as set_dns, patch(
            "app.services.app_access_service.profile_connection_evidence",
            return_value={"running": False, "connections": 0, "has_session_evidence": False},
        ):
            vm = MainViewModel()
            vm.dns_profiles = [first, second]
            results = []
            vm.app_access_changed.connect(results.append)
            vm.start_app_access("discord", "login", "Wi-Fi", allow_warp=True)
            deadline = time.time() + 3
            while not results and time.time() < deadline:
                qt_app.processEvents()
                time.sleep(0.01)
            self.assertTrue(vm.wait_for_app_access())
            qt_app.processEvents()
            self.assertTrue(results)
            self.assertTrue(results[-1]["ok"])
            self.assertEqual(results[-1]["route"], "dns")
            self.assertEqual(results[-1]["dns_name"], "Second")
            self.assertEqual(results[-1]["dns_candidates_tested"], 2)
            self.assertEqual(set_dns.call_count, 2)
            for timer in vm.findChildren(type(vm._app_access_watch_timer)):
                timer.stop()

    def test_non_admin_app_access_batches_dns_into_one_elevation(self):
        from PySide6.QtCore import QCoreApplication
        from app.viewmodels.main_viewmodel import MainViewModel

        qt_app = QCoreApplication.instance() or QCoreApplication([])
        baseline = {
            "healthy": False, "attempted": 2, "resolved": 2,
            "reachable": 0, "tls_ok": 0, "median_ms": -1,
        }
        verified = {
            "healthy": True, "attempted": 2, "resolved": 2,
            "reachable": 2, "tls_ok": 2, "median_ms": 44,
        }
        first = DnsProfile("First", "1.1.1.1", region="iran", purpose="anti_sanction")
        second = DnsProfile("Second", "8.8.8.8", region="iran", purpose="anti_sanction")
        ranking = [{"profile": first, "score": 95}, {"profile": second, "score": 90}]
        status = official_warp_service.OfficialWarpStatus(
            installed=False, signature_valid=False, connected=False,
        )
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ), patch(
            "app.services.app_access_service.probe_profile", return_value=baseline,
        ), patch(
            "app.services.connectivity_service.rank_dns_profiles", return_value=ranking,
        ), patch(
            "app.services.official_warp_service.inspect", return_value=status,
        ), patch(
            "app.services.privileged_helper.is_admin", return_value=False,
        ), patch(
            "app.services.privileged_helper.select_dns", return_value={
                "ok": True, "selected": {"name": "Second", "probe": verified, "index": 2},
            },
        ) as select_dns, patch(
            "app.services.dns_service.set_dns",
        ) as set_dns, patch(
            "app.services.app_access_service.profile_connection_evidence",
            return_value={"running": False, "connections": 0, "has_session_evidence": False},
        ):
            vm = MainViewModel()
            vm.dns_profiles = [first, second]
            results = []
            vm.app_access_changed.connect(results.append)
            vm.start_app_access("discord", "login", "Wi-Fi", allow_warp=True)
            deadline = time.time() + 3
            while not results and time.time() < deadline:
                qt_app.processEvents()
                time.sleep(0.01)
            self.assertTrue(vm.wait_for_app_access())
            qt_app.processEvents()
            self.assertTrue(results[-1]["ok"])
            self.assertEqual(results[-1]["dns_name"], "Second")
            select_dns.assert_called_once()
            set_dns.assert_not_called()
            for timer in vm.findChildren(type(vm._app_access_watch_timer)):
                timer.stop()


class ProductFoundationTests(unittest.TestCase):
    def test_public_edition_does_not_enable_custom_tunnels(self):
        self.assertEqual(app_info.EDITION, "public")
        self.assertFalse(app_info.ALLOW_CUSTOM_TUNNELS)
        self.assertFalse(app_info.ALLOW_SYSTEM_WIDE_TUNNEL)
        self.assertFalse(app_info.ALLOW_LEGACY_WARP_REGISTRATION)

    def test_public_ui_hides_legacy_saved_tunnel_controls(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "views" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("legacy_routes_panel.setVisible(ALLOW_CUSTOM_TUNNELS)", source)
        self.assertIn("WARP سرور قابل‌انتخاب یا ذخیره‌شده", source)

    def test_warp_inspection_processes_stay_hidden_on_windows(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "services" /
                  "official_warp_service.py").read_text(encoding="utf-8")
        signature_probe = source[source.index("def _signature_is_cloudflare"):source.index(
            "def _cli_output"
        )]
        self.assertIn('creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)', signature_probe)

    def test_legacy_data_is_copied_without_deleting_the_source(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            legacy = Path(folder) / app_info.LEGACY_DATA_FOLDER_NAME
            legacy.mkdir()
            source = legacy / "sample.json"
            source.write_text('{"legacy": true}', encoding="utf-8")
            target = app_paths.migrated_file("sample.json")
            self.assertEqual(target.parent.name, app_info.DATA_FOLDER_NAME)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"legacy": true}')
            self.assertTrue(source.exists())

    def test_public_build_does_not_bundle_unused_tunnel_engines(self):
        spec = (Path(__file__).resolve().parents[1] / "LAGSHIFT.spec").read_text(encoding="utf-8")
        self.assertIn("binaries=[]", spec)
        for filename in ("xray.exe", "wintun.dll", "geoip.dat", "geosite.dat"):
            self.assertNotIn(f'root / "{filename}"', spec)

    def test_installer_never_deletes_user_profile_data(self):
        script = (Path(__file__).resolve().parents[1] / "installer" / "LAGSHIFT.iss").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("[UninstallDelete]", script)
        self.assertNotIn("{userappdata}", script.lower())
        self.assertNotIn("{localappdata}", script.lower())

    def test_upgrade_replaces_runtime_as_one_unit_and_keeps_rollback(self):
        root = Path(__file__).resolve().parents[1]
        inno = (root / "installer" / "LAGSHIFT.iss").read_text(encoding="utf-8")
        wrapper = (root / "installer" / "bootstrapper" / "MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn('[InstallDelete]', inno)
        self.assertIn('Name: "{app}\\_internal"', inno)
        self.assertIn('Name: "{app}\\{#MyAppExeName}"', inno)
        self.assertNotIn('{userappdata}', inno.lower())
        self.assertIn('VerifyInstalledPayload(installPath)', wrapper)
        self.assertIn('DeleteKnownPayload(installPath)', wrapper)
        self.assertLess(
            wrapper.index('DeleteKnownPayload(installPath)'),
            wrapper.index('CopyDirectory(backupPath, installPath, overwrite: true)'),
        )

    def test_release_build_enforces_pinned_python_and_qt(self):
        script = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("sys.version_info[:2] == (3, 12)", script)
        self.assertIn("PySide6.__version__ == '6.8.3'", script)
        self.assertIn("shiboken6.__version__ == '6.8.3'", script)

    def test_signed_release_pipeline_signs_inner_layers_before_packaging(self):
        script = (Path(__file__).resolve().parents[1] / "build-installer.ps1").read_text(
            encoding="utf-8"
        )
        sign_app = script.index("-Files @($distExe)")
        build_engine = script.index("'/DBootstrapEngine'")
        sign_engine = script.index("-Files @($engineInstaller)")
        build_wrapper = script.index("dotnet publish")
        sign_wrapper = script.rindex("sign_windows_release.ps1")
        self.assertLess(sign_app, build_engine)
        self.assertLess(build_engine, sign_engine)
        self.assertLess(sign_engine, build_wrapper)
        self.assertLess(build_wrapper, sign_wrapper)

    def test_legal_acceptance_is_versioned(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            settings = settings_service.load_settings()
            self.assertFalse(settings_service.has_current_legal_acceptance(settings))
            settings["terms_accepted_version"] = app_info.TERMS_VERSION
            settings["privacy_acknowledged_version"] = app_info.PRIVACY_VERSION
            settings_service.save_settings(settings)
            self.assertTrue(settings_service.has_current_legal_acceptance())

    def test_public_stable_ignores_stale_cloud_preferences(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            settings_service.save_settings({
                **settings_service.DEFAULTS,
                "turbo_mode": True,
                "gamelink_api_url": "https://example.com",
                "anonymous_radar": True,
                "route_dna_remote_geo": True,
                "route_dna_share_aggregate": True,
            })
            settings = settings_service.load_settings()
            self.assertFalse(settings["turbo_mode"])
            self.assertEqual(settings["gamelink_api_url"], "")
            self.assertFalse(settings["anonymous_radar"])
            self.assertFalse(settings["route_dna_remote_geo"])
            self.assertFalse(settings["route_dna_share_aggregate"])


class ParserTests(unittest.TestCase):
    def test_vless_reality(self):
        item = config_parser.parse_link(
            f"vless://{UUID}@example.com:443?security=reality&type=tcp&pbk=key&sid=01#Fast"
        )
        self.assertEqual(item.protocol, "vless")
        self.assertEqual(item.extra["public_key"], "key")

    def test_trojan(self):
        item = config_parser.parse_link("trojan://secret@example.com:443?security=tls#T")
        self.assertEqual(item.extra["password"], "secret")

    def test_socks_partial_base64(self):
        credentials = base64.urlsafe_b64encode(b"user:pass").decode().rstrip("=")
        item = config_parser.parse_link(f"socks://{credentials}@127.0.0.1:1080#Local")
        self.assertEqual(item.extra["username"], "user")

    def test_hysteria_uses_bundled_xray_when_possible_and_tuic_uses_sing_box(self):
        hy2 = config_parser.parse_link("hy2://secret@example.com:443?sni=example.com#HY2")
        tuic = config_parser.parse_link(f"tuic://{UUID}:pass@example.com:443?sni=example.com#TUIC")
        self.assertEqual(engine_for(hy2), "xray")
        self.assertEqual(engine_for(tuic), "sing-box")
        self.assertEqual(build_sing_box_config(hy2)["outbounds"][0]["type"], "hysteria2")

    def test_invalid_uuid_rejected(self):
        with self.assertRaises(ValueError):
            config_parser.parse_link("vless://bad@example.com:443")


class ConfigBuilderTests(unittest.TestCase):
    def test_xray_tun_is_system_wide_and_mux_is_off(self):
        item = TunnelConfig("1", "x", "vless", "example.com", 443, "", {
            "uuid": UUID, "security": "tls", "network": "tcp",
        })
        document = build_xray_config(item, mode="tun")
        tun = document["inbounds"][0]
        self.assertEqual(tun["protocol"], "tun")
        self.assertIn("0.0.0.0/0", tun["settings"]["autoSystemRoutingTable"])
        self.assertFalse(document["outbounds"][0]["mux"]["enabled"])

    def test_xray_can_route_only_the_detected_game_process(self):
        item = TunnelConfig("1", "x", "vless", "example.com", 443, "", {
            "uuid": UUID, "security": "tls", "network": "tcp",
        })
        document = build_xray_config(item, mode="tun", process_names=["cs2.exe"])
        rules = document["routing"]["rules"]
        self.assertIn({
            "type": "field", "inboundTag": ["tun-in"], "process": ["cs2"],
            "outboundTag": "proxy",
        }, rules)
        self.assertEqual(rules[-1]["outboundTag"], "direct")

    def test_sing_box_can_route_only_the_detected_game_process(self):
        item = config_parser.parse_link(
            f"tuic://{UUID}:pass@example.com:443?sni=example.com#TUIC"
        )
        document = build_sing_box_config(item, mode="tun", process_names=["Game.exe"])
        self.assertEqual(document["route"]["rules"][0]["process_name"], ["Game"])
        self.assertEqual(document["route"]["final"], "direct")

    def test_learned_mtu_is_applied_to_both_tun_engines(self):
        xray_item = config_parser.parse_link(
            f"vless://{UUID}@example.com:443?security=tls#One"
        )
        sing_item = config_parser.parse_link(
            f"tuic://{UUID}:pass@example.com:443?sni=example.com#TUIC"
        )
        self.assertEqual(build_xray_config(xray_item, mode="tun", mtu=1320)["inbounds"][0]["settings"]["mtu"], 1320)
        self.assertEqual(build_sing_box_config(sing_item, mode="tun", mtu=1320)["inbounds"][0]["mtu"], 1320)

    def test_warp_fields_are_complete(self):
        item = TunnelConfig("1", "WARP", "wireguard", "engage.cloudflareclient.com", 2408, "", {
            "private_key": "private", "public_key": "public",
            "client_ipv4": "172.16.0.2/32", "client_ipv6": "2606::2/128",
            "reserved": [1, 2, 3], "mtu": 1280,
        })
        settings = build_xray_config(item)["outbounds"][0]["settings"]
        self.assertEqual(settings["reserved"], [1, 2, 3])
        self.assertEqual(settings["mtu"], 1280)


class SubscriptionTests(unittest.TestCase):
    def test_base64_subscription(self):
        link = f"vless://{UUID}@example.com:443?security=tls#One"
        encoded = base64.b64encode((link + "\n").encode()).decode()
        configs = subscription_service.parse_document(encoded)
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].source, "subscription")

    def test_subscription_rejects_insecure_or_local_urls(self):
        for url in (
            "http://example.com/list",
            "https://127.0.0.1/list",
            "https://192.168.1.5/list",
            "file:///tmp/configs",
            "https://user:secret@example.com/list",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                subscription_service._validated_subscription_url(url)

    def test_public_edition_cannot_fetch_a_subscription(self):
        with self.assertRaisesRegex(ValueError, "نسخه عمومی"):
            subscription_service.fetch("https://example.com/list")


class DnsSelectionTests(unittest.TestCase):
    class _NcsiResponse:
        status = 200
        url = connectivity_service.NCSI_PROBE_URL

        def __init__(self, body=b"Microsoft Connect Test"):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=-1):
            return self.body

    @patch("app.services.connectivity_service.urllib.request.urlopen")
    def test_ncsi_exact_response_confirms_public_internet(self, urlopen):
        urlopen.return_value = self._NcsiResponse()
        result = connectivity_service.detect_internet_scope()
        self.assertEqual(result["state"], "online")
        self.assertTrue(result["online"])

    @patch("app.services.connectivity_service.urllib.request.urlopen")
    def test_ncsi_altered_response_is_captive_portal_evidence(self, urlopen):
        response = self._NcsiResponse(b"Sign in to Wi-Fi")
        response.url = "http://portal.local/login"
        urlopen.return_value = response
        result = connectivity_service.detect_internet_scope()
        self.assertEqual(result["state"], "captive")
        self.assertTrue(result["captive"])

    @patch("app.services.connectivity_service.psutil.net_if_addrs")
    def test_ipv6_audit_warns_for_global_address_with_ipv4_dns(self, addresses):
        addresses.return_value = {
            "Wi-Fi": [MagicMock(family=socket.AF_INET6, address="2606:4700:4700::1111%7")]
        }
        result = connectivity_service.audit_ipv6_exposure(True)
        self.assertTrue(result["global_ipv6"])
        self.assertTrue(result["possible_dns_bypass"])

    @patch("app.services.connectivity_service._dns_exchange")
    def test_reserved_invalid_domain_detects_synthetic_dns_answer(self, exchange):
        query_id = 321
        exchange.return_value = (
            query_id,
            struct.pack("!HHHHHH", query_id, 0x8180, 1, 1, 0, 0),
        )
        result = connectivity_service.detect_dns_hijacking("1.1.1.1")
        self.assertTrue(result["conclusive"])
        self.assertTrue(result["hijacked"])

    @patch("app.services.connectivity_service._dns_exchange")
    def test_reserved_invalid_domain_accepts_nxdomain(self, exchange):
        query_id = 654
        exchange.return_value = (
            query_id,
            struct.pack("!HHHHHH", query_id, 0x8183, 1, 0, 0, 0),
        )
        result = connectivity_service.detect_dns_hijacking("1.1.1.1")
        self.assertTrue(result["conclusive"])
        self.assertFalse(result["hijacked"])

    @patch("app.services.connectivity_service.measure_dns_query_ms")
    def test_only_real_answers_are_ranked(self, measure):
        measure.side_effect = lambda server: {"1.1.1.1": 80, "8.8.8.8": -1, "9.9.9.9": 35}[server]
        profiles = [
            DnsProfile("A", "1.1.1.1"), DnsProfile("B", "8.8.8.8"),
            DnsProfile("C", "9.9.9.9"),
        ]
        selected, latency = connectivity_service.select_fastest_dns(profiles)
        self.assertEqual(selected.name, "C")
        self.assertEqual(latency, 35)

    def test_dns_score_prefers_reliable_stable_service(self):
        stable = connectivity_service.calculate_dns_score(45, 4, 100, True, True, True)
        flaky = connectivity_service.calculate_dns_score(20, 25, 60, False, True, False)
        self.assertGreater(stable, flaky)

    def test_dns_summary_uses_median_and_reports_failures(self):
        result = connectivity_service._summarize_samples([20, 22, 21, 400, -1])
        self.assertEqual(result["median_ms"], 22)
        self.assertEqual(result["success_rate"], 80.0)

    @patch("app.services.connectivity_service.benchmark_dns_profile")
    def test_dns_preference_changes_winner_without_accepting_flaky_results(self, benchmark):
        profiles = [DnsProfile("Fast", "1.1.1.1"), DnsProfile("Stable", "8.8.8.8")]
        values = {
            "Fast": {"score": 78, "median_ms": 20, "jitter_ms": 12, "success_rate": 80},
            "Stable": {"score": 91, "median_ms": 40, "jitter_ms": 2, "success_rate": 100},
        }
        benchmark.side_effect = lambda profile: {
            "profile": profile, "name": profile.name, **values[profile.name]
        }
        fastest = connectivity_service.rank_dns_profiles(profiles, preference="fastest")
        stable = connectivity_service.rank_dns_profiles(profiles, preference="stable")
        self.assertEqual(fastest[0]["name"], "Fast")
        self.assertEqual(stable[0]["name"], "Stable")

    @patch("app.services.connectivity_service.benchmark_dns_profile")
    def test_dns_goal_separates_iranian_bypass_from_global_speed(self, benchmark):
        profiles = [
            DnsProfile("Global", "1.1.1.1"),
            DnsProfile("Iran", "10.0.0.1", region="iran", purpose="anti_sanction"),
        ]
        benchmark.side_effect = lambda profile: {
            "profile": profile, "name": profile.name, "score": 90,
            "median_ms": 20, "jitter_ms": 2, "success_rate": 100,
        }
        speed = connectivity_service.rank_dns_profiles(profiles, goal="speed")
        bypass = connectivity_service.rank_dns_profiles(profiles, goal="anti_sanction")
        self.assertEqual([item["name"] for item in speed], ["Global"])
        self.assertEqual([item["name"] for item in bypass], ["Iran"])


class QualityTests(unittest.TestCase):
    def test_loss_and_jitter_outweigh_small_latency_win(self):
        unstable = quality_service.calculate_game_quality(45, 30, 3, 5)
        stable = quality_service.calculate_game_quality(60, 4, 5, 5)
        self.assertGreater(stable.score, unstable.score)

    def test_competitive_mode_rewards_lower_latency(self):
        fast = quality_service.calculate_game_quality(35, 5, 5, 5, "competitive")
        slow = quality_service.calculate_game_quality(110, 5, 5, 5, "competitive")
        self.assertGreater(fast.score, slow.score)


class GameDetectionTests(unittest.TestCase):
    class _Process:
        def __init__(self, pid, name, exe):
            self.info = {"pid": pid, "name": name, "exe": exe}

    @patch("app.services.game_detection_service.Path.is_file", return_value=False)
    @patch("app.services.game_detection_service._foreground_pid", return_value=42)
    @patch("app.services.game_detection_service.psutil.process_iter")
    def test_unknown_steam_game_is_offered_for_confirmation(self, process_iter, foreground, is_file):
        process_iter.return_value = [self._Process(
            42, "CoolGame-Win64-Shipping.exe",
            r"D:\\SteamLibrary\\steamapps\\common\\CoolGame\\CoolGame-Win64-Shipping.exe",
        )]
        candidate = game_detection_service.detect_unregistered_game([])
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.process_name, "CoolGame-Win64-Shipping.exe")
        self.assertGreaterEqual(candidate.confidence, 55)

    @patch("app.services.game_detection_service._foreground_pid", return_value=42)
    @patch("app.services.game_detection_service.psutil.process_iter")
    def test_browser_is_never_offered_as_a_game(self, process_iter, foreground):
        process_iter.return_value = [self._Process(42, "chrome.exe", r"C:\\Chrome\\chrome.exe")]
        self.assertIsNone(game_detection_service.detect_unregistered_game([]))


class GameServerProbeTests(unittest.TestCase):
    def test_raw_udp_packet_is_matched_by_game_local_port(self):
        source = socket.inet_aton("192.168.1.10")
        destination = socket.inet_aton("9.9.9.9")
        ip_header = bytes([0x45, 0, 0, 28, 0, 0, 0, 0, 64, socket.IPPROTO_UDP, 0, 0]) + source + destination
        udp_header = struct.pack("!HHHH", 58590, 27015, 8, 0)
        result = game_server_probe_service._parse_ipv4_udp_packet(
            ip_header + udp_header, {58590}
        )
        self.assertEqual(result["host"], "9.9.9.9")
        self.assertEqual(result["port"], 27015)
        self.assertEqual(result["source"], "process_port_capture")

    @patch("app.services.game_server_probe_service.psutil.net_connections")
    @patch("app.services.game_server_probe_service.psutil.process_iter")
    def test_probe_discovers_public_game_endpoint_and_prefers_udp(self, process_iter, connections):
        from types import SimpleNamespace
        process_iter.return_value = [SimpleNamespace(info={"pid": 42, "name": "Game.exe"})]
        connections.return_value = [
            SimpleNamespace(
                pid=42, raddr=("8.8.8.8", 443), type=socket.SOCK_STREAM,
            ),
            SimpleNamespace(
                pid=42, raddr=("9.9.9.9", 27015), type=socket.SOCK_DGRAM,
            ),
            SimpleNamespace(
                pid=42, raddr=("192.168.1.2", 9999), type=socket.SOCK_DGRAM,
            ),
        ]
        endpoints = game_server_probe_service.discover_game_endpoints("game.exe")
        self.assertEqual(endpoints[0]["host"], "9.9.9.9")
        self.assertEqual(endpoints[0]["transport"], "udp")
        self.assertNotIn("192.168.1.2", [item["host"] for item in endpoints])

    @patch("app.services.game_server_probe_service._icmp_sample")
    def test_probe_reports_median_jitter_and_loss(self, sample):
        sample.side_effect = [40, 44, -1, 42, 41]
        result = game_server_probe_service.benchmark_endpoint({
            "host": "9.9.9.9", "port": 27015, "transport": "udp", "priority": 1,
        })
        self.assertTrue(result["available"])
        self.assertEqual(result["latency_ms"], 42)
        self.assertEqual(result["loss"], 20.0)


class NetworkLabTests(unittest.TestCase):
    @patch("app.services.network_lab_service._udp_sample", return_value=-1)
    @patch("app.services.network_lab_service.connectivity_service.measure_latency_ms")
    @patch("app.services.network_lab_service.game_server_probe_service._icmp_sample")
    def test_matrix_separates_silent_udp_from_proven_loss(self, icmp, tcp, udp):
        icmp.side_effect = [40, 42, 41]
        tcp.side_effect = [50, 52, 51]
        result = network_lab_service.ping_matrix(
            {"host": "9.9.9.9", "port": 27015, "transport": "udp"}
        )
        self.assertEqual(result["ip_version"], 4)
        self.assertTrue(result["icmp"]["available"])
        self.assertFalse(result["udp"]["conclusive"])
        self.assertIn("نادیده", result["udp"]["note"])

    def test_truth_engine_rejects_process_scoped_external_probe(self):
        result = network_lab_service.truth_engine(
            {"latency_ms": 90, "loss": 1}, {"latency_ms": 60, "loss": 0}, True
        )
        self.assertEqual(result["verdict"], "indirect")
        self.assertFalse(result["trusted"])

    def test_qos_policy_name_is_stable_and_input_is_validated(self):
        self.assertEqual(game_qos_service.policy_name("Game.exe"),
                         game_qos_service.policy_name("game.exe"))
        with self.assertRaises(ValueError):
            game_qos_service.apply("bad'; Remove-Item.exe")


class GameRouteProfileTests(unittest.TestCase):
    def test_learning_merges_frequency_ports_and_quality(self):
        endpoint = {"host": "9.9.9.9", "port": 27015, "transport": "udp"}
        measured = {**endpoint, "score": 88, "latency_ms": 42, "jitter_ms": 3, "loss": 0.0}
        first = game_route_profile_service.merge_observation(
            {}, [endpoint], [measured], "2026-09-01T10:00:00+00:00"
        )
        second = game_route_profile_service.merge_observation(
            first, [endpoint], [measured], "2026-09-02T10:00:00+00:00"
        )
        self.assertEqual(second["endpoints"][0]["seen_count"], 2)
        self.assertEqual(second["udp_ports"], [27015])
        self.assertGreater(second["confidence"], first["confidence"])

    def test_seen_endpoint_history_prevents_evicted_route_becoming_new_again(self):
        endpoints = [
            {"host": f"9.9.9.{index}", "port": 27000 + index, "transport": "udp"}
            for index in range(1, 10)
        ]
        profile = game_route_profile_service.merge_observation({}, endpoints)
        self.assertEqual(len(profile["seen_keys"]), len(endpoints))
        self.assertIn("9.9.9.1:27001/udp", profile["seen_keys"])

    def test_empty_profile_is_never_treated_as_learned(self):
        self.assertFalse(game_route_profile_service.summary({})["available"])

    @patch("app.services.game_route_profile_service.game_server_probe_service.detect_active_anti_cheat", return_value=[])
    @patch("app.services.game_route_profile_service.game_server_probe_service.discover_log_endpoints", return_value=[])
    @patch("app.services.game_route_profile_service.game_server_probe_service.discover_game_endpoints", return_value=[])
    def test_lobby_without_visible_remote_endpoint_is_waiting_not_error(self, *_mocks):
        profile = game_route_profile_service.learn("Game.exe")
        self.assertNotIn("error", profile)
        self.assertTrue(profile["lobby_waiting"])
        self.assertEqual(profile["endpoints"], [])

    @patch("app.services.game_route_profile_service.discover_path_mtu", return_value=1380)
    @patch("app.services.game_route_profile_service.game_server_probe_service.detect_active_anti_cheat", return_value=["vgc.exe"])
    @patch("app.services.game_route_profile_service.game_server_probe_service.discover_log_endpoints")
    @patch("app.services.game_route_profile_service.game_server_probe_service.benchmark_endpoint")
    @patch("app.services.game_route_profile_service.game_server_probe_service.discover_game_endpoints")
    def test_route_lab_builds_context_history_and_recommendations(
        self, discover, benchmark, logs, anti_cheat, path_mtu,
    ):
        endpoint = {"host": "9.9.9.9", "port": 27015, "transport": "udp"}
        discover.return_value = [endpoint]
        logs.return_value = []
        benchmark.return_value = {
            **endpoint, "available": True, "score": 75, "latency_ms": 80,
            "jitter_ms": 18, "loss": 4.0,
        }
        profile = game_route_profile_service.learn("Game.exe", context="Wi-Fi|direct")
        self.assertEqual(profile["recommended_mtu"], 1340)
        self.assertTrue(profile["recommendations"]["fec"])
        self.assertIn("Wi-Fi|direct", profile["contexts"])
        self.assertEqual(len(profile["history"]), 1)
        self.assertEqual(profile["anti_cheat"], ["vgc.exe"])

    def test_route_recipe_round_trip_and_rejects_private_destination(self):
        profile = game_route_profile_service.merge_observation({}, [
            {"host": "9.9.9.9", "port": 27015, "transport": "udp"},
        ])
        text = game_route_profile_service.export_recipe("Game", "Game.exe", profile)
        name, process, loaded = game_route_profile_service.import_recipe(text)
        self.assertEqual((name, process), ("Game", "Game.exe"))
        self.assertEqual(loaded["endpoints"][0]["host"], "9.9.9.9")
        loaded["endpoints"][0]["host"] = "192.168.1.2"
        with self.assertRaises(ValueError):
            game_route_profile_service.import_recipe(
                game_route_profile_service.export_recipe("Game", "Game.exe", loaded)
            )


class GameLinkTests(unittest.TestCase):
    def test_xor_fec_recovers_one_missing_packet(self):
        packets = [b"hello", b"GameDNS", b"udp"]
        parity, lengths = gamelink_service.xor_parity(packets)
        recovered = gamelink_service.recover_one([packets[0], None, packets[2]], parity, lengths)
        self.assertEqual(recovered, packets[1])

    def test_public_stable_blocks_gamelink_bootstrap(self):
        with self.assertRaisesRegex(RuntimeError, "غیرفعال"):
            gamelink_service.bootstrap("https://example.com")

    def test_public_stable_blocks_remote_route_dna(self):
        self.assertEqual(route_dna_service.fetch_remote_hint("https://example.com", True), {})
        result = route_dna_service.measure_controlled_bandwidth("https://example.com", "light")
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "local-stable")


class DiagnosticsTests(unittest.TestCase):
    def test_blackbox_redacts_network_identity_and_secrets(self):
        clean = crash_service.sanitize(
            r"C:\Users\Alice\app token=topsecret https://example.com 203.0.113.9 "
            "2606:4700:4700::1111 aa:bb:cc:dd:ee:ff alice@example.com"
        )
        self.assertNotIn("Alice", clean)
        self.assertNotIn("topsecret", clean)
        self.assertNotIn("example.com", clean)
        self.assertNotIn("203.0.113.9", clean)
        self.assertNotIn("2606:4700", clean)
        self.assertNotIn("aa:bb:cc", clean)
        self.assertNotIn("alice@example.com", clean)

    def test_blackbox_queue_is_local_encrypted_and_export_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder, "APPDATA": folder}
        ):
            crash_service.clear_pending()
            path = crash_service.capture_event(
                "test", "failed at 203.0.113.9 token=topsecret"
            )
            self.assertIsNotNone(path)
            self.assertNotIn("topsecret", path.read_text(encoding="ascii"))
            preview = crash_service.preview_pending()
            self.assertEqual(preview["report_count"], 1)
            self.assertFalse(preview["automatic_upload"])
            exported = crash_service.export_pending().read_text(encoding="utf-8")
            self.assertNotIn("topsecret", exported)
            self.assertNotIn("203.0.113.9", exported)
            self.assertIn("automatic_upload", exported)

    def test_safe_report_excludes_server_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder, "APPDATA": folder}
        ):
            config = TunnelConfig(
                "private-id", "Secret server", "vless", "secret.example.com", 443,
                "vless://very-secret", {"uuid": UUID, "password": "hidden"},
            )
            report = diagnostics_service.build_report(
                [config], {"score": 80, "standby": "Secret server"}
            )
            text = report.read_text(encoding="utf-8")
            self.assertNotIn("secret.example.com", text)
            self.assertNotIn("very-secret", text)
            self.assertNotIn("hidden", text)
            self.assertNotIn("Secret server", text)
            self.assertIn('"score": 80', text)


class DnsServiceTests(unittest.TestCase):
    @patch("app.services.dns_service._run")
    def test_doh_policy_requires_no_udp_fallback(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = (
            "Template: https://cloudflare-dns.com/dns-query\nUDP fallback: no"
        )
        run.return_value.stderr = ""
        result = dns_service.verify_doh_no_downgrade(
            "1.1.1.1", "https://cloudflare-dns.com/dns-query"
        )
        self.assertTrue(result["configured"])
        self.assertTrue(result["no_downgrade"])

    def test_dns_backup_is_protected_and_round_trips(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            state = {"adapter": "Wi-Fi", "mode": "static",
                     "servers": ["1.1.1.1", "1.0.0.1"]}
            dns_service._write_backup(state)
            raw = dns_service._state_file().read_text(encoding="ascii")
            self.assertNotIn("Wi-Fi", raw)
            self.assertNotIn("1.1.1.1", raw)
            self.assertEqual(dns_service._read_backup(), state)

    @patch("app.services.dns_service._powershell")
    def test_adapter_guid_is_handled_as_a_string(self, powershell):
        powershell.return_value.returncode = 0
        powershell.return_value.stdout = '{"adapter":"Wi-Fi","mode":"automatic","servers":[]}'
        powershell.return_value.stderr = ""
        state = dns_service._read_current_state("Wi-Fi")
        script = powershell.call_args.args[0]
        self.assertEqual(state["adapter"], "Wi-Fi")
        self.assertIn("$guid=[string]$adapter.InterfaceGuid", script)
        self.assertNotIn("ToString('B')", script)

    def test_privileged_helper_rejects_unknown_or_unsafe_requests(self):
        with self.assertRaises(ValueError):
            privileged_helper._validate_request({
                "version": 1, "nonce": "a" * 32, "operation": "command",
                "adapter": "Wi-Fi",
            })
        with self.assertRaises(OSError):
            privileged_helper._validate_request({
                "version": 1, "nonce": "a" * 32, "operation": "set_dns",
                "adapter": "Wi-Fi", "servers": ["not-an-ip"], "doh_url": "",
            })

    def test_privileged_helper_accepts_only_valid_dns_schema(self):
        privileged_helper._validate_request({
            "version": 1, "nonce": "a" * 32, "operation": "set_dns",
            "adapter": "Wi-Fi", "servers": ["1.1.1.1", "1.0.0.1"],
            "doh_url": "https://cloudflare-dns.com/dns-query",
        })

    def test_privileged_helper_accepts_bounded_dns_tournament(self):
        privileged_helper._validate_request({
            "version": 1, "nonce": "a" * 32, "operation": "select_dns",
            "adapter": "Wi-Fi", "domains": ["discord.com", "gateway.discord.gg"],
            "candidates": [{
                "name": "Test DNS", "servers": ["1.1.1.1", "1.0.0.1"],
                "doh_url": "https://cloudflare-dns.com/dns-query",
            }],
        })
        with self.assertRaises(ValueError):
            privileged_helper._validate_request({
                "version": 1, "nonce": "a" * 32, "operation": "select_dns",
                "adapter": "Wi-Fi", "domains": ["localhost"],
                "candidates": [{"name": "Unsafe", "servers": ["1.1.1.1"]}],
            })

    def test_emergency_reset_schema_is_fixed_and_rejects_extra_fields(self):
        privileged_helper._validate_request({
            "version": 1, "nonce": "a" * 32,
            "operation": "emergency_reset", "adapter": "",
        })
        with self.assertRaisesRegex(ValueError, "فیلد ناشناخته"):
            privileged_helper._validate_request({
                "version": 1, "nonce": "a" * 32,
                "operation": "emergency_reset", "adapter": "",
                "command": "Remove-Everything",
            })

    def test_game_preflight_blocks_captive_portal_before_mutation(self):
        result = connectivity_service.evaluate_game_preflight(
            {"online": False, "captive": True}, True, "Wi-Fi"
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "captive")

    def test_game_preflight_accepts_conservative_tcp_fallback(self):
        result = connectivity_service.evaluate_game_preflight(
            {"online": False, "captive": False}, True, "Ethernet"
        )
        self.assertTrue(result["ready"])
        self.assertIn("جایگزین", result["message"])

    def test_game_preflight_blocks_missing_adapter(self):
        result = connectivity_service.evaluate_game_preflight(
            {"online": True, "captive": False}, True, ""
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "no-adapter")

    def test_recovery_receipt_is_encrypted_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            recovery_service.record("dns-change", "success", "network changed")
            recovery_service.record("dns-restore", "success")
            raw = recovery_service._path().read_text(encoding="ascii")
            self.assertNotIn("network changed", raw)
            receipt = recovery_service.receipt()
            self.assertEqual(receipt["count"], 2)
            self.assertFalse(receipt["pending_dns"])

    def test_warp_recovery_intent_is_encrypted_and_clearable(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            self.assertTrue(recovery_service.set_warp_intent(
                "unknown-client-mode", "MASQUE", "warp+doh"
            ))
            raw = recovery_service._warp_path().read_text(encoding="ascii")
            self.assertNotIn("warp+doh", raw)
            intent = recovery_service.warp_intent()
            self.assertEqual(intent["expected_mode"], "warp+doh")
            self.assertEqual(intent["original_mode"], "")
            self.assertTrue(recovery_service.receipt()["pending_warp"])
            recovery_service.clear_warp_intent()
            self.assertFalse(recovery_service.receipt()["pending_warp"])

    def test_qos_recovery_receipt_tracks_unfinished_change(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}
        ):
            recovery_service.record("qos-change", "success")
            self.assertTrue(recovery_service.receipt()["pending_qos"])
            recovery_service.record("qos-restore", "success")
            self.assertFalse(recovery_service.receipt()["pending_qos"])


class StorageTests(unittest.TestCase):
    def test_secrets_are_not_plaintext_and_warp_is_replaced(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"APPDATA": folder, "LOCALAPPDATA": folder}):
            first = TunnelConfig("1", "Cloudflare WARP (رایگان)", "wireguard", "edge", 2408,
                                 "secret-link", {"private_key": "first"}, "warp")
            second = TunnelConfig("2", "Cloudflare WARP (رایگان)", "wireguard", "edge", 2408,
                                  "", {"private_key": "second"}, "warp")
            configs = tunnel_storage_service.add_config([], first)
            configs = tunnel_storage_service.add_config(configs, second)
            self.assertEqual(len(configs), 1)
            raw = tunnel_storage_service._configs_file().read_text(encoding="utf-8")
            self.assertNotIn("second", raw)
            self.assertEqual(tunnel_storage_service.load_configs()[0].id, "2")


class WarpTests(unittest.TestCase):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "config": {
                    "client_id": base64.b64encode(bytes([7, 8, 9])).decode(),
                    "interface": {"addresses": {"v4": "172.16.0.2", "v6": "2606::2"}},
                    "peers": [{"public_key": "peer", "endpoint": {"host": "edge.example:2408"}}],
                }
            }).encode()

    @patch("app.services.warp_service._generate_wg_keypair", return_value=("private", "public"))
    @patch("app.services.warp_service.urllib.request.urlopen", return_value=_Response())
    def test_client_id_becomes_reserved_bytes(self, urlopen, keys):
        item = warp_service.register_warp_account()
        self.assertEqual(item.extra["reserved"], [7, 8, 9])
        self.assertEqual(item.extra["client_ipv4"], "172.16.0.2/32")
        self.assertEqual(item.source, "warp")

    def test_official_wireguard_fallback_ports_are_available(self):
        self.assertEqual(warp_service.WIREGUARD_PORTS, (2408, 500, 1701, 4500))

    @patch("app.services.official_warp_service._run_cli")
    @patch("app.services.official_warp_service.inspect")
    def test_official_warp_cancel_restores_before_returning(self, inspect, run_cli):
        inspect.return_value = official_warp_service.OfficialWarpStatus(
            installed=True, cli_path=Path("warp-cli.exe"), service_running=True,
            signature_valid=True, mode="warp", protocol="WireGuard",
        )
        run_cli.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = official_warp_service.connect_best(
            modes=("warp+doh",), protocols=("MASQUE",), cancelled=lambda: True,
        )
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["active"])
        commands = [call.args[1] for call in run_cli.call_args_list]
        self.assertIn(["disconnect"], commands)
        self.assertIn(["mode", "warp"], commands)

    @patch("app.services.official_warp_service.urllib.request.urlopen")
    def test_official_trace_requires_warp_on(self, urlopen):
        response = self._Response()
        response.read = lambda *_: b"fl=1\nwarp=on\nip=203.0.113.1\n"
        urlopen.return_value = response
        self.assertTrue(official_warp_service.trace_says_warp_on())

    @patch("app.services.official_warp_service.urllib.request.urlopen")
    def test_official_trace_rejects_ordinary_cloudflare_response(self, urlopen):
        response = self._Response()
        response.read = lambda *_: b"fl=1\nwarp=off\nip=203.0.113.1\n"
        urlopen.return_value = response
        self.assertFalse(official_warp_service.trace_says_warp_on())

    @patch("app.services.official_warp_service.time.sleep", return_value=None)
    @patch("app.services.official_warp_service.trace_says_warp_on")
    @patch("app.services.official_warp_service._cli_output", return_value="Status update: Connected")
    @patch("app.services.official_warp_service._run_cli")
    @patch("app.services.official_warp_service.inspect")
    def test_official_bridge_falls_back_to_wireguard(
        self, inspect, run_cli, _cli_output, trace, _sleep,
    ):
        inspect.return_value = official_warp_service.OfficialWarpStatus(
            installed=True, cli_path=Path("warp-cli.exe"), service_running=True,
            signature_valid=True,
        )
        run_cli.return_value = MagicMock(returncode=0, stdout="", stderr="")
        trace.side_effect = [False] * 5 + [True]
        result = official_warp_service.connect_best(modes=("warp",))
        self.assertTrue(result["ok"])
        self.assertEqual(result["protocol"], "WireGuard")
        commands = [call.args[1] for call in run_cli.call_args_list]
        self.assertIn(["tunnel", "protocol", "set", "MASQUE"], commands)
        self.assertIn(["tunnel", "protocol", "set", "WireGuard"], commands)

    @patch("app.services.official_warp_service.time.sleep", return_value=None)
    @patch("app.services.official_warp_service.trace_says_warp_on", return_value=False)
    @patch(
        "app.services.official_warp_service._cli_output",
        return_value="Status update: Connecting\nReason: Performing happy eyeballs to 162.159.198.2:443",
    )
    @patch("app.services.official_warp_service._run_cli")
    @patch("app.services.official_warp_service.inspect")
    def test_official_bridge_explains_blocked_cloudflare_path(
        self, inspect, run_cli, _cli_output, _trace, _sleep,
    ):
        inspect.return_value = official_warp_service.OfficialWarpStatus(
            installed=True, cli_path=Path("warp-cli.exe"), service_running=True,
            signature_valid=True, mode="warp", protocol="WireGuard",
        )
        run_cli.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = official_warp_service.connect_best(modes=("warp",), protocols=("MASQUE",))
        self.assertFalse(result["ok"])
        self.assertIn("نصب Cloudflare سالم است", result["error"])
        self.assertIn("تنظیم قبلی برگردانده شد", result["error"])

    @patch("app.services.official_warp_service.time.sleep", return_value=None)
    @patch("app.services.official_warp_service.trace_says_warp_on", return_value=False)
    @patch("app.services.official_warp_service._cli_output", return_value="Status: Connecting")
    @patch("app.services.official_warp_service._run_cli")
    @patch("app.services.official_warp_service.inspect")
    def test_official_bridge_respects_attempt_budget(
        self, inspect, run_cli, _cli_output, _trace, _sleep,
    ):
        inspect.return_value = official_warp_service.OfficialWarpStatus(
            installed=True, cli_path=Path("warp-cli.exe"), service_running=True,
            signature_valid=True,
        )
        run_cli.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = official_warp_service.connect_best(
            modes=("warp", "warp+doh"), max_attempts=1, verify_attempts=1,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 1)
        connects = [call for call in run_cli.call_args_list if call.args[1] == ["connect"]]
        self.assertEqual(len(connects), 1)

    @patch("app.services.official_warp_service._run_cli")
    @patch("app.services.official_warp_service.inspect")
    def test_bridge_never_disconnects_user_owned_warp(self, inspect, run_cli):
        inspect.return_value = official_warp_service.OfficialWarpStatus(
            installed=True, cli_path=Path("warp-cli.exe"), trace_active=True, connected=True,
            signature_valid=True,
        )
        result = official_warp_service.disconnect_if_started(False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["active"])
        run_cli.assert_not_called()

    def test_all_six_official_modes_are_declared(self):
        self.assertEqual(set(official_warp_service.MODE_LABELS), {
            "doh", "dot", "warp", "warp+doh", "warp+dot", "tunnel_only",
        })


class UpdateTests(unittest.TestCase):
    def _signed_manifest(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        document = {
            "version": "1.1.0",
            "channel": "stable",
            "url": "https://updates.example.com/LAGSHIFT-1.1.0-Setup.exe",
            "sha256": "a" * 64,
            "size": 123456,
            "notes": "Security update",
        }
        document["signature"] = base64.b64encode(
            private.sign(update_service._canonical_payload(document))
        ).decode()
        return document, base64.b64encode(public).decode()

    def test_signed_update_manifest_is_accepted(self):
        document, public_key = self._signed_manifest()
        verified = update_service.verify_manifest(document, public_key)
        self.assertEqual(verified["version"], "1.1.0")

    def test_published_update_manifests_match_embedded_trust_key(self):
        root = Path(__file__).resolve().parents[1]
        for channel in ("stable", "beta"):
            document = json.loads(
                (root / f"update-manifest-{channel}.json").read_text(encoding="utf-8")
            )
            verified = update_service.verify_manifest(
                document, app_info.UPDATE_PUBLIC_KEY_B64, channel
            )
            # During packaging, the already-published manifest may still point
            # at the previous release. It must never point at a future version;
            # the final release gate replaces it after the installer exists.
            self.assertLessEqual(
                update_service._version_tuple(verified["version"]),
                update_service._version_tuple(app_info.APP_VERSION),
            )
            self.assertEqual(verified["channel"], channel)
            self.assertIn(
                f'/releases/download/v{verified["version"]}/', verified["url"]
            )

    def test_tampered_update_manifest_is_rejected(self):
        document, public_key = self._signed_manifest()
        document["size"] += 1
        with self.assertRaisesRegex(ValueError, "امضای دیجیتال"):
            update_service.verify_manifest(document, public_key)

    def test_update_urls_must_be_public_https(self):
        for url in ("http://example.com/file.exe", "https://127.0.0.1/file.exe"):
            with self.assertRaises(ValueError):
                update_service._validate_https_url(url)

    def test_unconfigured_updater_never_connects(self):
        result = update_service.check_for_update("", "")
        self.assertFalse(result.configured)
        self.assertFalse(result.available)

    def test_update_channels_are_isolated(self):
        document, public_key = self._signed_manifest()
        with self.assertRaisesRegex(ValueError, "کانال"):
            update_service.verify_manifest(document, public_key, channel="beta")
        result = update_service.check_for_update(
            "https://updates.example.com/manifest.json", public_key,
            channel="nightly",
        )
        self.assertFalse(result.configured)

    def test_verified_update_resumes_from_bounded_partial_file(self):
        payload = b"abcdef"
        manifest = {
            "version": "1.1.0", "url": "https://updates.example.com/setup.exe",
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        }

        class Response:
            status = 206
            headers = {"Content-Range": "bytes 3-5/6"}
            def __init__(self):
                self._chunks = [b"def", b""]
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, _size):
                return self._chunks.pop(0)

        opener = MagicMock()
        opener.open.return_value = Response()
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.services.update_service._opener", return_value=opener
        ):
            destination = Path(folder)
            (destination / "LAGSHIFT-1.1.0-Setup.part").write_bytes(b"abc")
            result = update_service.download_verified_installer(manifest, destination)
            self.assertEqual(result.read_bytes(), payload)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header("Range"), "bytes=3-")

    def test_verified_existing_installer_is_reused_without_network(self):
        payload = b"already-downloaded"
        manifest = {
            "version": "1.1.0", "url": "https://updates.example.com/setup.exe",
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.services.update_service._opener"
        ) as opener:
            destination = Path(folder)
            target = destination / "LAGSHIFT-1.1.0-Setup.exe"
            target.write_bytes(payload)
            progress = MagicMock()
            result = update_service.download_verified_installer(
                manifest, destination, progress=progress
            )
            self.assertEqual(result, target)
            opener.assert_not_called()
            progress.assert_called_with(len(payload), len(payload))

    def test_user_cancel_keeps_bounded_partial_download(self):
        payload = b"abcdef"
        manifest = {
            "version": "1.1.0", "url": "https://updates.example.com/setup.exe",
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        }

        class Response:
            status = 200
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, _size):
                return payload

        opener = MagicMock()
        opener.open.return_value = Response()
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.services.update_service._opener", return_value=opener
        ):
            destination = Path(folder)
            with self.assertRaises(update_service.UpdateDownloadCancelled):
                update_service.download_verified_installer(
                    manifest, destination, cancelled=lambda: True
                )
            self.assertTrue(
                (destination / "LAGSHIFT-1.1.0-Setup.part").exists()
            )

    @patch("app.services.update_service.subprocess.Popen")
    @patch("app.services.update_service.has_valid_authenticode", return_value=False)
    @patch(
        "app.services.update_service.verify_downloaded_installer",
        return_value=(True, "ok"),
    )
    def test_unsigned_installer_requires_explicit_consent(
        self, _verify, _authenticode, popen
    ):
        path = Path("LAGSHIFT-1.1.0-Setup.exe")
        manifest = {"version": "1.1.0"}
        ok, _message = update_service.launch_verified_installer(path, manifest)
        self.assertFalse(ok)
        popen.assert_not_called()
        ok, _message = update_service.launch_verified_installer(
            path, manifest, allow_unsigned=True
        )
        self.assertTrue(ok)
        popen.assert_called_once()


class AppProfileCatalogTests(unittest.TestCase):
    def _signed_catalog(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        document = {
            "version": 1,
            "revision": "test-1",
            "profiles": [{
                "id": "discord",
                "login_domains": ["discord.com"],
                "download_domains": ["cdn.discordapp.com"],
                "service_domains": ["gateway.discord.gg"],
                "process_names": ["Discord.exe"],
                "registry_names": ["Discord"],
            }],
        }
        document["signature"] = base64.b64encode(
            private.sign(app_profile_catalog_service._canonical(document))
        ).decode()
        return document, base64.b64encode(public).decode()

    def test_signed_profile_catalog_updates_only_known_profiles(self):
        document, public_key = self._signed_catalog()
        verified = app_profile_catalog_service.verify_catalog(document, public_key)
        self.assertEqual(verified["profiles"][0]["id"], "discord")

    def test_tampered_profile_catalog_fails_closed(self):
        document, public_key = self._signed_catalog()
        document["profiles"][0]["login_domains"] = ["evil.example"]
        with self.assertRaisesRegex(ValueError, "امضای"):
            app_profile_catalog_service.verify_catalog(document, public_key)

    def test_unconfigured_profile_catalog_keeps_bundled_profiles(self):
        self.assertEqual(
            app_profile_catalog_service.load_profiles(""), DEFAULT_APP_ACCESS_PROFILES
        )
        self.assertFalse(app_profile_catalog_service.refresh("", ""))


class IntegrityCatalogTests(unittest.TestCase):
    def test_integrity_catalog_detects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            critical = root / "LAGSHIFT.exe"
            critical.write_bytes(b"trusted-build")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({
                "schema": 1,
                "algorithm": "SHA-256",
                "entries": [{
                    "path": "LAGSHIFT.exe",
                    "size": critical.stat().st_size,
                    "sha256": hashlib.sha256(critical.read_bytes()).hexdigest(),
                }],
            }), encoding="utf-8")
            good = integrity_service.verify_catalog(
                root=root, catalog_path=catalog, full=True
            )
            self.assertTrue(good["healthy"])
            critical.write_bytes(b"tampered")
            bad = integrity_service.verify_catalog(
                root=root, catalog_path=catalog, full=True
            )
            self.assertFalse(bad["healthy"])
            self.assertIn("LAGSHIFT.exe", bad["failures"])

    def test_integrity_catalog_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({
                "schema": 1,
                "algorithm": "SHA-256",
                "entries": [{"path": "../outside", "size": 0, "sha256": "0" * 64}],
            }), encoding="utf-8")
            result = integrity_service.verify_catalog(
                root=root, catalog_path=catalog, full=True
            )
            self.assertFalse(result["healthy"])


if __name__ == "__main__":
    unittest.main()
