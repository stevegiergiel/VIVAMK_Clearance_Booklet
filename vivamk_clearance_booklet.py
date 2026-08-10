#!/usr/bin/env python3
# VIVAMK CLEARANCE BOOKLET ENGINE VERSION v2.04
# Updated: 2026-08-09 16:55 +0100
# Changes: Generic config-driven engine based on approved Christmas v1.11 visual baseline.
# Changes: Sale wording, URLs, filenames, professional left/right/footer decorations and colours are config parameters.
# Changes: Supports source PDF mode (Christmas) and direct Magento category scraping mode (other clearance sales).
# Changes: Generates audit CSV/PDF, A5 reading-order booklet and A4 pre-imposed booklet.
# Changes: Retains larger/bold SKU, sale QR, per-product QR and forced Steve personal VivaMK URLs.
# Changes: Card cosmetic pass - one clean OFF badge, roomier pricing panel, clearer WAS/NOW/SKU separation.
"""
VivaMK Config-Driven Clearance Booklet Generator
=============================================

Takes the clearance price-list PDF, extracts SKU/product/was/now/saving/%
rows, looks each SKU up on the Steve & Jus VivaMK web shop, follows the
product result, downloads the product image and description, and creates:

  1) christmas_clearance_a5.pdf
     - normal reading-order A5 brochure

  2) christmas_clearance_booklet_a4.pdf
     - A4 landscape, imposed 2-up for folding into an A5 booklet
     - print double-sided, flip on SHORT edge, then fold in half

Usage
-----
    python vivamk_christmas_booklet.py Christmas_Sale_GBP1.pdf

Optional:
    python vivamk_christmas_booklet.py Christmas_Sale_GBP1.pdf --out output
    python vivamk_christmas_booklet.py Christmas_Sale_GBP1.pdf --refresh
    python vivamk_christmas_booklet.py Christmas_Sale_GBP1.pdf --cards-per-page 4

Install dependencies:
    pip install requests beautifulsoup4 pymupdf reportlab pillow pypdf

The script deliberately caches web results/images so that a second run is much
faster and does not repeatedly request every product page.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import fitz  # PyMuPDF
import requests
import qrcode
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


DEFAULT_BASE_URL = "https://stevegiergiel.vivamknetwork.co.uk/"
BASE_URL = DEFAULT_BASE_URL
SEARCH_URL = BASE_URL + "catalogsearch/result/?q={sku}"

INTRO_TEXT = (
    "Steve and Jus bring you special Christmas Offers at amazing prices. "
    "Once they are gone they are gone, so be quick to pick your favourites. "
    "Order as usual or text your requirements for speed to "
    "<b>0771 304 5597</b>. If you are using a phone number that I may not "
    "recognise, please add your name and postal address so that I can be sure "
    "to deliver to the right address.<br/><br/>"
    "If you are receiving this leaflet you are one of our top customers and "
    "we thank you sincerely for your valued custom through the years. "
    "If easier, please email your orders to <b>steve@ezeget.com</b>, "
    "remembering to state your name and postal address for clarification."
)

PHONE = "0771 304 5597"
EMAIL = "steve@ezeget.com"
TITLE_OWNER = "STEVE & JUS"
ORDER_URL = "https://stevegiergiel.vivamknetwork.co.uk/clearance/christmas-sale.html"
OPPORTUNITY_URL = "https://ezeget.com"
OPPORTUNITY_PHONE = "07429 21 21 40"
EZEGET_LOGO_FILE = "ezeget_logo.png"
PRO_FOLIAGE_RIGHT_FILE = "preferred_holly_top_right_transparent.png"
PRO_FOLIAGE_LEFT_FILE = "preferred_holly_top_left_transparent.png"
PRO_FOLIAGE_FOOTER_FILE = "preferred_holly_top_right_transparent.png"
PRO_FOLIAGE_FOOTER_LEFT_FILE = ""
THEME_HEADER_ASSET_MAX_WIDTH_MM = 23.0
THEME_HEADER_ASSET_MAX_HEIGHT_MM = 22.0
THEME_FOOTER_ASSET_MAX_WIDTH_MM = 27.0
THEME_FOOTER_ASSET_MAX_HEIGHT_MM = 22.0
OPPORTUNITY_ART_FILE = "opportunity_back_cover.png"

PRODUCT_CODE_LABEL = "SKU"
PRODUCT_CODE_FONT_SIZE = 6.8
PRODUCT_CODE_BOLD = True
MASK_SOURCE_SALE_BADGE = False
SALE_QR_SIZE_MM = 24.0
PRODUCT_QR_SIZE_MM = 10.5
QR_BOX_SIZE = 10
SALE_QR_CAPTION = "SCAN TO VIEW THIS SALE"
PRODUCT_QR_CAPTION = "SCAN"
BACK_PAGE_QR_URL = "https://ezeget.com"
BACK_PAGE_QR_SIZE_MM = 19.0

SALE_ID = "christmas"
SALE_DISPLAY_NAME = "Christmas Clearance Specials"
HEADER_TITLE = "CHRISTMAS CLEARANCE"
HEADER_SUBTITLE = "Limited stocks - order your favourites quickly!"
COVER_LINE1 = "CHRISTMAS"
COVER_LINE2 = "CLEARANCE"
COVER_LINE3 = "SPECIAL OFFERS"
INTRO_TITLE = "A SPECIAL THANK YOU"
DEFAULT_DESCRIPTION = "Clearance special - limited stock while available."
OUTPUT_PREFIX = "christmas_clearance"
DATA_SOURCE_MODE = "pdf"
CATEGORY_URL = ORDER_URL
SOURCE_PRICE_FILE = "Christmas_Sale_GBP1.pdf"
PRICE_AUDIT_PDF = True
PADDING_THANKS_LINE = "in these clearance offers."


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)


def load_config(path: Path) -> dict:
    """Load optional JSON config. Missing config is treated as an empty config."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def apply_config(cfg: dict):
    """Apply site/content settings that are used by the scraper and PDF renderer."""
    global BASE_URL, SEARCH_URL, INTRO_TEXT, PHONE, EMAIL, TITLE_OWNER
    global ORDER_URL, OPPORTUNITY_URL, OPPORTUNITY_PHONE, EZEGET_LOGO_FILE
    global PRO_FOLIAGE_RIGHT_FILE, PRO_FOLIAGE_LEFT_FILE, PRO_FOLIAGE_FOOTER_FILE, PRO_FOLIAGE_FOOTER_LEFT_FILE, OPPORTUNITY_ART_FILE
    global THEME_HEADER_ASSET_MAX_WIDTH_MM, THEME_HEADER_ASSET_MAX_HEIGHT_MM
    global THEME_FOOTER_ASSET_MAX_WIDTH_MM, THEME_FOOTER_ASSET_MAX_HEIGHT_MM
    global PRODUCT_CODE_LABEL, PRODUCT_CODE_FONT_SIZE, PRODUCT_CODE_BOLD, MASK_SOURCE_SALE_BADGE
    global SALE_QR_SIZE_MM, PRODUCT_QR_SIZE_MM, QR_BOX_SIZE, SALE_QR_CAPTION, PRODUCT_QR_CAPTION
    global BACK_PAGE_QR_URL, BACK_PAGE_QR_SIZE_MM
    global SALE_ID, SALE_DISPLAY_NAME, HEADER_TITLE, HEADER_SUBTITLE, COVER_LINE1, COVER_LINE2, COVER_LINE3
    global INTRO_TITLE, DEFAULT_DESCRIPTION, OUTPUT_PREFIX, DATA_SOURCE_MODE, CATEGORY_URL, SOURCE_PRICE_FILE, PRICE_AUDIT_PDF, PADDING_THANKS_LINE
    global RED, DARK_RED, GREEN, DARK_GREEN, GOLD, CREAM, PALE_GREEN, INK

    BASE_URL = cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/") + "/"
    SEARCH_URL = cfg.get(
        "search_url_template",
        BASE_URL + "catalogsearch/result/?q={sku}"
    )

    intro = cfg.get("intro_text")
    if intro:
        INTRO_TEXT = intro

    PHONE = cfg.get("phone", PHONE)
    EMAIL = cfg.get("email", EMAIL)
    TITLE_OWNER = cfg.get("owner_display_name", TITLE_OWNER)
    ORDER_URL = cfg.get("order_url", ORDER_URL)
    OPPORTUNITY_URL = cfg.get("opportunity_url", OPPORTUNITY_URL)
    OPPORTUNITY_PHONE = cfg.get("opportunity_phone", OPPORTUNITY_PHONE)
    EZEGET_LOGO_FILE = cfg.get("ezeget_logo_file", EZEGET_LOGO_FILE)
    assets = cfg.get("theme_assets", cfg.get("theme", {}).get("assets", {}))
    PRO_FOLIAGE_RIGHT_FILE = assets.get("header_right", cfg.get("pro_foliage_right_file", PRO_FOLIAGE_RIGHT_FILE))
    PRO_FOLIAGE_LEFT_FILE = assets.get("header_left", cfg.get("pro_foliage_left_file", PRO_FOLIAGE_LEFT_FILE))
    PRO_FOLIAGE_FOOTER_FILE = assets.get("footer_right", cfg.get("pro_foliage_footer_file", PRO_FOLIAGE_FOOTER_FILE))
    PRO_FOLIAGE_FOOTER_LEFT_FILE = assets.get("footer_left", "")
    OPPORTUNITY_ART_FILE = assets.get("back_cover", cfg.get("opportunity_art_file", OPPORTUNITY_ART_FILE))
    asset_layout = cfg.get("theme_asset_layout", {})
    THEME_HEADER_ASSET_MAX_WIDTH_MM = float(asset_layout.get("header_max_width_mm", THEME_HEADER_ASSET_MAX_WIDTH_MM))
    THEME_HEADER_ASSET_MAX_HEIGHT_MM = float(asset_layout.get("header_max_height_mm", THEME_HEADER_ASSET_MAX_HEIGHT_MM))
    THEME_FOOTER_ASSET_MAX_WIDTH_MM = float(asset_layout.get("footer_max_width_mm", THEME_FOOTER_ASSET_MAX_WIDTH_MM))
    THEME_FOOTER_ASSET_MAX_HEIGHT_MM = float(asset_layout.get("footer_max_height_mm", THEME_FOOTER_ASSET_MAX_HEIGHT_MM))
    pc = cfg.get("product_code", {})
    PRODUCT_CODE_LABEL = pc.get("label", PRODUCT_CODE_LABEL)
    PRODUCT_CODE_FONT_SIZE = float(pc.get("font_size_pt", PRODUCT_CODE_FONT_SIZE))
    PRODUCT_CODE_BOLD = bool(pc.get("bold", PRODUCT_CODE_BOLD))
    MASK_SOURCE_SALE_BADGE = bool(cfg.get("layout", {}).get("mask_source_sale_badge", MASK_SOURCE_SALE_BADGE))
    qr = cfg.get("qr", {})
    SALE_QR_SIZE_MM = float(qr.get("sale_qr_size_mm", SALE_QR_SIZE_MM))
    PRODUCT_QR_SIZE_MM = float(qr.get("product_qr_size_mm", PRODUCT_QR_SIZE_MM))
    QR_BOX_SIZE = int(qr.get("box_size", QR_BOX_SIZE))
    SALE_QR_CAPTION = qr.get("sale_qr_caption", SALE_QR_CAPTION)
    PRODUCT_QR_CAPTION = qr.get("product_qr_caption", PRODUCT_QR_CAPTION)
    BACK_PAGE_QR_URL = qr.get("back_page_qr_url", BACK_PAGE_QR_URL)
    BACK_PAGE_QR_SIZE_MM = float(qr.get("back_page_qr_size_mm", BACK_PAGE_QR_SIZE_MM))

    sale = cfg.get("sale", {})
    SALE_ID = sale.get("id", cfg.get("sale_id", SALE_ID))
    SALE_DISPLAY_NAME = sale.get("display_name", cfg.get("sale_display_name", SALE_DISPLAY_NAME))
    CATEGORY_URL = sale.get("source_url", cfg.get("category_url", ORDER_URL))
    ORDER_URL = sale.get("source_url", cfg.get("order_url", ORDER_URL))
    HEADER_TITLE = cfg.get("header_title", sale.get("header_title", HEADER_TITLE))
    HEADER_SUBTITLE = cfg.get("header_subtitle", sale.get("header_subtitle", HEADER_SUBTITLE))
    COVER_LINE1 = cfg.get("cover_line1", sale.get("cover_line1", COVER_LINE1))
    COVER_LINE2 = cfg.get("cover_line2", sale.get("cover_line2", COVER_LINE2))
    COVER_LINE3 = cfg.get("cover_line3", sale.get("cover_line3", COVER_LINE3))
    INTRO_TITLE = cfg.get("intro_title", INTRO_TITLE)
    DEFAULT_DESCRIPTION = cfg.get("default_description", DEFAULT_DESCRIPTION)
    OUTPUT_PREFIX = cfg.get("output_prefix", SALE_ID + "_clearance")
    ds = cfg.get("data_source", {})
    DATA_SOURCE_MODE = ds.get("mode", cfg.get("data_source_mode", DATA_SOURCE_MODE))
    SOURCE_PRICE_FILE = ds.get("price_pdf", cfg.get("source_price_file", SOURCE_PRICE_FILE))
    PRICE_AUDIT_PDF = bool(ds.get("generate_price_audit_pdf", True))
    PADDING_THANKS_LINE = cfg.get("padding_thanks_line", PADDING_THANKS_LINE)
    palette = cfg.get("theme", {}).get("colours", cfg.get("theme_colours", {}))
    if palette:
        RED = colors.HexColor(palette.get("sale", "#B5121B"))
        DARK_RED = colors.HexColor(palette.get("sale_dark", "#781018"))
        GREEN = colors.HexColor(palette.get("secondary", "#0B6B3A"))
        DARK_GREEN = colors.HexColor(palette.get("primary", "#064629"))
        GOLD = colors.HexColor(palette.get("accent", "#E3B341"))
        CREAM = colors.HexColor(palette.get("cream", "#FFF7E2"))
        PALE_GREEN = colors.HexColor(palette.get("pale", "#EAF4EB"))
        INK = colors.HexColor(palette.get("ink", "#202020"))


