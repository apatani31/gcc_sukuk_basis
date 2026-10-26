"""Smoke test: open a session, pull one field for one ISIN, print OK, close.

Usage:
    .venv\\Scripts\\python check_session.py --session desktop
    .venv\\Scripts\\python check_session.py --session platform
"""
from __future__ import annotations

import argparse
import sys

from src.config import setup_logging
from src.session import LIB, ld, lseg_session

# KSA Sukuk Ltd 3.628% 2027 (from the Sukuk export); active, liquid sovereign sukuk.
TEST_ISIN = "XS1599284202"
TEST_FIELD = "TR.CommonName"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", choices=["desktop", "platform"], default="desktop")
    p.add_argument("--isin", default=TEST_ISIN)
    args = p.parse_args()
    log_path = setup_logging("check_session")

    try:
        with lseg_session(args.session):
            df = ld.get_data(args.isin, [TEST_FIELD])
            print(df.to_string(index=False))
            if df.empty or df.iloc[0, -1] in (None, ""):
                print(f"FAILED: {TEST_FIELD} came back empty for {args.isin}")
                return 1
            # Also prove the pricing-history endpoint is reachable.
            hist = ld.get_history("SASUKSK4202=", fields=["BID", "ASK"], interval="daily", count=5)
            print(hist.tail().to_string())
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print(f"See log: {log_path}")
        return 1
    print(f"OK ({LIB} {ld.__version__}, {args.session} session)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
