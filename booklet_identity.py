#!/usr/bin/env python3
"""Booklet edition identity, frozen SKU layout registry, and safe SOLD OUT overprints.

The product SKU is the identity. Card position is stored only as metadata for a
specific physical booklet edition, so a later scrape/order change cannot move a
SOLD OUT ribbon onto the wrong product.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_booklet_id(sale_id: str, rows: list[dict]) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fingerprint = hashlib.sha1(
        "|".join((r.get("sku") or "").strip() for r in rows).encode("utf-8")
    ).hexdigest()[:6].upper()
    prefix = "XMAS" if sale_id.lower() == "christmas" else sale_id.upper().replace("_", "-")[:12]
    return f"{prefix}-{stamp}-{fingerprint}"


def _read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _layout(rows: list[dict], cards_per_page: int) -> list[dict]:
    per_page = 4 if cards_per_page <= 4 else 6
    result = []
    for i, row in enumerate(rows):
        sku = (row.get("sku") or "").strip()
        if not sku:
            continue
        result.append({
            "sku": sku,
            "product": (row.get("product") or "").strip(),
            "stock_status_at_generation": (row.get("stock_status") or "active").strip(),
            "sold_out_since": (row.get("sold_out_since") or "").strip(),
            "a5_page": 3 + i // per_page,
            "card_position": 1 + i % per_page,
        })
    return result


def _id_overlay(path: Path, booklet_id: str, page_count: int) -> Path:
    overlay_path = path.with_name(path.stem + "_booklet_id_overlay.pdf")
    w, h = A5
    c = canvas.Canvas(str(overlay_path), pagesize=A5)
    for _ in range(page_count):
        c.setFillColor(HexColor("#D8D8D8"))
        c.setFont("Helvetica", 4.2)
        c.drawRightString(w - 4 * mm, 1.8 * mm, f"Booklet ID: {booklet_id}")
        c.showPage()
    c.save()
    return overlay_path


def stamp_a5_booklet(a5_pdf: Path, booklet_id: str) -> int:
    reader = PdfReader(str(a5_pdf))
    overlay_path = _id_overlay(a5_pdf, booklet_id, len(reader.pages))
    overlay = PdfReader(str(overlay_path))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        page.merge_page(overlay.pages[i])
        writer.add_page(page)
    tmp = a5_pdf.with_name(a5_pdf.stem + "_identified.pdf")
    with tmp.open("wb") as f:
        writer.write(f)
    tmp.replace(a5_pdf)
    overlay_path.unlink(missing_ok=True)
    return len(reader.pages)


def register_booklet(config_path: Path, booklet_id: str | None = None) -> tuple[str, Path]:
    cfg = _load_config(config_path)
    sale_id = cfg["sale"]["id"]
    out_dir = ROOT / cfg.get("output_folder", f"output/{sale_id}")
    output_prefix = cfg.get("output_prefix", sale_id + "_clearance")
    cards_per_page = int(cfg.get("cards_per_page", 6))
    csv_path = out_dir / f"{sale_id}_price_list.csv"
    a5_pdf = out_dir / f"{output_prefix}_A5_FOR_EPSON_BOOKLET.pdf"
    a4_pdf = out_dir / f"{output_prefix}_A4_PREIMPOSED_NO_BOOKLET_SETTING.pdf"
    if not csv_path.exists() or not a5_pdf.exists():
        raise FileNotFoundError("Build the booklet first; price CSV/A5 PDF is missing.")

    rows = _read_rows(csv_path)
    booklet_id = booklet_id or _make_booklet_id(sale_id, rows)
    page_count = stamp_a5_booklet(a5_pdf, booklet_id)

    # Re-impose from the now-identified A5 source so the physical A4 booklet carries the same ID.
    from vivamk_clearance_booklet import impose_booklet
    impose_booklet(a5_pdf, a4_pdf)

    registry = out_dir / "booklet_editions"
    registry.mkdir(parents=True, exist_ok=True)
    manifest = {
        "booklet_id": booklet_id,
        "sale_id": sale_id,
        "display_name": cfg["sale"].get("display_name", sale_id),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_mode": cfg.get("data_source", {}).get("mode", ""),
        "cards_per_page": cards_per_page,
        "a5_page_count": page_count,
        "a5_pdf": str(a5_pdf.relative_to(ROOT)),
        "a4_pdf": str(a4_pdf.relative_to(ROOT)),
        "products": _layout(rows, cards_per_page),
    }
    manifest_path = registry / f"{booklet_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (registry / "CURRENT_BOOKLET_ID.txt").write_text(booklet_id + "\n", encoding="utf-8")
    print(f"Booklet ID: {booklet_id}")
    print(f"Frozen layout: {manifest_path}")
    return booklet_id, manifest_path


def _sold_out_skus(sale_id: str) -> set[str]:
    result: set[str] = set()
    state_path = ROOT / "monitor_state" / f"{sale_id}.json"
    if state_path.exists():
        data = json.loads(state_path.read_text(encoding="utf-8"))
        for key, item in data.get("products", {}).items():
            if item.get("status") == "sold_out":
                sku = (item.get("sku") or key or "").strip()
                if sku:
                    result.add(sku)
    return result


def _card_box(position: int, cards_per_page: int):
    width, height = A5
    margin_x = 3.5 * mm
    top = height - 30 * mm
    bottom = 25.5 * mm
    gap = 1.8 * mm
    cols, rws = (2, 2) if cards_per_page <= 4 else (2, 3)
    card_w = (width - 2 * margin_x - gap) / cols
    card_h = (top - bottom - (rws - 1) * gap) / rws
    idx = position - 1
    rr, cc = divmod(idx, cols)
    x = margin_x + cc * (card_w + gap)
    y = top - (rr + 1) * card_h - rr * gap
    pad = 2.4 * mm
    compact = card_h < 92 * mm
    image_h = card_h * (0.49 if compact else 0.48)
    image_y = y + card_h - image_h - pad
    return x + pad, image_y, card_w - 2 * pad, image_h


def _draw_ribbon(c: canvas.Canvas, x: float, y: float, w: float, h: float):
    c.saveState()
    c.translate(x + w / 2, y + h / 2)
    c.rotate(18)
    ribbon_h = min(11.5 * mm, h * 0.34)
    ribbon_w = min(w * 1.12, 68 * mm)
    c.setFillColor(HexColor("#B5121B"))
    c.setStrokeColor(white)
    c.setLineWidth(1.2)
    c.roundRect(-ribbon_w / 2, -ribbon_h / 2, ribbon_w, ribbon_h, 2 * mm, stroke=1, fill=1)
    c.setFillColor(white)
    font_size = 16 if ribbon_h >= 10 * mm else 13
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(0, -font_size * 0.32, "SOLD OUT")
    c.restoreState()


def make_overprint(config_path: Path, booklet_id: str | None = None) -> Path:
    cfg = _load_config(config_path)
    sale_id = cfg["sale"]["id"]
    out_dir = ROOT / cfg.get("output_folder", f"output/{sale_id}")
    registry = out_dir / "booklet_editions"
    if not booklet_id:
        current = registry / "CURRENT_BOOKLET_ID.txt"
        if not current.exists():
            raise FileNotFoundError("No CURRENT_BOOKLET_ID.txt. Register a booklet edition first.")
        booklet_id = current.read_text(encoding="utf-8").strip()
    manifest_path = registry / f"{booklet_id}.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Unknown booklet ID: {booklet_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sale_id") != sale_id or manifest.get("booklet_id") != booklet_id:
        raise RuntimeError("Booklet ID validation failed; refusing to create an overprint.")

    sold = _sold_out_skus(sale_id)
    products = {p["sku"]: p for p in manifest.get("products", [])}
    matched = sorted(sold.intersection(products))
    overprint_dir = out_dir / "overprints"
    overprint_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = overprint_dir / f"{booklet_id}_SOLD_OUT_OVERPRINT.pdf"

    c = canvas.Canvas(str(out_pdf), pagesize=A5)
    page_count = int(manifest["a5_page_count"])
    by_page: dict[int, list[dict]] = {}
    for sku in matched:
        by_page.setdefault(int(products[sku]["a5_page"]), []).append(products[sku])
    for page_no in range(1, page_count + 1):
        for p in by_page.get(page_no, []):
            x, y, w, h = _card_box(int(p["card_position"]), int(manifest["cards_per_page"]))
            _draw_ribbon(c, x, y, w, h)
        # Visible identity check. Same ID is already printed on the underlying booklet.
        c.setFillColor(HexColor("#777777"))
        c.setFont("Helvetica", 4.2)
        c.drawRightString(A5[0] - 4 * mm, 1.8 * mm, f"OVERPRINT FOR: {booklet_id}")
        c.showPage()
    c.save()

    report = overprint_dir / f"{booklet_id}_OVERPRINT_VALIDATION.txt"
    report.write_text(
        "\n".join([
            f"BOOKLET ID: {booklet_id}",
            f"SALE: {sale_id}",
            f"SOLD OUT SKUs in current history: {len(sold)}",
            f"SOLD OUT SKUs present in this booklet: {len(matched)}",
            "SKUs: " + (", ".join(matched) if matched else "NONE"),
            "",
            "Safety rule: ribbon positions came only from this booklet ID's frozen SKU map.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Overprint: {out_pdf}")
    print(f"Validated SKUs: {', '.join(matched) if matched else 'none'}")
    return out_pdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--register", action="store_true", help="Stamp/register the just-built booklet")
    ap.add_argument("--overprint", action="store_true", help="Create SKU-validated SOLD OUT overprint")
    ap.add_argument("--booklet-id", default=None)
    args = ap.parse_args()
    if not args.register and not args.overprint:
        ap.error("Choose --register or --overprint")
    if args.register:
        register_booklet(args.config, args.booklet_id)
    if args.overprint:
        make_overprint(args.config, args.booklet_id)


if __name__ == "__main__":
    main()
