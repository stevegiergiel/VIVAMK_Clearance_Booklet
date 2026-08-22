import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class DynamicDailyMonitorRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = importlib.import_module("run_daily_monitor_with_petals_paws")
        self.monitor = self.wrapper.monitor
        self.original = list(self.monitor.SALE_CONFIGS)
        self.original_discovered = list(self.wrapper._DISCOVERED)
        self.addCleanup(lambda: self.monitor.SALE_CONFIGS.__setitem__(slice(None), self.original))
        self.addCleanup(lambda: setattr(self.wrapper, "_DISCOVERED", self.original_discovered))

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

    def test_rebuild_iframe_only_skips_booklet(self):
        self.wrapper._DISCOVERED = [{
            "filename": "new_sale.json",
            "display_name": "New Sale",
            "iframe_path": "new-sale",
            "generate_iframe": True,
            "generate_print": False,
        }]
        commands = []
        original_run = self.monitor.run
        self.monitor.run = lambda cmd, **kwargs: (commands.append(cmd) or SimpleNamespace(stdout="", stderr=""))
        self.addCleanup(lambda: setattr(self.monitor, "run", original_run))

        self.wrapper.rebuild_with_output_policy(
            Path("configs/new_sale.json"), "new-sale", Path("state.json"), []
        )

        rendered = [" ".join(cmd) for cmd in commands]
        self.assertEqual(len(rendered), 1)
        self.assertIn("vivamk_clearance_iframe.py", rendered[0])
        self.assertNotIn("vivamk_clearance_booklet.py", rendered[0])

    def test_rebuild_print_only_skips_iframe(self):
        self.wrapper._DISCOVERED = [{
            "filename": "print_sale.json",
            "display_name": "Print Sale",
            "iframe_path": "print-sale",
            "generate_iframe": False,
            "generate_print": True,
        }]
        commands = []
        original_run = self.monitor.run
        self.monitor.run = lambda cmd, **kwargs: (commands.append(cmd) or SimpleNamespace(stdout="", stderr=""))
        self.addCleanup(lambda: setattr(self.monitor, "run", original_run))

        self.wrapper.rebuild_with_output_policy(
            Path("configs/print_sale.json"), "print-sale", Path("state.json"), []
        )

        rendered = [" ".join(cmd) for cmd in commands]
        self.assertEqual(len(rendered), 1)
        self.assertIn("vivamk_clearance_booklet.py", rendered[0])
        self.assertNotIn("vivamk_clearance_iframe.py", rendered[0])

    def test_iframe_publish_paths_respect_manifest_policy(self):
        self.wrapper._DISCOVERED = [
            {"iframe_path": "alpha", "generate_iframe": True},
            {"iframe_path": "beta", "generate_iframe": False},
        ]
        self.assertEqual(self.wrapper._iframe_enabled_paths(["alpha", "beta"]), ["alpha"])

    def test_heartbeat_reprint_wording_respects_print_policy(self):
        self.wrapper._DISCOVERED = [{
            "display_name": "Iframe Only",
            "generate_iframe": True,
            "generate_print": False,
        }]
        body = (
            "CATALOGUE STATUS CHANGES\n\n"
            "Iframe Only:\n"
            "  SOLD OUT: 123 - Example\n"
            "  Booklet and iframe regenerated successfully.\n"
            "  ACTION: reprint this catalogue.\n"
        )
        rewritten = self.wrapper._rewrite_output_messages(body)
        self.assertIn("Iframe regenerated successfully; print generation disabled by config.", rewritten)
        self.assertNotIn("ACTION: reprint this catalogue.", rewritten)

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
