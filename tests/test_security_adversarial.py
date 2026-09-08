import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import connection_state_service, integrity_service, privileged_helper, update_service


class PrivilegeBoundaryAdversarialTests(unittest.TestCase):
    def _dns_request(self):
        return {
            "version": 1, "nonce": "a" * 32, "operation": "set_dns",
            "adapter": "Wi-Fi", "servers": ["1.1.1.1"],
            "doh_url": "https://cloudflare-dns.com/dns-query",
        }

    def test_control_characters_never_cross_uac_adapter_boundary(self):
        document = self._dns_request()
        document["adapter"] = "Wi-Fi\nInjected"
        with self.assertRaises(ValueError):
            privileged_helper._validate_request(document)

    def test_doh_credentials_and_local_ip_are_rejected(self):
        for url in ("https://user:pass@example.com/dns-query", "https://127.0.0.1/dns-query"):
            document = self._dns_request()
            document["doh_url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                privileged_helper._validate_request(document)

    def test_candidate_cannot_smuggle_an_unknown_command(self):
        document = {
            "version": 1, "nonce": "a" * 32, "operation": "select_dns",
            "adapter": "Wi-Fi", "domains": ["example.com"],
            "candidates": [{"name": "safe", "servers": ["1.1.1.1"], "command": "calc"}],
        }
        with self.assertRaises(ValueError):
            privileged_helper._validate_request(document)


class CatalogAdversarialTests(unittest.TestCase):
    def test_duplicate_catalog_entry_cannot_fake_critical_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "LAGSHIFT.exe"
            target.write_bytes(b"safe")
            digest = hashlib.sha256(b"safe").hexdigest()
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({
                "schema": 1, "algorithm": "SHA-256",
                "entries": [
                    {"path": "LAGSHIFT.exe", "size": 4, "sha256": digest},
                    {"path": "LAGSHIFT.exe", "size": 4, "sha256": digest},
                ],
            }), encoding="utf-8")
            result = integrity_service.verify_catalog(root=root, catalog_path=catalog)
            self.assertFalse(result["healthy"])
            self.assertIn("catalog-duplicate-path", result["failures"])


class StateRaceAdversarialTests(unittest.TestCase):
    def test_invalid_scope_and_phase_fail_closed(self):
        state = connection_state_service.ConnectionState()
        with self.assertRaises(ValueError):
            state.begin("shell")
        generation = state.begin("dns")
        with self.assertRaises(ValueError):
            state.advance(generation, "execute")


class UpdateAdversarialTests(unittest.TestCase):
    def test_signed_manifest_still_rejects_channel_confusion(self):
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )).decode()
        document = {
            "version": "2.0.0", "channel": "beta", "url": "https://example.com/setup.exe",
            "sha256": "a" * 64, "size": 100,
        }
        document["signature"] = base64.b64encode(
            key.sign(update_service._canonical_payload(document))
        ).decode()
        with self.assertRaises(ValueError):
            update_service.verify_manifest(document, public, "stable")


if __name__ == "__main__":
    unittest.main()
