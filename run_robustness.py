"""How far the sub-IG result reaches: bond structure, dependence on governments, periods and samples. No LSEG calls.

Needs: run_twin.py, run_drivers.py and run_structure_check.py outputs.

Usage:
    .venv\\Scripts\\python run_robustness.py            # 9,999 bootstrap draws
    .venv\\Scripts\\python run_robustness.py --draws 999
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.data_quality import classify_deals, flag_off_market, new_issue_premia, rule_summary
from src.inference import fmt_p
from src.ratings import ISSUER_GOVERNMENT, load_ratings
from src.robustness import gap_row, leave_one_government_out, level_panel, period_splits, permutation_test, structure_table
from src.summary import _md
from src.twin import UstCurve, load_panel, sukuk_basis

log = logging.getLogger("run_robustness")
LEADS = (2, 5, 10, 20)
NEAR_PAR_SUKUK, NEAR_PAR_BOTH = (97, 103), (95, 105)


def sample_variants(obs, panel, uni, flags, ratings, B) -> pd.DataFrame:
    """The level gap after removing bonds that could make the two curves incomparable."""
    methods = C.TWIN["main_methods"]
    rows = [gap_row(level_panel(obs, ratings), "Baseline", B)]
    senior = uni.loc[uni["is_sukuk"] | (uni["seniority"] == "Senior Unsecured"), "instrument_id"]
    rows.append(gap_row(level_panel(sukuk_basis(panel[panel["instrument_id"].isin(senior)]), ratings),
                        "Conventional curves from senior unsecured bonds only", B))
    dewa = uni.loc[uni["issuer_name"].str.contains("Dubai Electricity", na=False) & ~uni["is_sukuk"], "instrument_id"]
    rows.append(gap_row(level_panel(sukuk_basis(panel[~panel["instrument_id"].isin(dewa)]), ratings),
                        "DEWA bond removed from Dubai's conventional curve", B))
    called = uni.loc[uni["isin"].isin(flags.loc[flags["is_callable"] == True, "isin"]), "instrument_id"]  # noqa: E712
    rows.append(gap_row(level_panel(sukuk_basis(panel[~panel["instrument_id"].isin(called)]), ratings),
                        "Bonds LSEG flags as callable removed, both sides", B))
    px = panel[["instrument_id", "date", "mid_price"]]
    near = obs[obs["match_method"].isin(methods)].merge(px, on=["instrument_id", "date"], how="left")
    near = near[near["mid_price"].between(*NEAR_PAR_SUKUK)]
    rows.append(gap_row(level_panel(near, ratings), f"Sukuk-days priced {NEAR_PAR_SUKUK[0]}-{NEAR_PAR_SUKUK[1]}", B))
    rows.append(gap_row(level_panel(sukuk_basis(panel[panel["mid_price"].between(*NEAR_PAR_BOTH)]), ratings),
                        f"All bond-days priced {NEAR_PAR_BOTH[0]}-{NEAR_PAR_BOTH[1]}, both sides", B))
    return pd.DataFrame(rows)


def lead_sensitivity(uni, panel, keys, ust, ratings, cds) -> pd.DataFrame:
    """Primary-market MAIN result when the curve is read 2, 5, 10 or 20 business days before issue."""
    rows = []
    for lead in LEADS:
        cfg = {**C.PRIMARY_MARKET, "lead_bdays": lead}
        nip = flag_off_market(new_issue_premia(uni, panel, keys, ust, lead_bdays=lead))
        _, s = rule_summary(classify_deals(nip, ratings, ISSUER_GOVERNMENT, cds, ust, cfg), ("MAIN",))
        r = s[s["sample"] == "All issuers"].iloc[0]
        ex_bahrain = s[s["sample"] != "All issuers"].iloc[0]
        rows.append({"lead_bdays": lead, "weak_sukuk_median_bp": r.weak_sukuk_median_bp, "weak_sukuk_n": r.weak_sukuk_n,
                     "weak_sukuk_n_ex_bahrain": ex_bahrain.weak_sukuk_n,
                     "weak_conv_median_bp": r.weak_conv_median_bp, "weak_conv_n": r.weak_conv_n,
                     "weak_sukuk_minus_conv_bp": r.weak_sukuk_minus_conv_bp,
                     "other_sukuk_median_bp": r.other_sukuk_median_bp})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    ap.add_argument("--draws", type=int, default=9999)
    a = ap.parse_args(argv)
    C.setup_logging("run_robustness")
    out = a.data / "analysis" / "robustness"
    out.mkdir(parents=True, exist_ok=True)
    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    obs = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")
    flags = pd.read_parquet(a.data / "interim" / "structure_flags.parquet")
    ratings = load_ratings(C.SOVEREIGN_RATINGS_PATH)
    ust = UstCurve(C.TWIN["ust_curve_path"])
    cds = pd.read_parquet(C.DATA_DIR / "market" / "sovereign_cds.parquet").astype(float)
    cds.index = pd.to_datetime(cds.index)
    panel = load_panel(uni, a.data / "timeseries")
    keys = obs["parent_key"].unique()

    # a. structure
    last = panel.dropna(subset=["mid_yield"]).sort_values("date").groupby("instrument_id").tail(1)[["instrument_id", "mid_yield"]]
    cols = ["isin", "instrument_id", "parent_key", "coupon_rate", "maturity_date"]
    in_panel = uni[uni["instrument_id"].isin(panel["instrument_id"].unique())].merge(last, on="instrument_id", how="left")
    sukuk_ids = obs["instrument_id"].unique()
    twin = in_panel[in_panel["instrument_id"].isin(sukuk_ids)]
    conv = in_panel[~in_panel["is_sukuk"] & in_panel["parent_key"].isin(keys)]
    weak = ("Bahrain", "Oman")
    is_weak = lambda d: d["parent_key"].map(ISSUER_GOVERNMENT).isin(weak)  # noqa: E731
    control = uni[uni["parent_key"].isin(C.TWIN["exclude_parents"]) & uni["is_sukuk"]].assign(mid_yield=float("nan"))
    keep = cols + ["mid_yield"]
    struct = structure_table(flags, {
        "Twin sukuk": twin[keep], "Twin sukuk, Bahrain and Oman": twin.loc[is_weak(twin), keep],
        "Conventional bonds of twin issuers": conv[keep], "Conventional, Bahrain and Oman": conv.loc[is_weak(conv), keep],
        "Control: Emirates airline sukuk (known amortising)": control[keep]})
    struct.to_csv(out / "robustness_structure.csv", index=False)

    # b-d. governments, periods, samples
    m = level_panel(obs, ratings)
    logo = leave_one_government_out(m, a.draws)
    logo.to_csv(out / "robustness_leave_one_government.csv", index=False)
    perm, perm_all = permutation_test(m)
    pd.DataFrame([perm]).to_csv(out / "robustness_permutation.csv", index=False)
    perm_all.to_csv(out / "robustness_permutation_assignments.csv", index=False)
    periods = period_splits(m, a.draws)
    periods.to_csv(out / "robustness_periods.csv", index=False)
    samples = sample_variants(obs, panel, uni, flags, ratings, a.draws)
    samples.to_csv(out / "robustness_samples.csv", index=False)
    leads = lead_sensitivity(uni, panel, keys, ust, ratings, cds)
    leads.to_csv(out / "robustness_primary_leads.csv", index=False)

    tw, ctl = struct.iloc[0], struct.iloc[-1]
    wk, wkc = struct.iloc[1], struct.iloc[3]
    no_b = logo[logo["sample"] == "Without Bahrain"].iloc[0]
    no_o = logo[logo["sample"] == "Without Oman"].iloc[0]
    second = perm_all.iloc[1]
    gov_means = m.groupby("government")["basis"].mean().round(1).sort_values().rename("mean_basis_bp").reset_index()
    amortising_clear = tw.sinkable == 0 and tw.ratio_min > 0.95
    L = ["# How far the sub-IG result reaches\n",
         f"Generated {date.today():%Y-%m-%d}. Level gap: issuer-month basis on the MAIN sub-IG flag, clustered by "
         f"obligor group, {a.draws:,} wild bootstrap draws.\n",
         "## a. Are any sukuk amortising?\n",
         "An amortising sukuk has a shorter average life than its final maturity. Matched to a bullet conventional bond "
         "of the same final maturity on an upward-sloping curve, it would look rich, and the bias would be largest for "
         "weak credits with steep curves. LSEG's sinkable flag comes from the Search API (the TR.Fi structure fields are "
         "denied on this login). As a second test, the ratio compares LSEG's modified duration with a bullet bond of the "
         "same coupon and maturity (bonds with over a year left, as of the pull date): near 1 means bullet.\n",
         _md(struct), "",
         (f"**Reading.** No twin sukuk is flagged sinkable ({int(tw.flag_found)} of {int(tw.bonds)} checked), and the "
          f"{int(tw.duration_tested)} with a duration test sit at {tw.ratio_min:.3f} to {tw.ratio_max:.3f} of a bullet. "
          if amortising_clear else
          f"**Reading.** Some twin sukuk may amortise: {int(tw.sinkable)} flagged sinkable, lowest duration ratio "
          f"{tw.ratio_min:.3f}. These need rematching on average life. "),
         f"The control shows both tests can detect amortisation: {int(ctl.sinkable)} of {int(ctl.bonds)} Emirates airline "
         f"sukuk lines are flagged sinkable, and the duration ratio is {ctl.ratio_min:.2f} for the "
         f"{int(ctl.duration_tested)} control bond still long enough to test. Duration only covers live bonds, so matured "
         "sukuk rest on the flag alone. No prospectus has been read for this check.",
         f"Calls cannot explain the sub-IG gap: Bahrain and Oman have {int(wk.callable)} callable sukuk and "
         f"{int(wkc.callable)} callable conventional bonds flagged, and removing all callable bonds leaves the gap in "
         "section d.\n",
         "## b. Dependence on individual governments\n", _md(logo), "",
         f"The size of the gap survives dropping either sub-IG government ({no_b.gap_bp:.0f}bp without Bahrain, "
         f"{no_o.gap_bp:.0f}bp without Oman), but significance does not (p = {fmt_p(no_b.p_wild_government)} and "
         f"{fmt_p(no_o.p_wild_government)}). Those two rows have one sub-IG government each, a case where the wild cluster "
         "bootstrap is unreliable, so read them as showing that one government cannot establish the result.\n",
         "**Permutation test.** With only two sub-IG governments, a test that does not rely on cluster asymptotics is "
         "useful: compare them with every other pair of governments.\n",
         _md(pd.DataFrame([perm])), "", _md(perm_all.head(5)), "", _md(gov_means), "",
         f"{perm['sub_ig_governments']} is the most extreme of {perm['assignments']} pairs, so p = {perm['p_two_sided']:.3f}, "
         f"which is also the lowest value this test can give with {perm['governments']} governments. The evidence is "
         f"therefore at most about 1 in {perm['assignments']}, whatever a bootstrap p-value says. The next pair is "
         f"{second.governments} ({second.difference_bp:.1f}bp): Sharjah, investment grade under the rule, is close to "
         "Oman. Oman's mean mixes its sub-IG and investment-grade months.\n",
         "## c. Over time\n", _md(periods), "",
         "The gap is persistent but not stable: it is smaller in recent years, and its significance is sensitive to the "
         "period. Report it as a range, not as a fixed number of basis points.\n",
         "## d. Which bonds are compared\n", _md(samples), "",
         f"The near-par rows limit coupon and price effects. The sukuk-only row filters the sukuk side alone; the "
         f"both-sides row rebuilds the curves from bonds priced {NEAR_PAR_BOTH[0]}-{NEAR_PAR_BOTH[1]}.\n",
         "## e. Primary market: length of the lead\n", _md(leads), "",
         f"The sign and rough size of the new-issue premium do not depend on the 5-day lead (weak-credit sukuk median "
         f"{leads['weak_sukuk_median_bp'].max():.1f}bp to {leads['weak_sukuk_median_bp'].min():.1f}bp, smallest at 20 days). "
         f"Non-Bahraini weak-credit sukuk at any lead: at most {int(leads['weak_sukuk_n_ex_bahrain'].max())}.\n",
         "## What this supports\n",
         "- Supported: sukuk trade richer in Bahrain and Oman than in investment-grade issuers in secondary quotes, and "
         "in Bahrain at issue. The checks here find no sign that amortisation, calls, seniority or the lead cause it; "
         "limiting to near-par bonds trims the gap slightly but does not remove it.",
         "- Not established: that sub-IG status itself, rather than something else specific to these two governments, "
         "drives it. Two treated governments cannot separate the two, and Sharjah shows a premium without the rating.\n"]
    (out / "robustness_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote %s\n%s\n%s\n%s", out / "robustness_results.md", logo.to_string(index=False),
             periods.to_string(index=False), samples.to_string(index=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
