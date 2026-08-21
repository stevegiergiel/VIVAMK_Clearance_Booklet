#!/usr/bin/env python3
# VIVAMK CLEARANCE IFRAME ENGINE VERSION v2.19
import argparse, html, importlib.util, sys
from pathlib import Path
from urllib.parse import urlencode


def load_engine():
    p = Path(__file__).with_name('vivamk_clearance_booklet.py')
    spec = importlib.util.spec_from_file_location('booklet_engine', p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def esc(v):
    return html.escape(str(v or ''), quote=True)


def resolver_href(cfg, row, target_url):
    """Return a generic local resolver URL for a currently-active product.

    The resolver deliberately does not infer SOLD OUT from browser/network errors.
    It uses the supplier's live SKU search at click time, which avoids hard 404
    product links when an item disappears between scheduled snapshots.
    """
    sku = str(row.sku or '').strip()
    sale = cfg.get('sale', {})
    search_template = cfg.get('search_url_template', '')
    live_search = search_template.format(sku=sku) if search_template and sku else ''
    fallback = cfg.get('order_url') or sale.get('source_url') or cfg.get('base_url', '')
    params = urlencode({
        'sku': sku,
        'name': str(row.product or ''),
        'sale': str(sale.get('display_name') or ''),
        'target': str(target_url or ''),
        'search': str(live_search or ''),
        'fallback': str(fallback or ''),
    })
    # Explicit index.html works both from local file:// testing and GitHub Pages.
    return f'../resolve/index.html?{params}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True, type=Path)
    ap.add_argument('--state-file', type=Path, default=None)
    args = ap.parse_args()

    m = load_engine()
    cfg = m.load_config(args.config)
    m.apply_config(cfg)

    if m.DATA_SOURCE_MODE == 'category':
        rows = m.scrape_category_rows(m.CATEGORY_URL, int(cfg.get('max_category_pages', 30)))
        rows = m.enrich_category_rows(rows, Path('cache') / m.SALE_ID, delay=float(cfg.get('request_delay_seconds', .35)))
    else:
        pdf = args.config.resolve().parent.parent / cfg['data_source']['price_pdf']
        rows = m.extract_sale_rows(pdf)
        rows = m.enrich_rows(rows, Path('cache') / m.SALE_ID, delay=float(cfg.get('request_delay_seconds', .35)))

    rows = m.merge_monitor_state(rows, args.state_file)

    publishable_rows = []
    for r in rows:
        sold_out = getattr(r, 'stock_status', 'active') == 'sold_out'
        local_image_ok = bool(r.image_file and Path(r.image_file).exists())
        live_image_ok = bool((r.image_url or '').strip())
        if sold_out:
            if local_image_ok:
                publishable_rows.append(r)
        elif live_image_ok or local_image_ok:
            publishable_rows.append(r)

    cards = []
    for r in publishable_rows:
        url = m.personal_vivamk_url(r.product_url)
        sold_out = getattr(r, 'stock_status', 'active') == 'sold_out'
        local_image_ok = bool(r.image_file and Path(r.image_file).exists())

        if local_image_ok and (sold_out or not (r.image_url or '').strip()):
            import base64, mimetypes
            mime = mimetypes.guess_type(r.image_file)[0] or 'image/jpeg'
            img = 'data:' + mime + ';base64,' + base64.b64encode(Path(r.image_file).read_bytes()).decode('ascii')
        else:
            img = esc(r.image_url)
        photo = f'<img src="{img}" alt="{esc(r.product)}" loading="lazy">' if img else ''
        overlay = '<span class="soldout-ribbon">SOLD OUT</span>' if sold_out else ''
        if sold_out:
            action = '<span class="soldout-button">SOLD OUT</span>'
        else:
            resolve_url = resolver_href(cfg, r, url)
            action = f'<a href="{esc(resolve_url)}" target="_blank" rel="noopener">BUY ME</a>'
        klass = ' class="soldout-card"' if sold_out else ''
        cards.append(
            f'<article{klass}><div class="photo">' + photo +
            f'<b class="off">{esc(r.percent)}<small>OFF</small></b>{overlay}</div>'
            f'<div class="body"><b class="sku">SKU {esc(r.sku)}</b>'
            f'<h2>{esc(r.product)}</h2><p>{esc(r.description)}</p>'
            f'<div class="prices"><del>WAS {esc(r.was)}</del><em>SAVE {esc(r.saving)}</em>'
            f'<strong>NOW {esc(r.now)}</strong></div>'
            f'{action}</div></article>'
        )

    sale = cfg['sale']
    title = esc(sale['display_name'])
    cards_html = ''.join(cards)
    colours = cfg.get('theme', {}).get('colours', {})
    primary = colours.get('primary', '#064629')
    accent = colours.get('accent', '#E3B341')
    sale_col = colours.get('sale', '#B5121B')
    cream = colours.get('cream', '#FFF7E2')

    page = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
:root{--p:__P__;--a:__A__;--s:__S__;--c:__C__}*{box-sizing:border-box}body{font-family:Arial;margin:0;background:#f5f1e8;color:#222}header{background:var(--p);color:white;padding:24px;text-align:center;border-bottom:4px solid var(--a)}main{max-width:1150px;margin:auto;padding:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:12px}article{background:white;border-radius:12px;overflow:hidden;border:1px solid #ddd0b8}.photo{height:190px;position:relative;display:flex;align-items:center;justify-content:center}.photo img{width:100%;height:100%;object-fit:contain}.off{position:absolute;right:8px;top:8px;width:54px;height:54px;border-radius:50%;background:var(--s);color:#fff;display:grid;place-content:center;text-align:center}.off small{display:block;font-size:8px}.body{padding:11px}.sku{font-size:13px;font-weight:900}h2{font-size:17px;color:var(--p);margin:5px 0}p{font-size:13px;min-height:35px}.prices{background:#fff9ea;padding:8px;border-radius:8px;display:grid;grid-template-columns:1fr auto}.prices em{color:var(--p);font-style:normal;font-weight:800}.prices strong{grid-column:1/-1;color:var(--s);font-size:21px;margin-top:4px}a{display:block;background:var(--s);color:white;padding:10px;text-align:center;text-decoration:none;border-radius:8px;font-weight:bold;margin-top:8px}.soldout-card .photo img{opacity:.42;filter:grayscale(.2)}.soldout-ribbon{position:absolute;left:-18%;top:42%;width:136%;transform:rotate(-16deg);background:#b5121b;color:#fff;border:2px solid #fff;box-shadow:0 2px 7px #0006;text-align:center;font-weight:900;font-size:22px;letter-spacing:1.5px;padding:7px 0;z-index:5}.soldout-button{display:block;background:#555;color:#fff;padding:10px;text-align:center;border-radius:8px;font-weight:900;margin-top:8px;cursor:not-allowed}.soldout-card .off{opacity:.55}</style></head><body><header><h1>__TITLE__</h1><p>__SUBTITLE__</p></header><main>__CARDS__</main></body></html>'''
    page = (page.replace('__TITLE__', title)
                .replace('__SUBTITLE__', esc(cfg.get('header_subtitle', '')))
                .replace('__CARDS__', cards_html)
                .replace('__P__', primary)
                .replace('__A__', accent)
                .replace('__S__', sale_col)
                .replace('__C__', cream))

    out = Path('site') / cfg.get('iframe_path', m.SALE_ID)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(page, encoding='utf-8')
    print(out / 'index.html')


if __name__ == '__main__':
    main()
