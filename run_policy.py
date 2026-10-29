"""Policy numbers: sukuk coupon savings per issuer and an out-of-sample counterfactual (NEXT_PROMPT task 5).

Usage:
    .venv\\Scripts\\python run_policy.py --session platform   # pull Kuwait CDS once, then compute
    .venv\\Scripts\\python run_policy.py                      # reuse data/market/counterfactual_cds.parquet

Needs: run_twin.py and run_mechanism.py outputs.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as C
from src.mechanism import issuer_ratings
from src.policy import counterfactual, outstanding_sukuk, savings, today
from src.summary import _md
from src.twin_report import INK, INK2, SUKUK_C, SURFACE, _style

log = logging.getLogger("run_policy")
CF_PATH = C.DATA_DIR / "market" / "counterfactual_cds.parquet"
# Sovereigns with no USD sukuk in the universe: parent_key -> (label, CDS column or None)
TARGETS = {"kuwait state": ("Kuwait", "Kuwait"), "abu dhabi emirate": ("Abu Dhabi", "Abu Dhabi"),
           "arab emirates united": ("UAE (federal)", None)}
KUWAIT_CDS = "KWGV5YUSAC=R"   # probed 2026-10-25: available from 2024-11


def pull_kuwait(out: Path) -> pd.DataFrame:
    from src.session import call_api, ld, lseg_session  # noqa: F401

    h = call_api(ld.get_history, KUWAIT_CDS, fields=["MID_SPREAD"], interval="daily", start="2016-01-01",
                 end=date.today().isoformat())
    df = pd.DataFrame({"Kuwait": pd.to_numeric(h["MID_SPREAD"], errors="coerce")})
    df.index.name = "date"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    log.info("Kuwait CDS: %d days from %s", df["Kuwait"].notna().sum(), df["Kuwait"].first_valid_index())
    return df


def chart_savings(s: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = s.dropna(subset=["saving_12m_usd_m"]).sort_values("saving_12m_usd_m")
    lo = d["saving_12m_ci90"].map(lambda x: float(re.findall(r"-?\d+\.?\d*", x)[0]) if x else np.nan)
    hi = d["saving_12m_ci90"].map(lambda x: float(re.findall(r"-?\d+\.?\d*", x)[1]) if x else np.nan)
    fig, ax = plt.subplots(figsize=(8.5, 0.42 * len(d) + 1.4), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.6)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(d))
    ax.barh(y, d["saving_12m_usd_m"], height=0.6, color=SUKUK_C)
    ax.errorbar(d["saving_12m_usd_m"], y, xerr=[d["saving_12m_usd_m"] - lo, hi - d["saving_12m_usd_m"]],
                fmt="none", ecolor=INK2, elinewidth=1, capsize=2)
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.set_yticks(y, [n.split(",")[0][:30] for n in d["issuer"]], fontsize=8, color=INK2)
    for yi, v, amt in zip(y, d["saving_12m_usd_m"], d["outstanding_usd_bn"]):
        ax.annotate(f"{v:,.0f}  (on ${amt:,.1f}bn)", (max(v, 0), yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=INK2)
    ax.set_xlabel("Annual coupon saving from issuing sukuk, USD m (trailing 12-month basis x outstanding sukuk)",
                  color=INK2, fontsize=8.5)
    ax.set_title("Sukuk cost advantage by issuer, with 90% intervals", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["desktop", "platform"], help="pull Kuwait CDS first")
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = ap.parse_args(argv)
    C.setup_logging("run_policy")
    out = a.data / "analysis" / "policy"
    out.mkdir(parents=True, exist_ok=True)

    if a.session:
        from src.session import lseg_session
        with lseg_session(a.session):
            kw = pull_kuwait(CF_PATH)
    elif CF_PATH.exists():
        kw = pd.read_parquet(CF_PATH)
    else:
        kw = pd.DataFrame()
        log.warning("No Kuwait CDS at %s (run with --session platform); Kuwait uses the rating model only", CF_PATH)

    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    daily = pd.read_csv(a.data / "analysis" / "twin_basis_issuer_daily.csv", parse_dates=["date"])
    stats = pd.read_csv(a.data / "analysis" / "twin_issuer_stats.csv")
    iss = pd.read_csv(a.data / "analysis" / "mechanism" / "mechanism_issuer_ratings.csv")
    prof = pd.read_csv(a.data / "analysis" / "mechanism" / "mechanism_spline_profile_cross.csv")
    kink = float(prof.loc[prof["best"], "kink_bp"].iloc[0]) if len(prof) else None
    cds = pd.read_parquet(C.DATA_DIR / "market" / "sovereign_cds.parquet").astype(float)
    if len(kw):
        cds = cds.join(kw.astype(float), how="outer")
    cds.index = pd.to_datetime(cds.index)

    asof = min(today(), daily["date"].max())
    outst = outstanding_sukuk(uni, daily["parent_key"].unique(), asof)
    sav = savings(daily, stats, outst, asof)

    rat = issuer_ratings(uni, list(TARGETS)).set_index("parent_key")
    trows = []
    for key, (label, col) in TARGETS.items():
        cur = float(cds[col].dropna().tail(21).mean()) if col and col in cds and cds[col].notna().any() else np.nan
        trows.append({"name": label, "cds": cur, "sub_ig": bool(rat.loc[key, "sub_ig"]) if key in rat.index else False,
                      "rating": rat.loc[key, "rating_snapshot"] if key in rat.index else None})
    targets = pd.DataFrame(trows)
    cf = counterfactual(iss, targets.dropna(subset=["cds"]), kink)
    no_cds = targets[targets["cds"].isna()]
    if len(no_cds):  # rating-only model for sovereigns without a CDS series
        cf_r = counterfactual(iss, no_cds.assign(cds=0.0), None)
        cf_r = cf_r[cf_r["model"] == "IG vs sub-IG dummy"].assign(current_cds_bp=np.nan)
        cf = pd.concat([cf, cf_r], ignore_index=True)

    sav.to_csv(out / "policy_savings_by_issuer.csv", index=False)
    cf.to_csv(out / "policy_counterfactual.csv", index=False)
    chart_savings(sav, out / "policy_savings.png")

    tot12 = sav["saving_12m_usd_m"].sum(skipna=True)
    totf = sav["saving_full_usd_m"].sum(skipna=True)
    L = ["# Policy numbers: what is the sukuk discount worth?\n",
         f"Generated {date.today():%Y-%m-%d}. As of {asof:%Y-%m-%d}.\n",
         "## a. Annual coupon saving by issuer\n",
         "Saving (USD m a year) = USD sukuk outstanding (maturity after the as-of date; perpetuals excluded) x "
         "minus the mean basis / 10,000. A negative basis means the sukuk yields less than the same issuer's "
         "conventional curve at the same maturity, so the issuer pays that much less coupon on its sukuk. The "
         "90% interval uses the Newey-West standard error of the issuer's daily basis (20 lags). Trailing "
         "12 months = the year to the as-of date; issuers without 20 matched days in that year show blank.\n\n",
         _md(sav),
         f"\nSum across issuers: **{tot12:,.0f}m a year** at trailing-12-month bases, **{totf:,.0f}m** at "
         "full-sample bases. Sums ignore the interval width and cross-issuer correlation.\n",
         "![savings](policy_savings.png)\n",
         "## b. Counterfactual: sovereigns with no USD sukuk\n",
         "**Out-of-sample extrapolation.** The models are fitted on 15 issuers' mean basis (Dubai govt excluded, "
         "as in mechanism_results.md) and applied to each sovereign's current CDS (mean of the last 21 days) "
         f"or snapshot rating. Kuwait CDS: `{KUWAIT_CDS}`. UAE federal has no CDS series on this login, so only "
         "the rating model applies. Saving per USD 1bn issued = minus the predicted basis x USD 0.1m per bp. "
         "Prediction intervals (90%) include the cross-issuer residual spread, which is large.\n\n",
         _md(targets.assign(cds=targets["cds"].round(1))), "\n", _md(cf),
         "\n**Reading:** these sovereigns are investment grade with low CDS, the region where the fitted models "
         "predict a small discount (the investment-grade issuers in the sample, such as KSA and Qatar, average "
         "single digits). The intervals are wide and include zero, so expect a saving of a few bp at most.\n",
         "## Caveats\n",
         "- The saving applies today's basis to bonds issued years ago. It measures the current relative cost, "
         "not the saving each bond achieved at issue (see the primary-market check in data_quality_results.md).",
         "- Secondary-market sukuk quotes are staler than conventional ones (data_quality_results.md), so part "
         "of the measured discount may be quote smoothing.",
         "- Outstanding amounts are USD only, from the security universe.\n"]
    (out / "policy_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Savings:\n%s", sav.to_string(index=False))
    log.info("Counterfactual:\n%s", cf.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
