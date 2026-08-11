#!/usr/bin/env python3
"""Compare the Christmas PDF source list with the live Christmas category.

This is deliberately an audit only. It does not change christmas.json or the
operational booklet source. Once repeated audits show that the live category is
complete/reliable, Christmas can be migrated to category mode.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "configs" / "christmas.json"
OUT_DIR = ROOT / "output" / "christmas" / "live_audit"


def load_engine():
    path = ROOT / "vivamk_clearance_booklet.py"
    spec = importlib.util.spec_from_file_location("vivamk_christmas_audit_engine", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def key(row):
    return (row.sku or "").strip()


def main() -> int:
    engine = load_engine()
    cfg = engine.load_config(CONFIG)
    engine.apply_config(cfg)

    pdf_path = CONFIG.resolve().parent.parent / cfg["data_source"]["price_pdf"]
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    print("Reading Christmas PDF source list...")
    pdf_rows = engine.extract_sale_rows(pdf_path)
    pdf = {key(r): r for r in pdf_rows if key(r)}

    print("Scraping live Christmas category...")
    live_rows = engine.scrape_category_rows(
        engine.CATEGORY_URL,
        int(cfg.get("max_category_pages", 30)),
    )
    live = {key(r): r for r in live_rows if key(r)}

    print("Checking which live products can also provide usable images/details...")
    enriched = engine.enrich_category_rows(
        live_rows,
        OUT_DIR / "cache",
        delay=float(cfg.get("request_delay_seconds", 0.35)),
    )
    usable = {key(r): r for r in enriched if key(r)}

    all_skus = sorted(set(pdf) | set(live))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "christmas_pdf_vs_live_category.csv"

    counts = {
        "PDF_ONLY": 0,
        "LIVE_ONLY": 0,
        "IN_BOTH_USABLE": 0,
        "IN_BOTH_NO_USABLE_IMAGE": 0,
    }

    with report.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "sku", "product", "pdf_listed", "live_found", "usable_image",
            "status", "pdf_was", "pdf_now", "live_was", "live_now", "product_url",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for sku in all_skus:
            p = pdf.get(sku)
            l = live.get(sku)
            u = usable.get(sku)

            if p and l and u:
                status = "IN_BOTH_USABLE"
            elif p and l:
                status = "IN_BOTH_NO_USABLE_IMAGE"
            elif p:
                status = "PDF_ONLY"
            else:
                status = "LIVE_ONLY"
            counts[status] += 1

            source = l or p
            w.writerow({
                "sku": sku,
                "product": getattr(source, "product", ""),
                "pdf_listed": "YES" if p else "NO",
                "live_found": "YES" if l else "NO",
                "usable_image": "YES" if u else "NO",
                "status": status,
                "pdf_was": getattr(p, "was", "") if p else "",
                "pdf_now": getattr(p, "now", "") if p else "",
                "live_was": getattr(l, "was", "") if l else "",
                "live_now": getattr(l, "now", "") if l else "",
                "product_url": getattr(l, "product_url", "") if l else "",
            })

    summary = OUT_DIR / "christmas_pdf_vs_live_category_summary.txt"
    lines = [
        "CHRISTMAS PDF vs LIVE CATEGORY AUDIT",
        "",
        f"PDF source items: {len(pdf)}",
        f"Live category items: {len(live)}",
        f"Live products with usable images/details: {len(usable)}",
        "",
        f"In both and usable: {counts['IN_BOTH_USABLE']}",
        f"In both but no usable image: {counts['IN_BOTH_NO_USABLE_IMAGE']}",
        f"PDF only: {counts['PDF_ONLY']}",
        f"Live only: {counts['LIVE_ONLY']}",
        "",
        "This audit does NOT change the Christmas booklet source.",
        "Use repeated clean comparisons to decide when Christmas can safely move to category mode.",
        "",
        f"CSV: {report}",
    ]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