@dataclass
class SaleRow:
    sku: str
    product: str
    was: str
    now: str
    saving: str
    percent: str
    product_url: str = ""
    description: str = ""
    image_url: str = ""
    image_file: str = ""
    qr_file: str = ""
    availability: str = ""


# -----------------------------
# Parsing the uploaded sale PDF
# -----------------------------

MONEY = r"£\s*\d+(?:\.\d{2})?"
ROW_RE = re.compile(
    rf"^\s*(\d{{4,8}})\s+(.+?)\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+(\d{{1,3}}%)\s*$"
)


def clean_text(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("‐", "-").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def extract_sale_rows(pdf_path: Path) -> list[SaleRow]:
    doc = fitz.open(pdf_path)
    rows: list[SaleRow] = []

    for page in doc:
        text = page.get_text("text")
        for raw in text.splitlines():
            line = clean_text(raw)
            if not line or line.lower().startswith("sku product"):
                continue
            m = ROW_RE.match(line)
            if m:
                sku, product, was, now, saving, pct = m.groups()
                rows.append(
                    SaleRow(
                        sku=sku,
                        product=clean_text(product),
                        was=clean_text(was),
                        now=clean_text(now),
                        saving=clean_text(saving),
                        percent=pct,
                    )
                )

    # PyMuPDF may split a table row into columns/lines on some PDFs. Fall back to
    # word-based reconstruction if the obvious extraction did not yield enough rows.
    if len(rows) < 5:
        rows = extract_rows_from_words(doc)

    # de-duplicate by SKU while preserving order
    seen = set()
    unique = []
    for row in rows:
        if row.sku not in seen:
            seen.add(row.sku)
            unique.append(row)

    if not unique:
        raise RuntimeError(
            "No product rows could be parsed from the clearance PDF. "
            "If its layout changes, export it as CSV or adjust ROW_RE."
        )
    return unique


def extract_rows_from_words(doc: fitz.Document) -> list[SaleRow]:
    found: list[SaleRow] = []
    for page in doc:
        words = page.get_text("words")
        # group words into visual lines by rounded y coordinate
        lines: dict[int, list] = {}
        for w in words:
            x0, y0, x1, y1, txt, *_ = w
            key = round(y0 / 3) * 3
            lines.setdefault(key, []).append(w)
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda w: w[0])
            line = clean_text(" ".join(w[4] for w in ws))
            m = ROW_RE.match(line)
            if m:
                sku, product, was, now, saving, pct = m.groups()
                found.append(SaleRow(sku, product, was, now, saving, pct))
    return found


