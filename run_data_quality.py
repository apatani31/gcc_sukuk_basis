"""Secondary-market data quality and a primary-market check (NEXT_PROMPT task 7a-d). No LSEG calls.

Needs: run_twin.py, run_shocks.py, run_drivers.py outputs.

Usage:
    .venv\\Scripts\\python run_data_quality.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.data_quality import (OFF_MARKET_BP, flag_off_market, lead_lag, new_issue_premia, premium_by_issuer,
                              reversal, staleness)
from src.event_study import bond_paths, passthrough
from src.summary import _md
from src.twin import UstCurve, load_panel

log = logging.getLogger("run_data_quality")
WEAK = {"bahrain kingdom", "oman sultanate", "bapco energies", "emirate sharjah"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = ap.parse_args(argv)
    C.setup_logging("run_data_quality")
    out = a.data / "analysis" / "data_quality"
    out.mkdir(parents=True, exist_ok=True)

    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    basis = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")
    keys = basis["parent_key"].unique()
    coverage = pd.read_csv(a.data / "coverage_report.csv", usecols=["instrument_id", "price_ric"])
    panel_im = pd.read_csv(a.data / "analysis" / "drivers" / "drivers_panel_issuer_month.csv")
    shocks = pd.read_csv(C.DATA_DIR / "market" / "oil_shocks_z3_min5pct_h1.csv", parse_dates=["date"])
    shocks["event_id"] = shocks["date"].dt.strftime("%Y-%m-%d") + "_" + shocks["sign"]

    # a. staleness: the twin-curve bond set (fixed coupon, >= USD 100m, one line per bond)
    bonds = uni[(uni["instrument_class"] == "bond") & uni["is_primary_line"] & ~uni["possible_sukuk_mislabel"]
                & uni["parent_key"].isin(keys) & uni["coupon_type"].isin(C.TWIN["coupon_types"])
                & (uni["amount_issued_usd"].fillna(0) >= C.TWIN["min_amount_usd"])]
    bonds = bonds.assign(parent_name=bonds["issuer_name"])
    stale_sum, stale_bonds = staleness(a.data / "timeseries", bonds, coverage)
    stale_src = (stale_bonds.groupby(["group", "price_source"])
                 .agg(bonds=("instrument_id", "size"), unchanged_mid_share=("unchanged_mid_share", "median"),
                      ar1_yield_change=("ar1_daily_yield_change", "median")).round(3).reset_index())

    # b. lead-lag and long-horizon pass-through
    groups = {"All twin issuers": lambda d: d["parent_key"].notna(),
              "Weak credits (Bahrain, Oman, BAPCO, Sharjah)": lambda d: d["parent_key"].isin(WEAK),
              "Other issuers": lambda d: ~d["parent_key"].isin(WEAK),
              "KSA government": lambda d: d["parent_key"] == "arabia kingdom saudi"}
    ll = lead_lag(basis, groups)
    paths = bond_paths(basis, shocks, pre=5, post=120)
    pt = pd.concat([passthrough(paths, basis, shocks["date"], h, exclude_days=max(40, int(h * 1.6)))
                    for h in (5, 20, 60, 120)], ignore_index=True)

    # c. reversal
    rv = reversal(panel_im, {"Pooled (all issuers with CDS)": lambda d: d["parent_key"].notna(),
                             "Oman government": lambda d: d["parent_key"] == "oman sultanate",
                             "Bahrain government": lambda d: d["parent_key"] == "bahrain kingdom",
                             "BAPCO": lambda d: d["parent_key"] == "bapco energies",
                             "Weak credits pooled": lambda d: d["parent_key"].isin(WEAK)})

    # d. primary market
    panel = load_panel(uni, a.data / "timeseries")
    ust = UstCurve(C.TWIN["ust_curve_path"]) if Path(C.TWIN["ust_curve_path"]).exists() else None
    nip = new_issue_premia(uni, panel, keys, ust)
    cds = pd.read_parquet(C.DATA_DIR / "market" / "sovereign_cds.parquet").astype(float)
    cds.index = pd.to_datetime(cds.index)
    cm = cds.resample("ME").mean()
    cm.index = cm.index.to_period("M")
    daily = pd.read_csv(a.data / "analysis" / "twin_basis_issuer_daily.csv")
    secondary = daily.groupby("parent_key")["basis_bp"].mean().rename("mean_basis_bp").reset_index()
    prem = premium_by_issuer(nip, cm, C.ISSUER_SOVEREIGN, secondary)
    nipf = flag_off_market(nip)
    off = nipf[nipf["off_market"]][["issuer", "isin", "issue_date", "is_sukuk", "tenor_at_issue", "yield_at_issue",
                                     "nip_bp"]].round(2)
    nd = nipf.dropna(subset=["nip_bp"])
    nd = nd[~nd["off_market"]]
    grp = nd.assign(weak=nd["parent_key"].isin(WEAK))
    grp_tbl = (grp.groupby(["weak", "is_sukuk"])["nip_bp"].agg(bonds="size", mean_bp="mean", median_bp="median")
               .round(1).reset_index())
    grp_tbl["weak"] = grp_tbl["weak"].map({True: "Weak credits", False: "Other issuers"})
    grp_tbl["is_sukuk"] = grp_tbl["is_sukuk"].map({True: "Sukuk", False: "Conventional"})
    both = prem.dropna(subset=["sukuk_minus_conv_bp", "secondary_basis_bp"])
    corr = both["sukuk_minus_conv_bp"].corr(both["secondary_basis_bp"]) if len(both) > 2 else float("nan")
    s_only = prem.dropna(subset=["sukuk_nip_median_bp", "secondary_basis_bp"])
    corr_s = s_only["sukuk_nip_median_bp"].corr(s_only["secondary_basis_bp"]) if len(s_only) > 2 else float("nan")
    import numpy as np
    from scipy import stats as _st
    wk = grp[grp["is_sukuk"]]
    tt = _st.ttest_ind(wk.loc[wk["weak"], "nip_bp"], wk.loc[~wk["weak"], "nip_bp"], equal_var=False)
    diff_txt = (f"Weak-credit sukuk priced {wk.loc[wk['weak'], 'nip_bp'].mean() - wk.loc[~wk['weak'], 'nip_bp'].mean():+.1f}bp "
                f"relative to other issuers' sukuk (mean difference, Welch t = {tt.statistic:.1f}).")
    status = nip["match_method"].value_counts().to_dict()

    for name, df in (("dq_staleness_summary", stale_sum), ("dq_staleness_by_source", stale_src),
                     ("dq_lead_lag", ll), ("dq_passthrough_horizons", pt), ("dq_reversal", rv),
                     ("dq_new_issue_premium_by_issuer", prem), ("dq_new_issue_premium_groups", grp_tbl)):
        df.to_csv(out / f"{name}.csv", index=False)

    L = ["# Secondary-market data quality and a primary-market check\n",
         f"Generated {date.today():%Y-%m-%d}. Bonds: the twin-curve set (fixed coupon, at least USD 100m, one line "
         "per bond) of the twin issuers.\n",
         "## a. How stale are sukuk quotes?\n",
         "Per bond, 2019 onward (bonds with 100+ days): share of days the mid price did not change, median "
         "bid-ask in price cents, first-order autocorrelation of daily yield changes (positive = sluggish "
         "quotes; negative = bounce or noise), median absolute daily yield change, and the share priced from "
         "Tradeweb `=TE` rather than a composite RIC (coverage_report.csv).\n\n",
         _md(stale_sum), "\n**By price source:**\n\n", _md(stale_src),
         "\n## b. Do sukuk marks lag the conventional curve?\n",
         "Daily sukuk yield change on the same-day and lagged (1-5 days) change in the matched conventional "
         "yield. Standard errors clustered by month. Sizeable lag coefficients mean sukuk marks update slowly; "
         "a *total* below 1 means sukuk move less even after a week.\n\n", _md(ll),
         "\n**Pass-through after oil shocks vs normal days, up to 120 business days** (slope of the sukuk-leg "
         "change on the conventional-leg change; normal days exclude windows around shocks):\n\n", _md(pt),
         "\n## c. Does the CDS effect reverse?\n",
         "Monthly basis change on the CDS change (per 100bp) and its six lags. If the same-month effect were a "
         "stale-quote artefact, the lags would undo it (share_reversed near 1). `net` is the cumulative effect "
         "after six months.\n\n", _md(rv),
         "\n## d. Primary market: new-issue premium\n",
         "For each new fixed-rate bond of a twin issuer with a yield at issue (computed, 30/360, from coupon and "
         "issue price), the premium is the yield at issue minus the issuer's conventional curve on the last "
         f"trading day at least 5 business days before the issue date (within {10} further days), matched at "
         "the new bond's maturity with the same rules as twin.py (interpolation, or the US Treasury-adjusted "
         "nearest bond within 1 year). New conventional bonds are compared with the issuer's *other* "
         "conventional bonds the same way. *Sukuk minus conventional* nets out the ordinary new-issue concession, "
         "leaving the primary-market sukuk discount.\n\n",
         f"Matching status of new issues: {status}.\n\n",
         f"**Off-market deals excluded** (|premium| > {OFF_MARKET_BP:.0f}bp; e.g. 1% coupon official placements "
         "that are not market transactions):\n\n", _md(off) if len(off) else "_none_\n",
         "\n**Weak credits vs other issuers** (market deals only):\n\n", _md(grp_tbl), "\n", diff_txt, "\n",
         "\n**By issuer** (medians; secondary_basis_bp = the issuer's mean twin-curve basis):\n\n", _md(prem),
         f"\nCorrelation across issuers with the secondary-market basis: sukuk new-issue premium **{corr_s:.2f}** "
         f"({len(s_only)} issuers); sukuk-minus-conventional premium **{corr:.2f}** ({len(both)} issuers with both).\n",
         "\n## Caveats\n",
         "- Yield at issue is computed (30/360, settlement on the issue date). LSEG secondary yields use their "
         "own conventions, so levels can differ by a few bp. The sukuk-minus-conventional difference cancels "
         "most of this.",
         "- Pre-2019 price coverage is thin, so early issues often have no curve.",
         "- Staleness metrics depend on the price source (Tradeweb vs composite) as well as on the bond type.\n"]
    (out / "data_quality_results.md").write_text("\n".join(L), encoding="utf-8")
    for nm, df in (("Staleness", stale_sum), ("Lead-lag", ll), ("Pass-through", pt), ("Reversal", rv),
                   ("NIP groups", grp_tbl), ("NIP by issuer", prem)):
        log.info("%s:\n%s", nm, df.to_string(index=False))
    log.info("corr primary vs secondary %.2f; status %s", corr, status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
