"""Event study of the twin-curve basis around oil shocks (no LSEG calls).

Needs: data/USD/analysis/twin_basis_obs.parquet (run_twin.py) and the shock list (run_shocks.py).

Usage:
    .venv\\Scripts\\python run_event_study.py
    .venv\\Scripts\\python run_event_study.py --shocks data/market/oil_shocks_z3_min7pct_h1.csv --out data/USD/analysis/event_study_min7
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from src import config as C
from src.event_report import write_event_report

log = logging.getLogger("run_event_study")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--shocks", type=Path, default=C.DATA_DIR / "market" / "oil_shocks_z3_min5pct_h1.csv")
    p.add_argument("--basis", type=Path, default=C.DATA_DIR / "USD" / "analysis" / "twin_basis_obs.parquet")
    p.add_argument("--out", type=Path, default=C.DATA_DIR / "USD" / "analysis" / "event_study")
    p.add_argument("--pre", type=int, default=5)
    p.add_argument("--post", type=int, default=20)
    a = p.parse_args(argv)
    C.setup_logging("run_event_study")

    obs = pd.read_parquet(a.basis)
    shocks = pd.read_csv(a.shocks, parse_dates=["date"])
    mk = C.DATA_DIR / "market" / "market_daily.parquet"
    market = pd.read_parquet(mk) if mk.exists() else None
    s = C.SHOCK
    rule = (f"Brent front-month 1-day move, net of S&P 500 (rolling beta), |z| >= {s['z']:g} vs trailing "
            f"{s['vol_window']} days AND raw move >= {s['min_abs_ret_pct']:g}%; up/down selected separately, "
            f"{s['cluster_days']} business days apart ({a.shocks.name})")
    res = write_event_report(obs, shocks, market, a.out, rule, a.pre, a.post)
    log.info("Main results:\n%s", res["main"].to_string(index=False))
    log.info("Wrote %s", a.out / "event_study.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
