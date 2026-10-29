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
from src.inference import fmt_p, issuer_slopes, wild_cluster_bootstrap
from src.mechanism import issuer_ratings
from src.summary import _md
from src.twin import load_panel
from src.twin_report import CONV_C, INK, INK2, SUKUK_C, SURFACE, _style

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


CASE_ISSUERS = ["Bahrain, Kingdom of (Government)", "Oman, Sultanate of (Government)",
                "Saudi Arabia, Kingdom of (Government)"]


def chart_case_studies(panel: pd.DataFrame, out: Path) -> None:
    """Monthly basis (top row) and the government's CDS (bottom row) for Bahrain, Oman and KSA.
    Two rows instead of a dual axis: the measures have different scales."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(12, 5.4), sharex=True, facecolor=SURFACE,
                             gridspec_kw={"height_ratios": [3, 2]})
    for j, name in enumerate(CASE_ISSUERS):
        d = panel[panel["parent_name"] == name].sort_values("month")
        t = d["month"].dt.to_timestamp()
        top, bot = axes[0, j], axes[1, j]
        for ax in (top, bot):
            _style(ax)
        top.axhline(0, color=INK2, linewidth=0.8)
        top.plot(t, d["basis"], color=SUKUK_C, linewidth=2)
        bot.plot(t, d["cds"], color=CONV_C, linewidth=2)
        top.set_title(f"{name.split(',')[0]}: basis (bp)", fontsize=10, color=INK, loc="left")
        bot.set_title("Government 5y CDS (bp)", fontsize=9, color=INK2, loc="left")
    fig.suptitle("Within issuers: the sukuk discount widens when the government's CDS rises (Bahrain, Oman); "
                 "KSA's CDS barely moves", fontsize=10.5, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", choices=["desktop", "platform"], help="pull/refresh sovereign CDS first")
    p.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    p.add_argument("--draws", type=int, default=9999, help="wild cluster bootstrap draws")
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
    within = within_issuer(panel, B=a.draws)
    iss, xs = cross_issuer(panel)
    loo = leave_one_sovereign_out(panel, iss)
    slopes = issuer_slopes(panel)
    slopes.to_csv(out / "credit_issuer_slopes.csv", index=False)
    chart_case_studies(panel, out / "credit_case_studies.png")

    # Level result across issuers: every issuer's mean basis, and the sub-IG gap with a wild bootstrap
    ratings = issuer_ratings(uni, panel["parent_key"].unique())
    ratings["sub_ig_oman"] = ratings["sub_ig"].where(ratings["parent_key"] != "oman sultanate", True)
    lv = iss.merge(ratings[["parent_key", "rating_snapshot", "sub_ig_oman"]], on="parent_key", how="left")
    lv["government"] = lv["cds_sovereign"].fillna(lv["parent_name"])
    n_neg, n_all = int((lv["basis"] < 0).sum()), int(lv["basis"].notna().sum())
    gov_means = lv.groupby("government")["basis"].mean()
    lvd = lv.dropna(subset=["sub_ig_oman"]).assign(sub=lambda x: x["sub_ig_oman"].astype(float))
    gap = wild_cluster_bootstrap("basis ~ sub", lvd, "sub", "government", B=a.draws)
    sub_mean = lvd.loc[lvd["sub"] == 1, "basis"].mean()
    ig_mean = lvd.loc[lvd["sub"] == 0, "basis"].mean()
    case = slopes.set_index("issuer")
    pd.DataFrame([{"issuers": n_all, "issuers_negative": n_neg, "governments": len(gov_means),
                   "governments_negative": int((gov_means < 0).sum()), "sub_ig_mean_bp": round(sub_mean, 1),
                   "ig_mean_bp": round(ig_mean, 1), "gap_bp": round(gap["coef"], 1),
                   "p_wild_government": round(gap["p_wild"], 3), "clusters": gap["clusters"]}]).to_csv(
        out / "credit_level_gap.csv", index=False)
    loo.to_csv(out / "credit_leave_one_out.csv", index=False)
    panel.assign(month=panel["month"].astype(str)).to_csv(out / "credit_panel_issuer_month.csv", index=False)
    within.to_csv(out / "credit_within_issuer.csv", index=False)
    xs.to_csv(out / "credit_cross_issuer.csv", index=False)
    iss.to_csv(out / "credit_issuer_means.csv", index=False)
    chart_cross_issuer(iss, out / "credit_cross_issuer.png")

    cov = (cds.astype(float).apply(lambda s: f"{s.first_valid_index():%Y-%m}" if s.notna().any() else "none"))
    main_row = within[within["model"] == "Sovereign CDS + liquidity gap"].iloc[0]

    def case_line(name: str) -> str:
        if name not in case.index:
            return f"- {name}: not enough months."
        r = case.loc[name]
        return (f"- **{name.split(',')[0]}** (CDS range {r.cds_range_bp:.0f}bp over {r.months} months): "
                f"{r.slope_levels_per_100bp:+.1f}bp per 100bp in levels (Newey-West t {r.t_nw_levels:.1f}), "
                f"{r.slope_changes_per_100bp:+.1f}bp in monthly changes (t {r.t_nw_changes:.1f}).")

    L = ["# Credit stress and the sukuk discount\n",
         f"Generated {date.today():%Y-%m-%d}. Issuer-month panel from the twin-curve basis.\n",
         "## What the evidence supports\n",
         "The claim rests on three pieces, in this order of strength:\n",
         f"1. **Level, across issuers.** {n_neg} of {n_all} issuers have a negative mean basis, and the "
         f"average is negative in {int((gov_means < 0).sum())} of {len(gov_means)} obligor groups (issuers grouped "
         "by the government whose credit backs them; Sharjah and the multilateral Arab Energy Fund form their own "
         "groups). "
         f"Sub-investment-grade issuers (Bahrain, BAPCO, Sharjah, Oman Electricity Transmission, and the Oman "
         f"sovereign, which was sub-IG for most of the sample) average {sub_mean:.0f}bp against {ig_mean:.0f}bp for "
         f"investment-grade issuers: a gap of {gap['coef']:.0f}bp, wild cluster bootstrap p = {fmt_p(gap['p_wild'])} "
         f"clustering by obligor group ({gap['clusters']} clusters).",
         "2. **Case studies within issuers.** The two governments whose CDS moved most show the discount "
         "widening as credit risk rises, in levels and in monthly changes:",
         case_line("Oman, Sultanate of (Government)"), case_line("Bahrain, Kingdom of (Government)"),
         case_line("BAPCO Energies BSCC Closed"),
         "   Issuers whose CDS moved less than about 100bp give noisy slopes of both signs (issuer table below).",
         f"3. **Panel slope (supporting only).** Pooling all issuers gives {main_row.slope_per_100bp:+.1f}bp per "
         f"100bp (issuer-clustered t {main_row.t_cluster_issuer:.1f}), but the restricted wild cluster bootstrap "
         f"gives p = {main_row.p_wild_government:.2f} clustering by government and p = {main_row.p_wild_issuer:.2f} "
         "by issuer. With only six independent CDS series, the pooled panel is not significant on its own and "
         "should not be cited as the main evidence.\n",
         "![case studies](credit_case_studies.png)\n",
         "## Issuer-by-issuer slopes\n",
         "Time-series regression of the issuer's monthly basis on its government's CDS (per 100bp), Newey-West "
         "t-stats (6 lags in levels, 3 in monthly changes). Sorted by how far CDS moved.\n\n", _md(slopes),
         "\n## Data\n",
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
         f"common monthly shocks), plus restricted wild cluster bootstrap p-values (Webb weights, {a.draws:,} "
         "draws) by government and by issuer. Issuers without a sovereign CDS form their own government "
         "cluster.\n",
         "## Across issuers: is the discount bigger for weaker credits?\n",
         "![cross issuer](credit_cross_issuer.png)\n",
         _md(xs),
         "\n## Panel regressions within issuers\n",
         "Slope = change in basis (bp) per 100bp rise in the credit measure. Compare the clustered t-stats with "
         "the wild bootstrap p-values: the gap shows how much the conventional t-stats overstate precision.\n\n",
         _md(within),
         "\n## Robustness: leave one government out\n",
         "Issuers that share a government share its CDS series, so there are only six independent credit "
         "series. Each row drops one government's issuers. *t (cluster government)* clusters standard "
         "errors by government (very few clusters, so conservative and approximate).\n\n",
         _md(loo),
         "\n## Reading the results\n",
         "- **Within issuers:** the pooled slope is stable whichever government is dropped, but its precision "
         "leans on Oman, whose CDS ranged most widely, and the government-level bootstrap does not reject zero. "
         "That is why the case studies, not the panel t-stat, carry the within-issuer claim.",
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