# -----------------------------
# Website scraping
# -----------------------------

def personal_vivamk_url(url: str) -> str:
    """Force a product/category path onto Steve's personal VivaMK hostname."""
    if not url:
        return ""
    base = urlsplit(BASE_URL)
    parsed = urlsplit(urljoin(BASE_URL, url))
    return urlunsplit((base.scheme or "https", base.netloc, parsed.path, parsed.query, parsed.fragment))


def make_qr(url: str, path: Path) -> str:
    """Create a print-quality QR with quiet zone and Q-level error correction."""
    if not url:
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=QR_BOX_SIZE,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").convert("RGB").save(path)
    return str(path)



def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        }
    )
    return s


def get_soup(session: requests.Session, url: str, timeout: int = 30) -> BeautifulSoup:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            txt = clean_text(node.get_text(" ", strip=True))
            if txt:
                return txt
    return ""


def first_attr(soup: BeautifulSoup, selectors: list[tuple[str, str]]) -> str:
    for sel, attr in selectors:
        node = soup.select_one(sel)
        if node and node.get(attr):
            return clean_text(str(node.get(attr)))
    return ""


def product_link_from_search(soup: BeautifulSoup) -> str:
    selectors = [
        "a.product-item-link",
        ".product-item-name a",
        ".product.name.product-item-name a",
        "ol.products a.product-item-link",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if node and node.get("href"):
            return urljoin(BASE_URL, node["href"])
    return ""


def scrape_product(session: requests.Session, row: SaleRow) -> SaleRow:
    search_url = SEARCH_URL.format(sku=row.sku)
    search_soup = get_soup(session, search_url)

    product_url = product_link_from_search(search_soup)
    if not product_url:
        # Sometimes an exact URL might be exposed in canonical metadata.
        canonical = first_attr(search_soup, [('link[rel="canonical"]', "href")])
        if canonical and "catalogsearch" not in canonical:
            product_url = urljoin(BASE_URL, canonical)

    if not product_url:
        print(f"[WARN] SKU {row.sku}: no product result found")
        return row

    product_url = personal_vivamk_url(product_url)
    soup = get_soup(session, product_url)
    row.product_url = product_url

    # Product name
    name = first_text(
        soup,
        [
            "h1.page-title span",
            "h1.page-title",
            "h1",
        ],
    )
    if name:
        row.product = name

    # Description: Magento usually exposes one of these.
    desc = first_text(
        soup,
        [
            ".product.attribute.overview .value",
            ".product.attribute.description .value",
            "#description .value",
            ".product-info-main .product.attribute.overview",
            "[itemprop='description']",
        ],
    )
    row.description = desc

    # Image: prefer OpenGraph, then Magento gallery attributes, then visible product image.
    image_url = first_attr(
        soup,
        [
            ('meta[property="og:image"]', "content"),
            ('meta[name="twitter:image"]', "content"),
            (".fotorama__stage__frame img", "src"),
            (".gallery-placeholder img", "data-src"),
            (".gallery-placeholder img", "src"),
            (".product.media img", "src"),
        ],
    )

    # Magento can keep gallery JSON in data-gallery-role / script.
    if not image_url:
        for script in soup.find_all("script"):
            txt = script.string or script.get_text(" ", strip=True)
            if "full" in txt and ("img" in txt or "thumb" in txt):
                m = re.search(r'"full"\s*:\s*"([^"]+)"', txt)
                if m:
                    image_url = m.group(1).replace("\\/", "/")
                    break

    row.image_url = urljoin(product_url, html.unescape(image_url)) if image_url else ""

    # Availability
    row.availability = first_text(
        soup,
        [
            ".stock.available",
            ".stock.unavailable",
            ".product-info-stock-sku .stock",
        ],
    )
    return row


def download_image(session: requests.Session, url: str, image_dir: Path, sku: str) -> str:
    if not url:
        return ""
    try:
        r = session.get(url, timeout=40)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            return ""

        suffix = ".jpg"
        if "png" in ctype:
            suffix = ".png"
        elif "webp" in ctype:
            suffix = ".webp"

        path = image_dir / f"{sku}{suffix}"
        path.write_bytes(r.content)

        # Verify/normalise; PDF libraries are happier with RGB JPEG.
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                bg = Image.new("RGB", im.size, "white")
                if "A" in im.getbands():
                    bg.paste(im, mask=im.getchannel("A"))
                else:
                    bg.paste(im)
                im = bg
            else:
                im = im.convert("RGB")
            jpg = image_dir / f"{sku}.jpg"
            im.save(jpg, "JPEG", quality=90, optimize=True)
        if path != jpg and path.exists():
            path.unlink(missing_ok=True)
        return str(jpg)
    except Exception as exc:
        print(f"[WARN] SKU {sku}: image download failed: {exc}")
        return ""


def enrich_rows(rows: list[SaleRow], cache_dir: Path, refresh: bool = False, delay: float = 0.35) -> list[SaleRow]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    image_dir = cache_dir / "images"
    image_dir.mkdir(exist_ok=True)
    data_file = cache_dir / "products.json"

    cache = {}
    if data_file.exists() and not refresh:
        try:
            cache = json.loads(data_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    session = make_session()

    for i, row in enumerate(rows, 1):
        print(f"[{i:02d}/{len(rows):02d}] SKU {row.sku} - {row.product}")

        if row.sku in cache and not refresh:
            saved = cache[row.sku]
            for k, v in saved.items():
                if hasattr(row, k):
                    setattr(row, k, v)
        else:
            try:
                row = scrape_product(session, row)
            except Exception as exc:
                print(f"[WARN] SKU {row.sku}: scrape failed: {exc}")

            if row.image_url:
                row.image_file = download_image(session, row.image_url, image_dir, row.sku)
            if row.product_url:
                row.product_url = personal_vivamk_url(row.product_url)
                row.qr_file = ""

            cache[row.sku] = asdict(row)
            data_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
            time.sleep(delay)

        # If metadata is cached but the image was removed, re-download it.
        if row.image_url and (not row.image_file or not Path(row.image_file).exists()):
            row.image_file = download_image(session, row.image_url, image_dir, row.sku)
            cache[row.sku] = asdict(row)
            data_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        if row.product_url:
            row.product_url = personal_vivamk_url(row.product_url)
        row.qr_file = ""

    return rows



# -----------------------------
# Direct category-price scraping
# -----------------------------

def _money_value(s: str):
    from decimal import Decimal, InvalidOperation
    try:
        v = re.sub(r"[^0-9.]", "", s or "")
        return Decimal(v) if v else None
    except (InvalidOperation, ValueError):
        return None


def _derive_saving(was: str, now: str):
    from decimal import Decimal
    w, n = _money_value(was), _money_value(now)
    if w is None or n is None or w <= 0 or n > w:
        return "", ""
    save = w - n
    pct = int((save / w * Decimal(100)).quantize(Decimal("1")))
    return f"£{save:.2f}", f"{pct}%"


def _category_price_pair(node):
    was = first_text(node, [".old-price .price", ".old.price .price", ".price-box .old-price .price"])
    now = first_text(node, [".special-price .price", ".special.price .price", ".price-final_price .price"])
    prices = [clean_text(x.get_text(" ", strip=True)) for x in node.select(".price-box .price")]
    prices = [p for p in prices if "£" in p]
    if not now and prices:
        now = next((p for p in prices if p != was), prices[-1])
    return was, now


def scrape_category_rows(category_url: str, max_pages: int = 30) -> list[SaleRow]:
    session = make_session()
    url = personal_vivamk_url(category_url)
    seen_pages, seen_products, rows = set(), set(), []
    for page_no in range(1, max_pages + 1):
        if not url or url in seen_pages:
            break
        seen_pages.add(url)
        print(f"Category page {page_no}: {url}")
        soup = get_soup(session, url)
        items = soup.select("li.product-item") or soup.select(".product-item")
        for item in items:
            link = item.select_one("a.product-item-link") or item.select_one(".product-item-name a")
            if not link or not link.get("href"):
                continue
            product_url = personal_vivamk_url(link.get("href"))
            if product_url in seen_products:
                continue
            was, now = _category_price_pair(item)
            if not was or not now:
                continue
            saving, percent = _derive_saving(was, now)
            if not saving:
                continue
            seen_products.add(product_url)
            name = clean_text(link.get_text(" ", strip=True))
            sku = clean_text(item.get("data-product-sku", ""))
            row = SaleRow(sku=sku, product=name, was=was, now=now, saving=saving, percent=percent, product_url=product_url)
            try:
                ps = get_soup(session, product_url)
                row.sku = row.sku or first_text(ps, [".product.attribute.sku .value", ".product-info-stock-sku .value", "[itemprop='sku']"])
                row.description = first_text(ps, [".product.attribute.overview .value", ".product.attribute.description .value", "[itemprop='description']"])
                row.image_url = first_attr(ps, [("meta[property='og:image']", "content"), ("meta[name='twitter:image']", "content"), (".gallery-placeholder img", "src"), (".product.media img", "src")])
                pwas, pnow = _category_price_pair(ps)
                if pwas and pnow:
                    psave, ppct = _derive_saving(pwas, pnow)
                    if psave:
                        row.was, row.now, row.saving, row.percent = pwas, pnow, psave, ppct
            except Exception as exc:
                print(f"[WARN] product page enrichment failed for {product_url}: {exc}")
            rows.append(row)
        nxt = soup.select_one("a.action.next") or soup.select_one("a.next")
        url = personal_vivamk_url(nxt.get("href")) if nxt and nxt.get("href") else ""
    return rows


def enrich_category_rows(rows: list[SaleRow], cache_dir: Path, delay: float = 0.25) -> list[SaleRow]:
    session = make_session()
    image_dir = cache_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    out=[]
    for i,row in enumerate(rows,1):
        print(f"[{i:02d}/{len(rows):02d}] {row.sku or row.product}")
        if row.image_url:
            row.image_url=urljoin(row.product_url or BASE_URL,row.image_url)
            row.image_file=download_image(session,row.image_url,image_dir,row.sku or str(i))
        if row.product_url:
            row.product_url=personal_vivamk_url(row.product_url)
            row.qr_file=make_qr(row.product_url,image_dir/f"{row.sku or i}_qr.png")
        if row.image_file and Path(row.image_file).exists():
            out.append(row)
        else:
            print(f"Removed {row.sku or row.product}: no usable image")
        if delay: time.sleep(delay)
    return out


def write_price_audit_pdf(rows: list[SaleRow], out_pdf: Path):
    c=canvas.Canvas(str(out_pdf),pagesize=A4)
    w,h=A4; y=h-18*mm
    c.setFont("Helvetica-Bold",14); c.drawString(15*mm,y,f"{SALE_DISPLAY_NAME} - generated price list"); y-=9*mm
    c.setFont("Helvetica-Bold",7)
    for label,x in [("SKU",15),("PRODUCT",35),("WAS",143),("NOW",163),("SAVE/OFF",181)]: c.drawString(x*mm,y,label)
    y-=5*mm; c.setFont("Helvetica",6.3)
    for r in rows:
        if y<15*mm:
            c.showPage(); y=h-18*mm; c.setFont("Helvetica",6.3)
        name=r.product if len(r.product)<=55 else r.product[:54]+"..."
        for value,x in [(r.sku,15),(name,35),(r.was,143),(r.now,163),(f"{r.saving} {r.percent}",181)]: c.drawString(x*mm,y,value)
        y-=4.7*mm
    c.save()

# -----------------------------
# Design helpers
# -----------------------------

RED = colors.HexColor("#B5121B")
DARK_RED = colors.HexColor("#781018")
GREEN = colors.HexColor("#0B6B3A")
DARK_GREEN = colors.HexColor("#064629")
GOLD = colors.HexColor("#E3B341")
CREAM = colors.HexColor("#FFF7E2")
PALE_GREEN = colors.HexColor("#EAF4EB")
INK = colors.HexColor("#202020")



def local_asset(filename: str) -> Path:
    """Resolve an artwork file either from the working folder or beside this script."""
    p = Path(filename)
    if p.exists():
        return p
    return Path(__file__).resolve().parent / filename



def draw_festive_header(c: canvas.Canvas, width: float, height: float, title: str, subtitle: str = ""):
    """Config-driven header with independent left/right artwork and no forced mirroring."""
    band_h = 27 * mm
    c.setFillColor(DARK_GREEN)
    c.rect(0, height - band_h, width, band_h, stroke=0, fill=1)

    left_art = local_asset(PRO_FOLIAGE_LEFT_FILE) if PRO_FOLIAGE_LEFT_FILE else None
    right_art = local_asset(PRO_FOLIAGE_RIGHT_FILE) if PRO_FOLIAGE_RIGHT_FILE else None

    def place_patch(path: Path | None, x: float, y: float, max_w: float, max_h: float, anchor_right: bool = False) -> float:
        if path is None or not path.exists():
            return 0.0
        with Image.open(path) as im:
            iw, ih = im.size
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        px = x - dw if anchor_right else x
        py = y + (max_h - dh) / 2
        c.drawImage(str(path), px, py, dw, dh, preserveAspectRatio=True, mask="auto")
        return dw

    max_w = THEME_HEADER_ASSET_MAX_WIDTH_MM * mm
    max_h = THEME_HEADER_ASSET_MAX_HEIGHT_MM * mm
    left_w = place_patch(left_art, 1.5 * mm, height - 25.5 * mm, max_w, max_h)
    right_w = place_patch(right_art, width - 1.5 * mm, height - 25.5 * mm, max_w, max_h, anchor_right=True)

    # Centre wording in the genuinely free header space, avoiding the one-sided graphic.
    clear_left = 3.0 * mm + left_w
    clear_right = width - 3.0 * mm - right_w
    text_centre = (clear_left + clear_right) / 2

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17.0)
    c.drawCentredString(text_centre, height - 12.7 * mm, title)
    if subtitle:
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawCentredString(text_centre, height - 20.0 * mm, subtitle)


def draw_banner_footer(c: canvas.Canvas, width: float, page_no: int | None = None):
    """Config-driven banner footer with independent left/right theme artwork."""
    h = 24 * mm
    c.setFillColor(DARK_GREEN)
    c.rect(0, 0, width, h, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(5 * mm, h - 1.7 * mm, width - 5 * mm, h - 1.7 * mm)

    def place_footer(path_name: str, left: bool) -> float:
        if not path_name:
            return 0.0
        path = local_asset(path_name)
        if not path.exists():
            return 0.0
        with Image.open(path) as im:
            iw, ih = im.size
        max_w = THEME_FOOTER_ASSET_MAX_WIDTH_MM * mm
        max_h = THEME_FOOTER_ASSET_MAX_HEIGHT_MM * mm
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        x = 1.0 * mm if left else width - dw - 1.0 * mm
        y = 1.0 * mm + (max_h - dh) / 2
        c.drawImage(str(path), x, y, dw, dh, preserveAspectRatio=True, mask="auto")
        return dw

    left_w = place_footer(PRO_FOLIAGE_FOOTER_LEFT_FILE, True)
    right_w = place_footer(PRO_FOLIAGE_FOOTER_FILE, False)

    text_x = 8 * mm if left_w == 0 else left_w + 4.0 * mm
    text_right = width - 8 * mm if right_w == 0 else width - right_w - 4.0 * mm
    available = max(30 * mm, text_right - text_x)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.7)
    c.drawString(text_x, 15.0 * mm, "ORDER ONLINE:")

    c.setFillColor(colors.white)
    parsed_order = urlsplit(ORDER_URL)
    order_display = (parsed_order.netloc + parsed_order.path).rstrip("/")
    if parsed_order.query:
        order_display += "?" + parsed_order.query
    url_size = 5.8
    while url_size > 4.2 and stringWidth(order_display, "Helvetica-Bold", url_size) > available:
        url_size -= 0.2
    c.setFont("Helvetica-Bold", url_size)
    c.drawString(text_x, 10.3 * mm, order_display)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(text_x, 4.3 * mm, f"TEXT ORDERS: {PHONE}")

    if page_no is not None:
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 5.5)
        page_x = text_right
        c.drawRightString(page_x, 4.4 * mm, f"Page {page_no}")


