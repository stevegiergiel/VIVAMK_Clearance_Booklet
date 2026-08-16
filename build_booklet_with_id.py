#!/usr/bin/env python3
"""Build a clearance booklet, then stamp/register a unique physical Booklet ID."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

from booklet_identity import register_booklet

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--state-file", type=Path, default=None)
    ap.add_argument("--booklet-id", default=None)
    args = ap.parse_args()

    cmd = [sys.executable, str(ROOT / "vivamk_clearance_booklet.py"), "--config", str(args.config)]
    if args.refresh:
        cmd.append("--refresh")
    if args.state_file:
        cmd += ["--state-file", str(args.state_file)]
    subprocess.run(cmd, cwd=ROOT, check=True)
    register_booklet(args.config, args.booklet_id)


if __name__ == "__main__":
    main()
