# VivaMK Generic Clearance System v2.00

Operational scripts:
- `vivamk_clearance_booklet.py`
- `vivamk_clearance_iframe.py`

Configs: Christmas, Mega Sale, Pets, Personalised, Winter Warmers.

Run, for example:
`python vivamk_clearance_booklet.py --config configs/pets.json`

Christmas remains PDF-authoritative. The other four configs scrape WAS/NOW from their category pages, calculate SAVE/% OFF, follow product pages for SKU/image/description, omit products with no usable image, generate an audit CSV/PDF, then make the A5 and A4 booklets.

All product/category links are forced onto `https://stevegiergiel.vivamknetwork.co.uk/`.

Decorative positions are separately parameterised as `header_left`, `header_right`, `footer_right`, and `back_cover`. The engine never stretches or automatically mirrors one side to make the other.

## Verification status

`python self_test.py` passes offline and verifies all five configs, required theme assets, Magento-style price parsing, personal VivaMK URL rewriting, and the Christmas source PDF parser.

The four live category URLs could not be fetched from the ChatGPT execution environment because that hostname was not resolvable there. Therefore the category scraper has been fixture-tested against Magento-style markup, but its first live scrape should be run on Steve's machine or GitHub Actions and the generated audit price PDF checked before publication.

## v2.02 cosmetic fixes

- Removed the last hard-coded Christmas footer URL from the shared renderer. Each booklet footer now derives from that sale's configured `order_url` / `sale.source_url`.
- Strengthened the Pets left/right/footer paw artwork and deepened the teal banner for better contrast.
- The larger/bolder SKU and QR logic remain unchanged.

## v2.03 supplied theme graphics

For the four non-Christmas booklets, the user-supplied sale graphic is now used exactly as the theme decoration:

- Mega Sale: supplied graphic top-right, same graphic footer-left.
- Pets: supplied graphic top-right, same graphic footer-left.
- Personalised: supplied graphic top-right, same graphic footer-left.
- Winter Warmers: supplied graphic top-right, same graphic footer-left.
- The opposite top/footer positions are intentionally blank.
- Graphics are scaled proportionally; they are not stretched, mirrored, or replaced with invented companion artwork.
- Christmas retains its separate approved holly treatment.

The generic renderer now supports independent `header_left`, `header_right`, `footer_left`, and `footer_right` config assets.

## v2.04 QR simplification

- Individual product QR codes have been removed from printed product cards.
- The main sale QR remains on the front cover.
- The clearer EzeGet QR remains on the back opportunity page.
- Product URLs are retained for iframe BUY ME links.
- The freed product-card space is used for a cleaner full-width pricing/SKU panel.
