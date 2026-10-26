"""Build the oil-shock event list from the rule in config.SHOCK.

Usage:
    .venv\\Scripts\\python run_shocks.py --session platform        # pull market data, then detect
    .venv\\Scripts\\python run_shocks.py                           # reuse data/market/market_daily.parquet
    .venv\\Scripts\\python run_shocks.py --z 2.5 --horizon 5       # sensitivity variants
"""
from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from src import config as C
from src.shocks import add_coverage, detect_shocks, pull_market, shock_scores

log = logging.getLogger("run_shocks")
MARKET = C.DATA_DIR / "market" / "market_daily.parquet"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", choices=["desktop", "platform"], help="pull/refresh market data first")
    p.add_argument("--z", type=float)
    p.add_argument("--min-ret", type=float, help="minimum absolute raw Brent move, percent")
    p.add_argument("--horizon", type=int, help="return horizon in trading days")
    p.add_argument("--no-net", action="store_true", help="do not net out the S&P 500 move")
    p.add_argument("--start")
    a = p.parse_args(argv)
    C.setup_logging("run_shocks")
    cfg = dict(C.SHOCK)
    if a.z is not None:
        cfg["z"] = a.z
    if a.min_ret is not None:
        cfg["min_abs_ret_pct"] = a.min_ret
    if a.horizon is not None:
        cfg["horizon_days"] = a.horizon
    if a.no_net:
        cfg["net_of_equity"] = False
    if a.start:
        cfg["start"] = a.start

    if a.session:
        from src.session import lseg_session
        with lseg_session(a.session):
            market = pull_market(MARKET)
    elif MARKET.exists():
        market = pd.read_parquet(MARKET)
    else:
        log.error("No market data at %s; run with --session platform first", MARKET)
        return 1

    scores = shock_scores(market, cfg)
    shocks = detect_shocks(scores, cfg)
    daily_path = C.DATA_DIR / "USD" / "analysis" / "twin_basis_issuer_daily.csv"
    if daily_path.exists():
        shocks = add_coverage(shocks, pd.read_csv(daily_path, parse_dates=["date"]))
    tag = (f"z{cfg['z']:g}_min{cfg['min_abs_ret_pct']:g}pct_h{cfg['horizon_days']}"
           f"{'' if cfg['net_of_equity'] else '_gross'}")
    out = C.DATA_DIR / "market" / f"oil_shocks_{tag}.csv"
    shocks.to_csv(out, index=False)
    scores.to_parquet(C.DATA_DIR / "market" / f"oil_scores_{tag}.parquet")
    log.info("%d shock episodes (%d up, %d down) -> %s", len(shocks), int((shocks.sign == "up").sum()),
             int((shocks.sign == "down").sum()), out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
