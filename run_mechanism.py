"""Mechanism, threshold shape and small-cluster inference (NEXT_PROMPT tasks 1-3). No LSEG calls.

Needs: run_twin.py, run_credit.py and run_drivers.py outputs.

Usage:
    .venv\\Scripts\\python run_mechanism.py            # 9,999 bootstrap draws
    .venv\\Scripts\\python run_mechanism.py --draws 999
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as C
from src.mechanism import (before_after, bond_month_panel, hinge, inference_table, issuer_ratings,
                           mechanism_regressions, prep_issuer_month, structure_tables, threshold_models,
                           time_varying_threshold)
from src.ratings import ISSUER_GOVERNMENT, load_ratings, monthly_status, template
from src.summary import _md
from src.twin_report import CONV_C, GRID, INK, INK2, SUKUK_C, SURFACE, _style

log = logging.getLogger("run_mechanism")


def short(n: str) -> str:
    return n.split(",")[0].replace(" PJSC", "").replace(" SJSC", "").replace(" BSCC Closed", "")[:24]


def chart_threshold(xs: pd.DataFrame, prof: pd.DataFrame, out: Path) -> None:
    """Basis vs CDS across issuers with the linear fit, the best spline and sub-IG/IG means."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import statsmodels.formula.api as smf

    allp = xs.dropna(subset=["cds", "basis"]).copy()
    dub = allp[allp["parent_key"] == "dubai emirate"]
    d = allp[allp["parent_key"] != "dubai emirate"].copy()   # fits exclude Dubai govt (20y brackets)
    d["cds100"] = d["cds"] / 100
    fig, ax = plt.subplots(figsize=(8.5, 5.2), facecolor=SURFACE)
    _style(ax)
    ax.axhline(0, color=INK2, linewidth=0.8)
    grid = np.linspace(d["cds"].min(), d["cds"].max(), 200)
    if len(dub):
        ax.scatter(dub["cds"], dub["basis"], s=42, facecolor="none", edgecolor=SUKUK_C, linewidth=1.5, zorder=3,
                   label="Dubai govt (excluded: 20y brackets)")
    lin = smf.ols("basis ~ cds100", d).fit()
    ax.plot(grid, lin.params["Intercept"] + lin.params["cds100"] * grid / 100, color=GRID, linewidth=2,
            linestyle="--", label="Linear fit")
    if len(prof):
        k = float(prof.loc[prof["best"], "kink_bp"].iloc[0])
        sp = smf.ols("basis ~ cds100 + h", d.assign(h=hinge(d["cds"], k) / 100)).fit()
        ax.plot(grid, sp.params["Intercept"] + sp.params["cds100"] * grid / 100 + sp.params["h"] * hinge(grid, k) / 100,
                color=CONV_C, linewidth=2, label=f"Spline, kink at {k:.0f}bp")
    sub = d["sub_ig_oman"].astype(bool)
    ax.scatter(d.loc[~sub, "cds"], d.loc[~sub, "basis"], s=42, color=SUKUK_C, edgecolor=SURFACE, linewidth=1.5,
               zorder=3, label="Investment grade")
    ax.scatter(d.loc[sub, "cds"], d.loc[sub, "basis"], s=42, marker="s", color=SUKUK_C, edgecolor=SURFACE,
               linewidth=1.5, zorder=3, label="Sub-investment grade")
    for r in allp[(allp["cds"] > 100) | (allp["basis"].abs() > 15)].itertuples():
        ax.annotate(short(r.parent_name), (r.cds, r.basis), xytext=(5, 3), textcoords="offset points",
                    fontsize=8, color=INK2)
    ax.set_xlabel("Mean sovereign 5y CDS of the issuer's government (bp)", color=INK2, fontsize=9)
    ax.set_ylabel("Mean twin-curve basis (bp)", color=INK2, fontsize=9)
    ax.set_title("Sukuk discount vs credit risk across issuers: a threshold, not a line", fontsize=10,
                 color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def chart_profile(px: pd.DataFrame, pw: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), facecolor=SURFACE)
    for ax, p, title in ((axes[0], px, "Across issuers"), (axes[1], pw, "Within issuers (issuer FE)")):
        _style(ax)
        if len(p):
            ax.plot(p["kink_bp"], p["r2"], color=SUKUK_C, linewidth=2, marker="o", markersize=3)
            b = p[p["best"]].iloc[0]
            ax.annotate(f"best {b.kink_bp:.0f}bp", (b.kink_bp, b.r2), xytext=(5, -12), textcoords="offset points",
                        fontsize=8, color=INK2)
        ax.set_title(f"{title}: fit (R squared) by kink location", fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Kink in CDS (bp)", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    ap.add_argument("--draws", type=int, default=9999)
    a = ap.parse_args(argv)
    C.setup_logging("run_mechanism")
    out = a.data / "analysis" / "mechanism"
    out.mkdir(parents=True, exist_ok=True)

    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    basis = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")
    im = pd.read_csv(a.data / "analysis" / "drivers" / "drivers_panel_issuer_month.csv")
    ratings = issuer_ratings(uni, im["parent_key"].unique())
    ratings["sub_ig_oman"] = ratings["sub_ig"].where(ratings["parent_key"] != "oman sultanate", True)
    im = prep_issuer_month(im, ratings).merge(ratings[["parent_key", "sub_ig_oman"]], on="parent_key", how="left")
    # issuers without a sovereign CDS series (Sharjah, Arab Energy Fund) form their own government cluster
    im["cds_sovereign"] = im["cds_sovereign"].fillna(im["parent_name"])
    bm = bond_month_panel(basis, uni, im)

    overall, within = structure_tables(bm)
    mech = mechanism_regressions(bm, im, B=a.draws)
    inf = inference_table(im, B=a.draws)
    iss = (im.groupby(["parent_key", "parent_name", "cds_sovereign"], dropna=False)
             .agg(months=("month", "size"), basis=("basis", "mean"), cds=("cds", "mean"),
                  sub_ig=("sub_ig", "first"), sub_ig_oman=("sub_ig_oman", "first"),
                  rating_snapshot=("rating_snapshot", "first")).reset_index())
    thr = threshold_models(im, iss, B=a.draws)

    # 8. Time-varying classification: CDS rule now; rating rule when the ratings file exists
    im["sub_cds"] = np.where(im["cds"].notna(), (im["cds"] > C.CDS_SUB_IG_BP).astype(float), np.nan)
    tv_rows = time_varying_threshold(im, "sub_cds", f"CDS > {C.CDS_SUB_IG_BP:.0f}bp", B=a.draws)
    rating_note = ""
    if C.SOVEREIGN_RATINGS_PATH.exists():
        rt = load_ratings(C.SOVEREIGN_RATINGS_PATH)
        months = pd.PeriodIndex(sorted(im["month"].unique()), freq="M")
        ms = monthly_status(rt, months)
        ms["month"] = ms["month"].astype(str)
        im["government"] = im["parent_key"].map(ISSUER_GOVERNMENT)
        im = im.merge(ms[["government", "month", "sub_ig", "single_agency"]].rename(
            columns={"sub_ig": "sub_rating"}), on=["government", "month"], how="left")
        tv_rows += time_varying_threshold(im, "sub_rating", "Ratings, 2 of 3 agencies below BBB-/Baa3", B=a.draws)
        # robustness: drop Dubai, whose status comes from the DEWA proxy rather than its own rating
        im["sub_rating_ex_dubai"] = im["sub_rating"].where(im["government"] != "Dubai")
        tv_rows += time_varying_threshold(im, "sub_rating_ex_dubai", "Ratings, Dubai excluded (robustness)",
                                          B=a.draws)
        ms.to_csv(out / "mechanism_rating_status_monthly.csv", index=False)
        proxies = sorted({s.split(";")[0].strip() for s in rt["source"].dropna() if "proxy" in s.lower()})
        rating_note = (f"Ratings file: `{C.SOVEREIGN_RATINGS_PATH.name}` ({len(rt)} rating rows). "
                       f"Single-agency obligor-months: {int(im['single_agency'].fillna(False).sum())}. "
                       "**Dubai:** the government is not rated by S&P, Moody's or Fitch, so its rows are the ratings "
                       f"of a government-related entity ({', '.join(proxies) or 'see the source column'}); the "
                       "rationale is in README.md (Design decisions). Dubai is investment grade in every month on "
                       "this proxy, and the *Dubai excluded* rows show the result without it. **Sharjah** counts as "
                       "investment grade under the 2-of-3 rule: Fitch does not rate it, S&P has it at BBB- and "
                       "Moody's at Ba1, so only one of the two rating agencies is below the line.")
    else:
        tmpl = C.SOVEREIGN_RATINGS_PATH.with_name("sovereign_ratings_TEMPLATE.csv")
        template(tmpl, [(ag, f"{ym}-01", r) for ag, ym, r in C.OMAN_UPGRADES])
        rating_note = (f"**Rating-based rows pending:** `{C.SOVEREIGN_RATINGS_PATH.name}` is not present. LSEG "
                       "rating-history fields are not entitled on this login, so the file must be supplied by hand "
                       f"(template written to `{tmpl.name}`).")
    tv = pd.DataFrame(tv_rows)
    oman_ba = before_after(im, "oman sultanate", C.OMAN_UPGRADES)
    chart_threshold(iss, thr["profile_cross"], out / "mechanism_threshold_cross.png")
    chart_profile(thr["profile_cross"], thr["profile_within"], out / "mechanism_spline_profile.png")

    for name, df in (("mechanism_structure_overall", overall), ("mechanism_structure_within", within),
                     ("mechanism_regressions", mech), ("mechanism_inference", inf),
                     ("mechanism_threshold", thr["table"]), ("mechanism_spline_profile_cross", thr["profile_cross"]),
                     ("mechanism_spline_profile_within", thr["profile_within"]),
                     ("mechanism_issuer_ratings", iss.round(1)), ("mechanism_time_varying", tv),
                     ("mechanism_oman_before_after", oman_ba)):
        df.to_csv(out / f"{name}.csv", index=False)

    sen = bm["seniority"].value_counts().to_dict()

    def profile_text(p: pd.DataFrame, label: str) -> str:
        if p.empty:
            return f"- {label}: not estimable."
        b = p[p["best"]].iloc[0]
        near = p[p["r2"] >= p["r2"].max() - 0.005]
        return (f"- **{label}:** best kink {b.kink_bp:.0f}bp, but fit (R squared {p.r2.min():.2f}-{p.r2.max():.2f}) "
                f"is within 0.005 of the best for kinks {near.kink_bp.min():.0f}-{near.kink_bp.max():.0f}bp. Above "
                f"the kink the slope is {near.slope_above_per_100bp.min():.0f} to {near.slope_above_per_100bp.max():.0f}bp "
                f"per 100bp; below it {near.slope_below_per_100bp.min():.0f} to {near.slope_below_per_100bp.max():.0f}bp.")
    prof_reading = [profile_text(thr["profile_cross"], "Across issuers (excl. Dubai govt)"),
                    profile_text(thr["profile_within"], "Within issuers")]
    L = ["# Mechanism, threshold and inference\n",
         f"Generated {date.today():%Y-%m-%d}. Bootstrap: restricted wild cluster bootstrap-t, Webb six-point "
         f"weights, {a.draws:,} draws, clustered by government (6 CDS series) and by issuer. Coefficients are bp of "
         "basis per 100bp of sovereign CDS unless stated.\n",
         "## 1a. Sukuk structure\n",
         f"Seniority: {sen}. Every twin sukuk is senior unsecured, so seniority cannot separate anything.\n",
         "**All twin sukuk (bond-level mean basis):**\n\n", _md(overall),
         "\n**Within issuers that use more than one structure** (`vs_issuer_mean_bp` = the structure's mean basis "
         "minus the issuer's mean, so issuer credit is held fixed):\n\n", _md(within),
         "\n## 1b-1c. Mechanism regressions\n",
         "Bond-month regressions use each sukuk's monthly mean basis and remaining maturity, with issuer fixed "
         "effects. Interaction terms are centred (maturity at its sample mean, interbank spread at its mean).\n\n",
         _md(mech),
         "\nHow to read the predictions:",
         "- **Recovery / asset backing:** an Ijara sukuk is backed by a tangible asset, so if investors price "
         "recovery value the discount should *steepen* with CDS for Ijara (CDS x Ijara < 0).",
         "- **Default / recovery over time:** expected loss accumulates with maturity, so the CDS slope should "
         "grow with tenor (CDS x maturity < 0).",
         "- **Captive demand:** if local Islamic banks are the marginal buyer, tight local funding (a wider "
         "interbank spread) should *weaken* the discount (CDS x interbank > 0). The negative liquidity-gap "
         "coefficient fits the same story: sukuk that trade less are held to maturity by these banks and price "
         "richer, which is the opposite of a liquidity premium.\n",
         "## 2. Threshold shape\n",
         "Ratings are a **snapshot as of the export**, not a history. The Oman sovereign shows Baa3 (investment "
         "grade) after its 2024 upgrades, but it was rated below investment grade for most of the sample, so a "
         "variant counts it as sub-IG. The CDS spline does not need ratings because CDS varies over time.\n\n",
         _md(iss[["parent_name", "rating_snapshot", "sub_ig", "sub_ig_oman", "cds", "basis", "months"]].round(1)),
         "\n", _md(thr["table"]),
         "\n![threshold](mechanism_threshold_cross.png)\n",
         "\n![profile](mechanism_spline_profile.png)\n",
         "**Reading the spline profiles:**\n", *prof_reading,
         "- Across issuers only three issuers sit above 100bp CDS, so the data say \"flat, then a drop\" but "
         "cannot say *where* between roughly 100bp and 200bp the drop starts. Read the cross-issuer result as "
         "the IG vs sub-IG gap, not as a precise kink.\n",
         "Spline profiles (fit for each kink location):\n\n**Across issuers (excl. Dubai govt):**\n\n",
         _md(thr["profile_cross"].drop(columns=["ssr"]).round(2)),
         "\n**Within issuers:**\n\n", _md(thr["profile_within"].drop(columns=["ssr"]).round(2)),
         "\n## 8. Time-varying classification\n",
         "Snapshot ratings misclassify issuers whose rating changed (Oman). Here the sub-IG flag varies by "
         f"obligor-month. The CDS rule marks a month sub-IG when the government's 5y CDS exceeds "
         f"{C.CDS_SUB_IG_BP:.0f}bp. The rating rule needs at least two of S&P, Moody's and Fitch below "
         "BBB-/Baa3 (a single rating agency decides only where just one rates the government). Level gaps use "
         "obligor-months without fixed effects; the extra slope uses issuer fixed effects. Wild bootstrap "
         "clusters are obligor groups (government, or the issuer itself where no government CDS applies).\n\n",
         rating_note + "\n\n", _md(tv),
         "\n**Oman before vs after each upgrade to investment grade** (12 months either side, the upgrade month "
         "excluded; Newey-West 90% CI, 3 lags). Upgrade months as supplied: "
         + "; ".join(f"{ag} {r} {ym}" for ag, ym, r in C.OMAN_UPGRADES)
         + ". Windows overlap because the upgrades are 4-10 months apart, and the last one has fewer than 12 "
         "months after it, so read these as descriptive.\n\n", _md(oman_ba),
         "\n## 3. Inference with six credit series\n",
         "The panel t-statistics in credit_results.md treat 16 issuers as independent. They share only six "
         "CDS series, so the government-clustered wild bootstrap is the honest test. First differences remove "
         "the common trend in CDS and the basis.\n\n",
         _md(inf),
         "\n## Caveats\n",
         "- The kink is chosen on a grid, and the p-values do not account for that search.",
         "- Structure varies within only a few issuers (KSA, Bahrain, Aramco, Arab Energy Fund), so the Ijara "
         "interaction rests on a handful of bonds.",
         "- Snapshot ratings: see section 2.\n"]
    (out / "mechanism_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Mechanism:\n%s", mech.to_string(index=False))
    log.info("Inference:\n%s", inf.to_string(index=False))
    log.info("Threshold:\n%s", thr["table"].to_string(index=False))
    log.info("Wrote %s", out / "mechanism_results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
