"""Additional drivers of the twin-curve basis, and a factor (PCA) view of it.

- Local interbank spreads: 3-month local fixing minus the 3-month US Treasury
  bill (pegged currencies, so this is local funding tightness for the banks
  that hold most sukuk).
- Sukuk issuance: USD sukuk and conventional bond issuance by country of risk,
  from the security universe. Tests a supply / scarcity explanation: more
  sukuk supply should shrink the discount.
- PCA on the issuer-by-month basis panel: is there a common GCC-wide factor,
  and what moves it?
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import INTERBANK_RICS

log = logging.getLogger(__name__)


def pull_interbank(out_path: Path, start: str = "2016-01-01", end: str | None = None) -> pd.DataFrame:
    """Daily 3-month interbank fixings (percent) via ld.get_history (needs an open session)."""
    from .session import call_api, ld

    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    cols = {}
    for country, (ric, field) in INTERBANK_RICS.items():
        h = call_api(ld.get_history, ric, fields=[field], interval="daily", start=start, end=end)
        cols[country] = pd.to_numeric(h[field], errors="coerce")
        log.info("Interbank %s (%s): %d days", country, ric, cols[country].notna().sum())
    df = pd.DataFrame(cols)
    df.index.name = "date"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return df


def interbank_spread_monthly(interbank: pd.DataFrame, ust: pd.DataFrame) -> pd.DataFrame:
    """Monthly mean of (local 3m - US 3m bill) in bp, long format: country, month, ib_spread."""
    ib = interbank.astype(float).copy()
    ib.index = pd.to_datetime(ib.index)
    us3m = ust.astype(float)[0.25].reindex(ib.index, method="ffill")
    spread = ib.sub(us3m, axis=0) * 100
    m = spread.resample("ME").mean()
    m.index = m.index.to_period("M")
    return m.stack().rename("ib_spread").rename_axis(["month", "country"]).reset_index()


def issuance_monthly(universe: pd.DataFrame) -> pd.DataFrame:
    """USD bond issuance by country of risk and month (one line per bond, money market excluded).

    Returns country, month, sukuk_usd_bn, conv_usd_bn and trailing-12-month sums,
    log sukuk issuance and the sukuk share of trailing-12m issuance."""
    b = universe[(universe["instrument_class"] == "bond") & universe["is_primary_line"]
                 & ~universe["possible_sukuk_mislabel"] & universe["issue_date"].notna()].copy()
    b["month"] = b["issue_date"].dt.to_period("M")
    b["amt_bn"] = b["amount_issued_usd"].fillna(0) / 1e9
    g = b.pivot_table(index=["country_of_risk", "month"], columns="is_sukuk", values="amt_bn",
                      aggfunc="sum", fill_value=0.0)
    g.columns = ["sukuk_usd_bn" if c else "conv_usd_bn" for c in g.columns]
    out = []
    for c, gg in g.groupby(level=0):
        gg = gg.droplevel(0)
        idx = pd.period_range(gg.index.min(), pd.Timestamp.today().to_period("M"), freq="M")
        gg = gg.reindex(idx, fill_value=0.0)
        gg["sukuk_12m_bn"] = gg["sukuk_usd_bn"].rolling(12, min_periods=1).sum()
        gg["conv_12m_bn"] = gg["conv_usd_bn"].rolling(12, min_periods=1).sum()
        gg["log_sukuk_12m"] = np.log1p(gg["sukuk_12m_bn"])
        tot = gg["sukuk_12m_bn"] + gg["conv_12m_bn"]
        gg["sukuk_share_12m"] = np.where(tot > 0, gg["sukuk_12m_bn"] / tot, np.nan)
        gg["country"] = c
        out.append(gg.rename_axis("month").reset_index())
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# PCA on the basis panel
# ---------------------------------------------------------------------------
def basis_matrix(panel: pd.DataFrame, start: str, end: str, min_coverage: float = 0.8,
                 max_gap: int = 2) -> pd.DataFrame:
    """Balanced month x issuer matrix of the basis over [start, end].

    Keeps issuers observed in at least `min_coverage` of months; fills interior
    gaps of up to `max_gap` months by linear interpolation; then keeps only
    months where every kept issuer is observed."""
    w = panel.pivot_table(index="month", columns="parent_name", values="basis")
    w.index = pd.PeriodIndex(w.index, freq="M") if not isinstance(w.index, pd.PeriodIndex) else w.index
    idx = pd.period_range(start, end, freq="M")
    w = w.reindex(idx)
    keep = w.columns[w.notna().mean() >= min_coverage]
    w = w[keep].interpolate(limit=max_gap, limit_area="inside")
    return w.dropna()


def pca(x: pd.DataFrame, standardize: bool = True) -> dict:
    """PCA via SVD on demeaned (optionally standardized) columns."""
    z = x - x.mean()
    if standardize:
        z = z / x.std(ddof=1)
    u, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    var = s ** 2 / (len(z) - 1)
    share = var / var.sum()
    loadings = pd.DataFrame(vt.T, index=x.columns, columns=[f"PC{i + 1}" for i in range(len(s))])
    scores = pd.DataFrame(u * s, index=x.index, columns=loadings.columns)
    # sign convention: PC1 loads positively on average, so a higher score = wider (less negative) basis
    for c in loadings.columns:
        if loadings[c].mean() < 0:
            loadings[c] *= -1
            scores[c] *= -1
    return {"share": pd.Series(share, index=loadings.columns), "loadings": loadings, "scores": scores}


def factor_regression(scores: pd.Series, drivers: pd.DataFrame, lags: int = 3) -> pd.DataFrame:
    """Regress a factor score on standardized drivers (Newey-West SEs). One row per specification."""
    import statsmodels.api as sm

    d = pd.concat([scores.rename("pc"), drivers], axis=1).dropna()
    rows = []
    specs = [[c] for c in drivers.columns] + [list(drivers.columns)]
    for cols in specs:
        X = (d[cols] - d[cols].mean()) / d[cols].std(ddof=1)
        r = sm.OLS(d["pc"], sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        for c in cols:
            rows.append({"specification": "all drivers" if len(cols) > 1 else "single driver", "driver": c,
                         "coef_per_1sd": round(r.params[c], 3), "t_nw": round(r.tvalues[c], 2),
                         "r2": round(r.rsquared, 2), "months": int(r.nobs)})
    return pd.DataFrame(rows)
