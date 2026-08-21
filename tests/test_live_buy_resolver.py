import importlib
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse


class LiveBuyResolverTests(unittest.TestCase):
    def setUp(self):
        self.mod = importlib.import_module('vivamk_clearance_iframe')
        self.cfg = {
            'base_url': 'https://stevegiergiel.vivamknetwork.co.uk/',
            'search_url_template': 'https://stevegiergiel.vivamknetwork.co.uk/catalogsearch/result/?q={sku}',
            'order_url': 'https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html',
            'sale': {
                'id': 'personalised',
                'display_name': 'Personalised Items',
                'source_url': 'https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html',
            },
        }
        self.row = SimpleNamespace(sku='60345', product='Gonk Lidded Mug')

    def test_resolver_uses_local_shared_page_and_live_sku_search(self):
        href = self.mod.resolver_href(
            self.cfg,
            self.row,
            'https://stevegiergiel.vivamknetwork.co.uk/gonk-lidded-mug.html',
        )
        parsed = urlparse(href)
        self.assertEqual(parsed.path, '../resolve/')
        qs = parse_qs(parsed.query)
        self.assertEqual(qs['sku'], ['60345'])
        self.assertEqual(qs['sale'], ['Personalised Items'])
        self.assertEqual(
            qs['search'],
            ['https://stevegiergiel.vivamknetwork.co.uk/catalogsearch/result/?q=60345'],
        )
        self.assertEqual(
            qs['target'],
            ['https://stevegiergiel.vivamknetwork.co.uk/gonk-lidded-mug.html'],
        )

    def test_resolver_includes_sale_fallback(self):
        href = self.mod.resolver_href(self.cfg, self.row, '')
        qs = parse_qs(urlparse(href).query)
        self.assertEqual(
            qs['fallback'],
            ['https://stevegiergiel.vivamknetwork.co.uk/clearance/persgiftssale.html'],
        )


if __name__ == '__main__':
    unittest.main()
