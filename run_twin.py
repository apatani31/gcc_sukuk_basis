"""Within-issuer twin-curve analysis on the pulled history (no LSEG calls).

Usage:
    .venv\\Scripts\\python run_twin.py              # data/USD -> data/USD/analysis/
    .venv\\Scripts\\python run_twin.py --data data/slice_USD_Qatar_2019
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from src import config as C
from src.twin import load_panel, sukuk_basis, tenor_gaps, validate_nearest
from src.twin_report import write_report

log = logging.getLogger("run_twin")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    p.add_argument("--min-amount", type=float, help="override TWIN min_amount_usd (USD)")
    a = p.parse_args(argv)
    C.setup_logging("run_twin")
    cfg = dict(C.TWIN)
    if a.min_amount is not None:
        cfg["min_amount_usd"] = a.min_amount

    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    panel = load_panel(uni, a.data / "timeseries", cfg)
    basis = sukuk_basis(panel, cfg)
    if basis.empty:
        log.error("No sukuk could be matched to a conventional curve.")
        return 1
    gaps = tenor_gaps(panel, cfg)
    validation = validate_nearest(panel, basis, cfg)
    main_res = write_report(panel, basis, gaps, a.data / "analysis", cfg, validation)
    log.info("Headline: %s", main_res)
    log.info("Wrote %s", a.data / "analysis" / "twin_results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