def wrap_text(c: canvas.Canvas, text: str, font: str, size: float, max_width: float, max_lines: int) -> list[str]:
    words = clean_text(text).split()
    lines = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)

    if len(lines) == max_lines and words:
        # add ellipsis if likely truncated
        joined = " ".join(lines)
        if len(joined) < len(clean_text(text)):
            line = lines[-1]
            while line and stringWidth(line + "...", font, size) > max_width:
                line = line[:-1]
            lines[-1] = line.rstrip() + "..."
    return lines


def draw_image_contain(c: canvas.Canvas, image_file: str, x: float, y: float, w: float, h: float):
    if not image_file or not Path(image_file).exists():
        c.setFillColor(PALE_GREEN)
        c.roundRect(x, y, w, h, 3 * mm, stroke=0, fill=1)
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + w / 2, y + h / 2 + 2, "Product image")
        c.setFont("Helvetica", 6.5)
        c.drawCentredString(x + w / 2, y + h / 2 - 7, "not available")
        return None

    with Image.open(image_file) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx = x + (w - dw) / 2
    dy = y + (h - dh) / 2
    c.drawImage(image_file, dx, dy, dw, dh, preserveAspectRatio=True, mask="auto")
    return dx, dy, dw, dh


def draw_product_card(c: canvas.Canvas, row: SaleRow, x: float, y: float, w: float, h: float):
    """Compact clearance card prioritising large product photography and clear pricing."""
    c.saveState()

    c.setFillColor(colors.HexColor("#E9E2D3"))
    c.roundRect(x + 0.8 * mm, y - 0.8 * mm, w, h, 3 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D7CBAF"))
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, 3 * mm, stroke=1, fill=1)

    pad = 2.4 * mm
    compact = h < 92 * mm
    price_block_h = 19.0 * mm if compact else 21.0 * mm

    image_h = h * (0.49 if compact else 0.48)
    image_y = y + h - image_h - pad
    image_bounds = draw_image_contain(c, row.image_file, x + pad, image_y, w - 2 * pad, image_h)
    if MASK_SOURCE_SALE_BADGE and image_bounds:
        ix, iy, iw, ih = image_bounds
        mask_w = min(15 * mm, iw * 0.28)
        mask_h = min(14 * mm, ih * 0.30)
        c.setFillColor(colors.white)
        c.rect(ix + iw - mask_w, iy + ih - mask_h, mask_w, mask_h, stroke=0, fill=1)

    badge_r = 6.5 * mm if compact else 7.5 * mm
    # Pull the badge slightly inboard. A thin white backing masks any sale
    # ribbon/badge embedded in the source image so only one clear OFF badge shows.
    bx = x + w - 12.5 * mm
    by = y + h - 8.5 * mm
    c.setFillColor(colors.white)
    c.circle(bx, by, badge_r + 0.9 * mm, stroke=0, fill=1)
    c.setFillColor(RED)
    c.circle(bx, by, badge_r, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.2 if compact else 9.2)
    c.drawCentredString(bx, by + 1.2, row.percent)
    c.setFont("Helvetica-Bold", 4.8 if compact else 5.2)
    c.drawCentredString(bx, by - 4.4, "OFF")

    title_size = 7.5 if compact else 8.8
    title_leading = 8.1 if compact else 9.7
    ty = image_y - 2.0 * mm
    c.setFillColor(DARK_GREEN)
    for line in wrap_text(c, row.product, "Helvetica-Bold", title_size, w - 2 * pad, 2):
        c.setFont("Helvetica-Bold", title_size)
        c.drawString(x + pad, ty, line)
        ty -= title_leading

    price_top = y + price_block_h
    available = ty - price_top - 0.8 * mm
    if available > 6:
        desc_size = 5.3 if compact else 6.0
        desc_leading = 5.9 if compact else 6.8
        max_lines = 1 if compact else min(2, max(1, int(available // desc_leading)))
        desc = row.description or DEFAULT_DESCRIPTION
        dy = ty - 0.3
        c.setFillColor(INK)
        for line in wrap_text(c, desc, "Helvetica", desc_size, w - 2 * pad, max_lines):
            if dy < price_top + 0.5 * mm:
                break
            c.setFont("Helvetica", desc_size)
            c.drawString(x + pad, dy, line)
            dy -= desc_leading

    panel_y = y + 1.6 * mm
    panel_h = price_block_h - 2.2 * mm
    c.setFillColor(colors.HexColor("#FFF8E8"))
    c.setStrokeColor(colors.HexColor("#E5D4A7"))
    c.setLineWidth(0.5)
    c.roundRect(x + 1.5 * mm, panel_y, w - 3 * mm, panel_h, 1.8 * mm, stroke=1, fill=1)

    left = x + pad
    right = x + w - pad

    was_y = panel_y + panel_h - 4.0 * mm
    label_size = 6.0 if compact else 6.8
    price_size = 6.8 if compact else 7.6
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica-Bold", label_size)
    c.drawString(left, was_y, "WAS")
    label_w = stringWidth("WAS ", "Helvetica-Bold", label_size)
    px = left + label_w
    c.setFont("Helvetica-Bold", price_size)
    c.drawString(px, was_y, row.was)
    ww = stringWidth(row.was, "Helvetica-Bold", price_size)
    c.setStrokeColor(colors.HexColor("#777777"))
    c.setLineWidth(0.9)
    c.line(px, was_y + 2.1, px + ww, was_y + 2.1)

    # Product QR codes deliberately removed in v2.04.
    # The full panel width is used for cleaner WAS / SAVE / NOW / SKU details.
    price_right = right

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 5.9 if compact else 6.7)
    c.drawRightString(price_right, was_y, f"SAVE {row.saving}")

    now_y = panel_y + 7.0 * mm
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 11.0 if compact else 13.0)
    c.drawString(left, now_y, f"NOW {row.now}")

    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica-Bold" if PRODUCT_CODE_BOLD else "Helvetica", PRODUCT_CODE_FONT_SIZE)
    c.drawRightString(right, panel_y + 2.1 * mm, f"{PRODUCT_CODE_LABEL} {row.sku}")


def draw_sale_qr(c: canvas.Canvas, width: float, y: float):
    """Large QR to the current sale page on Steve's personal VivaMK website."""
    url = personal_vivamk_url(ORDER_URL)
    qr_path = local_asset("_generated_sale_qr.png")
    make_qr(url, qr_path)
    size = SALE_QR_SIZE_MM * mm
    x = width / 2 - size / 2
    c.setFillColor(colors.white)
    c.roundRect(x - 2 * mm, y - 2 * mm, size + 4 * mm, size + 8 * mm, 2 * mm, stroke=0, fill=1)
    c.drawImage(str(qr_path), x, y, size, size, preserveAspectRatio=True, mask="auto")
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(width / 2, y - 0.8 * mm, SALE_QR_CAPTION)



def draw_cover(c: canvas.Canvas, width: float, height: float):
    """Front cover using the approved template geometry and configured theme."""
    c.setFillColor(DARK_GREEN)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_festive_header(c, width, height, HEADER_TITLE, HEADER_SUBTITLE)

    c.setFillColor(CREAM)
    c.roundRect(11 * mm, 46 * mm, width - 22 * mm, height - 82 * mm, 5 * mm, stroke=0, fill=1)

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 52 * mm, f"{TITLE_OWNER} BRING YOU")
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 25)
    c.drawCentredString(width / 2, height - 72 * mm, COVER_LINE1)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(width / 2, height - 89 * mm, COVER_LINE2)
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 19)
    c.drawCentredString(width / 2, height - 104 * mm, COVER_LINE3)

    c.setFillColor(RED)
    c.roundRect(22 * mm, height - 137 * mm, width - 44 * mm, 20 * mm, 4 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(width / 2, height - 127 * mm, "AMAZING PRICES")
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(width / 2, height - 134 * mm, "Once they're gone, they're gone!")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, 67 * mm, "BE QUICK - PICK YOUR FAVOURITES")
    draw_sale_qr(c, width, 34 * mm)

    draw_banner_footer(c, width)

