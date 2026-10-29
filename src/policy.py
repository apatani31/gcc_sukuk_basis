"""Policy numbers (NEXT_PROMPT task 5).

a. Annual coupon saving per twin issuer = outstanding USD sukuk x (minus) mean
   basis. A negative basis means the sukuk yields less than the issuer's own
   conventional curve, so issuing sukuk saves that many bp per year on the
   amount outstanding. Two versions: trailing-12-month mean and full-sample
   mean, each with a 90% interval from the Newey-West standard error of the
   issuer's daily basis.
b. Out-of-sample counterfactual for sovereigns with no USD sukuk: apply the
   cross-issuer threshold models to their current CDS, with prediction
   intervals. This extrapolates from 16 issuers and is labelled as such.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .twin import newey_west_mean

Z90 = 1.644854


def outstanding_sukuk(universe: pd.DataFrame, keys, asof: pd.Timestamp) -> pd.DataFrame:
    """USD sukuk outstanding per issuer: primary lines, maturity after `asof` (perpetuals excluded)."""
    u = universe[(universe["instrument_class"] == "bond") & universe["is_primary_line"] & universe["is_sukuk"]
                 & universe["parent_key"].isin(keys)]
    live = u[u["maturity_date"] > asof]
    g = live.groupby("parent_key").agg(outstanding_usd_bn=("amount_issued_usd", lambda s: s.sum() / 1e9),
                                       sukuk_outstanding=("instrument_id", "size"))
    perps = u[u["maturity_date"].isna()].groupby("parent_key")["amount_issued_usd"].sum() / 1e9
    g["perpetual_excluded_usd_bn"] = perps.reindex(g.index).fillna(0.0)
    return g.reset_index()


def savings(daily: pd.DataFrame, stats: pd.DataFrame, outstanding: pd.DataFrame, asof: pd.Timestamp,
            nw_lags: int = 20) -> pd.DataFrame:
    """Annual saving (USD m) = outstanding x (-basis)/10,000, trailing 12m and full sample, 90% CI."""
    start = asof - pd.DateOffset(months=12)
    rows = []
    for (key, name), g in daily.groupby(["parent_key", "parent_name"]):
        o = outstanding[outstanding["parent_key"] == key]
        amt = float(o["outstanding_usd_bn"].iloc[0]) if len(o) else 0.0
        g = g.sort_values("date")
        t12 = g[(g["date"] > start) & (g["date"] <= asof)]
        m12, se12 = newey_west_mean(t12["basis_bp"].to_numpy(), nw_lags) if len(t12) >= 20 else (np.nan, np.nan)
        st = stats[stats["issuer"] == name]
        mf = float(st["mean_basis_bp"].iloc[0]) if len(st) else np.nan
        sef = float(st["nw_se_bp"].iloc[0]) if len(st) else np.nan
        musd = lambda bp: -amt * 1e3 * bp / 1e4  # noqa: E731  USD m per year
        rows.append({"issuer": name, "outstanding_usd_bn": round(amt, 2),
                     "trailing12m_days": len(t12), "basis_12m_bp": round(m12, 1),
                     "saving_12m_usd_m": round(musd(m12), 1),
                     "saving_12m_ci90": (f"[{musd(m12 + Z90 * se12):.1f}, {musd(m12 - Z90 * se12):.1f}]"
                                         if np.isfinite(se12) else ""),
                     "basis_full_bp": round(mf, 1), "saving_full_usd_m": round(musd(mf), 1),
                     "saving_full_ci90": (f"[{musd(mf + Z90 * sef):.1f}, {musd(mf - Z90 * sef):.1f}]"
                                          if np.isfinite(sef) else "")})
    out = pd.DataFrame(rows).sort_values("saving_12m_usd_m", ascending=False, na_position="last")
    return out.reset_index(drop=True)


def counterfactual(iss: pd.DataFrame, targets: pd.DataFrame, kink: float | None) -> pd.DataFrame:
    """Predicted basis (bp) and saving per USD 1bn for sovereigns without USD sukuk.

    iss: issuer means with basis, cds, sub_ig_oman (fits exclude Dubai govt, as in mechanism.py).
    targets: name, cds (current), sub_ig (bool, from ratings)."""
    import statsmodels.formula.api as smf

    d = iss.dropna(subset=["basis", "cds"])
    d = d[d["parent_key"] != "dubai emirate"].copy()
    d["cds100"] = d["cds"] / 100
    d["sub"] = d["sub_ig_oman"].astype(float)
    models = {"IG vs sub-IG dummy": smf.ols("basis ~ sub", d).fit()}
    if kink is not None:
        d["h"] = np.maximum(d["cds"] - kink, 0) / 100
        models[f"CDS spline (kink {kink:.0f}bp)"] = smf.ols("basis ~ cds100 + h", d).fit()
    models["Linear CDS"] = smf.ols("basis ~ cds100", d).fit()
    rows = []
    for t in targets.itertuples():
        x = pd.DataFrame({"sub": [float(t.sub_ig)], "cds100": [t.cds / 100],
                          "h": [max(t.cds - (kink or 0), 0) / 100]})
        for mname, m in models.items():
            pr = m.get_prediction(x).summary_frame(alpha=0.10)
            fit, lo, hi = pr["mean"].iloc[0], pr["obs_ci_lower"].iloc[0], pr["obs_ci_upper"].iloc[0]
            rows.append({"sovereign": t.name, "current_cds_bp": round(t.cds, 1), "model": mname,
                         "predicted_basis_bp": round(fit, 1), "pred_interval_90": f"[{lo:.1f}, {hi:.1f}]",
                         "saving_per_usd_1bn_m": round(-fit * 0.1, 2),
                         "saving_interval_90": f"[{-hi * 0.1:.2f}, {-lo * 0.1:.2f}]",
                         "fit_issuers": int(m.nobs)})
    return pd.DataFrame(rows)


def today() -> pd.Timestamp:
    return pd.Timestamp(date.today())
