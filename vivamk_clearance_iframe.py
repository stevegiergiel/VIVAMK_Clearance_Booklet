#!/usr/bin/env python3
# VIVAMK CLEARANCE IFRAME VERSION v1.00
# Updated: 2026-08-08 15:05 BST
# Changes: Initial GitHub Pages iframe publisher using the dedicated VivaMK Christmas clearance page.
# Changes: Excludes products without usable images and gives every product a direct BUY ME link.

from __future__ import annotations

import argparse
import html
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)


@dataclass
class Product:
    name: str
    url: str
    image: str
    now: str
    was: str = ""
    save: str = ""
    percent: str = ""
    sku: str = ""
    description: str = ""


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()


def money_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(re.sub(r"[^0-9.]", "", value or ""))
    except (InvalidOperation, ValueError):
        return None


def money(value: Decimal | None) -> str:
    return f"£{value:.2f}" if value is not None else ""


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return s


def soup_get(s: requests.Session, url: str) -> BeautifulSoup:
    r = s.get(url, timeout=40)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def first_text(node, selectors: list[str]) -> str:
    for selector in selectors:
        hit = node.select_one(selector)
        if hit:
            value = clean(hit.get_text(" ", strip=True))
            if value:
                return value
    return ""


def first_attr(node, choices: list[tuple[str, str]]) -> str:
    for selector, attr in choices:
        hit = node.select_one(selector)
        if hit and hit.get(attr):
            return clean(str(hit.get(attr)))
    return ""


def collect_listing_pages(s: requests.Session, start_url: str, max_pages: int) -> list[BeautifulSoup]:
    pages = []
    url = start_url
    seen = set()
    for _ in range(max_pages):
        if not url or url in seen:
            break
        seen.add(url)
        soup = soup_get(s, url)
        pages.append(soup)
        next_link = soup.select_one("a.action.next") or soup.select_one("a.next")
        url = urljoin(url, next_link.get("href")) if next_link and next_link.get("href") else ""
    return pages


def parse_listing_product(item, base_url: str) -> Product | None:
    link = item.select_one("a.product-item-link") or item.select_one(".product-item-name a")
    if not link or not link.get("href"):
        return None
    url = urljoin(base_url, link.get("href"))
    name = clean(link.get_text(" ", strip=True))
    if not name:
        return None

    image = first_attr(item, [
        ("img.product-image-photo", "src"),
        ("img.product-image-photo", "data-src"),
        ("img", "src"),
        ("img", "data-src"),
    ])
    image = urljoin(base_url, image) if image else ""

    old_price = first_text(item, [
        ".old-price .price",
        ".old.price .price",
        ".price-box .old-price",
    ])
    special = first_text(item, [
        ".special-price .price",
        ".special.price .price",
        ".price-final_price .price",
        ".price-box .price",
    ])
    now = special or old_price
    was = old_price if old_price and old_price != now else ""

    return Product(name=name, url=url, image=image, now=now, was=was)


def enrich_product(s: requests.Session, product: Product, base_url: str) -> Product:
    try:
        soup = soup_get(s, product.url)
    except Exception as exc:
        print(f"[WARN] {product.name}: product page failed: {exc}")
        return product

    product.sku = first_text(soup, [
        ".product.attribute.sku .value",
        ".product-info-stock-sku .value",
        "[itemprop='sku']",
    ])
    product.description = first_text(soup, [
        ".product.attribute.overview .value",
        ".product.attribute.description .value",
        "[itemprop='description']",
    ])

    if not product.image:
        image = first_attr(soup, [
            ('meta[property="og:image"]', "content"),
            ('meta[name="twitter:image"]', "content"),
            (".gallery-placeholder img", "src"),
            (".product.media img", "src"),
        ])
        if image:
            product.image = urljoin(base_url, image)

    if not product.was:
        old_price = first_text(soup, [".old-price .price", ".old.price .price"])
        if old_price:
            product.was = old_price
    if not product.now:
        product.now = first_text(soup, [".special-price .price", ".price-final_price .price", ".price-box .price"])

    was_n = money_decimal(product.was)
    now_n = money_decimal(product.now)
    if was_n is not None and now_n is not None and was_n > now_n:
        saving = was_n - now_n
        product.save = money(saving)
        product.percent = f"{int((saving / was_n * 100).quantize(Decimal('1')))}%"
    return product


