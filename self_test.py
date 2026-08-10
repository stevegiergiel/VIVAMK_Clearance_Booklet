#!/usr/bin/env python3
"""Offline structural tests for the generic clearance system."""
import importlib.util
import sys
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
P = ROOT / 'vivamk_clearance_booklet.py'
spec = importlib.util.spec_from_file_location('clearance_engine_test', P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

# Personal-site URL safety.
assert m.personal_vivamk_url('https://www.vivamknetwork.co.uk/foo/bar.html?x=1') == \
       'https://stevegiergiel.vivamknetwork.co.uk/foo/bar.html?x=1'

# Magento-style price parsing.
soup = BeautifulSoup('''
<div class="price-box">
  <span class="old-price"><span class="price">£12.00</span></span>
  <span class="special-price"><span class="price">£7.20</span></span>
</div>''', 'html.parser')
was, now = m._category_price_pair(soup)
save, pct = m._derive_saving(was, now)
assert (was, now, save, pct) == ('£12.00', '£7.20', '£4.80', '40%')

# All configs and artwork resolve.
for cfg_path in sorted((ROOT / 'configs').glob('*.json')):
    cfg = m.load_config(cfg_path)
    m.apply_config(cfg)
    m.validate_required_assets()
    assert m.personal_vivamk_url(cfg['sale']['source_url']).startswith('https://stevegiergiel.vivamknetwork.co.uk/')

    sale_id = cfg['sale']['id']
    if sale_id == 'christmas':
        # Approved Christmas treatment deliberately uses both top corners
        # and its approved footer-right holly.
        assert m.PRO_FOLIAGE_LEFT_FILE != ''
        assert m.PRO_FOLIAGE_RIGHT_FILE != ''
        assert m.PRO_FOLIAGE_FOOTER_FILE != ''
    else:
        # Locked generic rule: supplied graphic top-right + footer-left;
        # opposite positions intentionally blank.
        assert m.PRO_FOLIAGE_LEFT_FILE == ''
        assert m.PRO_FOLIAGE_RIGHT_FILE != ''
        assert m.PRO_FOLIAGE_FOOTER_LEFT_FILE != ''
        assert m.PRO_FOLIAGE_FOOTER_FILE == ''

# Christmas authoritative PDF remains parseable.
rows = m.extract_sale_rows(ROOT / 'data' / 'Christmas_Sale_GBP1.pdf')
assert len(rows) > 60

print('SELF TEST PASSED')
print('Configs checked: 5')
print('Christmas price rows parsed:', len(rows))
