"""Oil through credit: do oil shocks move sovereign CDS, and what does that imply for the basis?
(NEXT_PROMPT task 4). No LSEG calls.

Needs: run_shocks.py, run_credit.py, run_drivers.py and run_event_study.py outputs.

Usage:
    .venv\\Scripts\\python run_oil_credit.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.oil_credit import cds_event_study, implied_vs_direct
from src.summary import _md

log = logging.getLogger("run_oil_credit")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    ap.add_argument("--shocks", type=Path, default=C.DATA_DIR / "market" / "oil_shocks_z3_min5pct_h1.csv")
    a = ap.parse_args(argv)
    C.setup_logging("run_oil_credit")
    out = a.data / "analysis" / "oil_credit"
    out.mkdir(parents=True, exist_ok=True)

    cds = pd.read_parquet(C.DATA_DIR / "market" / "sovereign_cds.parquet")
    market = pd.read_parquet(C.DATA_DIR / "market" / "market_daily.parquet")
    shocks = pd.read_csv(a.shocks)
    panel = pd.read_csv(a.data / "analysis" / "drivers" / "drivers_panel_issuer_month.csv")
    direct = pd.read_csv(a.data / "analysis" / "event_study" / "event_key_main.csv")

    res = cds_event_study(cds, shocks, market)
    imp = implied_vs_direct(res["events"]["pooled"], panel, direct)
    res["pooled"].to_csv(out / "oil_cds_event_pooled.csv", index=False)
    res["by_sovereign"].to_csv(out / "oil_cds_event_by_sovereign.csv", index=False)
    imp.to_csv(out / "oil_implied_vs_direct.csv", index=False)

    pk = res["pooled"].set_index(["sample", "shock", "tau"])
    reading = []
    for sign, label in (("up", "Oil up-shocks"), ("down", "Oil down-shocks")):
        if ("All shocks", sign, 5) in pk.index:
            r = pk.loc[("All shocks", sign, 5)]
            reading.append(f"- **{label}, +5 days:** average sovereign CDS mean {r.mean_bp:+.1f}bp, median "
                           f"{r.median_bp:+.1f}bp, CDS rose in {r.rises} shocks, placebo p {r.placebo_p_median:.3f}.")
    up_dates = ", ".join(res["shocks"].loc[res["shocks"]["sign"] == "up", "date"].dt.strftime("%Y-%m-%d"))
    reading.append("- The up-shocks in this sample (" + up_dates + ") include several regional geopolitical "
                   "events (the 2019 Abqaiq attack, Russia's 2022 invasion of Ukraine, the June 2025 Israel-Iran "
                   "war) alongside supply/demand episodes (December 2018, April-May 2020). The causes of the 2026 "
                   "shocks are not classified here. If CDS rises after oil up-shocks, conflict risk can outweigh "
                   "the fiscal benefit of a higher oil price, so signing shocks by oil price alone mixes two "
                   "channels; read the pooled (sign-flipped) rows with that in mind.")

    fb = C.DATA_DIR / "market" / "fiscal_breakeven.csv"
    fiscal_note = ("`data/market/fiscal_breakeven.csv` is present but the Brent-minus-breakeven driver is not "
                   "implemented yet." if fb.exists() else
                   "Skipped: `data/market/fiscal_breakeven.csv` (country, year, breakeven_usd, source) was not "
                   "supplied, and breakeven values are not invented.")
    L = ["# Oil through credit\n",
         f"Generated {date.today():%Y-%m-%d}. Shocks: `{a.shocks.name}` (same as the basis event study).\n",
         "## a. Do oil shocks move sovereign CDS?\n",
         "Outcome: change in each government's 5y CDS (bp) from its last level before the shock. "
         "*Average of sovereigns* averages the six CDS changes per shock, then summarizes across shocks "
         "(each shock counts once). *Pooled* flips down-shocks, so it reads as the response to an oil-price "
         "**rise** (negative = CDS falls = credit improves). Placebo p and MDE come from the same "
         "volatility-matched placebo as the basis study (median across shocks).\n\n",
         "**Reading:**\n", *reading, "\n",
         _md(res["pooled"]),
         "\n**By sovereign (all shocks, +5 and +20 business days):**\n\n", _md(res["by_sovereign"]),
         "\n## b. Implied basis response vs the direct estimate\n",
         "Implied = (mean sign-adjusted CDS change across shocks) x (within-issuer CDS slope with the liquidity "
         "control). The 90% interval bootstraps shocks for the first factor and governments (pairs cluster "
         "bootstrap, six CDS series) for the slope. *Direct* is the pooled sign-adjusted basis response from "
         "event_study.md, with its minimum detectable effect.\n\n",
         _md(imp),
         "\nIf the implied response is small relative to the direct estimate's MDE, the null in the basis "
         "event study is what the credit channel predicts: oil shocks move CDS too little, for too short a "
         "time, to show up in the basis.\n",
         "## d. Fiscal stress (Brent minus fiscal breakeven)\n", fiscal_note, "\n",
         "## Caveats\n",
         "- The slope is an average across issuers. The within-issuer slope is concentrated in sub-investment-"
         "grade issuers (mechanism_results.md), so their implied response would be larger than the average.",
         "- Oman's CDS starts in August 2017, so the 2016-2017 shocks use five sovereigns.\n"]
    (out / "oil_credit_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("CDS pooled:\n%s", res["pooled"].to_string(index=False))
    log.info("By sovereign:\n%s", res["by_sovereign"].to_string(index=False))
    log.info("Implied vs direct:\n%s", imp.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
