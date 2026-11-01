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
from src.data_quality import (OFF_MARKET_BP, RULES, changes_vs_legacy, classify_deals, flag_off_market,
                              issuer_month_status, lead_lag, new_issue_premia, premium_by_issuer, reversal,
                              rule_summary, staleness)
from src.event_study import bond_paths, passthrough
from src.ratings import ISSUER_GOVERNMENT, load_ratings
from src.summary import _md
from src.twin import UstCurve, load_panel

log = logging.getLogger("run_data_quality")
PM = C.PRIMARY_MARKET


def reading(summ: pd.DataFrame) -> list[str]:
    """Plain-language reading computed from the rule summary (no hand-typed numbers)."""
    allr = summ[summ["sample"] == "All issuers"].set_index("rule")
    exb = summ[summ["sample"] != "All issuers"].set_index("rule")
    core = [r for r in ("MAIN", "Robustness A", "Robustness B") if r in allr.index]
    holds = all(allr.loc[r, "weak_sukuk_minus_conv_bp"] < 0
                and allr.loc[r, "weak_sukuk_median_bp"] < allr.loc[r, "other_sukuk_median_bp"] for r in core)
    gaps = [allr.loc[r, "weak_sukuk_minus_conv_bp"] for r in core]
    m, mx = allr.loc["MAIN"], exb.loc["MAIN"]
    out = [f"- **Does it hold under all three rules?** {'Yes' if holds else 'Not under every rule'}: weak-credit "
           f"sukuk minus weak-credit conventional (medians) is {', '.join(f'{r} {g:+.1f}bp' for r, g in zip(core, gaps))}, "
           f"a range of {min(gaps):+.1f} to {max(gaps):+.1f}bp.",
           f"- **MAIN:** weak-credit sukuk median {m.weak_sukuk_median_bp:+.1f}bp (n = {int(m.weak_sukuk_n)}) against "
           f"{m.weak_conv_median_bp:+.1f}bp for weak-credit conventional bonds (n = {int(m.weak_conv_n)}) and "
           f"{m.other_sukuk_median_bp:+.1f}bp for other issuers' sukuk (Welch t {m.welch_t_weak_vs_other_sukuk:.1f}).",
           f"- **Dependence on Bahrain:** without Bahrain and BAPCO, MAIN leaves {int(mx.weak_sukuk_n)} weak-credit "
           f"sukuk (median {mx.weak_sukuk_median_bp:+.1f}bp; sukuk-minus-conventional gap "
           f"{mx.weak_sukuk_minus_conv_bp:+.1f}bp). "
           + ("That is too few to test, so under MAIN the primary-market result rests on Bahrain. "
              if mx.weak_sukuk_n < 5 else "")
           + "The rules that classify more non-Bahraini deals as weak give: "
           + "; ".join(f"{r} {exb.loc[r, 'weak_sukuk_minus_conv_bp']:+.1f}bp (n = {int(exb.loc[r, 'weak_sukuk_n'])} sukuk"
                       + (f", Welch t {exb.loc[r, 'welch_t_weak_vs_other_sukuk']:.1f})"
                          if pd.notna(exb.loc[r, 'welch_t_weak_vs_other_sukuk']) else ")")
                       for r in ("Robustness A", "Robustness B") if r in exb.index)
           + ". The discount is smaller without Bahrain but keeps its sign."]
    return out


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
    ratings = load_ratings(C.SOVEREIGN_RATINGS_PATH) if C.SOVEREIGN_RATINGS_PATH.exists() else None
    if ratings is None:
        log.warning("No %s: rating rules (MAIN, Robustness A) leave every deal unclassified",
                    C.SOVEREIGN_RATINGS_PATH.name)

    # Issuer-month credit status under the MAIN rule (for the weak-credit rows of sections a-c)
    months = pd.period_range(basis["date"].min().to_period("M"), basis["date"].max().to_period("M"), freq="M")
    status = (issuer_month_status(ratings, ISSUER_GOVERNMENT, keys, months) if ratings is not None
              else pd.DataFrame(columns=["parent_key", "month", "sub_main"]))

    # a. staleness: the twin-curve bond set (fixed coupon, >= USD 100m, one line per bond)
    bonds = uni[(uni["instrument_class"] == "bond") & uni["is_primary_line"] & ~uni["possible_sukuk_mislabel"]
                & uni["parent_key"].isin(keys) & uni["coupon_type"].isin(C.TWIN["coupon_types"])
                & (uni["amount_issued_usd"].fillna(0) >= C.TWIN["min_amount_usd"])]
    bonds = bonds.assign(parent_name=bonds["issuer_name"])
    stale_sum, stale_bonds, stale_credit = staleness(a.data / "timeseries", bonds, coverage, status=status)
    stale_src = (stale_bonds.groupby(["group", "price_source"])
                 .agg(bonds=("instrument_id", "size"), unchanged_mid_share=("unchanged_mid_share", "median"),
                      ar1_yield_change=("ar1_daily_yield_change", "median")).round(3).reset_index())

    # b. lead-lag (weak credit = sub-IG issuer-month under MAIN) and long-horizon pass-through
    bm = basis.assign(month=basis["date"].dt.strftime("%Y-%m")).merge(status, on=["parent_key", "month"], how="left")
    groups = {"All twin issuers": lambda d: d["parent_key"].notna(),
              "Weak credit issuer-months (MAIN rule)": lambda d: d["sub_main"] == 1,
              "Other issuer-months (MAIN rule)": lambda d: d["sub_main"] == 0,
              "KSA government": lambda d: d["parent_key"] == "arabia kingdom saudi"}
    ll = lead_lag(bm, groups)
    paths = bond_paths(basis, shocks, pre=5, post=120)
    pt = pd.concat([passthrough(paths, basis, shocks["date"], h, exclude_days=max(40, int(h * 1.6)))
                    for h in (5, 20, 60, 120)], ignore_index=True)

    # c. reversal
    pim = panel_im.merge(status, on=["parent_key", "month"], how="left")
    rv = reversal(pim, {"Pooled (all issuers with CDS)": lambda d: d["parent_key"].notna(),
                        "Oman government": lambda d: d["parent_key"] == "oman sultanate",
                        "Bahrain government": lambda d: d["parent_key"] == "bahrain kingdom",
                        "BAPCO": lambda d: d["parent_key"] == "bapco energies",
                        "Weak credit issuer-months pooled (MAIN rule)": lambda d: d["sub_main"] == 1})

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
    deals = classify_deals(flag_off_market(nip), ratings, ISSUER_GOVERNMENT, cds, ust, PM)
    off = deals[deals["off_market"]][["issuer", "isin", "issue_date", "is_sukuk", "tenor_at_issue",
                                      "yield_at_issue", "nip_bp"]].round(2)
    grp_tbl, summ = rule_summary(deals, RULES)
    ch_counts, ch_deals = changes_vs_legacy(deals)
    both = prem.dropna(subset=["sukuk_minus_conv_bp", "secondary_basis_bp"])
    corr = both["sukuk_minus_conv_bp"].corr(both["secondary_basis_bp"]) if len(both) > 2 else float("nan")
    s_only = prem.dropna(subset=["sukuk_nip_median_bp", "secondary_basis_bp"])
    corr_s = s_only["sukuk_nip_median_bp"].corr(s_only["secondary_basis_bp"]) if len(s_only) > 2 else float("nan")
    match_status = nip["match_method"].value_counts().to_dict()
    unc = deals.dropna(subset=["nip_bp"])
    unc = unc[~unc["off_market"] & unc["sub_MAIN"].isna()]["issuer"].value_counts().to_dict()

    for name, df in (("dq_staleness_summary", stale_sum), ("dq_staleness_by_source", stale_src),
                     ("dq_staleness_by_credit", stale_credit), ("dq_lead_lag", ll),
                     ("dq_passthrough_horizons", pt), ("dq_reversal", rv),
                     ("dq_new_issue_premium_by_issuer", prem), ("dq_new_issue_premium_groups", grp_tbl),
                     ("dq_primary_rule_summary", summ), ("dq_primary_reclassified_by_issuer", ch_counts)):
        df.to_csv(out / f"{name}.csv", index=False)
    # deal-level files: not matched by the .gitignore whitelist (dq_*.csv), so they stay local
    deals.to_csv(out / "deal_level_new_issues.csv", index=False)
    ch_deals.to_csv(out / "deal_level_reclassified.csv", index=False)

    def rule_block(rule: str) -> list[str]:
        g = grp_tbl[(grp_tbl["rule"] == rule) & (grp_tbl["sample"] == "All issuers")].drop(columns=["rule", "sample"])
        s = summ[(summ["rule"] == rule) & (summ["sample"] == "All issuers")].drop(columns=["rule", "sample"])
        return [f"\n### {rule}: {PM['rules'][rule]}\n", _md(g), "\n", _md(s)]

    bah = summ[summ["sample"] != "All issuers"].drop(columns=["sample"])
    main_changes = ch_deals[ch_deals["rule"] == "MAIN"].drop(columns=["rule"]) if len(ch_deals) else ch_deals
    L = ["# Secondary-market data quality and a primary-market check\n",
         f"Generated {date.today():%Y-%m-%d}. Bonds: the twin-curve set (fixed coupon, at least USD 100m, one line "
         "per bond) of the twin issuers. **Weak credit** in every table means sub-investment grade under the MAIN "
         "rule (at least two of S&P, Moody's and Fitch below BBB-/Baa3; see README.md). Sections a to c classify "
         "each **issuer-month**; section d classifies each **deal at its reference date**. There is no fixed list "
         "of weak issuers: Oman, for example, is a weak credit only while two agencies rate it below investment "
         "grade.\n",
         "## a. How stale are sukuk quotes?\n",
         "Per bond, 2019 onward (bonds with 100+ days): share of days the mid price did not change, median "
         "bid-ask in price cents, first-order autocorrelation of daily yield changes (positive = sluggish "
         "quotes; negative = bounce or noise), median absolute daily yield change, and the share priced from "
         "Tradeweb `=TE` rather than a composite RIC (coverage_report.csv).\n\n",
         _md(stale_sum), "\n**By price source:**\n\n", _md(stale_src),
         "\n**By credit status** (each bond's days split by its issuer-month status under MAIN; segments with 60+ "
         "days):\n\n", _md(stale_credit),
         "\n## b. Do sukuk marks lag the conventional curve?\n",
         "Daily sukuk yield change on the same-day and lagged (1-5 days) change in the matched conventional "
         "yield. Standard errors clustered by month. Sizeable lag coefficients mean sukuk marks update slowly; "
         "a *total* below 1 means sukuk move less even after a week. Weak-credit rows use sub-IG issuer-months "
         "under MAIN.\n\n", _md(ll),
         "\n**Pass-through after oil shocks vs normal days, up to 120 business days** (slope of the sukuk-leg "
         "change on the conventional-leg change; normal days exclude windows around shocks):\n\n", _md(pt),
         "\n## c. Does the CDS effect reverse?\n",
         "Monthly basis change on the CDS change (per 100bp) and its six lags. If the same-month effect were a "
         "stale-quote artefact, the lags would undo it (share_reversed near 1). `net` is the cumulative effect "
         "after six months. The pooled weak-credit row uses sub-IG issuer-months under MAIN.\n\n", _md(rv),
         "\n## d. Primary market: new-issue premium\n",
         "For each new fixed-rate bond of a twin issuer with a yield at issue (computed, 30/360, from coupon and "
         "issue price), the premium is the yield at issue minus the issuer's conventional curve on the last "
         "trading day at least 5 business days before the issue date (within 10 further days), matched at "
         "the new bond's maturity with the same rules as twin.py (interpolation, or the US Treasury-adjusted "
         "nearest bond within 1 year). New conventional bonds are compared with the issuer's *other* "
         "conventional bonds the same way. *Sukuk minus conventional* nets out the ordinary new-issue concession, "
         "leaving the primary-market sukuk discount.\n\n",
         f"Matching status of new issues: {match_status}.\n\n",
         f"**Off-market deals excluded** (|premium| > {OFF_MARKET_BP:.0f}bp; e.g. 1% coupon official placements "
         "that are not market transactions):\n\n", _md(off) if len(off) else "_none_\n",
         "\n**Which deals count as weak credit.** Each deal is classified on its **reference date**: the curve date "
         "above, a proxy for the pricing date (the export has no pricing date). Rating rows dated after the "
         "reference date are not used. State companies take their owner's rating (BAPCO and Bahrain; Oman "
         "Electricity Transmission and Oman; Aramco, PIF, SNB, BSF and KSA; DP World, ICD, DAE and Dubai, whose "
         "rows are the DEWA proxy; FAB, Mamoura and Abu Dhabi). The multilateral Arab Energy Fund has no "
         f"government rating, so the rating rules leave it unclassified ({unc or 'none'}). The MAIN rule was "
         "chosen before seeing these results; the others are robustness checks.\n",
         "\n**Reading:**\n", *reading(summ),
         *rule_block("MAIN"), *rule_block("Robustness A"), *rule_block("Robustness B"),
         "\n### Excluding Bahrain (government and BAPCO)\n", _md(bah),
         *rule_block("Legacy"),
         "\n### Deals classified differently from the legacy list\n",
         "Counts by issuer (market deals). *unclassified* = no government rating under that rule.\n\n",
         _md(ch_counts) if len(ch_counts) else "_none_\n",
         "\n**MAIN rule, deal by deal:**\n\n", _md(main_changes) if len(main_changes) else "_none_\n",
         "\n**By issuer** (medians; secondary_basis_bp = the issuer's mean twin-curve basis):\n\n", _md(prem),
         f"\nCorrelation across issuers with the secondary-market basis: sukuk new-issue premium **{corr_s:.2f}** "
         f"({len(s_only)} issuers); sukuk-minus-conventional premium **{corr:.2f}** ({len(both)} issuers with both).\n",
         "\n## Caveats\n",
         "- Yield at issue is computed (30/360, settlement on the issue date). LSEG secondary yields use their "
         "own conventions, so levels can differ by a few bp. The sukuk-minus-conventional difference cancels "
         "most of this.",
         "- Pre-2019 price coverage is thin, so early issues often have no curve.",
         "- Ratings are hand-compiled from public announcements (data/market/sovereign_ratings.csv); Dubai uses "
         "the DEWA proxy.",
         "- Staleness metrics depend on the price source (Tradeweb vs composite) as well as on the bond type.\n"]
    (out / "data_quality_results.md").write_text("\n".join(L), encoding="utf-8")
    for nm, df in (("Rule summary", summ), ("Changes vs legacy", ch_counts), ("Lead-lag", ll), ("Reversal", rv),
                   ("Staleness by credit", stale_credit)):
        log.info("%s:\n%s", nm, df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