def draw_intro(c: canvas.Canvas, width: float, height: float):
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_festive_header(c, width, height, INTRO_TITLE)

    box_x, box_y = 12 * mm, 30 * mm
    box_w, box_h = width - 24 * mm, height - 70 * mm
    c.setFillColor(colors.white)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.roundRect(box_x, box_y, box_w, box_h, 5 * mm, stroke=1, fill=1)

    style = ParagraphStyle(
        "intro",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=INK,
        alignment=TA_LEFT,
    )
    p = Paragraph(INTRO_TEXT, style)
    _, ph = p.wrap(box_w - 14 * mm, box_h - 18 * mm)
    p.drawOn(c, box_x + 7 * mm, box_y + box_h - ph - 9 * mm)
    draw_banner_footer(c, width, 2)


def draw_product_page(c: canvas.Canvas, width: float, height: float, rows: list[SaleRow], page_no: int, cards_per_page: int):
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_festive_header(c, width, height, HEADER_TITLE, HEADER_SUBTITLE)

    margin_x = 3.5 * mm
    top = height - 30 * mm
    bottom = 25.5 * mm
    gap = 1.8 * mm

    if cards_per_page <= 4:
        cols, rws = 2, 2
    else:
        cols, rws = 2, 3

    card_w = (width - 2 * margin_x - gap) / cols
    card_h = (top - bottom - (rws - 1) * gap) / rws

    for idx, row in enumerate(rows[: cols * rws]):
        rr = idx // cols
        cc = idx % cols
        x = margin_x + cc * (card_w + gap)
        y = top - (rr + 1) * card_h - rr * gap
        draw_product_card(c, row, x, y, card_w, card_h)
    draw_banner_footer(c, width, page_no)


