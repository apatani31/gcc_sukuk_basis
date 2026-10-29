"""Small-cluster inference for the issuer-month regressions.

Only six independent sovereign CDS series exist, so conventional clustered
t-stats overstate precision. The wild cluster bootstrap (restricted, Webb
six-point weights) gives p-values that remain reliable with few clusters
(Webb 2023; Roodman et al. 2019, "boottest").

Implementation: OLS with fixed effects as dummy columns. For the target
coefficient b_k = h'y with h = X (X'X)^-1 e_k, and the CR1 variance is
c * sum_g (sum_{i in g} h_i e_i)^2 with c = G/(G-1) * (N-1)/(N-K). Both are
linear in y, so all bootstrap draws are evaluated with matrix products.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def _design(formula: str, data: pd.DataFrame):
    from patsy import dmatrices

    y, X = dmatrices(formula, data, return_type="dataframe", NA_action="drop")
    return y.iloc[:, 0], X


def wild_cluster_bootstrap(formula: str, data: pd.DataFrame, target: str, cluster: str,
                           B: int = 9999, seed: int = 0, chunk: int = 1000) -> dict:
    """Restricted wild cluster bootstrap-t (Webb weights) for one coefficient.

    Returns the OLS coefficient, its CR1 t-stat, the bootstrap two-sided p-value
    (symmetric, |t*| >= |t|), the t(G-1) p-value for comparison, and G."""
    from scipy import stats

    yv, X = _design(formula, data)
    d = data.loc[yv.index]
    g = pd.factorize(d[cluster])[0]
    G = g.max() + 1
    n, K = X.shape
    Xv, y = X.to_numpy(float), yv.to_numpy(float)
    k = list(X.columns).index(target)
    XtXi = np.linalg.pinv(Xv.T @ Xv)
    h = Xv @ XtXi[:, k]                         # b_k = h'y
    c = G / (G - 1) * (n - 1) / (n - K)

    def t_of(Y):                                # Y: n x m
        b = h @ Y
        E = Y - Xv @ (XtXi @ (Xv.T @ Y))
        S = np.zeros((G, Y.shape[1]))
        np.add.at(S, g, h[:, None] * E)
        return b, b / np.sqrt(c * (S ** 2).sum(axis=0))

    b0, t0 = t_of(y[:, None])
    b0, t0 = float(b0[0]), float(t0[0])
    Xr = np.delete(Xv, k, axis=1)               # restricted model imposes b_k = 0
    yr = Xr @ np.linalg.lstsq(Xr, y, rcond=None)[0]
    er = y - yr
    rng = np.random.default_rng(seed)
    ts = []
    for start in range(0, B, chunk):
        m = min(chunk, B - start)
        W = rng.choice(WEBB, size=(G, m))[g]    # one weight per cluster per draw
        ts.append(t_of(yr[:, None] + er[:, None] * W)[1])
    ts = np.concatenate(ts)
    return {"coef": b0, "t_cr1": t0, "p_wild": float(np.mean(np.abs(ts) >= abs(t0))),
            "p_t_G_minus_1": float(2 * stats.t.sf(abs(t0), G - 1)), "clusters": int(G), "n_obs": int(n)}


def holm(pvalues) -> np.ndarray:
    """Holm step-down adjusted p-values (family-wise error control), in the input order."""
    p = np.asarray(pvalues, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.maximum.accumulate((m - np.arange(m)) * p[order])
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out


def fmt_p(p: float) -> str:
    """p-value for text: '< 0.001' rather than '0.000'."""
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def nw_slope(y: pd.Series, x: pd.Series, lags: int) -> tuple[float, float, int]:
    """OLS slope of y on x with Newey-West t (time series)."""
    import statsmodels.api as sm

    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(d) < 8 or d["x"].std() == 0:
        return np.nan, np.nan, len(d)
    r = sm.OLS(d["y"], sm.add_constant(d["x"])).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(r.params["x"]), float(r.tvalues["x"]), len(d)


def issuer_slopes(p: pd.DataFrame, min_months: int = 12, unit: float = 100.0) -> pd.DataFrame:
    """Issuer-by-issuer basis-on-CDS slopes (per 100bp), levels (NW 6 lags) and monthly changes (NW 3)."""
    rows = []
    for name, d in p.dropna(subset=["basis", "cds"]).groupby("parent_name"):
        if len(d) < min_months:
            continue
        d = d.sort_values("month")
        sl, tl, n = nw_slope(d["basis"], d["cds"], 6)
        consecutive = d["month"].astype("period[M]").astype("int64").diff().eq(1)
        dd = d.assign(db=d["basis"].diff().where(consecutive), dc=d["cds"].diff().where(consecutive))
        sc, tc, nc = nw_slope(dd["db"], dd["dc"], 3)
        rows.append({"issuer": name, "government": d["cds_sovereign"].iloc[0], "months": n,
                     "cds_range_bp": round(d["cds"].max() - d["cds"].min()),
                     "slope_levels_per_100bp": round(sl * unit, 1), "t_nw_levels": round(tl, 2),
                     "slope_changes_per_100bp": round(sc * unit, 1), "t_nw_changes": round(tc, 2)})
    return pd.DataFrame(rows).sort_values("cds_range_bp", ascending=False).reset_index(drop=True)
