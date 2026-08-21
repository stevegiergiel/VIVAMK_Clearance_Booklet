#!/usr/bin/env python3
"""Run the existing daily catalogue monitor using dynamically discovered sale configs.

This is deliberately a thin integration layer. It does not implement a second
stock engine or redefine status semantics; it reuses vivamk_daily_monitor.py
while the canonical shared stock-data migration is being validated.

Operational improvements provided here:
- Prefer configs/catalogue_manifest.json as the declarative catalogue registry,
  while retaining safe config-directory discovery as a compatibility fallback.
- Add a MONITORED CATALOGUES section to every heartbeat so successful no-change
  runs prove which catalogues were actually included.
- Guard the legacy publisher against unrelated files under site/ causing an
  empty git commit failure.
- Under GitHub Actions, commit changed iframe output locally and let the workflow
  publish it through a short-lived PR rather than pushing directly through main
  branch protection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import vivamk_daily_monitor as monitor

_ORIGINAL_GIT_PUBLISH = monitor.git_publish
_ORIGINAL_SEND_EMAIL = monitor.send_email
_DISCOVERED: list[dict[str, Any]] = []
MANIFEST_NAME = "catalogue_manifest.json"


def _read_config(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _catalogue_record(path: Path, manifest_entry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    cfg = _read_config(path)
    if not cfg:
        return None

    sale = cfg.get("sale") or {}
    data_source = cfg.get("data_source") or {}
    monitor_cfg = cfg.get("monitor") or {}
    sale_id = str(sale.get("id") or "").strip()
    display_name = str(sale.get("display_name") or "").strip()
    mode = str(data_source.get("mode") or "").strip().lower()

    if not sale_id or not display_name or mode not in {"pdf", "category"}:
        return None
    if monitor_cfg.get("enabled", True) is False:
        return None

    entry = manifest_entry or {}
    source = ""
    if mode == "pdf":
        source = str(data_source.get("price_pdf") or "").strip()
    else:
        source = str(sale.get("source_url") or cfg.get("category_url") or "").strip()

    return {
        "filename": path.name,
        "sale_id": sale_id,
        "display_name": display_name,
        "mode": mode,
        "source": source,
        "live_url": str(entry.get("live_url") or sale.get("source_url") or "").strip(),
        "operational_source": str(entry.get("operational_source") or mode).strip().lower(),
        "generate_iframe": bool(entry.get("generate_iframe", True)),
        # New catalogues default to no print. Existing catalogues are explicitly
        # true in the manifest so introducing this control is backwards-safe.
        "generate_print": bool(entry.get("generate_print", False)),
        "migration": str(entry.get("migration") or "").strip(),
        "iframe_path": str(cfg.get("iframe_path") or sale_id).strip(),
    }


def discover_sale_configs(config_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return valid, enabled catalogue configs.

    When catalogue_manifest.json exists, it is authoritative for catalogue
    membership/order/output flags. The underlying per-sale JSON files remain
    authoritative for layout/theme and current operational data-source mechanics.

    If the manifest is absent, fall back to the previous safe configs/*.json
    discovery behaviour for rollback/backwards compatibility.
    """
    root = config_dir or monitor.CONFIG_DIR
    manifest_path = root / MANIFEST_NAME
    found: list[dict[str, Any]] = []

    manifest = _read_config(manifest_path) if manifest_path.exists() else None
    if manifest:
        defaults = manifest.get("defaults") or {}
        entries = manifest.get("catalogues") or []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            filename = str(raw.get("config") or "").strip()
            if not filename:
                continue
            merged = dict(defaults)
            merged.update(raw)
            rec = _catalogue_record(root / filename, merged)
            if rec:
                found.append(rec)
        return found

    for path in sorted(root.glob("*.json")):
        if path.name == MANIFEST_NAME:
            continue
        rec = _catalogue_record(path)
        if rec:
            # Compatibility mode preserves legacy behaviour for existing configs.
            rec["generate_iframe"] = True
            rec["generate_print"] = True
            found.append(rec)

    return found


def configure_monitor() -> list[str]:
    """Replace the legacy hard-coded list with declarative catalogue discovery."""
    global _DISCOVERED
    _DISCOVERED = discover_sale_configs()
    monitor.SALE_CONFIGS[:] = [item["filename"] for item in _DISCOVERED]
    return list(monitor.SALE_CONFIGS)


def safe_git_publish(
    affected_iframe_paths: list[str],
    settings: dict[str, Any],
    lines: list[str],
) -> str:
    """Publish only when one of the specifically affected iframe files changed."""
    if not affected_iframe_paths:
        return "No iframe changes required."

    site_files = [f"site/{path}/index.html" for path in affected_iframe_paths]
    status = monitor.run(
        ["git", "status", "--porcelain", "--", *site_files],
        check=True,
    ).stdout.strip()

    if not status:
        monitor.log(
            "Affected iframe HTML is unchanged; unrelated site changes ignored.",
            lines,
        )
        return "Iframe rebuilt; affected generated HTML was unchanged so no Git push was needed."

    if os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true":
        monitor.run(["git", "add", *site_files])
        staged = monitor.run(
            ["git", "diff", "--cached", "--quiet"], check=False
        ).returncode
        if staged == 0:
            monitor.log("Affected iframe HTML produced no staged changes.", lines)
            return "Iframe rebuilt; generated HTML was unchanged so no publish was needed."
        monitor.run([
            "git", "commit", "-m",
            "Daily catalogue monitor: refresh affected iframe pages",
        ])
        monitor.log(
            "GitHub Actions: affected iframe pages committed locally for workflow publishing.",
            lines,
        )
        return (
            "Affected iframe pages were committed by GitHub Actions; "
            "the workflow will publish them through a protected-branch PR."
        )

    return _ORIGINAL_GIT_PUBLISH(affected_iframe_paths, settings, lines)


def send_email_with_catalogue_summary(
    settings: dict[str, Any], subject: str, body: str
) -> None:
    """Append proof of the catalogue population to every heartbeat email."""
    lines = [body.rstrip(), "", "MONITORED CATALOGUES"]
    if not _DISCOVERED:
        lines.append("  WARNING: no monitorable catalogue configs were discovered.")
    else:
        for item in _DISCOVERED:
            source_note = f" - {item['source']}" if item["source"] else ""
            output_note = (
                f" | iframe={'YES' if item['generate_iframe'] else 'NO'}"
                f" | print={'YES' if item['generate_print'] else 'NO'}"
            )
            lines.append(
                f"  OK: {item['display_name']} [{item['mode'].upper()}]{source_note}{output_note}"
            )
    lines.extend([
        "",
        f"Catalogue registry: {monitor.CONFIG_DIR / MANIFEST_NAME}",
    ])
    _ORIGINAL_SEND_EMAIL(settings, subject, "\n".join(lines))


def main() -> int:
    configured = configure_monitor()
    if not configured:
        raise RuntimeError("No monitorable catalogues were discovered.")
    monitor.git_publish = safe_git_publish
    monitor.send_email = send_email_with_catalogue_summary
    return monitor.main()


if __name__ == "__main__":
    raise SystemExit(main())