def draw_padding_page(c: canvas.Canvas, width: float, height: float, index: int, total: int):
    """Designed booklet padding page - never an empty white page."""
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    title = "THANK YOU" if index == 1 else "HOW TO ORDER"
    subtitle = "For your valued custom" if index == 1 else f"{SALE_DISPLAY_NAME} - while stocks last"
    draw_festive_header(c, width, height, title, subtitle)

    c.setFillColor(colors.white)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.roundRect(15 * mm, 52 * mm, width - 30 * mm, height - 100 * mm, 5 * mm, stroke=1, fill=1)

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 15)
    if index == 1:
        c.drawCentredString(width / 2, height - 74 * mm, "Steve & Jus sincerely thank you")
        c.setFont("Helvetica", 9.5)
        lines = [
            "for your valued custom through the years.",
            "We hope you find something special",
            PADDING_THANKS_LINE
        ]
    else:
        c.drawCentredString(width / 2, height - 74 * mm, "ORDER YOUR FAVOURITES QUICKLY")
        c.setFont("Helvetica", 8.8)
        lines = [
            "Order as normal using the paper order form.",
            "For a faster service, and to increase your chances",
            "of reserving your favourite items before they sell out,",
            f"text your requirements to {PHONE}.",
            "Please include your name and postal address",
            "if we may not recognise your telephone number.",
            f"You can also email your order to {EMAIL}."
        ]
    yy = height - 91 * mm
    c.setFillColor(INK)
    for line in lines:
        c.drawCentredString(width / 2, yy, line)
        yy -= 6 * mm

    c.setFillColor(RED)
    c.roundRect(28 * mm, 57 * mm, width - 56 * mm, 14 * mm, 4 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9.0)
    c.drawCentredString(width / 2, 64.5 * mm, "ONCE THEY'RE GONE, THEY'RE GONE!")

    draw_banner_footer(c, width)

