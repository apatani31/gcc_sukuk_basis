"""Oil through credit (NEXT_PROMPT task 4).

a. Event study with each government's 5y CDS as the outcome: same shocks,
   volatility-matched median placebo, clean and ex-2020 variants. Reuses the
   basis event-study machinery by treating each CDS series as a one-"bond"
   issuer whose "basis" is the CDS level (so d_basis = change in CDS, bp).
b. Implied basis response = (oil -> CDS) x (CDS -> basis slope), with a
   bootstrap over shocks (oil -> CDS) and over governments (the slope), compared
   with the direct event-study estimate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .event_report import KEY_TAUS, run_sample
from .event_study import oil_vol, placebo_event_means, vol_bins


def cds_obs(cds: pd.DataFrame) -> pd.DataFrame:
    """Long frame in the event-study 'obs' layout: one pseudo-bond per sovereign, basis_bp = CDS (bp)."""
    c = cds.astype(float).copy()
    c.index = pd.to_datetime(c.index)
    long = c.stack().rename("cds").rename_axis(["date", "sovereign_name"]).reset_index()
    return pd.DataFrame({"parent_key": long["sovereign_name"], "parent_name": long["sovereign_name"],
                         "sovereign": True, "instrument_id": long["sovereign_name"], "date": long["date"],
                         "match_method": "interp", "basis_bp": long["cds"], "y_sukuk": long["cds"] / 100,
                         "y_conv": 0.0, "tau": np.nan})


def prep_shocks(shocks: pd.DataFrame, market: pd.DataFrame, obs: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, np.ndarray]:
    s = shocks.copy()
    s["date"] = pd.to_datetime(s["date"])
    s["event_id"] = s["date"].dt.strftime("%Y-%m-%d") + "_" + s["sign"]
    vol = oil_vol(market)
    span = vol.loc[obs["date"].min():obs["date"].max()].dropna()
    edges = span.quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    s["vol_bin"] = vol_bins(vol, s["date"], edges)
    return s, vol, edges


def _key(res: dict, sample: str, unit: str) -> list[dict]:
    rows = []
    for sign in ("up", "down", "pooled"):
        a = res[sign]["agg"].set_index("tau") if len(res[sign]["agg"]) else pd.DataFrame()
        pl = res[sign]["placebo"]["d_basis"].set_index("tau") if len(res[sign]["placebo"]["d_basis"]) else pd.DataFrame()
        for tau in KEY_TAUS:
            if tau not in a.index:
                continue
            n = int(a.loc[tau, "n_shocks"])
            rows.append({"sample": sample, "unit": unit, "shock": sign, "tau": tau, "n_shocks": n,
                         "mean_bp": round(a.loc[tau, "d_basis_mean"], 1),
                         "median_bp": round(a.loc[tau, "d_basis_median"], 1),
                         "t_mean": round(a.loc[tau, "d_basis_t"], 2),
                         "rises": f"{n - int(a.loc[tau, 'd_basis_n_neg'])}/{n}",
                         "placebo_p_median": round(pl.loc[tau, "d_basis_placebo_p"], 3) if tau in pl.index else np.nan,
                         "mde80_bp": round(pl.loc[tau, "d_basis_mde80"], 1) if tau in pl.index else np.nan})
    return rows


def cds_event_study(cds: pd.DataFrame, shocks: pd.DataFrame, market: pd.DataFrame,
                    pre: int = 5, post: int = 20) -> dict:
    """CDS responses: average across sovereigns and by sovereign, for all / clean / ex-2020 shocks."""
    obs = cds_obs(cds)
    s, vol, edges = prep_shocks(shocks, market, obs)
    variants = {"All shocks": s,
                "Clean (no opposite-sign shock in window)": s[~s["opposite_shock_within_window"].astype(bool)],
                "Excluding 2020": s[s["date"].dt.year != 2020]}
    pooled_rows, by_rows, event_level = [], [], {}
    pl_all = placebo_event_means(obs, s["date"], vol, edges, pre=pre, post=post)
    for vname, sv in variants.items():
        res = run_sample(obs, sv, pl_all, pre, post)
        pooled_rows += _key(res, vname, "average of sovereigns")
        if vname == "All shocks":
            event_level = {sign: res[sign]["events"] for sign in ("up", "down", "pooled")}
    for sov in cds.columns:
        o = obs[obs["parent_key"] == sov]
        pl = placebo_event_means(o, s["date"], vol, edges, pre=pre, post=post)
        res = run_sample(o, s, pl, pre, post)
        by_rows += [r for r in _key(res, "All shocks", sov) if r["tau"] in (5, 20)]
    return {"pooled": pd.DataFrame(pooled_rows), "by_sovereign": pd.DataFrame(by_rows), "events": event_level,
            "shocks": s}


def _fe_slope(d: pd.DataFrame) -> float:
    """Within-issuer slope of basis on CDS (bp per bp) with a liquidity control, by demeaning."""
    cols = ["basis", "cds", "liq_gap"]
    z = d[cols] - d.groupby("parent_key")[cols].transform("mean")
    X = z[["cds", "liq_gap"]].to_numpy()
    return float(np.linalg.lstsq(X, z["basis"].to_numpy(), rcond=None)[0][0])


def implied_vs_direct(events_pooled: pd.DataFrame, panel: pd.DataFrame, direct: pd.DataFrame,
                      B: int = 4999, seed: int = 5) -> pd.DataFrame:
    """Implied basis response per oil-price rise = mean d(CDS) x within slope, bootstrap CI.

    events_pooled: event-level sign-adjusted CDS changes (d_basis column = d CDS) by tau.
    panel: issuer-month panel (basis, cds, liq_gap, parent_key, cds_sovereign).
    direct: event_key_main.csv (pooled rows give the direct basis estimate)."""
    rng = np.random.default_rng(seed)
    p = panel.dropna(subset=["basis", "cds", "liq_gap", "cds_sovereign"])
    b0 = _fe_slope(p)
    govs = p["cds_sovereign"].unique()
    by_gov = {g: p[p["cds_sovereign"] == g] for g in govs}
    slopes = []
    for _ in range(B):                       # pairs cluster bootstrap over governments
        pick = rng.choice(govs, size=len(govs), replace=True)
        parts = []
        for j, g in enumerate(pick):
            q = by_gov[g].copy()
            q["parent_key"] = q["parent_key"] + f"#{j}"  # duplicated governments become distinct issuers
            parts.append(q)
        slopes.append(_fe_slope(pd.concat(parts)))
    slopes = np.array(slopes)
    rows = []
    for tau in (5, 20):
        e = events_pooled[events_pooled["tau"] == tau]["d_basis"].dropna().to_numpy()
        if not len(e):
            continue
        dcds = rng.choice(e, size=(B, len(e)), replace=True).mean(axis=1)
        implied = dcds * slopes
        dr = direct[(direct["shock"] == "pooled") & (direct["tau"] == tau)]
        rows.append({"tau": tau, "shocks": len(e), "oil_to_cds_bp": round(e.mean(), 1),
                     "oil_to_cds_ci90": f"[{np.percentile(dcds, 5):.1f}, {np.percentile(dcds, 95):.1f}]",
                     "cds_to_basis_bp_per_100bp": round(100 * b0, 1),
                     "slope_ci90": f"[{100 * np.percentile(slopes, 5):.1f}, {100 * np.percentile(slopes, 95):.1f}]",
                     "implied_basis_bp": round(e.mean() * b0, 2),
                     "implied_ci90": f"[{np.percentile(implied, 5):.2f}, {np.percentile(implied, 95):.2f}]",
                     "direct_basis_mean_bp": float(dr["basis mean"].iloc[0]) if len(dr) else np.nan,
                     "direct_basis_median_bp": float(dr["basis median"].iloc[0]) if len(dr) else np.nan,
                     "direct_mde80_bp": float(dr["basis MDE 80% (bp)"].iloc[0]) if len(dr) else np.nan})
    return pd.DataFrame(rows)
