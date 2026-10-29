"""Why do weak credits get a bigger sukuk discount? Mechanism, threshold and inference.

1. Mechanism
   a. Structure: basis by sukuk structure, within issuers that use several;
      CDS x asset-backed (Ijara) at bond-month level. A recovery/seniority story
      predicts a steeper CDS slope for asset-backed sukuk.
   b. Tenor: CDS x remaining maturity at bond-month level. A default/recovery
      story predicts a slope that grows with maturity.
   c. Captive demand: CDS x local interbank spread. If Islamic banks are the
      marginal buyer, tight local liquidity should weaken the discount.
2. Threshold: investment-grade vs sub-IG dummy (snapshot ratings) and a
   piecewise-linear CDS spline with the kink chosen on a grid, within and
   across issuers.
3. Inference: restricted wild cluster bootstrap by government (6 CDS series)
   and by issuer, and a first-differences version of the main regression.

CDS enters per 100bp (cds100) so coefficients read as bp of basis per 100bp CDS.
"""
from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd

from .config import TWIN
from .inference import wild_cluster_bootstrap

log = logging.getLogger(__name__)

IG_MOODYS = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3"]
SUB_IG_MOODYS = ["Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def issuer_ratings(universe: pd.DataFrame, keys) -> pd.DataFrame:
    """Snapshot rating per issuer: modal Moody's issuer/issue rating (WR/NR ignored),
    falling back to the modal LSEG bond grade. Ratings are as of the export date."""
    b = universe[universe["parent_key"].isin(keys) & (universe["instrument_class"] == "bond")]
    rows = []
    for k, g in b.groupby("parent_key"):
        r = pd.concat([g["moodys_issuer_rating"], g["moodys_issue_rating"]]).dropna()
        r = r[r.isin(IG_MOODYS + SUB_IG_MOODYS)]
        if len(r):
            rating = r.mode().iat[0]
            sub = rating in SUB_IG_MOODYS
            src = "Moody's"
        else:
            bg = g["bond_grade"].dropna()
            rating = bg.mode().iat[0] if len(bg) else None
            sub = rating == "High Yield" if rating else np.nan
            src = "LSEG bond grade" if rating else "none"
        rows.append({"parent_key": k, "rating_snapshot": rating, "rating_source": src, "sub_ig": sub})
    return pd.DataFrame(rows)


def bond_month_panel(basis: pd.DataFrame, universe: pd.DataFrame, issuer_month: pd.DataFrame) -> pd.DataFrame:
    """Sukuk-month panel (main matches) with structure, tenor and issuer-month drivers."""
    b = basis[basis["match_method"].isin(TWIN["main_methods"])].copy()
    b["month"] = b["date"].dt.to_period("M").astype(str)
    bm = (b.groupby(["instrument_id", "parent_key", "month"])
           .agg(basis=("basis_bp", "mean"), tau=("tau", "mean")).reset_index())
    meta = universe.drop_duplicates("instrument_id").set_index("instrument_id")
    bm["structure"] = bm["instrument_id"].map(meta["sukuk_structure_type"]).fillna("Unknown")
    bm["seniority"] = bm["instrument_id"].map(meta["seniority"])
    bm["ijara"] = (bm["structure"] == "Ijara").astype(int)
    im = issuer_month[["parent_key", "parent_name", "month", "cds", "liq_gap", "ib_spread", "cds_sovereign",
                       "sovereign"]]
    bm = bm.merge(im, on=["parent_key", "month"], how="left")
    bm["cds100"] = bm["cds"] / 100
    bm["t"] = bm["month"]
    return bm


def prep_issuer_month(p: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    p = p.merge(ratings[["parent_key", "sub_ig", "rating_snapshot"]], on="parent_key", how="left")
    p["cds100"] = p["cds"] / 100
    p["t"] = p["month"]
    p = p.sort_values(["parent_key", "month"])
    mi = pd.PeriodIndex(p["month"], freq="M").astype("int64")
    ok = pd.Series(mi, index=p.index).groupby(p["parent_key"]).diff().eq(1)
    for c in ("basis", "cds100", "liq_gap"):
        p[f"d_{c}"] = p.groupby("parent_key")[c].diff().where(ok)
    return p


# ---------------------------------------------------------------------------
# 1a. Structure
# ---------------------------------------------------------------------------
def structure_tables(bm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    bond = bm.groupby(["instrument_id", "parent_name", "structure"])["basis"].mean().reset_index()
    overall = (bond.groupby("structure")["basis"].agg(sukuk="size", mean_basis_bp="mean", median_basis_bp="median")
               .round(1).reset_index().sort_values("sukuk", ascending=False))
    multi = bond.groupby("parent_name")["structure"].nunique()
    multi = multi[multi > 1].index
    w = bond[bond["parent_name"].isin(multi)].copy()
    w["vs_issuer_mean_bp"] = w["basis"] - w.groupby("parent_name")["basis"].transform("mean")
    within = (w.groupby(["parent_name", "structure"])
              .agg(sukuk=("basis", "size"), mean_basis_bp=("basis", "mean"),
                   vs_issuer_mean_bp=("vs_issuer_mean_bp", "mean")).round(1).reset_index())
    return overall, within


# ---------------------------------------------------------------------------
# Generic regression row with clustered t and wild bootstrap
# ---------------------------------------------------------------------------
def reg_row(label: str, formula: str, data: pd.DataFrame, target: str, B: int, extra: dict | None = None) -> dict:
    import statsmodels.formula.api as smf

    cols = [c for c in set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", formula)) if c in data.columns]
    d = data.dropna(subset=cols)
    m = smf.ols(formula, d)
    cl = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["parent_key"])[0]})
    out = {"model": label, "term": target, "coef_bp": round(cl.params[target], 2),
           "t_cluster_issuer": round(cl.tvalues[target], 2), "n_obs": int(cl.nobs),
           "issuers": d["parent_key"].nunique()}
    for cname, ccol in (("government", "cds_sovereign"), ("issuer", "parent_key")):
        if d[ccol].nunique() >= 3:
            w = wild_cluster_bootstrap(formula, d, target, ccol, B=B)
            out[f"p_wild_{cname}"] = round(w["p_wild"], 3)
    out.update(extra or {})
    return out


# ---------------------------------------------------------------------------
# 1b/1c and 3. Mechanism and inference regressions
# ---------------------------------------------------------------------------
def mechanism_regressions(bm: pd.DataFrame, im: pd.DataFrame, B: int = 9999) -> pd.DataFrame:
    fe = "C(parent_key)"
    bm = bm.dropna(subset=["cds"]).copy()
    bm["tau_c"] = bm["tau"] - bm["tau"].mean()
    im = im.dropna(subset=["cds"]).copy()
    im["ib_c"] = im["ib_spread"] - im["ib_spread"].mean()
    rows = [
        reg_row("1a. Bond-month: CDS x Ijara (asset-backed)", f"basis ~ cds100 + ijara + cds100:ijara + {fe}",
                bm, "cds100:ijara", B),
        reg_row("1a. Bond-month: CDS slope (same sample)", f"basis ~ cds100 + ijara + cds100:ijara + {fe}",
                bm, "cds100", B, {"note": "slope for non-Ijara sukuk"}),
        reg_row("1b. Bond-month: CDS x remaining maturity (per year)", f"basis ~ cds100 + tau_c + cds100:tau_c + {fe}",
                bm, "cds100:tau_c", B),
        reg_row("1b. Bond-month: CDS slope at mean maturity", f"basis ~ cds100 + tau_c + cds100:tau_c + {fe}",
                bm, "cds100", B, {"note": f"mean remaining maturity {bm['tau'].mean():.1f}y"}),
        reg_row("1c. Issuer-month: CDS x interbank spread (per bp)",
                f"basis ~ cds100 + ib_c + cds100:ib_c + liq_gap + {fe}", im, "cds100:ib_c", B),
        reg_row("1c. Issuer-month: CDS slope at mean interbank spread",
                f"basis ~ cds100 + ib_c + cds100:ib_c + liq_gap + {fe}", im, "cds100", B),
        reg_row("1c. Issuer-month: liquidity gap (bp basis per bp bid-ask)",
                f"basis ~ cds100 + liq_gap + {fe}", im, "liq_gap", B),
    ]
    return pd.DataFrame(rows)


def inference_table(im: pd.DataFrame, B: int = 9999) -> pd.DataFrame:
    fe = "C(parent_key)"
    im = im.dropna(subset=["cds"])
    return pd.DataFrame([
        reg_row("Main within slope: basis ~ CDS + liquidity, issuer FE", f"basis ~ cds100 + liq_gap + {fe}",
                im, "cds100", B),
        reg_row("Main within slope, no liquidity control", f"basis ~ cds100 + {fe}", im, "cds100", B),
        reg_row("First differences: d(basis) ~ d(CDS) + d(liquidity)", "d_basis ~ d_cds100 + d_liq_gap",
                im, "d_cds100", B),
        reg_row("First differences, no liquidity control", "d_basis ~ d_cds100", im, "d_cds100", B),
    ])


# ---------------------------------------------------------------------------
# 8b. Time-varying sub-IG classification
# ---------------------------------------------------------------------------
def time_varying_threshold(im: pd.DataFrame, flag: str, label: str, B: int = 9999) -> list[dict]:
    """Level gap and extra within slope with a monthly sub-IG flag (column `flag`, 0/1).

    Level gap: issuer-month basis on the flag, no fixed effects (cross-sectional and over time),
    clustered by obligor group. Extra slope: CDS x flag with issuer fixed effects, so it is identified
    within issuers, including from issuers whose status changes (e.g. Oman's upgrades)."""
    d = im.dropna(subset=["basis", flag]).copy()
    d["sub_t"] = d[flag].astype(float)
    switchers = d.groupby("parent_key")["sub_t"].nunique()
    note = f"{int((d['sub_t'] == 1).sum())} sub-IG obligor-months; issuers switching status: {int((switchers > 1).sum())}"
    rows = [reg_row(f"{label}: level gap, sub-IG minus IG (obligor-months)", "basis ~ sub_t", d, "sub_t", B,
                    {"note": note})]
    dc = d.dropna(subset=["cds"])
    rows.append(reg_row(f"{label}: CDS slope when IG", "basis ~ cds100 + sub_t + cds100:sub_t + C(parent_key)",
                        dc, "cds100", B))
    rows.append(reg_row(f"{label}: extra CDS slope when sub-IG",
                        "basis ~ cds100 + sub_t + cds100:sub_t + C(parent_key)", dc, "cds100:sub_t", B))
    return rows


def before_after(im: pd.DataFrame, parent_key: str, events, window: int = 12, lags: int = 3) -> pd.DataFrame:
    """Mean basis in the `window` months before vs after each event month (event month excluded).

    events: (agency, 'YYYY-MM', rating). Difference = after - before with a Newey-West 90% CI
    from regressing the monthly basis on an 'after' dummy."""
    import statsmodels.api as sm

    s = im[im["parent_key"] == parent_key].dropna(subset=["basis"]).copy()
    s["m"] = pd.PeriodIndex(s["month"], freq="M")
    rows = []
    for agency, ym, rating in events:
        e = pd.Period(ym, "M")
        pre = s[(s["m"] >= e - window) & (s["m"] <= e - 1)]
        post = s[(s["m"] >= e + 1) & (s["m"] <= e + window)]
        rec = {"event": f"{agency} to {rating}", "month": ym, "months_before": len(pre), "months_after": len(post),
               "mean_before_bp": round(pre["basis"].mean(), 1) if len(pre) else np.nan,
               "mean_after_bp": round(post["basis"].mean(), 1) if len(post) else np.nan}
        if len(pre) >= 3 and len(post) >= 3:
            w = pd.concat([pre.assign(after=0.0), post.assign(after=1.0)]).sort_values("m")
            r = sm.OLS(w["basis"], sm.add_constant(w["after"])).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
            lo, hi = r.conf_int(alpha=0.10).loc["after"]
            rec.update(change_bp=round(r.params["after"], 1), ci90=f"[{lo:.1f}, {hi:.1f}]",
                       t_nw=round(r.tvalues["after"], 2))
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Threshold
# ---------------------------------------------------------------------------
def hinge(x: pd.Series, k: float) -> pd.Series:
    return np.maximum(x - k, 0.0)


def spline_profile(d: pd.DataFrame, grid, fe: bool, min_side: int) -> pd.DataFrame:
    """SSR for basis ~ cds + hinge(cds, k) [+ issuer FE] over a grid of kinks k (bp)."""
    import statsmodels.formula.api as smf

    rows = []
    for k in grid:
        n_above = int((d["cds"] > k).sum())
        n_below = int((d["cds"] <= k).sum())
        if min(n_above, n_below) < min_side:
            continue
        dd = d.assign(h=hinge(d["cds"], k) / 100)
        f = "basis ~ cds100 + h" + (" + C(parent_key)" if fe else "")
        r = smf.ols(f, dd).fit()
        rows.append({"kink_bp": k, "ssr": r.ssr, "r2": round(r.rsquared, 4),
                     "slope_below_per_100bp": round(r.params["cds100"], 1),
                     "slope_above_per_100bp": round(r.params["cds100"] + r.params["h"], 1),
                     "obs_above_kink": n_above})
    out = pd.DataFrame(rows)
    if len(out):
        out["best"] = out["ssr"] == out["ssr"].min()
    return out


def threshold_models(im: pd.DataFrame, iss: pd.DataFrame, B: int = 9999) -> dict:
    """iss: issuer means with cds, basis, sub_ig, sub_ig_oman, cds_sovereign, parent_key."""
    fe = "C(parent_key)"
    im = im.dropna(subset=["cds"])
    xd = iss.dropna(subset=["basis", "sub_ig"]).copy()     # dummy models do not need CDS (keeps Sharjah)
    xd["sub_ig_i"] = xd["sub_ig"].astype(float)
    xd["sub_ig_oman_i"] = xd["sub_ig_oman"].astype(float)
    xs = iss.dropna(subset=["cds", "basis"]).copy()
    xs["cds100"] = xs["cds"] / 100
    imx = im.dropna(subset=["sub_ig"]).copy()
    imx["sub_ig_i"] = imx["sub_ig"].astype(float)
    imx["sub_ig_oman_i"] = imx["sub_ig_oman"].astype(float)
    rows = [
        reg_row("Across issuers: basis ~ sub-IG dummy (snapshot ratings)", "basis ~ sub_ig_i", xd, "sub_ig_i", B),
        reg_row("Across issuers: basis ~ sub-IG dummy (Oman sovereign counted as sub-IG)",
                "basis ~ sub_ig_oman_i", xd, "sub_ig_oman_i", B),
        reg_row("Across issuers: basis ~ CDS (linear, for comparison)", "basis ~ cds100", xs, "cds100", B),
        reg_row("Within issuers: CDS slope, investment grade", f"basis ~ cds100 + cds100:sub_ig_oman_i + {fe}",
                imx, "cds100", B),
        reg_row("Within issuers: extra CDS slope for sub-IG (Oman counted sub-IG)",
                f"basis ~ cds100 + cds100:sub_ig_oman_i + {fe}", imx, "cds100:sub_ig_oman_i", B),
    ]
    grid_x = list(range(50, 260, 10))
    grid_w = list(range(50, 400, 10))
    # Dubai govt's basis rests on ~20y interpolation brackets (twin_results.md); with only 16 points it
    # alone decides the cross-issuer kink, so the cross-issuer spline is fitted without it.
    xs_exd = xs[xs["parent_key"] != "dubai emirate"]
    prof_x_all = spline_profile(xs, grid_x, fe=False, min_side=3)
    prof_x = spline_profile(xs_exd, grid_x, fe=False, min_side=3)
    prof_w = spline_profile(im, grid_w, fe=True, min_side=40)
    for lab, prof, data, f in (("Across issuers incl. Dubai govt", prof_x_all, xs, "basis ~ cds100 + h"),
                               ("Across issuers excl. Dubai govt", prof_x, xs_exd, "basis ~ cds100 + h"),
                               ("Within issuers", prof_w, im, f"basis ~ cds100 + h + {fe}")):
        if len(prof):
            k = float(prof.loc[prof["best"], "kink_bp"].iloc[0])
            dd = data.assign(h=hinge(data["cds"], k) / 100)
            rows.append(reg_row(f"{lab}: spline, extra slope above best kink ({k:.0f}bp)", f, dd, "h", B,
                                {"note": "kink chosen on the grid (search not reflected in p-values)"}))
    return {"table": pd.DataFrame(rows), "profile_cross": prof_x, "profile_within": prof_w}