def draw_back_cover(c: canvas.Canvas, width: float, height: float):
    """
    Physical back cover: use the user's supplied RIGHT-HAND opportunity advert intact.
    It is scaled proportionally and centred; it is never rebuilt from separately positioned elements.
    A clearer QR for ezeget.com is overlaid on top so the code scans more reliably.
    """
    art = local_asset(OPPORTUNITY_ART_FILE)
    if not art.exists():
        raise FileNotFoundError(f"Opportunity artwork not found: {art}")

    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    with Image.open(art) as im:
        iw, ih = im.size
    scale = min(width / iw, height / ih)
    dw, dh = iw * scale, ih * scale
    x = (width - dw) / 2
    y = (height - dh) / 2
    c.drawImage(str(art), x, y, dw, dh, preserveAspectRatio=True, mask="auto")

    if BACK_PAGE_QR_URL:
        qr_path = local_asset("_generated_back_page_ezeget_qr.png")
        make_qr(BACK_PAGE_QR_URL, qr_path)
        size = BACK_PAGE_QR_SIZE_MM * mm
        qr_x = width - 30.5 * mm
        qr_y = 36.2 * mm
        c.setFillColor(colors.white)
        c.roundRect(qr_x - 1.1 * mm, qr_y - 1.1 * mm, size + 2.2 * mm, size + 2.2 * mm, 2 * mm, stroke=0, fill=1)
        c.drawImage(str(qr_path), qr_x, qr_y, size, size, preserveAspectRatio=True, mask="auto")


