#!/usr/bin/env python3
"""Run the existing daily catalogue monitor with Petals & Paws registered.

This is deliberately a thin integration layer. It does not implement a second
stock engine or redefine status semantics; it reuses vivamk_daily_monitor.py
unchanged while the canonical shared stock-data migration is being validated.
"""

from __future__ import annotations

import vivamk_daily_monitor as monitor

PETALS_PAWS_CONFIG = "petals_paws_specials.json"


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


def main() -> int:
    configure_monitor()
    return monitor.main()


if __name__ == "__main__":
    raise SystemExit(main())
