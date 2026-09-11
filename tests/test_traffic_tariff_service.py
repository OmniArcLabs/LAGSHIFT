import unittest
import json
import tempfile
import base64
from pathlib import Path
from unittest.mock import MagicMock

from app.services import traffic_tariff_service as tariff
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class _Response:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True


class TrafficTariffTests(unittest.TestCase):
    def test_sanitize_removes_query_fragment_and_rejects_credentials(self):
        self.assertEqual(
            tariff.sanitize_url("https://Example.com/file.zip?token=secret#part"),
            "https://example.com/file.zip",
        )
        with self.assertRaises(tariff.TariffAnalysisError):
            tariff.sanitize_url("https://user:secret@example.com/file")
        with self.assertRaises(tariff.TariffAnalysisError):
            tariff.sanitize_url("https://example.com:not-a-port/file")

    def test_history_does_not_retain_path_or_query(self):
        result = tariff.history_identity("https://cdn.example/file/private-name.zip?token=secret")
        self.assertEqual(result["host"], "cdn.example")
        self.assertEqual(result["extension"], ".zip")
        self.assertNotIn("private-name", str(result))
        self.assertNotIn("secret", str(result))

    def test_catalog_matches_exact_subdomain_and_ip_prefix(self):
        catalog = tariff.TariffCatalog.from_document({
            "version": 1,
            "domestic_domains": ["example.ir"],
            "domestic_networks": ["203.0.113.0/24"],
        })
        self.assertTrue(catalog.matches("cdn.example.ir", ["8.8.8.8"]))
        self.assertTrue(catalog.matches("elsewhere.test", ["203.0.113.7"]))
        self.assertFalse(catalog.matches("fakeexample.ir", ["8.8.8.8"]))

    def test_private_destination_is_rejected_before_request(self):
        opener = MagicMock()
        with self.assertRaises(tariff.TariffAnalysisError):
            tariff.analyze_url(
                "https://example.com/", resolver=lambda _host: ("127.0.0.1",), opener=opener
            )
        opener.open.assert_not_called()

    def test_redirect_target_is_resolved_and_private_target_blocked(self):
        opener = MagicMock()
        opener.open.return_value = _Response(302, {"Location": "http://localhost/admin"})
        with self.assertRaises(tariff.TariffAnalysisError):
            tariff.analyze_url(
                "https://example.com/", resolver=lambda host: (
                    "127.0.0.1" if host == "localhost" else "8.8.8.8",
                ), opener=opener,
            )
        self.assertEqual(opener.open.call_count, 1)

    def test_unlisted_ir_domain_remains_unknown(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200, {"Content-Length": "2048"})
        result = tariff.analyze_url(
            "https://example.ir/file", resolver=lambda _host: ("8.8.8.8",), opener=opener
        )
        self.assertEqual(result.classification, "unknown")
        self.assertEqual(result.content_length, 2048)

    def test_registered_chain_is_domestic_and_warp_lowers_confidence(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200)
        catalog = tariff.TariffCatalog.from_document({
            "version": 1, "revision": "official-1", "source_name": "Test",
            "domestic_domains": ["example.ir"], "domestic_networks": [],
        })
        result = tariff.analyze_url(
            "https://cdn.example.ir/file", catalog, warp_or_vpn_active=True,
            resolver=lambda _host: ("8.8.8.8",), opener=opener,
        )
        self.assertEqual(result.classification, "domestic")
        self.assertEqual(result.confidence, "محدود")
        self.assertIn("WARP", result.warning)

    def test_mixed_redirect_is_not_reported_as_fully_domestic(self):
        opener = MagicMock()
        opener.open.side_effect = [
            _Response(302, {"Location": "https://foreign.example/file"}),
            _Response(200),
        ]
        catalog = tariff.TariffCatalog.from_document({
            "version": 1, "domestic_domains": ["inside.ir"], "domestic_networks": [],
        })
        result = tariff.analyze_url(
            "https://inside.ir/start", catalog,
            resolver=lambda _host: ("8.8.8.8",), opener=opener,
        )
        self.assertEqual(result.classification, "mixed")
        self.assertEqual(len(result.steps), 2)

    def test_history_is_bounded_and_contains_no_url_secret(self):
        response = _Response(200)
        opener = MagicMock()
        opener.open.return_value = response
        result = tariff.analyze_url(
            "https://example.com/private/file.zip?token=secret",
            resolver=lambda _host: ("8.8.8.8",), opener=opener,
        )
        with tempfile.TemporaryDirectory() as folder, \
                unittest.mock.patch.object(tariff, "_history_path", return_value=Path(folder) / "h.json"):
            tariff.remember_result(result)
            raw = (Path(folder) / "h.json").read_text(encoding="utf-8")
            self.assertNotIn("private", raw)
            self.assertNotIn("secret", raw)
            self.assertEqual(tariff.load_history()[0]["host"], "example.com")

    def test_signed_catalog_rejects_tampering(self):
        private = Ed25519PrivateKey.generate()
        document = {
            "version": 1, "revision": "r1", "source_name": "official",
            "domestic_domains": ["example.ir"], "domestic_networks": [],
        }
        document["signature"] = base64.b64encode(
            private.sign(tariff._canonical_catalog(document))
        ).decode("ascii")
        public = base64.b64encode(private.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )).decode("ascii")
        self.assertTrue(tariff.verify_signed_catalog(document, public).matches("example.ir", []))
        document["domestic_domains"] = ["attacker.example"]
        with self.assertRaises(tariff.TariffAnalysisError):
            tariff.verify_signed_catalog(document, public)

    def test_modified_unsigned_bundled_catalog_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_text(json.dumps({
                "version": 1, "revision": "fake", "source_name": "fake",
                "domestic_domains": ["attacker.example"], "domestic_networks": [],
            }), encoding="utf-8")
            loaded = tariff.load_bundled_catalog(path)
            self.assertFalse(loaded.domestic_domains)
            self.assertFalse(loaded.matches("attacker.example", []))


if __name__ == "__main__":
    unittest.main()
