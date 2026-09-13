from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import (
    adapter_service,
    app_access_service,
    macos_dns_service,
    network_lab_service,
    update_service,
)


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class MacOSPlatformTests(unittest.TestCase):
    def test_macos_catalog_omits_windows_only_profiles(self):
        with patch.object(app_access_service.sys, "platform", "darwin"):
            ids = {profile.id for profile in app_access_service.available_profiles()}
        self.assertIn("discord", ids)
        self.assertIn("vscode", ids)
        self.assertIn("chatgpt", ids)
        self.assertNotIn("amd", ids)
        self.assertNotIn("nvidia", ids)
        self.assertNotIn("xbox", ids)
        self.assertNotIn("rockstar", ids)

    def test_macos_adapter_services_ignore_disabled_and_inactive(self):
        def fake_networksetup(*args):
            if args == ("-listallnetworkservices",):
                return completed("An asterisk denotes disabled services.\nWi-Fi\n*Old VPN\nEthernet\n")
            if args == ("-getinfo", "Wi-Fi"):
                return completed("IP address: 192.0.2.2\n")
            if args == ("-getdnsservers", "Wi-Fi"):
                return completed("1.1.1.1\n1.0.0.1\n")
            if args == ("-getinfo", "Ethernet"):
                return completed("IP address: none\n")
            raise AssertionError(args)

        with patch.object(adapter_service, "_networksetup", side_effect=fake_networksetup):
            rows = adapter_service._list_macos_services()
        self.assertEqual([row.name for row in rows], ["Wi-Fi"])
        self.assertEqual(rows[0].current_dns, ["1.1.1.1", "1.0.0.1"])

    def test_macos_dns_restores_exact_static_servers(self):
        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / "dns.secure"
            backup.write_text("placeholder", encoding="ascii")
            with (
                patch.object(macos_dns_service, "_backup_path", return_value=backup),
                patch.object(macos_dns_service, "_read_backup", return_value={
                    "service": "Wi-Fi", "mode": "static",
                    "servers": ["9.9.9.9", "149.112.112.112"],
                }),
                patch.object(macos_dns_service, "_run_admin", return_value=completed()) as run,
                patch.object(macos_dns_service.recovery_service, "safe_record"),
            ):
                self.assertTrue(macos_dns_service.restore_original_dns("Wi-Fi"))
            run.assert_called_once_with([
                "-setdnsservers", "Wi-Fi", "9.9.9.9", "149.112.112.112",
            ])
            self.assertFalse(backup.exists())

    def test_macos_dns_rejects_second_service_until_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / "dns.secure"
            backup.write_text("placeholder", encoding="ascii")
            with (
                patch.object(macos_dns_service, "_backup_path", return_value=backup),
                patch.object(macos_dns_service, "_read_backup", return_value={
                    "service": "Wi-Fi", "mode": "automatic", "servers": [],
                }),
                patch.object(macos_dns_service, "_run_admin") as run,
                patch.object(macos_dns_service.recovery_service, "safe_record"),
            ):
                self.assertFalse(
                    macos_dns_service.set_dns("Ethernet", "1.1.1.1", "1.0.0.1")
                )
            run.assert_not_called()
            self.assertIn("سرویس قبلی", macos_dns_service.get_last_error())

    def test_failed_macos_dns_change_removes_new_unused_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / "dns.secure"

            def write_backup(_state):
                backup.write_text("placeholder", encoding="ascii")

            with (
                patch.object(macos_dns_service, "_backup_path", return_value=backup),
                patch.object(macos_dns_service, "_read_state", return_value={
                    "service": "Wi-Fi", "mode": "automatic", "servers": [],
                }),
                patch.object(macos_dns_service, "_write_backup", side_effect=write_backup),
                patch.object(macos_dns_service, "_run_admin", return_value=completed(
                    stderr="cancelled", code=1,
                )),
                patch.object(macos_dns_service.recovery_service, "safe_record"),
            ):
                self.assertFalse(macos_dns_service.set_dns("Wi-Fi", "1.1.1.1"))
            self.assertFalse(backup.exists())

    def test_macos_dns_restores_automatic_mode_with_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / "dns.secure"
            backup.write_text("placeholder", encoding="ascii")
            with (
                patch.object(macos_dns_service, "_backup_path", return_value=backup),
                patch.object(macos_dns_service, "_read_backup", return_value={
                    "service": "USB 10/100/1000 LAN", "mode": "automatic", "servers": [],
                }),
                patch.object(macos_dns_service, "_run_admin", return_value=completed()) as run,
                patch.object(macos_dns_service.recovery_service, "safe_record"),
            ):
                self.assertTrue(macos_dns_service.restore_original_dns())
            run.assert_called_once_with([
                "-setdnsservers", "USB 10/100/1000 LAN", "Empty",
            ])

    def test_update_service_never_offers_windows_payload_on_macos(self):
        with patch.object(update_service.sys, "platform", "darwin"):
            result = update_service.check_for_update()
        self.assertFalse(result.configured)
        self.assertFalse(result.available)
        self.assertIn("macOS", result.message)

    def test_macos_default_gateway_parsing(self):
        output = "   route to: default\n destination: default\n    gateway: 192.0.2.1\n"
        with (
            patch.object(network_lab_service.sys, "platform", "darwin"),
            patch.object(network_lab_service.subprocess, "run", return_value=completed(output)),
        ):
            self.assertEqual(network_lab_service.default_gateway(), "192.0.2.1")


if __name__ == "__main__":
    unittest.main()
