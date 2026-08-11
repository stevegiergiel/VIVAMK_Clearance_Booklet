#!/usr/bin/env python3
"""
VivaMK daily catalogue monitor.

Daily behaviour:
- Scans all five configured sales.
- A product is considered currently printable only if a usable image can be obtained.
- Compares today's printable SKUs with the last successful snapshot.
- Any apparent disappearance is verified with a second scan before action.
- If confirmed, rebuilds only affected PDF booklet(s) and iframe page(s).
- Commits/pushes changed site pages so GitHub Pages can redeploy.
- Sends a heartbeat email on EVERY successful run, including no-change days.
- Sends an error heartbeat if a scan/build/deploy step fails.

First run establishes a baseline and does not request reprinting.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "configs"
STATE_DIR = ROOT / "monitor_state"
LOG_DIR = ROOT / "monitor_logs"
TMP_DIR = ROOT / "monitor_tmp"
CACHE_DIR = ROOT / "monitor_cache"
SETTINGS_FILE = ROOT / "daily_monitor_config.json"

SALE_CONFIGS = [
    "christmas.json",
    "mega_sale.json",
    "pets.json",
    "personalised.json",
    "winter_warmers.json",
]


CHRISTMAS_AUDIT_DIR = ROOT / "output" / "christmas" / "live_audit"
CHRISTMAS_AUDIT_STATE = STATE_DIR / "christmas_live_audit.json"



def log(msg: str, lines: list[str]) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    lines.append(line)


def run(cmd: list[str], *, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check)


def load_engine():
    import importlib.util
    path = ROOT / "vivamk_clearance_booklet.py"
    spec = importlib.util.spec_from_file_location("vivamk_monitor_engine", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_settings() -> dict[str, Any]:
    """
    Load monitor settings plus email settings from email_config.ini.

    email_config.ini is authoritative for SMTP/mail values.
    daily_monitor_config.json remains authoritative for git/safety settings.
    """
    settings: dict[str, Any] = {}

    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

    ini_path = ROOT / "email_config.ini"
    if not ini_path.exists():
        raise FileNotFoundError(
            "Missing email_config.ini. Place the supplied email config beside vivamk_daily_monitor.py."
        )

    cp = configparser.ConfigParser()
    cp.read(ini_path, encoding="utf-8")

    sender = cp.get("Email", "sender_email", fallback="").strip()
    app_password = cp.get("Email", "app_password", fallback="").strip()

    smtp_server = cp.get("Settings", "smtp_server", fallback="smtp.gmail.com").strip()
    smtp_port = cp.getint("Settings", "smtp_port", fallback=587)
    smtp_user = cp.get("Settings", "smtp_user", fallback="").strip()
    smtp_password = cp.get("Settings", "smtp_password", fallback="").strip()
    to_email = cp.get("Settings", "to_email", fallback="").strip()

    # The supplied INI contains template placeholders in some Settings values.
    # If left as placeholders, use the actual sender_email/app_password values above.
    placeholder_values = {
        "",
        "your_email@gmail.com",
        "your_app_password",
        "change_me",
        "changeme",
    }

    if smtp_user.lower() in placeholder_values:
        smtp_user = sender

    if smtp_password.lower() in placeholder_values:
        smtp_password = app_password

    if to_email.lower() in placeholder_values:
        to_email = sender

    settings["email"] = {
        "enabled": True,
        "smtp_host": smtp_server,
        "smtp_port": smtp_port,
        "smtp_starttls": smtp_port != 465,
        "smtp_ssl": smtp_port == 465,
        "smtp_username": smtp_user,
        "smtp_password": smtp_password,
        "smtp_password_env": "",
        "from": sender or smtp_user,
        "to": [to_email] if to_email else ([sender] if sender else []),
    }

    return settings

def send_email(settings: dict[str, Any], subject: str, body: str) -> None:
    email_cfg = settings.get("email", {})
    if not email_cfg.get("enabled", True):
        print("EMAIL DISABLED:", subject)
        print(body)
        return

    host = email_cfg.get("smtp_host", "").strip()
    port = int(email_cfg.get("smtp_port", 587))
    username = email_cfg.get("smtp_username", "").strip()
    password_env = email_cfg.get("smtp_password_env", "").strip()
    password = os.environ.get(password_env, "") if password_env else email_cfg.get("smtp_password", "")
    sender = email_cfg.get("from", username).strip()
    recipients = email_cfg.get("to", [])
    if isinstance(recipients, str):
        recipients = [recipients]

    missing = [
        name for name, val in {
            "smtp_host": host,
            "from": sender,
            "to": recipients,
        }.items() if not val
    ]
    if missing:
        raise RuntimeError("Email configuration incomplete: " + ", ".join(missing))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    use_ssl = bool(email_cfg.get("smtp_ssl", False))
    use_starttls = bool(email_cfg.get("smtp_starttls", not use_ssl))

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=45) as smtp:
        if not use_ssl:
            smtp.ehlo()
            if use_starttls:
                smtp.starttls()
                smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def row_key(row) -> str:
    sku = (getattr(row, "sku", "") or "").strip()
    if sku:
        return sku
    return (getattr(row, "product_url", "") or getattr(row, "product", "") or "").strip()


def scan_sale(engine, cfg_path: Path, pass_no: int, lines: list[str]) -> dict[str, dict]:
    """Scan a sale and persist a known-good copy of every active product image."""
    cfg = engine.load_config(cfg_path)
    engine.apply_config(cfg)

    sale_id = cfg["sale"]["id"]
    mode = cfg["data_source"]["mode"].lower()
    cache_dir = TMP_DIR / sale_id / f"pass{pass_no}"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    persistent = CACHE_DIR / sale_id
    persistent.mkdir(parents=True, exist_ok=True)

    log(f"{sale_id}: scan pass {pass_no} ({mode})", lines)

    if mode == "pdf":
        pdf = cfg_path.resolve().parent.parent / cfg["data_source"]["price_pdf"]
        source_rows = engine.extract_sale_rows(pdf)
        rows = engine.enrich_rows(
            source_rows,
            cache_dir,
            refresh=True,
            delay=float(cfg.get("request_delay_seconds", 0.35)),
        )
        rows = [r for r in rows if r.image_file and Path(r.image_file).exists()]
    elif mode == "category":
        source_rows = engine.scrape_category_rows(
            engine.CATEGORY_URL,
            int(cfg.get("max_category_pages", 30)),
        )
        rows = engine.enrich_category_rows(
            source_rows,
            cache_dir,
            delay=float(cfg.get("request_delay_seconds", 0.35)),
        )
    else:
        raise RuntimeError(f"{sale_id}: unsupported data source mode {mode}")

    result: dict[str, dict] = {}
    for r in rows:
        key = row_key(r)
        if not key:
            continue

        image_src = Path(r.image_file) if r.image_file else None
        persistent_image = ""
        if image_src and image_src.exists():
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (r.sku or key))[:80] or "product"
            ext = image_src.suffix.lower() or ".jpg"
            dest = persistent / f"{safe}{ext}"
            shutil.copy2(image_src, dest)
            persistent_image = str(dest.relative_to(ROOT))

        result[key] = {
            "sku": (r.sku or "").strip(),
            "product": (r.product or "").strip(),
            "was": (r.was or "").strip(),
            "now": (r.now or "").strip(),
            "saving": (r.saving or "").strip(),
            "percent": (r.percent or "").strip(),
            "product_url": (r.product_url or "").strip(),
            "description": (r.description or "").strip(),
            "image_url": (r.image_url or "").strip(),
            "image_file": persistent_image,
            "status": "active",
            "sold_out_since": "",
        }

    log(f"{sale_id}: {len(result)} printable products found", lines)
    return result


def state_path(sale_id: str) -> Path:
    return STATE_DIR / f"{sale_id}.json"


def pending_state_path(sale_id: str) -> Path:
    return STATE_DIR / f"{sale_id}.pending.json"


def write_state_file(path: Path, sale_id: str, display_name: str, products: dict[str, dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "sale_id": sale_id,
        "display_name": display_name,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "products": products,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")



def load_state(sale_id: str) -> dict[str, dict] | None:
    p = state_path(sale_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("products", {})


def save_state(sale_id: str, display_name: str, products: dict[str, dict]) -> None:
    write_state_file(state_path(sale_id), sale_id, display_name, products)


def rebuild(cfg_path: Path, iframe_path: str, state_file: Path, lines: list[str]) -> None:
    log(f"Rebuilding booklet: {cfg_path.name}", lines)
    cp = run([
        sys.executable, "vivamk_clearance_booklet.py",
        "--config", str(cfg_path), "--refresh",
        "--state-file", str(state_file),
    ])
    if cp.stdout:
        lines.extend(cp.stdout.rstrip().splitlines())
    if cp.stderr:
        lines.extend(cp.stderr.rstrip().splitlines())

    log(f"Rebuilding iframe: {cfg_path.name}", lines)
    cp = run([
        sys.executable, "vivamk_clearance_iframe.py",
        "--config", str(cfg_path),
        "--state-file", str(state_file),
    ])
    if cp.stdout:
        lines.extend(cp.stdout.rstrip().splitlines())
    if cp.stderr:
        lines.extend(cp.stderr.rstrip().splitlines())


def git_publish(affected_iframe_paths: list[str], settings: dict[str, Any], lines: list[str]) -> str:
    if not affected_iframe_paths:
        return "No iframe changes required."

    git_cfg = settings.get("git", {})
    if not git_cfg.get("enabled", True):
        return "Iframe files regenerated locally; Git publish is disabled in daily_monitor_config.json."

    # Add only affected live site folders.
    add_cmd = ["git", "add"]
    add_cmd.extend([f"site/{p}/index.html" for p in affected_iframe_paths])
    run(add_cmd)

    status = run(["git", "status", "--porcelain", "--", "site"]).stdout.strip()
    if not status:
        log("Generated iframe HTML is unchanged; nothing to push.", lines)
        return "Iframe rebuilt; generated HTML was unchanged so no Git push was needed."

    message = "Daily catalogue monitor: refresh affected iframe pages"
    run(["git", "commit", "-m", message])
    run(["git", "push"])
    log("Affected iframe pages committed and pushed.", lines)
    return "Affected iframe pages were committed and pushed. GitHub Pages will redeploy automatically."



def run_christmas_live_audit(engine, lines: list[str]) -> dict[str, Any]:
    """
    Compare the Christmas PDF source with the live Christmas category.

    Audit only: never changes the operational Christmas data source.
    Saves a daily CSV plus a compact JSON snapshot used for change detection.
    """
    import csv

    cfg_path = CONFIG_DIR / "christmas.json"
    cfg = engine.load_config(cfg_path)
    engine.apply_config(cfg)

    pdf_path = cfg_path.resolve().parent.parent / cfg["data_source"]["price_pdf"]
    if not pdf_path.exists():
        raise FileNotFoundError(f"Christmas audit PDF not found: {pdf_path}")

    log("Christmas audit: reading PDF source list.", lines)
    pdf_rows = engine.extract_sale_rows(pdf_path)
    pdf = {(r.sku or "").strip(): r for r in pdf_rows if (r.sku or "").strip()}

    log("Christmas audit: scraping live Christmas category.", lines)
    live_rows = engine.scrape_category_rows(
        engine.CATEGORY_URL,
        int(cfg.get("max_category_pages", 30)),
    )
    live = {(r.sku or "").strip(): r for r in live_rows if (r.sku or "").strip()}

    audit_cache = CHRISTMAS_AUDIT_DIR / "cache"
    CHRISTMAS_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    log("Christmas audit: checking usable images/details.", lines)
    enriched = engine.enrich_category_rows(
        live_rows,
        audit_cache,
        delay=float(cfg.get("request_delay_seconds", 0.35)),
    )
    usable = {(r.sku or "").strip(): r for r in enriched if (r.sku or "").strip()}

    pdf_only = sorted(set(pdf) - set(live))
    live_only = sorted(set(live) - set(pdf))
    common = sorted(set(pdf) & set(live))
    common_usable = [sku for sku in common if sku in usable]
    image_failures = sorted(set(live) - set(usable))

    price_mismatches = []
    for sku in common:
        p = pdf[sku]
        l = live[sku]
        if (p.was or "").strip() != (l.was or "").strip() or (p.now or "").strip() != (l.now or "").strip():
            price_mismatches.append({
                "sku": sku,
                "product": (l.product or p.product or "").strip(),
                "pdf_was": (p.was or "").strip(),
                "pdf_now": (p.now or "").strip(),
                "live_was": (l.was or "").strip(),
                "live_now": (l.now or "").strip(),
            })

    previous = None
    if CHRISTMAS_AUDIT_STATE.exists():
        try:
            previous = json.loads(CHRISTMAS_AUDIT_STATE.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "pdf_count": len(pdf),
        "live_count": len(live),
        "common_count": len(common),
        "common_usable_count": len(common_usable),
        "pdf_only_count": len(pdf_only),
        "live_only_count": len(live_only),
        "image_failure_count": len(image_failures),
        "price_mismatch_count": len(price_mismatches),
        "pdf_only_skus": pdf_only,
        "live_only_skus": live_only,
        "image_failure_skus": image_failures,
        "price_mismatches": price_mismatches,
    }

    # Determine meaningful change against yesterday/last successful audit.
    if previous:
        tracked = [
            "pdf_count", "live_count", "common_count", "common_usable_count",
            "pdf_only_count", "live_only_count", "image_failure_count",
            "price_mismatch_count",
        ]
        changed_fields = [k for k in tracked if previous.get(k) != result.get(k)]
        set_changes = (
            previous.get("pdf_only_skus", []) != pdf_only
            or previous.get("live_only_skus", []) != live_only
            or previous.get("image_failure_skus", []) != image_failures
        )
        result["changed_since_previous"] = bool(changed_fields or set_changes)
        result["changed_fields"] = changed_fields
    else:
        result["changed_since_previous"] = None
        result["changed_fields"] = []

    # Migration confidence: deliberately conservative.
    # GREEN requires perfect live usability, no price mismatch, and at least
    # 3 consecutive stable successful audits. Consecutive count is maintained here.
    previous_streak = int(previous.get("stable_streak", 0)) if previous else 0
    clean = (len(image_failures) == 0 and len(price_mismatches) == 0)
    if previous and result["changed_since_previous"] is False and clean:
        stable_streak = previous_streak + 1
    elif clean:
        stable_streak = 1
    else:
        stable_streak = 0
    result["stable_streak"] = stable_streak

    audit_cfg = load_settings().get("christmas_audit", {})
    confidence_days = int(audit_cfg.get("stable_audits_for_confidence", 3))
    review_days = int(audit_cfg.get("stable_audits_for_review", 5))

    if not clean:
        migration_status = "INVESTIGATE"
    elif stable_streak >= review_days:
        migration_status = "READY TO REVIEW SWITCH"
    elif stable_streak >= confidence_days:
        migration_status = "STABLE - BUILDING CONFIDENCE"
    else:
        migration_status = "MONITORING"
    result["migration_status"] = migration_status

    # Write dated CSV and rolling latest CSV.
    date_tag = datetime.now().strftime("%Y%m%d")
    fields = [
        "sku", "product", "pdf_listed", "live_found", "usable_image", "status",
        "pdf_was", "pdf_now", "live_was", "live_now", "product_url",
    ]
    rows_out = []
    for sku in sorted(set(pdf) | set(live)):
        pr = pdf.get(sku)
        lr = live.get(sku)
        ur = usable.get(sku)
        if pr and lr and ur:
            status = "IN_BOTH_USABLE"
        elif pr and lr:
            status = "IN_BOTH_NO_USABLE_IMAGE"
        elif pr:
            status = "PDF_ONLY"
        else:
            status = "LIVE_ONLY"
        source = lr or pr
        rows_out.append({
            "sku": sku,
            "product": getattr(source, "product", "") or "",
            "pdf_listed": "YES" if pr else "NO",
            "live_found": "YES" if lr else "NO",
            "usable_image": "YES" if ur else "NO",
            "status": status,
            "pdf_was": getattr(pr, "was", "") if pr else "",
            "pdf_now": getattr(pr, "now", "") if pr else "",
            "live_was": getattr(lr, "was", "") if lr else "",
            "live_now": getattr(lr, "now", "") if lr else "",
            "product_url": getattr(lr, "product_url", "") if lr else "",
        })

    for csv_path in [
        CHRISTMAS_AUDIT_DIR / f"christmas_pdf_vs_live_{date_tag}.csv",
        CHRISTMAS_AUDIT_DIR / "christmas_pdf_vs_live_latest.csv",
    ]:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows_out)

    CHRISTMAS_AUDIT_STATE.write_text(json.dumps(result, indent=2), encoding="utf-8")

    log(
        "Christmas audit: "
        f"PDF {len(pdf)}, live {len(live)}, common usable {len(common_usable)}, "
        f"PDF-only {len(pdf_only)}, live-only {len(live_only)}, "
        f"price mismatches {len(price_mismatches)}, image failures {len(image_failures)}.",
        lines,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-email", action="store_true", help="Run check without sending heartbeat email.")
    args = parser.parse_args()

    STATE_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    TMP_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)

    lines: list[str] = []
    changed_catalogues: list[dict[str, Any]] = []
    baseline_catalogues: list[str] = []
    migrated_catalogues: list[str] = []
    errors: list[str] = []
    settings = {}
    christmas_audit: dict[str, Any] | None = None

    try:
        settings = load_settings()
        if args.no_email:
            settings.setdefault("email", {})["enabled"] = False

        engine = load_engine()
        safety = settings.get("safety", {})
        catastrophic_drop_ratio = float(safety.get("catastrophic_drop_ratio", 0.50))
        retention_days = int(safety.get("sold_out_retention_days", 14))

        for filename in SALE_CONFIGS:
            cfg_path = CONFIG_DIR / filename
            cfg = engine.load_config(cfg_path)
            sale_id = cfg["sale"]["id"]
            display_name = cfg["sale"]["display_name"]
            iframe_path = cfg.get("iframe_path", sale_id)
            previous = load_state(sale_id)

            try:
                first = scan_sale(engine, cfg_path, 1, lines)

                if previous is None:
                    if not first:
                        raise RuntimeError("First baseline scan returned zero printable products.")
                    save_state(sale_id, display_name, first)
                    baseline_catalogues.append(display_name)
                    log(f"{display_name}: baseline established; no reprint alert on first run.", lines)
                    continue

                # v2.06 states did not retain full product metadata/images. Upgrade them
                # safely by taking one fresh baseline rather than inventing SOLD OUT history.
                legacy_state = any(
                    ("status" not in item) or ("image_file" not in item)
                    for item in previous.values()
                )
                if legacy_state:
                    if not first:
                        raise RuntimeError("Legacy-state migration scan returned zero printable products.")
                    save_state(sale_id, display_name, first)
                    migrated_catalogues.append(display_name)
                    log(f"{display_name}: monitor state upgraded to persistent-image v2.08 baseline.", lines)
                    continue

                prev_active = {k:v for k,v in previous.items() if v.get("status","active") != "sold_out"}
                prev_sold = {k:v for k,v in previous.items() if v.get("status") == "sold_out"}

                if not first:
                    raise RuntimeError("Scan returned zero printable products; treated as a site/network error, not stock-out.")

                prev_active_count = len(prev_active)
                if prev_active_count and len(first) < prev_active_count * catastrophic_drop_ratio:
                    raise RuntimeError(
                        f"Suspicious catalogue collapse ({prev_active_count} -> {len(first)}). "
                        "No rebuild/state update performed."
                    )

                missing_first = sorted(set(prev_active) - set(first))
                current = first

                if missing_first:
                    log(f"{display_name}: {len(missing_first)} possible removal(s); verifying with second scan.", lines)
                    time.sleep(float(safety.get("verification_pause_seconds", 3)))
                    current = scan_sale(engine, cfg_path, 2, lines)
                    if prev_active_count and len(current) < prev_active_count * catastrophic_drop_ratio:
                        raise RuntimeError(
                            f"Verification scan also shows suspicious collapse ({prev_active_count} -> {len(current)}). "
                            "No rebuild/state update performed."
                        )

                confirmed_missing = sorted(set(prev_active) - set(current))
                recovered = sorted(set(prev_sold) & set(current))
                added = sorted(set(current) - set(prev_active) - set(prev_sold))

                now_dt = datetime.now()
                retained_sold: dict[str, dict] = {}
                expired: list[dict] = []

                for key, item in prev_sold.items():
                    if key in current:
                        continue
                    since_text = item.get("sold_out_since", "")
                    try:
                        since = datetime.fromisoformat(since_text) if since_text else now_dt
                    except ValueError:
                        since = now_dt
                    age_days = (now_dt - since).days
                    if age_days >= retention_days:
                        expired.append(item)
                    else:
                        retained_sold[key] = item

                newly_sold: list[dict] = []
                for key in confirmed_missing:
                    item = dict(prev_active[key])
                    item["status"] = "sold_out"
                    item["sold_out_since"] = now_dt.isoformat(timespec="seconds")
                    retained_sold[key] = item
                    newly_sold.append(item)

                merged: dict[str, dict] = {}
                for key, item in current.items():
                    active_item = dict(item)
                    active_item["status"] = "active"
                    active_item["sold_out_since"] = ""
                    merged[key] = active_item
                merged.update(retained_sold)

                change_needed = bool(newly_sold or recovered or expired or added)

                if not change_needed:
                    save_state(sale_id, display_name, merged)
                    log(f"{display_name}: no status changes.", lines)
                    continue

                pending = pending_state_path(sale_id)
                write_state_file(pending, sale_id, display_name, merged)

                changed_catalogues.append({
                    "sale_id": sale_id,
                    "display_name": display_name,
                    "config": cfg_path,
                    "iframe_path": iframe_path,
                    "pending_state": pending,
                    "newly_sold": newly_sold,
                    "recovered": [current[k] for k in recovered],
                    "expired": expired,
                    "added": [current[k] for k in added],
                    "merged": merged,
                })

            except Exception as exc:
                msg = f"{display_name}: {exc}"
                errors.append(msg)
                log("ERROR: " + msg, lines)

        # Rebuild only catalogues whose visible content/status changed.
        for change in changed_catalogues:
            try:
                rebuild(change["config"], change["iframe_path"], change["pending_state"], lines)
            except Exception as exc:
                msg = f"{change['display_name']} rebuild failed: {exc}"
                errors.append(msg)
                change["rebuild_failed"] = True
                log("ERROR: " + msg, lines)

        publishable = [
            c["iframe_path"] for c in changed_catalogues
            if not c.get("rebuild_failed")
        ]
        publish_note = ""
        publish_ok = True
        if publishable:
            try:
                publish_note = git_publish(publishable, settings, lines)
            except Exception as exc:
                publish_ok = False
                publish_note = f"Git publish FAILED: {exc}"
                errors.append(publish_note)
                log("ERROR: " + publish_note, lines)

        # Promote pending state only after rebuild and required Git publish succeed.
        if publish_ok:
            for change in changed_catalogues:
                if not change.get("rebuild_failed"):
                    change["pending_state"].replace(state_path(change["sale_id"]))

        # Christmas PDF-vs-live audit is observational only. Failure is reported
        # in the heartbeat but never changes the operational Christmas source.
        if settings.get("christmas_audit", {}).get("enabled", True):
            try:
                christmas_audit = run_christmas_live_audit(engine, lines)
            except Exception as exc:
                msg = f"Christmas live audit failed: {exc}"
                errors.append(msg)
                log("ERROR: " + msg, lines)

        now = datetime.now().strftime("%A %d %B %Y at %H:%M")
        if errors:
            subject = "[VivaMK] Daily catalogue check - ATTENTION REQUIRED"
        elif changed_catalogues:
            names = ", ".join(c["display_name"] for c in changed_catalogues)
            subject = f"[VivaMK] REPRINT REQUIRED - {names}"
        else:
            subject = "[VivaMK] Daily catalogue check OK - no changes"

        body: list[str] = [
            "VivaMK daily clearance catalogue check",
            f"Completed: {now}",
            "",
        ]

        if changed_catalogues:
            body.append("CATALOGUE STATUS CHANGES")
            body.append("")
            for c in changed_catalogues:
                body.append(f"{c['display_name']}:")
                for item in c["newly_sold"]:
                    body.append(f"  SOLD OUT: {item.get('sku') or '(no SKU)'} - {item.get('product') or '(unnamed product)'}")
                for item in c["recovered"]:
                    body.append(f"  BACK IN STOCK: {item.get('sku') or '(no SKU)'} - {item.get('product') or '(unnamed product)'}")
                for item in c["added"]:
                    body.append(f"  NEW LIVE ITEM: {item.get('sku') or '(no SKU)'} - {item.get('product') or '(unnamed product)'}")
                for item in c["expired"]:
                    body.append(f"  REMOVED AFTER {retention_days} DAYS SOLD OUT: {item.get('sku') or '(no SKU)'} - {item.get('product') or '(unnamed product)'}")

                if c.get("rebuild_failed"):
                    body.append("  BOOKLET/IFRAME REBUILD FAILED - see errors below.")
                else:
                    body.append("  Booklet and iframe regenerated successfully.")
                    body.append("  ACTION: reprint this catalogue.")
                body.append("")
            if publish_note:
                body.append(publish_note)
                body.append("")
        else:
            body.append("HEARTBEAT: Check completed successfully. No catalogue status changes were confirmed today.")
            body.append("No booklet reprints are required.")
            body.append("")

        if christmas_audit:
            body.append("CHRISTMAS PDF vs LIVE CATEGORY AUDIT")
            body.append(f"  PDF source items: {christmas_audit['pdf_count']}")
            body.append(f"  Live category items: {christmas_audit['live_count']}")
            body.append(f"  Common usable: {christmas_audit['common_usable_count']}")
            body.append(f"  PDF only: {christmas_audit['pdf_only_count']}")
            body.append(f"  Live only: {christmas_audit['live_only_count']}")
            body.append(f"  Price mismatches: {christmas_audit['price_mismatch_count']}")
            body.append(f"  Image failures: {christmas_audit['image_failure_count']}")
            changed = christmas_audit.get("changed_since_previous")
            if changed is None:
                body.append("  Change since previous audit: first recorded daily audit")
            elif changed:
                fields = ", ".join(christmas_audit.get("changed_fields", [])) or "SKU membership changed"
                body.append(f"  Change since previous audit: YES ({fields})")
            else:
                body.append("  Change since previous audit: none")
            body.append(f"  Stable clean audit streak: {christmas_audit.get('stable_streak', 0)}")
            body.append(f"  Migration status: {christmas_audit.get('migration_status', 'MONITORING')}")
            body.append("  Operational Christmas source remains the PDF for now.")
            body.append("")

        if baseline_catalogues:
            body.append("Baseline established for: " + ", ".join(baseline_catalogues))
            body.append("The first run records current live products and deliberately does not request reprinting.")
            body.append("")

        if migrated_catalogues:
            body.append("State upgraded for: " + ", ".join(migrated_catalogues))
            body.append("This one-time upgrade cached full product images/details for future SOLD OUT overlays.")
            body.append("No reprint was requested solely because of the state upgrade.")
            body.append("")

        if errors:
            body.append("ERRORS / WARNINGS")
            for e in errors:
                body.append("  - " + e)
            body.append("")
            body.append("Where an error occurred, the monitor did NOT intentionally treat it as a stock-out.")
            body.append("Check the log before reprinting.")

        log_file = LOG_DIR / f"daily_monitor_{datetime.now():%Y%m%d_%H%M%S}.log"
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        body.append("")
        body.append(f"Local log: {log_file}")

        send_email(settings, subject, "\n".join(body))
        log(f"Heartbeat email sent: {subject}", lines)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1 if errors else 0

    except Exception as exc:
        details = traceback.format_exc()
        print(details, file=sys.stderr)
        try:
            if not settings:
                settings = load_settings()
            if args.no_email:
                settings.setdefault("email", {})["enabled"] = False
            send_email(
                settings,
                "[VivaMK] Daily catalogue monitor FAILED",
                "The daily catalogue monitor failed before completing.\n\n"
                + str(exc)
                + "\n\n"
                + details,
            )
        except Exception as email_exc:
            print("Could not send failure email:", email_exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
