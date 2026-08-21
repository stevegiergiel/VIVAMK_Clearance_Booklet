import importlib
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse


class LiveBuyResolverTests(unittest.TestCase):
    def setUp(self):
        self.mod = importlib.import_module('vivamk_clearance_iframe')
        self.cfg = {
            'base_url': 'https://stevegiergiel.vivamknetwork.co.uk/',
            'order_url': 'https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html',
            'sale': {
                'id': 'personalised',
                'display_name': 'Personalised Items',
                'source_url': 'https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html',
            },
        }
        self.row = SimpleNamespace(sku='60345', product='Gonk Lidded Mug')

    def test_resolver_uses_explicit_local_index_and_shared_snapshot(self):
        href = self.mod.resolver_href(
            self.cfg,
            self.row,
            'https://stevegiergiel.vivamknetwork.co.uk/gonk-lidded-mug.html',
        )
        parsed = urlparse(href)
        self.assertEqual(parsed.path, '../resolve/index.html')
        qs = parse_qs(parsed.query)
        self.assertEqual(qs['sku'], ['60345'])
        self.assertEqual(qs['sale'], ['Personalised Items'])
        self.assertEqual(
            qs['target'],
            ['https://stevegiergiel.vivamknetwork.co.uk/gonk-lidded-mug.html'],
        )
        self.assertEqual(qs['stock'], [self.mod.SHARED_STOCK_SNAPSHOT_URL])

    def test_resolver_includes_sale_fallback(self):
        href = self.mod.resolver_href(self.cfg, self.row, '')
        qs = parse_qs(urlparse(href).query)
        self.assertEqual(
            qs['fallback'],
            ['https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html'],
        )

    def test_config_can_override_shared_snapshot_url(self):
        self.cfg['shared_stock_snapshot_url'] = 'https://example.github.io/data/stock.json'
        href = self.mod.resolver_href(self.cfg, self.row, '')
        qs = parse_qs(urlparse(href).query)
        self.assertEqual(qs['stock'], ['https://example.github.io/data/stock.json'])


if __name__ == '__main__':
    unittest.main()
