"""Convenience entrypoint: python scripts/decide_now.py SPY"""
from __future__ import annotations

import sys

from astrotrader.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        symbol = sys.argv[1]
        sys.argv = [sys.argv[0], "decide-cmd", "--symbol", symbol]
    main()
