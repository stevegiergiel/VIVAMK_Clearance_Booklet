from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import vivamk_daily_monitor as monitor


class DailyMonitorUnitTests(unittest.TestCase):
    def test_row_key_prefers_sku(self):
        row = SimpleNamespace(sku=" 13122 ", product_url="https://example/item", product="Dinosaur Cushion")
        self.assertEqual(monitor.row_key(row), "13122")

    def test_row_key_falls_back_to_product_url_then_name(self):
        with_url = SimpleNamespace(sku="", product_url="https://example/item", product="Example")
        name_only = SimpleNamespace(sku="", product_url="", product=" Example Product ")
        self.assertEqual(monitor.row_key(with_url), "https://example/item")
        self.assertEqual(monitor.row_key(name_only), "Example Product")

    def test_write_and_load_state_preserves_sold_out_metadata(self):
        products = {
            "13122": {
                "sku": "13122",
                "product": "Dinosaur Cushion - Brave",
                "status": "sold_out",
                "sold_out_since": "2026-08-15T12:59:01",
                "image_file": "monitor_cache/mega_sale/13122.jpg",
            }
        }
        with tempfile.TemporaryDirectory() as d:
            state_dir = Path(d)
            with patch.object(monitor, "STATE_DIR", state_dir):
                monitor.save_state("mega_sale", "Mega Sale Items", products)
                loaded = monitor.load_state("mega_sale")

        self.assertEqual(loaded, products)
        self.assertEqual(loaded["13122"]["status"], "sold_out")
        self.assertEqual(loaded["13122"]["sold_out_since"], "2026-08-15T12:59:01")

    def test_load_state_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(monitor, "STATE_DIR", Path(d)):
                self.assertIsNone(monitor.load_state("missing_sale"))

    def test_state_file_has_expected_envelope(self):
        products = {"10001": {"sku": "10001", "status": "active"}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            monitor.write_state_file(path, "sale", "Sale Name", products)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["sale_id"], "sale")
        self.assertEqual(data["display_name"], "Sale Name")
        self.assertEqual(data["products"], products)
        self.assertIn("checked_at", data)


if __name__ == "__main__":
    unittest.main()
