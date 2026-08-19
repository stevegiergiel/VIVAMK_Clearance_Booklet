import importlib
import unittest


class PetalsPawsDailyMonitorRegistrationTests(unittest.TestCase):
    def test_registers_petals_paws_once_without_replacing_existing_catalogues(self):
        wrapper = importlib.import_module("run_daily_monitor_with_petals_paws")
        monitor = wrapper.monitor

        original = list(monitor.SALE_CONFIGS)
        self.addCleanup(lambda: monitor.SALE_CONFIGS.__setitem__(slice(None), original))

        before = set(monitor.SALE_CONFIGS)
        first = wrapper.configure_monitor()
        second = wrapper.configure_monitor()

        self.assertIn("petals_paws_specials.json", first)
        self.assertEqual(first.count("petals_paws_specials.json"), 1)
        self.assertEqual(second.count("petals_paws_specials.json"), 1)
        self.assertTrue(before.issubset(set(first)))

    def test_petals_paws_config_file_exists(self):
        from pathlib import Path

        self.assertTrue(Path("configs/petals_paws_specials.json").is_file())


if __name__ == "__main__":
    unittest.main()
