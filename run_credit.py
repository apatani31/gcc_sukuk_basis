"""Credit-stress analysis of the twin-curve basis (sovereign CDS + liquidity).

Usage:
    .venv\\Scripts\\python run_credit.py --session platform   # pull/refresh sovereign CDS, then analyse
    .venv\\Scripts\\python run_credit.py                      # reuse data/market/sovereign_cds.parquet
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.credit import build_panel, cross_issuer, leave_one_sovereign_out, pull_cds, within_issuer
from src.summary import _md
from src.twin import load_panel
from src.twin_report import INK, INK2, SUKUK_C, SURFACE, _style

log = logging.getLogger("run_credit")
CDS_PATH = C.DATA_DIR / "market" / "sovereign_cds.parquet"


def chart_cross_issuer(iss: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = iss.dropna(subset=["cds"])
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    _style(ax)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.scatter(d["cds"], d["basis"], s=40, color=SUKUK_C, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    short = lambda n: n.split(",")[0].replace(" PJSC", "").replace(" SJSC", "").replace(" BSCC Closed", "")[:24]
    stand_out = (d["cds"] > 100) | (d["basis"].abs() > 15) | (d["cds"] < 45)
    for r in d[stand_out].itertuples():
        below = r.cds < 36  # Qatar sits next to FAB; put its label underneath
        ax.annotate(short(r.parent_name), (r.cds, r.basis), xytext=(5, -11 if below else 3),
                    textcoords="offset points", fontsize=8, color=INK2)
    rest = d[~stand_out]
    if len(rest):
        fig.text(0.01, 0.01, "Unlabelled cluster (basis -10 to +3bp): " + ", ".join(short(n) for n in rest["parent_name"]),
                 fontsize=7, color=INK2, wrap=True)
    ax.set_xlabel("Mean sovereign 5y CDS of the issuer's government (bp)", color=INK2, fontsize=9)
    ax.set_ylabel("Mean twin-curve basis (bp)", color=INK2, fontsize=9)
    ax.set_title("Sukuk discount vs credit risk, one point per issuer (below zero = sukuk yield less)",
                 fontsize=10, color=INK, loc="left")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", choices=["desktop", "platform"], help="pull/refresh sovereign CDS first")
    p.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = p.parse_args(argv)
    C.setup_logging("run_credit")

    if a.session:
        from src.session import lseg_session
        with lseg_session(a.session):
            cds = pull_cds(CDS_PATH)
    elif CDS_PATH.exists():
        cds = pd.read_parquet(CDS_PATH)
    else:
        log.error("No CDS data at %s; run with --session platform first", CDS_PATH)
        return 1

    out = a.data / "analysis" / "credit"
    out.mkdir(parents=True, exist_ok=True)
    basis = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")
    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    bonds = load_panel(uni, a.data / "timeseries")
    ust = pd.read_parquet(C.TWIN["ust_curve_path"]).astype(float).sort_index()

    panel = build_panel(basis, bonds, cds, ust)
    within = within_issuer(panel)
    iss, xs = cross_issuer(panel)
    loo = leave_one_sovereign_out(panel, iss)
    loo.to_csv(out / "credit_leave_one_out.csv", index=False)
    panel.assign(month=panel["month"].astype(str)).to_csv(out / "credit_panel_issuer_month.csv", index=False)
    within.to_csv(out / "credit_within_issuer.csv", index=False)
    xs.to_csv(out / "credit_cross_issuer.csv", index=False)
    iss.to_csv(out / "credit_issuer_means.csv", index=False)
    chart_cross_issuer(iss, out / "credit_cross_issuer.png")

    cov = (cds.astype(float).apply(lambda s: f"{s.first_valid_index():%Y-%m}" if s.notna().any() else "none"))
    L = ["# Credit stress and the sukuk discount\n",
         f"Generated {date.today():%Y-%m-%d}. Issuer-month panel from the twin-curve basis.\n",
         "## Data\n",
         "- **Basis:** twin-curve basis (sukuk yield minus same-maturity conventional yield, bp), issuer-month mean.",
         "- **Credit measure:** sovereign 5y USD CDS (`MID_SPREAD`) of the issuer's government. CDS comes from "
         "outside the bond data, so noise in the conventional yield cannot feed both sides of the regression "
         "(the problem with using the issuer's own conventional spread, kept below only for comparison). "
         "Government-related issuers are mapped to their owner (e.g. Aramco, PIF, SNB to KSA; BAPCO to "
         "Bahrain; ICD, DP World, DAE to Dubai; FAB, Mamoura to Abu Dhabi).",
         "- **CDS codes and start dates:** " + "; ".join(f"{k} `{C.CDS_RICS[k]}` from {v}" for k, v in cov.items())
         + ". No Sharjah or UAE-federal CDS is available, so Sharjah and Arab Energy Fund drop out of the CDS "
         "regressions.",
         "- **Liquidity gap:** sukuk minus conventional median bid-ask spread (bp of yield) for the issuer-month. "
         "It controls for the alternative explanation that sukuk simply trade less.",
         "- **Inference:** issuer fixed effects; t-stats clustered by issuer and Driscoll-Kraay (robust to "
         "common monthly shocks). With about 16 issuers, read t-stats near 2 with care.\n",
         "## Across issuers: is the discount bigger for weaker credits?\n",
         "![cross issuer](credit_cross_issuer.png)\n",
         _md(xs),
         "\n## Within issuers over time: does the discount widen when credit risk rises?\n",
         "Slope = change in basis (bp) per 100bp rise in the credit measure.\n\n",
         _md(within),
         "\n## Robustness: leave one government out\n",
         "Issuers that share a government share its CDS series, so there are only six independent credit "
         "series. Each row drops one government's issuers. *t (cluster government)* clusters standard "
         "errors by government (very few clusters, so conservative and approximate).\n\n",
         _md(loo),
         "\n## Reading the results\n",
         "- **Within issuers (main result):** the slope is stable whichever government is dropped. Its "
         "precision leans on Oman, whose CDS ranged most widely.",
         "- **Across issuers:** the cross-sectional slope depends on Bahrain (sovereign and BAPCO). Without it "
         "there is no gradient among issuers with CDS below about 100bp. Describe the cross-section as a "
         "threshold (large discounts for the sub-investment-grade sovereigns, small elsewhere), not a "
         "smooth gradient.",
         "- **Liquidity:** the liquidity-gap coefficient is *negative*: months when sukuk are relatively less "
         "liquid are months when they yield relatively *less*. A liquidity premium would show the opposite "
         "sign, so liquidity does not explain the discount.\n",
         "\n## Issuer means\n",
         _md(iss[["parent_name", "cds_sovereign", "months", "basis", "cds", "spread_conv", "ba_sukuk",
                  "ba_conv", "liq_gap"]]),
         "\n## Caveats\n",
         "- CDS for government-related issuers is the *owner's* credit, a proxy for state support rather than "
         "the issuer's own risk.",
         "- Few issuers (about 16 with CDS), and before 2021 only 4. Month fixed effects identify the slope only "
         "from differences between six CDS series.",
         "- Bid-ask spreads are LSEG composite quotes, a rough liquidity measure.",
         "- Dubai's basis relies on wide interpolation brackets. See the excluding-Dubai rows.\n"]
    (out / "credit_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Cross-issuer:\n%s", xs.to_string(index=False))
    log.info("Within-issuer:\n%s", within.to_string(index=False))
    log.info("Wrote %s", out / "credit_results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
