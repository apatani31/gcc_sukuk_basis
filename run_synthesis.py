"""Synthesis: headline numbers, main specifications and the three key charts (NEXT_PROMPT task 6).

Reads only the CSV outputs of the other stages (run them first), so every number here traces back to a
stage report. No LSEG calls.

Usage:
    .venv\\Scripts\\python run_synthesis.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.summary import _md

log = logging.getLogger("run_synthesis")


def row(df: pd.DataFrame, **match) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for k, v in match.items():
        m &= df[k] == v
    if not m.any():
        raise KeyError(f"no row matching {match}")
    return df[m].iloc[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = ap.parse_args(argv)
    C.setup_logging("run_synthesis")
    A = a.data / "analysis"
    rd = lambda p: pd.read_csv(A / p)  # noqa: E731

    rob, level = rd("twin_robustness.csv"), rd("credit/credit_level_gap.csv").iloc[0]
    slopes, within = rd("credit/credit_issuer_slopes.csv"), rd("credit/credit_within_issuer.csv")
    mech, thr, inf = (rd("mechanism/mechanism_regressions.csv"), rd("mechanism/mechanism_threshold.csv"),
                      rd("mechanism/mechanism_inference.csv"))
    nipg, nipi = rd("data_quality/dq_new_issue_premium_groups.csv"), rd("data_quality/dq_new_issue_premium_by_issuer.csv")
    stale, ll, rev = (rd("data_quality/dq_staleness_summary.csv"), rd("data_quality/dq_lead_lag.csv"),
                      rd("data_quality/dq_reversal.csv"))
    pt = rd("data_quality/dq_passthrough_horizons.csv")
    ev, imp = rd("event_study/event_key_main.csv"), rd("oil_credit/oil_implied_vs_direct.csv")
    cdsev = rd("oil_credit/oil_cds_event_pooled.csv")
    sav, cf = rd("policy/policy_savings_by_issuer.csv"), rd("policy/policy_counterfactual.csv")

    tw = row(rob, variant=rob["variant"].iloc[0])
    oman = row(slopes, issuer="Oman, Sultanate of (Government)")
    bah = row(slopes, issuer="Bahrain, Kingdom of (Government)")
    panel = row(within, model="Sovereign CDS + liquidity gap")
    fd = row(inf, model="First differences: d(basis) ~ d(CDS) + d(liquidity)")
    sub_extra = row(thr, term="cds100:sub_ig_oman_i")
    ig_slope = row(thr, model="Within issuers: CDS slope, investment grade")
    tenor = row(mech, term="cds100:tau_c")
    ijara = row(mech, term="cds100:ijara")
    ib = row(mech, term="cds100:ib_c")
    liq = row(mech, term="liq_gap")
    wk_s = row(nipg, weak="Weak credits", is_sukuk="Sukuk")
    wk_c = row(nipg, weak="Weak credits", is_sukuk="Conventional")
    ot_s = row(nipg, weak="Other issuers", is_sukuk="Sukuk")
    both = nipi.dropna(subset=["sukuk_minus_conv_bp", "secondary_basis_bp"])
    corr_ps = both["sukuk_minus_conv_bp"].corr(both["secondary_basis_bp"])
    st_s, st_c = row(stale, group="Sukuk"), row(stale, group="Conventional")
    ll_all, ll_ksa = row(ll, group="All twin issuers"), row(ll, group="KSA government")
    ll_weak = ll[ll["group"].str.startswith("Weak")].iloc[0]
    rv_pool = rev[rev["sample"].str.startswith("Pooled")].iloc[0]
    rv_bah = row(rev, sample="Bahrain government")
    pt120 = pt[(pt["horizon_days"] == 120) & (pt["sample"] == "Shocks ex-2020")].iloc[0]
    mde5, mde20 = row(ev, shock="pooled", tau=5)["basis MDE 80% (bp)"], row(ev, shock="pooled", tau=20)["basis MDE 80% (bp)"]
    med5 = row(ev, shock="pooled", tau=5)["basis median"]
    imp5 = row(imp, tau=5)
    up5 = row(cdsev, sample="All shocks", shock="up", tau=5)
    sav = sav.dropna(subset=["saving_12m_usd_m"])
    top = sav.sort_values("saving_12m_usd_m", ascending=False).head(3)
    cf_rng = (cf["saving_per_usd_1bn_m"].min(), cf["saving_per_usd_1bn_m"].max())

    H = [
        ("Sukuk trade below their own issuer's conventional curve",
         f"{tw.mean_of_issuer_means_bp:.1f}bp average across {tw.issuers} issuers (median {tw.median_of_issuer_means_bp:.1f}bp); "
         f"{tw.issuers_negative} of {tw.issuers} negative; {int(level.governments_negative)} of "
         f"{int(level.governments)} government groups negative on average.",
         "Holding the issuer fixed, investors accept a lower yield on sukuk."),
        ("The discount is a sub-investment-grade phenomenon",
         f"Sub-IG issuers {level.sub_ig_mean_bp:.0f}bp vs investment grade {level.ig_mean_bp:.0f}bp: gap "
         f"{level.gap_bp:.0f}bp, wild bootstrap p = {level.p_wild_government:.3f} by government.",
         "A threshold, not a smooth gradient: investment-grade issuers get single-digit discounts."),
        ("Within the weakest sovereigns, the discount moves with credit risk",
         f"Oman {oman.slope_levels_per_100bp:+.1f}bp and Bahrain {bah.slope_levels_per_100bp:+.1f}bp per 100bp of CDS "
         f"(Newey-West t {oman.t_nw_levels:.1f}, {bah.t_nw_levels:.1f}); also in monthly changes "
         f"({oman.slope_changes_per_100bp:+.1f}, {bah.slope_changes_per_100bp:+.1f}). For investment-grade issuers "
         f"the within slope is {ig_slope.coef_bp:+.1f}bp.",
         f"The pooled panel slope ({panel.slope_per_100bp:+.1f}bp) is not significant on its own once only six CDS "
         f"series are counted (wild bootstrap p = {panel.p_wild_government:.2f}); the case studies carry the claim."),
        ("The discount exists at issue, not only in secondary quotes",
         f"Weak-credit sukuk priced a median {wk_s.median_bp:+.1f}bp against their issuer's conventional curve at issue, "
         f"vs {wk_c.median_bp:+.1f}bp for the same issuers' new conventional bonds and {ot_s.median_bp:+.1f}bp for "
         f"other issuers' sukuk; issuer-level correlation with the secondary basis {corr_ps:.2f}.",
         "Stale secondary quotes cannot explain a discount that is already there on the pricing date."),
        ("Sukuk quotes are somewhat stale, but that is not the story",
         f"Unchanged mid price on {st_s.unchanged_mid_share:.1%} of days for sukuk vs {st_c.unchanged_mid_share:.1%} "
         f"for conventionals; sukuk absorb {ll_all.same_day:.2f} of a conventional move on the day and "
         f"{ll_all.total:.2f} within a week (weak credits {ll_weak.total:.2f}, KSA {ll_ksa.total:.2f}); "
         f"{rv_pool.share_reversed:.0%} of the pooled same-month CDS effect reverses within six months (Bahrain: "
         + (f"{rv_bah.share_reversed:.0%})." if rv_bah.share_reversed > 0 else "no reversal)."),
         f"Even after 120 business days sukuk move {pt120.beta_shock:.2f}bp per conventional bp: damping is real, "
         "and stale quotes explain only part of the monthly CDS response."),
        ("Mechanism: maturity matters, asset backing and local funding do not",
         f"CDS slope steepens by {tenor.coef_bp:+.1f}bp per 100bp per year of maturity (wild p {tenor.p_wild_government:.2f}); "
         f"CDS x Ijara {ijara.coef_bp:+.1f} (p {ijara.p_wild_government:.2f}); CDS x interbank {ib.coef_bp:+.2f} per bp "
         f"(p {ib.p_wild_government:.2f}); less liquid sukuk price richer ({liq.coef_bp:+.2f}bp per bp bid-ask gap, "
         f"p {liq.p_wild_government:.3f}).",
         "Consistent with default/recovery pricing over tenor plus buy-and-hold demand; asset backing (Ijara) "
         "does not carry it."),
        ("Oil shocks do not move the basis directly",
         f"Median basis response to an oil-price rise {med5:+.1f}bp at +5 days; the test could detect {mde5:.1f}bp (+5) "
         f"or {mde20:.1f}bp (+20) with 80% power. Implied via credit: {imp5.implied_basis_bp:+.2f}bp "
         f"(90% CI {imp5.implied_ci90}).",
         f"Oil reaches the basis only through credit risk, and oil up-shocks in this sample raise GCC CDS "
         f"(median {up5.median_bp:+.1f}bp at +5 days, placebo p {up5.placebo_p_median:.3f}); several of them are "
         "regional conflicts."),
        ("What it is worth",
         "; ".join(f"{r.issuer.split(',')[0]} about USD {r.saving_12m_usd_m:,.0f}m a year" for r in top.itertuples())
         + f" (trailing-12-month basis x outstanding USD sukuk). Investment-grade sovereigns without USD sukuk "
         f"(Kuwait, Abu Dhabi, UAE federal): predicted USD {cf_rng[0]:.1f}-{cf_rng[1]:.1f}m per USD 1bn issued, intervals "
         "including zero.",
         "Sukuk issuance pays most for the weakest credits, which is where the discount sits."),
    ]

    spec = pd.DataFrame([
        {"specification": "Twin-curve basis, cross-issuer mean", "estimate": f"{tw.mean_of_issuer_means_bp:.1f}bp",
         "inference": f"t = {tw.t:.2f} across {tw.issuers} issuers", "source": "twin_results.md"},
        {"specification": "Sub-IG minus IG basis (level)", "estimate": f"{level.gap_bp:.1f}bp",
         "inference": f"wild p = {level.p_wild_government:.3f} (government, {int(level.clusters)} clusters)",
         "source": "credit_results.md"},
        {"specification": "Oman: basis on CDS, levels / changes",
         "estimate": f"{oman.slope_levels_per_100bp:+.1f} / {oman.slope_changes_per_100bp:+.1f} per 100bp",
         "inference": f"NW t {oman.t_nw_levels:.1f} / {oman.t_nw_changes:.1f}", "source": "credit_results.md"},
        {"specification": "Bahrain: basis on CDS, levels / changes",
         "estimate": f"{bah.slope_levels_per_100bp:+.1f} / {bah.slope_changes_per_100bp:+.1f} per 100bp",
         "inference": f"NW t {bah.t_nw_levels:.1f} / {bah.t_nw_changes:.1f}", "source": "credit_results.md"},
        {"specification": "Panel within slope (issuer FE + liquidity)", "estimate": f"{panel.slope_per_100bp:+.1f} per 100bp",
         "inference": f"cluster t {panel.t_cluster_issuer:.1f}; wild p = {panel.p_wild_government:.2f} (gov), "
                      f"{panel.p_wild_issuer:.2f} (issuer)", "source": "credit_results.md"},
        {"specification": "Panel, first differences", "estimate": f"{fd.coef_bp:+.1f} per 100bp",
         "inference": f"wild p = {fd.p_wild_government:.2f} (gov)", "source": "mechanism_results.md"},
        {"specification": "Extra within slope for sub-IG issuers", "estimate": f"{sub_extra.coef_bp:+.1f} per 100bp",
         "inference": f"wild p = {sub_extra.p_wild_government:.2f} (gov), {sub_extra.p_wild_issuer:.2f} (issuer)",
         "source": "mechanism_results.md"},
        {"specification": "CDS x remaining maturity", "estimate": f"{tenor.coef_bp:+.2f} per 100bp per year",
         "inference": f"wild p = {tenor.p_wild_government:.3f} (gov)", "source": "mechanism_results.md"},
        {"specification": "Liquidity gap", "estimate": f"{liq.coef_bp:+.2f}bp per bp",
         "inference": f"wild p = {liq.p_wild_government:.3f} (gov)", "source": "mechanism_results.md"},
        {"specification": "New-issue premium, weak-credit sukuk minus conventional",
         "estimate": f"{wk_s.median_bp - wk_c.median_bp:+.1f}bp (medians)",
         "inference": f"{int(wk_s.bonds)} sukuk, {int(wk_c.bonds)} conventional", "source": "data_quality_results.md"},
        {"specification": "Oil-price rise, basis at +5 days (median)", "estimate": f"{med5:+.1f}bp",
         "inference": f"MDE80 {mde5:.1f}bp", "source": "event_study.md"},
        {"specification": "Implied via CDS, +5 days", "estimate": f"{imp5.implied_basis_bp:+.2f}bp",
         "inference": f"90% CI {imp5.implied_ci90}", "source": "oil_credit_results.md"},
    ])
    spec.to_csv(A / "synthesis_main_specifications.csv", index=False)
    pd.DataFrame([{"headline": h, "number": n, "interpretation": i} for h, n, i in H]).to_csv(
        A / "synthesis_headlines.csv", index=False)

    L = ["# GCC sukuk vs conventional bonds: synthesis\n",
         f"Generated {date.today():%Y-%m-%d}. Every number below is read from a stage report's CSV output.\n",
         "## Headline numbers\n"]
    for i, (h, n, interp) in enumerate(H, 1):
        L += [f"{i}. **{h}.** {n}", f"   *{interp}*"]
    L += ["\n## Main specifications\n", _md(spec),
          "\n## Charts\n",
          "**1. The discount across issuers is a threshold** (sub-investment-grade issuers marked as squares; the "
          "Dubai government's basis rests on 20-year interpolation brackets and is excluded from the fits):\n",
          "![threshold](mechanism/mechanism_threshold_cross.png)\n",
          "**2. Within issuers, the discount follows the government's CDS where CDS moves** (Bahrain, Oman), "
          "and stays near zero where it does not (KSA):\n",
          "![case studies](credit/credit_case_studies.png)\n",
          "**3. What the discount is worth by issuer:**\n",
          "![savings](policy/policy_savings.png)\n",
          "## Where to read more\n",
          "- twin_results.md: the twin-curve method, matching validation and the basis by issuer.",
          "- credit/credit_results.md: CDS evidence, case studies, wild bootstrap.",
          "- mechanism/mechanism_results.md: structure, tenor, captive demand, threshold, inference.",
          "- data_quality/data_quality_results.md: staleness, lead-lag, reversal, primary market.",
          "- event_study/event_study.md and oil_credit/oil_credit_results.md: oil shocks and the credit channel.",
          "- policy/policy_results.md: savings and the counterfactual.",
          "- drivers/drivers_results.md: interbank, issuance and the common factor.\n",
          "## Main caveats\n",
          "- Six independent sovereign CDS series and 18 issuers: small-sample inference throughout.",
          "- Ratings are snapshots; Oman's sovereign is treated as sub-IG because it was for most of the sample.",
          "- Secondary sukuk quotes are staler than conventional ones; the primary-market check is the defence.",
          "- Raw LSEG data is not distributed with this repository.\n"]
    (A / "synthesis.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote %s", A / "synthesis.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
