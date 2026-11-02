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
from src.inference import fmt_p, holm
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
    pr, nipi = rd("data_quality/dq_primary_rule_summary.csv"), rd("data_quality/dq_new_issue_premium_by_issuer.csv")
    stale, ll, rev = (rd("data_quality/dq_staleness_summary.csv"), rd("data_quality/dq_lead_lag.csv"),
                      rd("data_quality/dq_reversal.csv"))
    pt = rd("data_quality/dq_passthrough_horizons.csv")
    ev, imp = rd("event_study/event_key_main.csv"), rd("oil_credit/oil_implied_vs_direct.csv")
    cdsev = rd("oil_credit/oil_cds_event_pooled.csv")
    sav, cf = rd("policy/policy_savings_by_issuer.csv"), rd("policy/policy_counterfactual.csv")
    tv, oba = rd("mechanism/mechanism_time_varying.csv"), rd("mechanism/mechanism_oman_before_after.csv")
    struct = rd("mechanism/mechanism_structure_overall.csv").set_index("structure")["sukuk"]
    logo, perm = rd("robustness/robustness_leave_one_government.csv"), rd("robustness/robustness_permutation.csv").iloc[0]
    periods, structure = rd("robustness/robustness_periods.csv"), rd("robustness/robustness_structure.csv")
    no_bah, no_oman = row(logo, sample="Without Bahrain"), row(logo, sample="Without Oman")
    p_early, p_late = row(periods, sample="Before 2021"), row(periods, sample="2023 onward")
    twin_struct, ctl_struct = structure.iloc[0], structure.iloc[-1]

    tw = row(rob, variant=rob["variant"].iloc[0])
    oman = row(slopes, issuer="Oman, Sultanate of (Government)")
    bah = row(slopes, issuer="Bahrain, Kingdom of (Government)")
    panel = row(within, model="Sovereign CDS + liquidity gap")
    fd = row(inf, model="First differences: d(basis) ~ d(CDS) + d(liquidity)")
    sub_extra = row(thr, term="cds100:sub_ig_oman_i")
    tenor = row(mech, term="cds100:tau_c")
    ijara = row(mech, term="cds100:ijara")
    ib = row(mech, term="cds100:ib_c")
    liq = row(mech, term="liq_gap")
    # Holm correction across the four mechanism tests (government-clustered wild bootstrap p-values)
    four = [tenor, ijara, ib, liq]
    hp = dict(zip(("tenor", "ijara", "ib", "liq"), holm([r.p_wild_government for r in four])))
    n_struct, n_ijara, n_hybrid = int(struct.sum()), int(struct.get("Ijara", 0)), int(struct.get("Hybrid Sukuk", 0))
    tv_cds = tv[tv["model"].str.startswith("CDS >") & (tv["term"] == "sub_t")].iloc[0]
    tv_rat = tv[(tv["model"].str.startswith("Ratings") | tv["model"].str.startswith("Lowest")) & (tv["term"] == "sub_t")]
    tv_main = tv_rat[tv_rat["model"].str.startswith("Ratings, 2 of 3")].iloc[0]
    tv_exd = tv_rat[tv_rat["model"].str.contains("Dubai excluded")].iloc[0]
    tv_exs = tv_rat[tv_rat["model"].str.contains("Sharjah excluded")].iloc[0]
    tv_low = tv_rat[tv_rat["model"].str.startswith("Lowest")].iloc[0]
    tv_ig = tv[tv["model"].str.startswith("Ratings, 2 of 3") & (tv["term"] == "cds100")].iloc[0]
    tv_extra = tv[tv["model"].str.startswith("Ratings, 2 of 3") & (tv["term"] == "cds100:sub_t")].iloc[0]
    sharjah = rd("credit/credit_issuer_means.csv")
    sharjah = sharjah[sharjah["parent_key"] == "emirate sharjah"].iloc[0]
    moodys = oba[oba["event"].str.startswith("Moody's")].iloc[0]
    # primary market: MAIN rule; robustness range over A, B and Bahrain-excluded MAIN
    pm = row(pr, rule="MAIN", sample="All issuers")
    pm_rob = pr[(pr["rule"].isin(["Robustness A", "Robustness B"]) & (pr["sample"] == "All issuers"))
                | ((pr["rule"] == "MAIN") & (pr["sample"] != "All issuers"))]["weak_sukuk_minus_conv_bp"]
    pm_exb = pr[(pr["rule"] == "MAIN") & (pr["sample"] != "All issuers")].iloc[0]
    mr = rd("data_quality/dq_match_rates.csv")
    mr_all = mr[mr["dimension"] == "All market deals"].iloc[0]
    mr_sub = mr[(mr["dimension"] == "Credit (MAIN)") & (mr["group"] == "Sub-IG")].iloc[0]
    mr_ig = mr[(mr["dimension"] == "Credit (MAIN)") & (mr["group"] == "IG")].iloc[0]
    cfr = rd("data_quality/dq_curve_free_regressions.csv").set_index("sample")
    cf_m, cf_u = cfr.loc["Matched deals"], cfr.loc["Unmatched deals"]
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
         f"{int(level.governments)} obligor groups negative on average (issuers grouped by the government backing "
         "them; Sharjah and the multilateral Arab Energy Fund stand alone).",
         "Holding the issuer fixed, investors accept a lower yield on sukuk."),
        ("The sukuk premium is concentrated in the two governments rated sub-investment grade, Bahrain and Oman",
         f"By rating at the time (2 of 3 agencies below BBB-/Baa3; Dubai via its DEWA proxy), sub-IG obligor-months "
         f"average {tv_main.sub_ig_mean_bp:.0f}bp vs {tv_main.ig_mean_bp:.0f}bp for investment grade: gap "
         f"{tv_main.coef_bp:.0f}bp, wild bootstrap p = {fmt_p(tv_main.p_wild_government)} by obligor group. Robustness: "
         f"without Dubai {tv_exd.coef_bp:.0f}bp (p = {fmt_p(tv_exd.p_wild_government)}); without Sharjah "
         f"{tv_exs.coef_bp:.0f}bp (p = {fmt_p(tv_exs.p_wild_government)}); lowest rating {tv_low.coef_bp:.0f}bp "
         f"(p = {fmt_p(tv_low.p_wild_government)}); government CDS above 150bp {tv_cds.coef_bp:.0f}bp "
         f"(p = {fmt_p(tv_cds.p_wild_government)}); export-date snapshot ratings {level.snapshot_gap_bp:.0f}bp "
         f"(p = {fmt_p(level.snapshot_p_wild_government)}). Oman's sukuk premium narrowed by {moodys.change_bp:.0f}bp "
         f"(90% CI {moodys.ci90}) in the year after Moody's upgrade made it investment grade at two of three agencies. "
         f"Only two governments are ever sub-IG: the gap is {no_bah.gap_bp:.0f}bp without Bahrain (p = "
         f"{fmt_p(no_bah.p_wild_government)}) and {no_oman.gap_bp:.0f}bp without Oman (p = "
         f"{fmt_p(no_oman.p_wild_government)}), and against all {int(perm.assignments)} pairs of governments the "
         f"permutation p is {perm.p_two_sided:.3f}, the lowest that test can give. The gap falls from "
         f"{p_early.gap_bp:.0f}bp before 2021 to {p_late.gap_bp:.0f}bp from 2023 (p = {fmt_p(p_late.p_wild_government)}).",
         f"Concentrated, not exclusive: Sharjah ({sharjah.basis:.0f}bp) counts as investment grade under the rule "
         "because it is split rated and Fitch does not rate it, yet its premium looks like the sub-IG group's and "
         "predates Moody's 2022 cut. The rating line approximates what investors price; it is not a sharp threshold. "
         "Two sub-IG governments cannot separate sub-IG status from other features of Bahrain and Oman."),
        ("Within the weakest sovereigns, the sukuk premium moves with credit risk",
         f"Oman {oman.slope_levels_per_100bp:+.1f}bp and Bahrain {bah.slope_levels_per_100bp:+.1f}bp per 100bp of CDS "
         f"(Newey-West t {oman.t_nw_levels:.1f}, {bah.t_nw_levels:.1f}); also in monthly changes "
         f"({oman.slope_changes_per_100bp:+.1f}, {bah.slope_changes_per_100bp:+.1f}). By rating at the time, the within "
         f"slope is {tv_ig.coef_bp:+.1f}bp in investment-grade months and {tv_extra.coef_bp:+.1f}bp lower in sub-IG months "
         f"(p = {fmt_p(tv_extra.p_wild_government)}).",
         f"The pooled panel slope ({panel.slope_per_100bp:+.1f}bp) is not significant on its own once only six CDS "
         f"series are counted (wild bootstrap p = {fmt_p(panel.p_wild_government)}); the case studies carry the claim."),
        ("The sukuk premium exists at issue, not only in secondary quotes",
         f"Classifying each deal by its government's rating at pricing (MAIN rule: two of three agencies below "
         f"BBB-/Baa3), weak-credit sukuk priced through their issuer's conventional curve: median new-issue premium "
         f"{pm.weak_sukuk_median_bp:+.1f}bp (n = {int(pm.weak_sukuk_n)}), vs {pm.weak_conv_median_bp:+.1f}bp for "
         f"weak-credit conventional deals, which came with the ordinary concession (n = {int(pm.weak_conv_n)}), and "
         f"{pm.other_sukuk_median_bp:+.1f}bp for other issuers' sukuk: a sukuk-minus-conventional gap of "
         f"{pm.weak_sukuk_minus_conv_bp:+.1f}bp (robustness range "
         f"{pm_rob.min():+.1f} to {pm_rob.max():+.1f}bp). Issuer-level correlation with the secondary basis "
         f"{corr_ps:.2f}.",
         "Stale secondary quotes cannot explain a premium that is already there on the pricing date. Under MAIN "
         f"almost all weak-credit sukuk are Bahraini ({int(pm.weak_sukuk_n - pm_exb.weak_sukuk_n)} of "
         f"{int(pm.weak_sukuk_n)}); the lowest-rating and spread rules, which keep more non-Bahraini deals, give the "
         "same sign without Bahrain."),
        ("Sukuk quotes are somewhat stale, but that is not the story",
         f"Unchanged mid price on {st_s.unchanged_mid_share:.1%} of days for sukuk vs {st_c.unchanged_mid_share:.1%} "
         f"for conventionals; sukuk absorb {ll_all.same_day:.2f} of a conventional move on the day and "
         f"{ll_all.total:.2f} within a week (weak credits {ll_weak.total:.2f}, KSA {ll_ksa.total:.2f}); "
         f"{rv_pool.share_reversed:.0%} of the pooled same-month CDS effect reverses within six months (Bahrain: "
         + (f"{rv_bah.share_reversed:.0%})." if rv_bah.share_reversed > 0 else "no reversal)."),
         f"Even after 120 business days sukuk move {pt120.beta_shock:.2f}bp per conventional bp: damping is real, "
         "and stale quotes explain only part of the monthly CDS response."),
        ("Mechanism: tenor and buy-and-hold demand, with modest evidence",
         "Holm-adjusted p-values across the four mechanism tests (government-clustered wild bootstrap): "
         f"CDS slope steepens by {tenor.coef_bp:+.1f}bp per 100bp per year of maturity (p {fmt_p(hp['tenor'])}); "
         f"less liquid sukuk price richer, {liq.coef_bp:+.2f}bp per bp of bid-ask gap (p {fmt_p(hp['liq'])}); "
         f"CDS x interbank spread {ib.coef_bp:+.2f} per bp (p {fmt_p(hp['ib'])}); CDS x Ijara {ijara.coef_bp:+.1f} "
         f"(p {fmt_p(hp['ijara'])}), a low-power test because only {n_ijara} of the {n_struct} twin sukuk are Ijara "
         f"({n_hybrid} are Hybrid).",
         "After the multiple-testing correction none clears 5%; the tenor and liquidity signs fit default/recovery "
         "pricing plus buy-and-hold demand. The Ijara test cannot rule asset backing in or out."),
        ("Oil shocks do not move the basis directly",
         f"Median basis response to an oil-price rise {med5:+.1f}bp at +5 days; the test could detect {mde5:.1f}bp (+5) "
         f"or {mde20:.1f}bp (+20) with 80% power. Implied via credit: {imp5.implied_basis_bp:+.2f}bp "
         f"(90% CI {imp5.implied_ci90}).",
         f"Oil reaches the basis only through credit risk, and oil up-shocks in this sample raise GCC CDS "
         f"(median {up5.median_bp:+.1f}bp at +5 days, placebo p {fmt_p(up5.placebo_p_median)}); several of them are "
         "regional conflicts."),
        ("What it is worth",
         "; ".join(f"{r.issuer.split(',')[0]} about USD {r.saving_12m_usd_m:,.0f}m a year" for r in top.itertuples())
         + f" (trailing-12-month basis x outstanding USD sukuk). Investment-grade sovereigns without USD sukuk "
         f"(Kuwait, Abu Dhabi, UAE federal): predicted USD {cf_rng[0]:.1f}-{cf_rng[1]:.1f}m per USD 1bn issued, intervals "
         "including zero.",
         "Sukuk issuance pays most for the weakest credits, which is where the premium sits."),
    ]

    spec = pd.DataFrame([
        {"specification": "Twin-curve basis, cross-issuer mean", "estimate": f"{tw.mean_of_issuer_means_bp:.1f}bp",
         "inference": f"t = {tw.t:.2f} across {tw.issuers} issuers", "source": "twin_results.md"},
        *([{"specification": f"Sub-IG minus IG basis ({r.model.split(':')[0].replace('Ratings', 'time-varying ratings')}"
                             + (", Dubai via DEWA proxy)" if "excluded" not in r.model else ")"),
            "estimate": f"{r.coef_bp:.1f}bp",
            "inference": f"wild p = {fmt_p(r.p_wild_government)} (obligor groups), {fmt_p(r.p_wild_issuer)} (issuer)",
            "source": "mechanism_results.md"} for r in tv_rat.itertuples()]),
        {"specification": "Sub-IG minus IG basis, without Bahrain / without Oman (one sub-IG government left)",
         "estimate": f"{no_bah.gap_bp:.1f} / {no_oman.gap_bp:.1f}bp",
         "inference": f"wild p = {fmt_p(no_bah.p_wild_government)} / {fmt_p(no_oman.p_wild_government)}; unreliable with one "
                      "treated government", "source": "robustness_results.md"},
        {"specification": f"Permutation test: {perm.sub_ig_governments} vs all pairs of governments",
         "estimate": f"{perm.difference_bp:.1f}bp (government means)",
         "inference": f"p = {perm.p_two_sided:.3f}; lowest attainable {perm.smallest_possible_p:.3f}",
         "source": "robustness_results.md"},
        {"specification": "Sub-IG minus IG basis (time-varying: CDS > 150bp)", "estimate": f"{tv_cds.coef_bp:.1f}bp",
         "inference": f"wild p = {fmt_p(tv_cds.p_wild_government)} (obligor groups), {fmt_p(tv_cds.p_wild_issuer)} (issuer)",
         "source": "mechanism_results.md"},
        {"specification": "Sub-IG minus IG basis (comparison: export-date snapshot ratings, Oman counted sub-IG)",
         "estimate": f"{level.snapshot_gap_bp:.1f}bp",
         "inference": f"wild p = {fmt_p(level.snapshot_p_wild_government)} (obligor groups, {int(level.snapshot_clusters)} clusters)",
         "source": "credit_results.md"},
        *([{"specification": f"Extra CDS slope when sub-IG ({r.model.split(':')[0].replace('Ratings', 'time-varying ratings')})",
            "estimate": f"{r.coef_bp:+.1f} per 100bp",
            "inference": f"wild p = {fmt_p(r.p_wild_government)} (obligor groups), {fmt_p(r.p_wild_issuer)} (issuer)",
            "source": "mechanism_results.md"}
           for r in tv[tv["model"].str.startswith("Ratings") & (tv["term"] == "cds100:sub_t")].itertuples()]),
        {"specification": "Oman: basis change after Moody's upgrade (12m vs 12m)", "estimate": f"{moodys.change_bp:+.1f}bp",
         "inference": f"Newey-West 90% CI {moodys.ci90}", "source": "mechanism_results.md"},
        {"specification": "Oman: basis on CDS, levels / changes",
         "estimate": f"{oman.slope_levels_per_100bp:+.1f} / {oman.slope_changes_per_100bp:+.1f} per 100bp",
         "inference": f"NW t {oman.t_nw_levels:.1f} / {oman.t_nw_changes:.1f}", "source": "credit_results.md"},
        {"specification": "Bahrain: basis on CDS, levels / changes",
         "estimate": f"{bah.slope_levels_per_100bp:+.1f} / {bah.slope_changes_per_100bp:+.1f} per 100bp",
         "inference": f"NW t {bah.t_nw_levels:.1f} / {bah.t_nw_changes:.1f}", "source": "credit_results.md"},
        {"specification": "Panel within slope (issuer FE + liquidity)", "estimate": f"{panel.slope_per_100bp:+.1f} per 100bp",
         "inference": f"cluster t {panel.t_cluster_issuer:.1f}; wild p = {fmt_p(panel.p_wild_government)} (obligor "
                      f"groups), {fmt_p(panel.p_wild_issuer)} (issuer)", "source": "credit_results.md"},
        {"specification": "Panel, first differences", "estimate": f"{fd.coef_bp:+.1f} per 100bp",
         "inference": f"wild p = {fmt_p(fd.p_wild_government)} (obligor groups)", "source": "mechanism_results.md"},
        {"specification": "Extra within slope for sub-IG issuers (comparison: snapshot ratings)", "estimate": f"{sub_extra.coef_bp:+.1f} per 100bp",
         "inference": f"wild p = {fmt_p(sub_extra.p_wild_government)} (obligor groups), "
                      f"{fmt_p(sub_extra.p_wild_issuer)} (issuer)", "source": "mechanism_results.md"},
        {"specification": "CDS x remaining maturity", "estimate": f"{tenor.coef_bp:+.2f} per 100bp per year",
         "inference": f"wild p = {fmt_p(tenor.p_wild_government)}; Holm-adjusted {fmt_p(hp['tenor'])}",
         "source": "mechanism_results.md"},
        {"specification": "Liquidity gap", "estimate": f"{liq.coef_bp:+.2f}bp per bp",
         "inference": f"wild p = {fmt_p(liq.p_wild_government)}; Holm-adjusted {fmt_p(hp['liq'])}",
         "source": "mechanism_results.md"},
        {"specification": "CDS x Ijara (low power: few Ijara sukuk)", "estimate": f"{ijara.coef_bp:+.1f} per 100bp",
         "inference": f"wild p = {fmt_p(ijara.p_wild_government)}; Holm-adjusted {fmt_p(hp['ijara'])}",
         "source": "mechanism_results.md"},
        {"specification": "CDS x interbank spread", "estimate": f"{ib.coef_bp:+.2f} per 100bp per bp",
         "inference": f"wild p = {fmt_p(ib.p_wild_government)}; Holm-adjusted {fmt_p(hp['ib'])}",
         "source": "mechanism_results.md"},
        {"specification": "New-issue premium, weak-credit sukuk minus conventional (MAIN: 2 of 3 agencies below IG "
                          "at pricing)",
         "estimate": f"{pm.weak_sukuk_minus_conv_bp:+.1f}bp (medians)",
         "inference": f"{int(pm.weak_sukuk_n)} sukuk, {int(pm.weak_conv_n)} conventional; Welch t "
                      f"{pm.welch_t_weak_vs_other_sukuk:.1f} vs other sukuk; robustness range {pm_rob.min():+.1f} to "
                      f"{pm_rob.max():+.1f}bp (lowest rating, spread > 150bp, MAIN without Bahrain with "
                      f"n = {int(pm_exb.weak_sukuk_n)} sukuk)",
         "source": "data_quality_results.md"},
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
          "**1. The sukuk premium is concentrated in sub-investment-grade credits** (each issuer plotted by its rating "
          "status at the time, so Oman appears twice; dashed lines are the group means; the Dubai government's basis "
          "rests on 20-year interpolation brackets and is shown hollow; Sharjah has no CDS and is noted under the chart):\n",
          "![threshold](mechanism/mechanism_threshold_cross.png)\n",
          "**2. Within issuers, the sukuk premium follows the government's CDS where CDS moves** (Bahrain, Oman), "
          "and stays near zero where it does not (KSA):\n",
          "![case studies](credit/credit_case_studies.png)\n",
          "**3. What the sukuk premium is worth by issuer (lower funding cost):**\n",
          "![savings](policy/policy_savings.png)\n",
          "## Where to read more\n",
          "- twin_results.md: the twin-curve method, matching validation and the basis by issuer.",
          "- credit/credit_results.md: CDS evidence, case studies, wild bootstrap.",
          "- mechanism/mechanism_results.md: structure, tenor, captive demand, threshold, inference.",
          "- data_quality/data_quality_results.md: staleness, lead-lag, reversal, primary market.",
          "- event_study/event_study.md and oil_credit/oil_credit_results.md: oil shocks and the credit channel.",
          "- policy/policy_results.md: savings and the counterfactual.",
          "- drivers/drivers_results.md: interbank, issuance and the common factor.",
          "- robustness/robustness_results.md: amortisation, dependence on governments, periods, bond samples, new-issue lead.\n",
          "## Main caveats\n",
          "- Six independent sovereign CDS series and 18 issuers: small-sample inference throughout. The sub-IG contrast "
          f"rests on {perm.sub_ig_governments}, so its evidence is at most about 1 in {int(perm.assignments)}.",
          f"- Amortisation is ruled out from LSEG data, not prospectuses: {int(twin_struct.sinkable)} of "
          f"{int(twin_struct.bonds)} twin sukuk flagged sinkable; {int(twin_struct.duration_tested)} live ones have "
          f"durations {twin_struct.ratio_min:.3f}-{twin_struct.ratio_max:.3f} of a bullet (the Emirates control: "
          f"{int(ctl_struct.sinkable)} of {int(ctl_struct.bonds)} flagged, ratio {ctl_struct.ratio_min:.2f}).",
          "- Sub-IG status uses each government's rating at the time (hand-compiled histories; Dubai proxied by DEWA, "
          "rationale in README.md). Under the 2-of-3 rule Sharjah counts as investment grade despite a premium like the "
          "sub-IG group's. Export-date snapshot ratings are kept only as a comparison.",
          "- Secondary sukuk quotes are staler than conventional ones; the primary-market check is the defence.",
          f"- {int(mr_all.deals - mr_all.matched)} of {int(mr_all.deals)} market new deals have no usable curve and no "
          f"new-issue premium ({mr_sub.match_rate:.0%} of sub-IG and {mr_ig.match_rate:.0%} of investment-grade deals "
          f"match). A cruder curve-free check gives sub-IG sukuk minus conventional of "
          f"{cf_m.sub_ig_sukuk_minus_conv_bp:+.0f}bp on matched deals and {cf_u.sub_ig_sukuk_minus_conv_bp:+.0f}bp on "
          f"unmatched deals, the latter on only {int(cf_u.sub_ig_deals)} sub-IG deals (data_quality_results.md, section e).",
          "- Raw LSEG data is not distributed with this repository.\n"]
    (A / "synthesis.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote %s", A / "synthesis.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