def scrape_products(cfg: dict) -> list[Product]:
    s = session()
    clearance_url = cfg["clearance_url"]
    pages = collect_listing_pages(s, clearance_url, int(cfg.get("max_pages", 10)))
    products: list[Product] = []
    seen_urls = set()

    for page in pages:
        items = page.select("li.product-item") or page.select(".product-item")
        for item in items:
            p = parse_listing_product(item, clearance_url)
            if p and p.url not in seen_urls:
                seen_urls.add(p.url)
                products.append(p)

    delay = float(cfg.get("request_delay_seconds", 0.20))
    enriched = []
    for i, p in enumerate(products, 1):
        print(f"[{i:02d}/{len(products):02d}] {p.name}")
        p = enrich_product(s, p, clearance_url)
        if p.image:
            enriched.append(p)
        else:
            print(f"[SKIP] {p.name}: image not available")
        if delay:
            time.sleep(delay)
    return enriched


def esc(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def short(text: str, limit: int) -> str:
    text = clean(text)
    if not text:
        return "Christmas clearance special — limited stock while available."
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def render_card(p: Product, cfg: dict) -> str:
    was = f'<span class="was">WAS <b>{esc(p.was)}</b></span>' if p.was else ""
    save = f'<span class="save">SAVE {esc(p.save)}</span>' if p.save else ""
    badge = f'<div class="discount">{esc(p.percent)}<small>OFF</small></div>' if p.percent else ""
    sku = f'<div class="sku">SKU {esc(p.sku)}</div>' if p.sku else ""
    return f'''<article class="card">
<div class="photo"><img src="{esc(p.image)}" alt="{esc(p.name)}" loading="lazy">{badge}</div>
<div class="body">{sku}<h2>{esc(p.name)}</h2>
<p>{esc(short(p.description, int(cfg.get("description_max_chars", 180))))}</p>
<div class="pricebox">{was}{save}<strong>NOW {esc(p.now)}</strong></div>
<a class="buy" href="{esc(p.url)}" target="_blank" rel="noopener noreferrer">BUY ME</a>
</div></article>'''


def build_site(products: list[Product], cfg: dict) -> None:
    out = Path(cfg.get("site_output_folder", "site"))
    out.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(render_card(p, cfg) for p in products)
    phone = cfg.get("phone", "0771 304 5597")
    email = cfg.get("email", "steve@ezeget.com")
    opp_phone = cfg.get("opportunity_phone", "07429 21 21 40")
    clearance = cfg["clearance_url"]
    opportunity = cfg.get("opportunity_url", "https://ezeget.com")

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(cfg.get("page_title", "Steve & Jus Christmas Clearance Specials"))}</title>
<style>
:root{{--green:#064629;--red:#b5121b;--gold:#e3b341;--cream:#fff7e2;--ink:#202020}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:#f6f0e4}}
.hero{{background:linear-gradient(135deg,#043821,#0b6b3a);color:white;text-align:center;padding:28px 16px;border-bottom:6px solid var(--red)}}
.hero .tag{{display:inline-block;background:var(--gold);color:#173c28;padding:7px 16px;border-radius:999px;font-weight:900}}
.hero h1{{font-size:clamp(2rem,6vw,4rem);line-height:.96;margin:15px 0 8px;text-transform:uppercase}}
.hero p{{color:#ffe4a1;font-weight:800;margin:0}}
.intro{{width:min(1120px,calc(100% - 24px));margin:18px auto;background:#fff;border:2px solid var(--gold);border-radius:16px;padding:16px;box-shadow:0 7px 20px #0002;line-height:1.5}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}.actions a{{text-decoration:none;background:var(--green);color:white;padding:10px 14px;border-radius:999px;font-weight:900}}
.toolbar{{width:min(1120px,calc(100% - 24px));margin:0 auto 14px;display:flex;gap:10px;align-items:center}}.toolbar input{{width:100%;padding:12px 16px;border:2px solid #d5c7ac;border-radius:999px;font-size:16px}}.count{{white-space:nowrap;font-weight:900;color:var(--green)}}
.grid{{width:min(1200px,calc(100% - 18px));margin:auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:12px;padding-bottom:28px}}
.card{{background:white;border:1px solid #ddcfb4;border-radius:14px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 7px 18px #0002}}.photo{{position:relative;aspect-ratio:1.25/1;padding:8px;display:flex;align-items:center;justify-content:center}}.photo img{{width:100%;height:100%;object-fit:contain}}
.discount{{position:absolute;right:8px;top:8px;width:52px;height:52px;border-radius:50%;display:grid;place-content:center;text-align:center;background:var(--red);color:white;font-weight:900;font-size:16px;box-shadow:0 3px 8px #0004}}.discount small{{display:block;font-size:8px}}
.body{{padding:10px;display:flex;flex-direction:column;flex:1}}.sku{{font-size:11px;color:#666;font-weight:700}}h2{{font-size:17px;color:var(--green);line-height:1.12;margin:4px 0 6px}}.body p{{font-size:13px;line-height:1.35;margin:0 0 8px;flex:1}}
.pricebox{{background:#fff9ea;border-top:1px solid #eadfc9;padding:8px;border-radius:8px;display:grid;grid-template-columns:1fr auto;gap:3px 8px;align-items:end}}.was{{font-size:12px;color:#666}}.was b{{text-decoration:line-through}}.save{{font-size:12px;color:var(--green);font-weight:900}}.pricebox strong{{grid-column:1/-1;color:var(--red);font-size:23px;line-height:1}}
.buy{{margin-top:9px;text-align:center;text-decoration:none;background:var(--red);color:white;padding:11px;border-radius:9px;font-weight:900;letter-spacing:.04em}}
.opportunity{{background:var(--green);color:white;text-align:center;padding:26px 16px;border-top:6px solid var(--gold)}}.opportunity h2{{font-size:26px;margin:0 0 8px}}.opportunity a{{color:#ffe296;font-weight:900}}footer{{background:#042d1d;color:white;text-align:center;padding:15px;font-size:12px}}.hidden{{display:none!important}}
@media(max-width:560px){{.grid{{grid-template-columns:1fr 1fr;gap:8px}}h2{{font-size:14px}}.body p{{font-size:11px}}.pricebox strong{{font-size:20px}}}}@media(max-width:380px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<header class="hero"><div class="tag">STEVE &amp; JUS BRING YOU</div><h1>Christmas Clearance Specials</h1><p>Amazing prices — once they're gone, they're gone!</p></header>
<section class="intro"><strong>Steve and Jus bring you special Christmas offers at amazing prices.</strong> Once they are gone they are gone, so be quick to pick your favourites. If you are receiving this offer you are one of our top customers and we sincerely thank you for your valued custom through the years.<div class="actions"><a href="{esc(clearance)}" target="_blank" rel="noopener">ORDER ONLINE</a><a href="tel:{re.sub(r'[^0-9+]', '', phone)}">TEXT/CALL {esc(phone)}</a><a href="mailto:{esc(email)}">EMAIL {esc(email)}</a></div></section>
<div class="toolbar"><input id="q" type="search" placeholder="Search product or SKU…"><div class="count"><span id="count">{len(products)}</span> offers</div></div>
<main class="grid">{cards}</main>
<section class="opportunity"><h2>Know someone who would like their own business?</h2><p>We are always looking for distributors all across the United Kingdom.</p><p>Register at <a href="{esc(opportunity)}" target="_blank" rel="noopener">ezeget.com</a> or call Steve on <a href="tel:{re.sub(r'[^0-9+]', '', opp_phone)}">{esc(opp_phone)}</a> to discuss the opportunity.</p></section>
<footer>Clearance availability can change. Order promptly while stocks last.</footer>
<script>const q=document.getElementById('q'),cards=[...document.querySelectorAll('.card')],count=document.getElementById('count');q.addEventListener('input',()=>{{const s=q.value.trim().toLowerCase();let n=0;cards.forEach(c=>{{const ok=!s||c.textContent.toLowerCase().includes(s);c.classList.toggle('hidden',!ok);if(ok)n++}});count.textContent=n}});</script>
</body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the VivaMK Christmas clearance iframe catalogue")
    ap.add_argument("--config", type=Path, default=Path("iframe_config.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    products = scrape_products(cfg)
    if not products:
        raise RuntimeError("No products with usable images were found on the clearance page.")
    build_site(products, cfg)
    print(f"Generated {len(products)} products in {cfg.get('site_output_folder', 'site')}/index.html")


if __name__ == "__main__":
    main()
