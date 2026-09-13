import unittest
import json
import tempfile
import base64
import ipaddress
from pathlib import Path
from unittest.mock import MagicMock

from app.services import traffic_tariff_service as tariff
from app.services import linkirani_service, operator_detection_service, settings_service
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
    @staticmethod
    def _json_opener(document):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(document).encode("utf-8")
        opener = MagicMock(return_value=response)
        return opener

    def test_operator_detection_discards_ip_and_maps_known_provider(self):
        opener = self._json_opener({
            "clientIp": "203.0.113.9", "asn": 44244,
            "asOrganization": "Mobile Communication Company of Iran",
            "country": "IR", "region": "Tehran",
        })
        hint = operator_detection_service.detect(opener=opener)
        self.assertEqual(hint.name, "همراه اول")
        self.assertEqual(hint.asn, "AS44244")
        self.assertNotIn("203.0.113.9", str(hint))
        request = opener.call_args.args[0]
        self.assertEqual(request.headers["Origin"], "https://speed.cloudflare.com")
        self.assertIn("LAGSHIFT", request.headers["User-agent"])

    def test_operator_auto_detection_is_skipped_behind_tunnel(self):
        opener = MagicMock()
        hint = operator_detection_service.detect(tunnel_active=True, opener=opener)
        self.assertEqual(hint.source, "tunnel-active")
        opener.assert_not_called()

    def test_external_traffic_lookups_are_opt_in_by_default(self):
        self.assertEqual(settings_service.DEFAULTS["traffic_operator_mode"], "manual")
        self.assertFalse(settings_service.DEFAULTS["traffic_linkirani_enabled"])

    def test_linkirani_sends_only_origin_without_path_or_token(self):
        opener = self._json_opener({
            "isRegistered": True, "isInIran": True, "ipCountryCode": "ir",
            "link": {"netloc": {"value": "cdn.example.ir"}},
        })
        evidence = linkirani_service.check(
            "https://cdn.example.ir/private/file.zip?token=secret", opener=opener
        )
        requested = opener.call_args.args[0].full_url
        self.assertTrue(evidence.available)
        self.assertNotIn("private", requested)
        self.assertNotIn("secret", requested)
        self.assertIn("cdn.example.ir", requested)

    def test_linkirani_registered_result_is_labeled_probable_not_official(self):
        base = tariff.TariffResult(
            requested_url="https://example.ir/", final_url="https://example.ir/",
            classification="unknown", title="نامشخص", confidence="نامشخص",
            reasons=("فهرست خالی است",),
        )
        evidence = linkirani_service.LinkIraniEvidence(
            available=True, registered=True, in_iran=True, host="example.ir"
        )
        merged = tariff.merge_external_evidence(base, evidence)
        self.assertEqual(merged.classification, "likely_domestic")
        self.assertEqual(merged.external_source, "LinkIrani")
        self.assertNotEqual(merged.classification, "domestic")

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

    def test_unlisted_ir_domain_on_foreign_allocation_is_probably_full_rate(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200, {"Content-Length": "2048"})
        result = tariff.analyze_url(
            "https://example.ir/file", resolver=lambda _host: ("8.8.8.8",), opener=opener
        )
        self.assertEqual(result.classification, "likely_full")
        self.assertEqual(result.content_length, 2048)

    def test_offline_iran_allocation_is_useful_without_linkirani(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200)
        locations = tariff.IranNetworkCatalog(
            revision="test",
            source_name="RIPE NCC test",
            networks=(ipaddress.ip_network("5.22.0.0/17"),),
        )
        result = tariff.analyze_url(
            "https://download.example/file.zip",
            iran_catalog=locations,
            resolver=lambda _host: ("5.22.1.10",),
            opener=opener,
        )
        self.assertEqual(result.classification, "likely_domestic")
        self.assertEqual(result.confidence, "پایین")
        self.assertFalse(result.external_checked)
        self.assertIn("RIPE NCC", result.reasons[0])

    def test_mixed_iran_and_foreign_addresses_remain_unknown(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200)
        locations = tariff.IranNetworkCatalog(
            networks=(ipaddress.ip_network("5.22.0.0/17"),),
        )
        result = tariff.analyze_url(
            "https://dual.example/file.zip",
            iran_catalog=locations,
            resolver=lambda _host: ("5.22.1.10", "8.8.8.8"),
            opener=opener,
        )
        self.assertEqual(result.classification, "unknown")

    def test_signed_query_is_used_but_never_exposed(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200)
        result = tariff.analyze_url(
            "https://example.com/file.zip?token=very-secret#fragment",
            resolver=lambda _host: ("8.8.8.8",), opener=opener,
        )
        requested = opener.open.call_args.args[0]
        self.assertIn("token=very-secret", requested.full_url)
        self.assertNotIn("very-secret", result.requested_url)
        self.assertNotIn("very-secret", result.final_url)
        self.assertNotIn("very-secret", str(result.to_dict()))

    def test_http_hop_is_reported_as_insecure(self):
        opener = MagicMock()
        opener.open.return_value = _Response(200)
        result = tariff.analyze_url(
            "http://example.com/file", resolver=lambda _host: ("8.8.8.8",), opener=opener
        )
        self.assertTrue(result.insecure_path)
        self.assertIn("HTTP", result.warning)

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

    def test_registered_final_download_host_outweighs_control_redirect(self):
        opener = MagicMock()
        opener.open.side_effect = [
            _Response(302, {"Location": "https://files.inside.ir/file"}),
            _Response(200, {"Content-Length": "4096"}),
        ]
        catalog = tariff.TariffCatalog.from_document({
            "version": 1, "domestic_domains": ["inside.ir"], "domestic_networks": [],
        })
        result = tariff.analyze_url(
            "https://landing.example/start", catalog,
            resolver=lambda _host: ("8.8.8.8",), opener=opener,
        )
        self.assertEqual(result.classification, "domestic")
        self.assertEqual(result.confidence, "متوسط")
        self.assertIn("سرور نهایی", result.title)

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

    def test_expired_signed_catalog_fails_closed(self):
        private = Ed25519PrivateKey.generate()
        document = {
            "version": 1, "revision": "expired", "source_name": "official",
            "expires_at": "2000-01-01T00:00:00Z",
            "domestic_domains": ["example.ir"], "domestic_networks": [],
        }
        document["signature"] = base64.b64encode(
            private.sign(tariff._canonical_catalog(document))
        ).decode("ascii")
        public = base64.b64encode(private.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )).decode("ascii")
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