def create_a5_brochure(rows: list[SaleRow], out_pdf: Path, cards_per_page: int = 4):
    width, height = A5
    c = canvas.Canvas(str(out_pdf), pagesize=A5)

    # Front cover
    draw_cover(c, width, height)
    c.showPage()

    # Inside introduction
    draw_intro(c, width, height)
    c.showPage()

    per_page = 4 if cards_per_page <= 4 else 6
    product_pages = math.ceil(len(rows) / per_page)

    for p in range(product_pages):
        chunk = rows[p * per_page:(p + 1) * per_page]
        draw_product_page(c, width, height, chunk, p + 3, cards_per_page)
        c.showPage()

    # IMPORTANT: the opportunity advert must be the physical LAST page.
    # Insert any booklet padding BEFORE it, never after it.
    pages_before_back = 2 + product_pages
    blanks_before_back = (-(pages_before_back + 1)) % 4
    for pad_index in range(blanks_before_back):
        draw_padding_page(c, width, height, pad_index + 1, blanks_before_back)
        c.showPage()

    # Physical back cover = EzeGet business opportunity advert.
    draw_back_cover(c, width, height)
    c.showPage()
    c.save()


def pad_pdf_to_multiple_of_four(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    n = len(reader.pages)
    extra = (-n) % 4
    if not extra:
        return

    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)

    a5_w, a5_h = A5
    for _ in range(extra):
        writer.add_blank_page(width=a5_w, height=a5_h)

    tmp = pdf_path.with_name(pdf_path.stem + "_padded.pdf")
    with tmp.open("wb") as f:
        writer.write(f)
    tmp.replace(pdf_path)


def impose_booklet(a5_pdf: Path, out_pdf: Path):
    """
    Impose A5 pages onto A4 landscape sheets:
      sheet 1 front: [last, 1]
      sheet 1 back : [2, second-last]
      ...
    Output sequence is front/back/front/back for duplex printing.
    """
    reader = PdfReader(str(a5_pdf))
    n = len(reader.pages)
    if n % 4:
        raise ValueError("A5 source must contain a multiple of 4 pages.")

    a4_w, a4_h = landscape(A4)
    half_w = a4_w / 2

    writer = PdfWriter()

    def add_spread(left_idx: int, right_idx: int):
        spread = writer.add_blank_page(width=a4_w, height=a4_h)
        for idx, xoff in ((left_idx, 0), (right_idx, half_w)):
            page = reader.pages[idx]

            pw = float(page.mediabox.width)
            ph = float(page.mediabox.height)

            # A5 portrait should fit exactly into half of A4 landscape.
            scale = min(half_w / pw, a4_h / ph)
            tx = xoff + (half_w - pw * scale) / 2
            ty = (a4_h - ph * scale) / 2

            transform = Transformation().scale(scale).translate(tx, ty)
            spread.merge_transformed_page(page, transform)

    sheets = n // 4
    for s in range(sheets):
        # zero-based indexes
        front_left = n - 1 - 2 * s
        front_right = 2 * s
        back_left = 2 * s + 1
        back_right = n - 2 - 2 * s

        add_spread(front_left, front_right)
        add_spread(back_left, back_right)

    with out_pdf.open("wb") as f:
        writer.write(f)


def validate_required_assets():
    required = {
        "opportunity back cover": OPPORTUNITY_ART_FILE,
    }
    optional_configured = {
        "theme header-left decoration": PRO_FOLIAGE_LEFT_FILE,
        "theme header-right decoration": PRO_FOLIAGE_RIGHT_FILE,
        "theme footer-left decoration": PRO_FOLIAGE_FOOTER_LEFT_FILE,
        "theme footer-right decoration": PRO_FOLIAGE_FOOTER_FILE,
    }
    required.update({label: filename for label, filename in optional_configured.items() if filename})
    missing = [
        f"{label}: {local_asset(filename)}"
        for label, filename in required.items()
        if not local_asset(filename).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Required configured artwork is missing; generation stopped rather than using fallback artwork.\n  - "
            + "\n  - ".join(missing)
        )


# -----------------------------
# Main
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Create a config-driven VivaMK clearance booklet.")
    ap.add_argument("--config", type=Path, required=True, help="Sale JSON configuration file")
    ap.add_argument("--out", type=Path, default=None, help="Optional output folder override")
    ap.add_argument("--refresh", action="store_true", help="Refresh website data")
    ap.add_argument("--cards-per-page", type=int, choices=[4,6], default=None)
    ap.add_argument("--delay", type=float, default=None)
    args=ap.parse_args()

    cfg=load_config(args.config)
    apply_config(cfg)
    validate_required_assets()
    out_dir=args.out or Path(cfg.get("output_folder", f"output/{SALE_ID}"))
    cards_per_page=args.cards_per_page or int(cfg.get("cards_per_page",6))
    delay=args.delay if args.delay is not None else float(cfg.get("request_delay_seconds",0.35))
    out_dir.mkdir(parents=True,exist_ok=True)
    cache_dir=out_dir/"cache"

    if DATA_SOURCE_MODE.lower()=="pdf":
        sale_pdf=Path(SOURCE_PRICE_FILE)
        if not sale_pdf.is_absolute():
            sale_pdf=args.config.resolve().parent.parent / sale_pdf
        if not sale_pdf.exists():
            ap.error(f"Price PDF not found: {sale_pdf}")
        print(f"Extracting authoritative price list: {sale_pdf}")
        rows=extract_sale_rows(sale_pdf)
        rows=enrich_rows(rows,cache_dir,refresh=args.refresh,delay=delay)
        rows=[r for r in rows if r.image_file and Path(r.image_file).exists()]
    elif DATA_SOURCE_MODE.lower()=="category":
        print(f"Scraping category prices: {CATEGORY_URL}")
        rows=scrape_category_rows(CATEGORY_URL,int(cfg.get("max_category_pages",30)))
        rows=enrich_category_rows(rows,cache_dir,delay=delay)
    else:
        raise ValueError(f"Unsupported data_source.mode: {DATA_SOURCE_MODE}")

    if not rows:
        raise RuntimeError("No discounted products with usable images remain; nothing was published.")

    import csv
    data_csv=out_dir/f"{SALE_ID}_price_list.csv"
    with data_csv.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(asdict(rows[0]).keys())); w.writeheader()
        for row in rows:w.writerow(asdict(row))
    if PRICE_AUDIT_PDF:
        write_price_audit_pdf(rows,out_dir/f"{SALE_ID}_price_list.pdf")

    a5_pdf=out_dir/f"{OUTPUT_PREFIX}_A5_FOR_EPSON_BOOKLET.pdf"
    a4_pdf=out_dir/f"{OUTPUT_PREFIX}_A4_PREIMPOSED_NO_BOOKLET_SETTING.pdf"
    print("Building A5 brochure...")
    create_a5_brochure(rows,a5_pdf,cards_per_page=cards_per_page)
    print("Imposing A4 booklet...")
    impose_booklet(a5_pdf,a4_pdf)
    print(f"DONE - {len(rows)} products")
    print(a5_pdf.resolve()); print(a4_pdf.resolve()); print(data_csv.resolve())


if __name__ == "__main__":
    main()
