#!/usr/bin/env python3
# VIVAMK CLEARANCE CHRISTMAS VERSION v1.05
# Updated: 2026-08-09 02:02 +0100
# Changes: Uses the complete holly sprigs taken directly from the approved preferred-style reference; no stretched or truncated foliage assets.
# Changes: Adds the preferred dark-green/gold banner footer to product, intro, cover and booklet-padding pages.
# Changes: Required booklet padding pages are now designed Christmas/order pages rather than blank pages; preferred opportunity artwork remains the physical final page.
# Changes: Exact preferred opportunity_back_cover.png is mandatory; no fallback artwork is permitted.
"""
VivaMK Christmas Clearance Booklet Generator
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
from urllib.parse import urljoin

import fitz  # PyMuPDF
import requests
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
OPPORTUNITY_ART_FILE = "opportunity_back_cover.png"


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
    global PRO_FOLIAGE_RIGHT_FILE, PRO_FOLIAGE_LEFT_FILE, PRO_FOLIAGE_FOOTER_FILE, OPPORTUNITY_ART_FILE

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
    PRO_FOLIAGE_RIGHT_FILE = cfg.get("pro_foliage_right_file", PRO_FOLIAGE_RIGHT_FILE)
    PRO_FOLIAGE_LEFT_FILE = cfg.get("pro_foliage_left_file", PRO_FOLIAGE_LEFT_FILE)
    PRO_FOLIAGE_FOOTER_FILE = cfg.get("pro_foliage_footer_file", PRO_FOLIAGE_FOOTER_FILE)
    OPPORTUNITY_ART_FILE = cfg.get("opportunity_art_file", OPPORTUNITY_ART_FILE)


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

            cache[row.sku] = asdict(row)
            data_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
            time.sleep(delay)

        # If metadata is cached but the image was removed, re-download it.
        if row.image_url and (not row.image_file or not Path(row.image_file).exists()):
            row.image_file = download_image(session, row.image_url, image_dir, row.sku)
            cache[row.sku] = asdict(row)
            data_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    return rows


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
    """Preferred-style Christmas header using complete holly sprigs from the approved reference."""
    band_h = 27 * mm
    c.setFillColor(DARK_GREEN)
    c.rect(0, height - band_h, width, band_h, stroke=0, fill=1)

    left_art = local_asset(PRO_FOLIAGE_LEFT_FILE)
    right_art = local_asset(PRO_FOLIAGE_RIGHT_FILE)

    # Do not stretch these assets. They are complete reference crops and are scaled proportionally.
    def place_patch(path: Path, x: float, y: float, max_w: float, max_h: float, anchor_right: bool = False):
        with Image.open(path) as im:
            iw, ih = im.size
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        px = x - dw if anchor_right else x
        py = y + (max_h - dh) / 2
        c.drawImage(str(path), px, py, dw, dh, preserveAspectRatio=True, mask="auto")

    if left_art.exists():
        place_patch(left_art, 1.5 * mm, height - 25.5 * mm, 22 * mm, 22 * mm)
    if right_art.exists():
        place_patch(right_art, width - 1.5 * mm, height - 25.5 * mm, 23 * mm, 22 * mm, anchor_right=True)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17.0)
    c.drawCentredString(width / 2, height - 12.7 * mm, title)
    if subtitle:
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawCentredString(width / 2, height - 20.0 * mm, subtitle)


def draw_banner_footer(c: canvas.Canvas, width: float, page_no: int | None = None):
    """Preferred dark-green/gold footer banner with the complete reference holly cluster."""
    h = 24 * mm
    c.setFillColor(DARK_GREEN)
    c.rect(0, 0, width, h, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(5 * mm, h - 1.7 * mm, width - 5 * mm, h - 1.7 * mm)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.7)
    c.drawString(8 * mm, 15.0 * mm, "ORDER ONLINE:")
    c.setFillColor(colors.white)
    order_display = "stevegiergiel.vivamknetwork.co.uk/clearance/christmas-sale.html"
    max_url_w = width - 48 * mm
    url_size = 5.8
    while url_size > 4.6 and stringWidth(order_display, "Helvetica-Bold", url_size) > max_url_w:
        url_size -= 0.2
    c.setFont("Helvetica-Bold", url_size)
    c.drawString(8 * mm, 10.3 * mm, order_display)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(8 * mm, 4.3 * mm, f"TEXT ORDERS: {PHONE}")

    footer_art = local_asset(PRO_FOLIAGE_FOOTER_FILE)
    if footer_art.exists():
        with Image.open(footer_art) as im:
            iw, ih = im.size
        max_w, max_h = 27 * mm, 22 * mm
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(
            str(footer_art), width - dw - 1.0 * mm, 1.0 * mm,
            dw, dh, preserveAspectRatio=True, mask="auto"
        )

    if page_no is not None:
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 5.5)
        c.drawRightString(width - 31 * mm, 4.4 * mm, f"Page {page_no}")

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
        return

    with Image.open(image_file) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx = x + (w - dw) / 2
    dy = y + (h - dh) / 2
    c.drawImage(image_file, dx, dy, dw, dh, preserveAspectRatio=True, mask="auto")


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
    price_block_h = 16.5 * mm if compact else 19 * mm

    image_h = h * (0.49 if compact else 0.48)
    image_y = y + h - image_h - pad
    draw_image_contain(c, row.image_file, x + pad, image_y, w - 2 * pad, image_h)

    badge_r = 6.5 * mm if compact else 7.5 * mm
    bx = x + w - 8.0 * mm
    by = y + h - 8.0 * mm
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
        desc = row.description or "Christmas clearance special - limited stock while available."
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

    was_y = panel_y + panel_h - 4.9 * mm
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

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 5.9 if compact else 6.7)
    c.drawRightString(right, was_y, f"SAVE {row.saving}")

    now_y = panel_y + 2.4 * mm
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 12.0 if compact else 14.0)
    c.drawString(left, now_y, f"NOW {row.now}")

    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica", 5.0 if compact else 5.8)
    c.drawRightString(right, now_y + 0.8, f"SKU {row.sku}")

    c.restoreState()


def draw_cover(c: canvas.Canvas, width: float, height: float):
    """Front cover locked to the preferred Christmas style."""
    c.setFillColor(DARK_GREEN)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_festive_header(c, width, height, "CHRISTMAS CLEARANCE", "Limited stocks - order your favourites quickly!")

    c.setFillColor(CREAM)
    c.roundRect(11 * mm, 46 * mm, width - 22 * mm, height - 82 * mm, 5 * mm, stroke=0, fill=1)

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 52 * mm, f"{TITLE_OWNER} BRING YOU")
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 25)
    c.drawCentredString(width / 2, height - 72 * mm, "CHRISTMAS")
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(width / 2, height - 89 * mm, "CLEARANCE")
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 19)
    c.drawCentredString(width / 2, height - 104 * mm, "SPECIAL OFFERS")

    c.setFillColor(RED)
    c.roundRect(22 * mm, height - 137 * mm, width - 44 * mm, 20 * mm, 4 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(width / 2, height - 127 * mm, "AMAZING PRICES")
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(width / 2, height - 134 * mm, "Once they're gone, they're gone!")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, 63 * mm, "BE QUICK - PICK YOUR FAVOURITES")
    c.setFont("Helvetica", 8.3)
    c.drawCentredString(width / 2, 55 * mm, f"Text orders: {PHONE}")
    c.drawCentredString(width / 2, 49 * mm, f"Email: {EMAIL}")

    draw_banner_footer(c, width)

def draw_intro(c: canvas.Canvas, width: float, height: float):
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_festive_header(c, width, height, "A SPECIAL THANK YOU")

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
    draw_festive_header(c, width, height, "CHRISTMAS CLEARANCE", "Limited stocks - order your favourites quickly")

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
    subtitle = "For your valued custom" if index == 1 else "Christmas clearance - while stocks last"
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
            "in these Christmas clearance offers."
        ]
    else:
        c.drawCentredString(width / 2, height - 74 * mm, "ORDER YOUR FAVOURITES QUICKLY")
        c.setFont("Helvetica", 9.2)
        lines = [
            f"Text your requirements to {PHONE}",
            f"or email {EMAIL}",
            "Please include your name and postal address",
            "if we may not recognise your telephone number."
        ]
    yy = height - 91 * mm
    c.setFillColor(INK)
    for line in lines:
        c.drawCentredString(width / 2, yy, line)
        yy -= 8 * mm

    c.setFillColor(RED)
    c.roundRect(28 * mm, 72 * mm, width - 56 * mm, 18 * mm, 4 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(width / 2, 82 * mm, "ONCE THEY'RE GONE, THEY'RE GONE!")

    draw_banner_footer(c, width)

def draw_back_cover(c: canvas.Canvas, width: float, height: float):
    """
    Physical back cover: use the user's supplied RIGHT-HAND opportunity advert intact.
    It is scaled proportionally and centred; it is never rebuilt from separately positioned elements.
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
        "preferred top-left holly": local_asset(PRO_FOLIAGE_LEFT_FILE),
        "preferred top-right holly": local_asset(PRO_FOLIAGE_RIGHT_FILE),
        "preferred footer holly": local_asset(PRO_FOLIAGE_FOOTER_FILE),
        "preferred opportunity back cover": local_asset(OPPORTUNITY_ART_FILE),
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required preferred artwork is missing; generation stopped rather than using fallback artwork.\n  - "
            + "\n  - ".join(missing)
        )


