import importlib
import json
import tempfile
import unittest
from pathlib import Path


class DynamicDailyMonitorRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = importlib.import_module("run_daily_monitor_with_petals_paws")
        self.monitor = self.wrapper.monitor
        self.original = list(self.monitor.SALE_CONFIGS)
        self.addCleanup(lambda: self.monitor.SALE_CONFIGS.__setitem__(slice(None), self.original))

    def test_discovers_petals_paws_and_existing_catalogues_from_manifest(self):
        discovered = self.wrapper.discover_sale_configs()
        filenames = [item["filename"] for item in discovered]
        expected = {
            "christmas.json",
            "mega_sale.json",
            "pets.json",
            "petals_paws_specials.json",
            "personalised.json",
            "winter_warmers.json",
        }
        self.assertTrue(expected.issubset(set(filenames)))

    def test_existing_catalogues_are_explicitly_print_enabled(self):
        discovered = self.wrapper.discover_sale_configs()
        self.assertTrue(discovered)
        self.assertTrue(all(item["generate_print"] is True for item in discovered))

    def test_configure_monitor_uses_discovered_catalogues_not_legacy_registry(self):
        self.monitor.SALE_CONFIGS[:] = ["legacy_only.json"]
        configured = self.wrapper.configure_monitor()
        self.assertIn("petals_paws_specials.json", configured)
        self.assertNotIn("legacy_only.json", configured)

    def test_fallback_discovery_preserves_existing_print_behaviour(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "unrelated.json").write_text('{"hello":"world"}', encoding="utf-8")
            (root / "disabled.json").write_text(
                json.dumps({
                    "sale": {"id": "disabled", "display_name": "Disabled"},
                    "data_source": {"mode": "pdf", "price_pdf": "data/x.pdf"},
                    "monitor": {"enabled": False},
                }),
                encoding="utf-8",
            )
            (root / "valid.json").write_text(
                json.dumps({
                    "sale": {"id": "valid", "display_name": "Valid Sale"},
                    "data_source": {"mode": "pdf", "price_pdf": "data/valid.pdf"},
                    "iframe_path": "valid-sale",
                }),
                encoding="utf-8",
            )
            discovered = self.wrapper.discover_sale_configs(root)
            self.assertEqual([item["filename"] for item in discovered], ["valid.json"])
            self.assertTrue(discovered[0]["generate_print"])

    def test_manifest_new_catalogue_defaults_to_no_print(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "new_sale.json").write_text(
                json.dumps({
                    "sale": {
                        "id": "new_sale",
                        "display_name": "New Sale",
                        "source_url": "https://example.test/new-sale",
                    },
                    "data_source": {"mode": "category"},
                    "iframe_path": "new-sale",
                }),
                encoding="utf-8",
            )
            (root / "catalogue_manifest.json").write_text(
                json.dumps({
                    "defaults": {"generate_iframe": True, "generate_print": False},
                    "catalogues": [
                        {"config": "new_sale.json", "sale_id": "new_sale"}
                    ],
                }),
                encoding="utf-8",
            )
            discovered = self.wrapper.discover_sale_configs(root)
            self.assertEqual(len(discovered), 1)
            self.assertTrue(discovered[0]["generate_iframe"])
            self.assertFalse(discovered[0]["generate_print"])

    def test_heartbeat_summary_lists_outputs(self):
        self.wrapper._DISCOVERED = [
            {
                "filename": "a.json",
                "sale_id": "a",
                "display_name": "Alpha Sale",
                "mode": "pdf",
                "source": "data/a.pdf",
                "iframe_path": "alpha",
                "generate_iframe": True,
                "generate_print": True,
            },
            {
                "filename": "b.json",
                "sale_id": "b",
                "display_name": "Beta Sale",
                "mode": "category",
                "source": "https://example.test/sale",
                "iframe_path": "beta",
                "generate_iframe": True,
                "generate_print": False,
            },
        ]
        captured = {}
        original_sender = self.wrapper._ORIGINAL_SEND_EMAIL
        self.wrapper._ORIGINAL_SEND_EMAIL = lambda settings, subject, body: captured.update(
            subject=subject, body=body
        )
        self.addCleanup(lambda: setattr(self.wrapper, "_ORIGINAL_SEND_EMAIL", original_sender))

        self.wrapper.send_email_with_catalogue_summary({}, "subject", "heartbeat")
        self.assertIn("MONITORED CATALOGUES", captured["body"])
        self.assertIn("Alpha Sale [PDF]", captured["body"])
        self.assertIn("print=YES", captured["body"])
        self.assertIn("Beta Sale [CATEGORY]", captured["body"])
        self.assertIn("print=NO", captured["body"])

    def test_petals_paws_config_file_exists(self):
        self.assertTrue(Path("configs/petals_paws_specials.json").is_file())


if __name__ == "__main__":
    unittest.main()
