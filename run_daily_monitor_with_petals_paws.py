#!/usr/bin/env python3
"""Run the existing daily catalogue monitor with Petals & Paws registered.

This is deliberately a thin integration layer. It does not implement a second
stock engine or redefine status semantics; it reuses vivamk_daily_monitor.py
unchanged while the canonical shared stock-data migration is being validated.

It also guards the existing publisher against a known false-positive condition:
`vivamk_daily_monitor.git_publish()` checks all of `site/` after staging only the
affected iframe paths. An unrelated untracked/modified site file can therefore
make that check non-empty even when none of the affected iframe files changed,
causing `git commit` to exit 1 with "nothing to commit".  The wrapper first
checks only the affected iframe paths and skips the publisher when those paths
are unchanged.
"""

from __future__ import annotations

from typing import Any

import vivamk_daily_monitor as monitor

PETALS_PAWS_CONFIG = "petals_paws_specials.json"
_ORIGINAL_GIT_PUBLISH = monitor.git_publish


def configure_monitor() -> list[str]:
    """Register Petals & Paws once and return the effective sale config list."""
    if PETALS_PAWS_CONFIG not in monitor.SALE_CONFIGS:
        # Keep Petals & Paws next to the existing pets catalogue for readability.
        try:
            pets_index = monitor.SALE_CONFIGS.index("pets.json") + 1
        except ValueError:
            pets_index = len(monitor.SALE_CONFIGS)
        monitor.SALE_CONFIGS.insert(pets_index, PETALS_PAWS_CONFIG)
    return list(monitor.SALE_CONFIGS)


def safe_git_publish(
    affected_iframe_paths: list[str],
    settings: dict[str, Any],
    lines: list[str],
) -> str:
    """Publish only when one of the specifically affected iframe files changed.

    This avoids unrelated files elsewhere under site/ making the legacy
    publisher attempt an empty commit.
    """
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

    return _ORIGINAL_GIT_PUBLISH(affected_iframe_paths, settings, lines)


def main() -> int:
    configure_monitor()
    monitor.git_publish = safe_git_publish
    return monitor.main()


if __name__ == "__main__":
    raise SystemExit(main())