# -----------------------------
# Main
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Create a VivaMK Christmas clearance booklet.")
    ap.add_argument("sale_pdf", type=Path, nargs="?", help="Optional override for the source price-list PDF")
    ap.add_argument("--config", type=Path, default=Path("booklet_config.json"), help="JSON configuration file")
    ap.add_argument("--out", type=Path, default=None, help="Optional override for the output folder")
    ap.add_argument("--refresh", action="store_true", help="Ignore cached website data and download again")
    ap.add_argument(
        "--cards-per-page",
        type=int,
        choices=[4, 6],
        default=None,
        help="Optional override: 4 = larger/eye-catching; 6 = more compact",
    )
    ap.add_argument("--delay", type=float, default=None, help="Optional override for request delay in seconds")
    args = ap.parse_args()

    cfg = load_config(args.config)
    apply_config(cfg)
    validate_required_assets()

    sale_pdf = args.sale_pdf or Path(cfg.get("source_price_file", "Christmas_Sale_GBP1.pdf"))
    out_dir = args.out or Path(cfg.get("output_folder", "christmas_booklet_output"))
    cards_per_page = args.cards_per_page or int(cfg.get("cards_per_page", 4))
    delay = args.delay if args.delay is not None else float(cfg.get("request_delay_seconds", 0.35))

    if not sale_pdf.exists():
        ap.error(f"File not found: {sale_pdf}. Update source_price_file in {args.config} or pass a PDF filename.")

    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache"

    print("Extracting clearance list...")
    rows = extract_sale_rows(sale_pdf)
    print(f"Found {len(rows)} sale products.")

    print("\nLooking up products on the Steve & Jus VivaMK web shop...")
    rows = enrich_rows(rows, cache_dir, refresh=args.refresh, delay=delay)

    before = len(rows)
    rows = [r for r in rows if r.image_file and Path(r.image_file).exists()]
    removed = before - len(rows)
    if removed:
        print(f"Removed {removed} item(s) because no usable product image was available.")
    if not rows:
        raise RuntimeError("No products with usable images remain; publication was not created.")

    # Save an audit copy so it is easy to see exactly what was collected.
    data_csv = out_dir / "products_collected.csv"
    with data_csv.open("w", encoding="utf-8-sig", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for row in rows:
            w.writerow(asdict(row))

    a5_pdf = out_dir / "christmas_clearance_A5_FOR_EPSON_BOOKLET.pdf"
    booklet_pdf = out_dir / "christmas_clearance_A4_PREIMPOSED_NO_BOOKLET_SETTING.pdf"

    print("\nBuilding A5 brochure...")
    create_a5_brochure(rows, a5_pdf, cards_per_page=cards_per_page)

    print("Imposing A4 booklet...")
    impose_booklet(a5_pdf, booklet_pdf)

    print("\nDONE")
    print(f"Reading-order brochure: {a5_pdf.resolve()}")
    print(f"Print-ready booklet:     {booklet_pdf.resolve()}")
    print(f"Collected product data:  {data_csv.resolve()}")
    print("\nPRINTING - USE ONE METHOD ONLY:")
    print("  Epson Booklet mode: open christmas_clearance_A5_FOR_EPSON_BOOKLET.pdf")
    print("  OR manual duplex: open christmas_clearance_A4_PREIMPOSED_NO_BOOKLET_SETTING.pdf")
    print("  For the A4 pre-imposed PDF, printer Booklet mode MUST be OFF.")
    print("  A4 manual duplex: landscape, flip SHORT edge, Actual Size / 100%.")


if __name__ == "__main__":
    main()
