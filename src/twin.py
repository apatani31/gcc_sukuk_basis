"""Within-issuer twin-curve comparison: sukuk vs conventional yields of the same
issuer on the same day, matched on remaining maturity.

Method (all yields are LSEG mid yields to maturity, in percent):

A. Sukuk-level basis (primary). For each sukuk on each date, the issuer's
   conventional yields that day form a curve in remaining maturity (tau).
   basis = y_sukuk - y_conv(tau_sukuk), where y_conv is linearly interpolated
   between the two conventional bonds bracketing tau_sukuk (no extrapolation).
   When no bracket exists, the nearest conventional bond within
   TWIN["nearest_max_gap"] years is used, shifted along the US Treasury curve
   to the sukuk's maturity: y_conv = y_near + UST(tau_sukuk) - UST(tau_near)
   (match_method="nearest_adj"; "nearest" if no UST curve is available).
   validate_nearest() measures the error of this rule on interpolated cases.
B. Standard-tenor gap (robustness). Both curves are interpolated at 3/5/7/10y
   when each brackets that tenor; gap = y_sukuk_curve - y_conv_curve.

Negative basis = sukuk yield below the issuer's own conventional curve
(sukuk trade rich); positive = sukuk premium.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SOVEREIGNS, TWIN

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------
def load_panel(universe: pd.DataFrame, timeseries_dir: Path, cfg: dict = TWIN) -> pd.DataFrame:
    """Clean daily yield panel for fixed-rate bonds of issuers with both types."""
    bonds = universe[
        (universe["instrument_class"] == "bond") & universe["is_primary_line"]
        & ~universe["possible_sukuk_mislabel"]
        & universe["coupon_type"].isin(cfg["coupon_types"])
        & universe["maturity_date"].notna()
        & (universe["amount_issued_usd"].fillna(0) >= cfg["min_amount_usd"])
        & universe["parent_key"].notna()
    ]
    bonds = bonds[~bonds["parent_key"].isin(cfg.get("exclude_parents", []))]
    both = bonds.groupby("parent_key")["is_sukuk"].agg(["any", "all"])
    keys = both[both["any"] & ~both["all"]].index
    bonds = bonds[bonds["parent_key"].isin(keys)]
    log.info("Twin universe: %d bonds (%d sukuk) across %d issuers with both types",
             len(bonds), int(bonds.is_sukuk.sum()), len(keys))

    fields = ["mid_yield", "bid_yield", "ask_yield", "mid_price"]
    # filter inside pyarrow (fields AND instruments): loading the whole dataset can exhaust memory
    ts = pd.read_parquet(timeseries_dir, columns=["date", "instrument_id", "field", "value"],
                         filters=[("field", "in", fields), ("instrument_id", "in", list(bonds["instrument_id"]))])
    w = ts.pivot_table(index=["instrument_id", "date"], columns="field", values="value",
                       aggfunc="first").reset_index()
    for f in fields:
        if f not in w:
            w[f] = np.nan
    w[fields] = w[fields].astype(float)
    w["y"] = w["mid_yield"].fillna((w["bid_yield"] + w["ask_yield"]) / 2)
    w = w.merge(bonds[["instrument_id", "isin", "parent_key", "parent_name", "is_sukuk", "maturity_date",
                       "issuer_name", "country_of_risk", "amount_issued_usd"]], on="instrument_id")
    w["tau"] = (w["maturity_date"] - w["date"]).dt.days / 365.25
    return clean_panel(w, cfg)


def clean_panel(w: pd.DataFrame, cfg: dict = TWIN) -> pd.DataFrame:
    n0 = len(w)
    steps = {}
    lo, hi = cfg["yield_bounds"]
    w = w[w["y"].between(lo, hi, inclusive="neither")]
    steps["yield_bounds"] = n0 - len(w)
    n = len(w)
    w = w[w["tau"].between(cfg["min_tau"], cfg["max_tau"])]
    steps["tau_range"] = n - len(w)

    w = w.sort_values(["instrument_id", "date"]).copy()
    g = w.groupby("instrument_id")
    med = g["y"].transform(lambda s: s.rolling(21, min_periods=5, center=True).median())
    n = len(w)
    w = w[(w["y"] - med).abs().fillna(0) <= cfg["outlier_pp"]]
    steps["outliers"] = n - len(w)

    g = w.groupby("instrument_id")["mid_price"]
    same = g.diff().eq(0)
    stale_share = same.groupby(w["instrument_id"]).transform("mean")
    run = same.groupby((~same).cumsum()).cumsum()  # consecutive unchanged days
    n = len(w)
    w = w[(stale_share <= cfg["max_stale_share"]) & (run < cfg["stale_run_days"] - 1)]
    steps["stale"] = n - len(w)
    log.info("Panel cleaning dropped %s of %d obs -> %d", steps, n0, len(w))
    w.attrs["cleaning"] = {"input_obs": n0, **steps, "kept_obs": len(w)}
    return w.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tenor matching
# ---------------------------------------------------------------------------
def _curve(tau: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sort by tenor and average bonds with identical tenor."""
    t, inv = np.unique(np.round(tau, 6), return_inverse=True)
    if len(t) == len(tau):
        return t, y[np.argsort(np.round(tau, 6), kind="stable")]
    return t, np.bincount(inv, weights=y) / np.bincount(inv)


class UstCurve:
    """Daily US Treasury yield curve (percent), linearly interpolated in maturity."""

    def __init__(self, path: Path):
        self.df = pd.read_parquet(path).astype(float).sort_index()
        self.tenors = np.array(self.df.columns, float)
        self._cache: dict = {}

    def row(self, date) -> tuple[np.ndarray, np.ndarray] | None:
        if date not in self._cache:
            r = self.df.loc[:date].tail(1)
            if r.empty:
                self._cache[date] = None
            else:
                v = r.to_numpy(float)[0]
                ok = ~np.isnan(v)
                self._cache[date] = (self.tenors[ok], v[ok]) if ok.sum() >= 2 else None
        return self._cache[date]

    def slope_fn(self, date):
        """f(tau_to, tau_from) = UST(tau_to) - UST(tau_from) on `date`, or None."""
        r = self.row(date)
        if r is None:
            return None
        t, y = r
        return lambda a, b: float(np.interp(a, t, y) - np.interp(b, t, y))


def match_day(s_tau: np.ndarray, s_y: np.ndarray, c_tau: np.ndarray, c_y: np.ndarray,
              cfg: dict = TWIN, ust_slope=None) -> list[tuple]:
    """Match each sukuk (tau, y) to the issuer's conventional curve on one date.

    Returns (sukuk_index, y_conv, method, bracket_lo, bracket_hi, n_conv) tuples.
    ust_slope(a, b) = UST(a) - UST(b) shifts nearest matches to the sukuk's maturity."""
    ct, cy = _curve(c_tau, c_y)
    out = []
    for i, (tau, _) in enumerate(zip(s_tau, s_y)):
        if len(ct) >= 2 and ct[0] <= tau <= ct[-1]:
            j = min(max(int(np.searchsorted(ct, tau)), 1), len(ct) - 1)
            out.append((i, float(np.interp(tau, ct, cy)), "interp", ct[j - 1], ct[j], len(ct)))
        else:
            k = int(np.argmin(np.abs(ct - tau)))
            if abs(ct[k] - tau) <= cfg["nearest_max_gap"]:
                if ust_slope is not None:
                    out.append((i, float(cy[k]) + ust_slope(tau, ct[k]), "nearest_adj", ct[k], ct[k], len(ct)))
                else:
                    out.append((i, float(cy[k]), "nearest", ct[k], ct[k], len(ct)))
    return out


def _issuer_days(panel: pd.DataFrame):
    """Yield (parent_key, date, sukuk rows, conv rows) using positional slices (fast)."""
    p = panel.sort_values(["parent_key", "date"]).reset_index(drop=True)
    keys = p["parent_key"].to_numpy()
    dates = p["date"].to_numpy()
    brk = np.flatnonzero((keys[1:] != keys[:-1]) | (dates[1:] != dates[:-1])) + 1
    starts = np.r_[0, brk]
    ends = np.r_[brk, len(p)]
    suk = p["is_sukuk"].to_numpy()
    for a, z in zip(starts, ends):
        sk = suk[a:z]
        if sk.any() and (~sk).any():
            idx = np.arange(a, z)
            yield p, keys[a], dates[a], idx[sk], idx[~sk]


def _load_ust(cfg: dict) -> UstCurve | None:
    path = cfg.get("ust_curve_path")
    if path is not None and Path(path).exists():
        return UstCurve(Path(path))
    log.warning("No US Treasury curve at %s: nearest matches are NOT slope-adjusted", path)
    return None


def sukuk_basis(panel: pd.DataFrame, cfg: dict = TWIN, ust: UstCurve | None = None) -> pd.DataFrame:
    ust = ust if ust is not None else _load_ust(cfg)
    out = []
    tau = y = iid = None
    for p, key, date, si, ci in _issuer_days(panel):
        if tau is None:
            tau, y, iid = p["tau"].to_numpy(), p["y"].to_numpy(), p["instrument_id"].to_numpy()
        slope = ust.slope_fn(date) if ust is not None else None
        for i, yc, method, lo, hi, nc in match_day(tau[si], y[si], tau[ci], y[ci], cfg, slope):
            r = si[i]
            out.append({"parent_key": key, "date": date, "instrument_id": iid[r], "tau": tau[r],
                        "y_sukuk": y[r], "y_conv": yc, "match_method": method,
                        "bracket_lo": lo, "bracket_hi": hi, "n_conv": nc,
                        "basis_bp": (y[r] - yc) * 100})
    b = pd.DataFrame(out)
    if b.empty:
        return b
    b["bracket_width"] = b["bracket_hi"] - b["bracket_lo"]
    meta = panel.drop_duplicates("instrument_id").set_index("instrument_id")
    b["isin"] = b["instrument_id"].map(meta["isin"])
    b["parent_name"] = b["parent_key"].map(panel.drop_duplicates("parent_key").set_index("parent_key")["parent_name"])
    b["country"] = b["instrument_id"].map(meta["country_of_risk"])
    b["sovereign"] = b["parent_key"].isin([k for v in SOVEREIGNS.values() for k in v])
    log.info("Sukuk-level basis: %d obs (%s)", len(b), b["match_method"].value_counts().to_dict())
    return b.sort_values(["parent_key", "date", "tau"]).reset_index(drop=True)


def validate_nearest(panel: pd.DataFrame, basis: pd.DataFrame, cfg: dict = TWIN,
                     ust: UstCurve | None = None) -> pd.DataFrame:
    """Error of nearest-bond matching, raw and UST-adjusted, on sukuk-days where
    interpolation is possible (interpolated yield = benchmark). Reports daily
    error, the persistent per-bond error (what biases an issuer's mean basis),
    and the error in 5/20-day changes (what the event study uses)."""
    ust = ust if ust is not None else _load_ust(cfg)
    b = basis[basis["match_method"] == "interp"]
    conv = panel[~panel["is_sukuk"]][["parent_key", "date", "tau", "y"]]
    m = b.merge(conv, on=["parent_key", "date"], suffixes=("", "_c"))
    m["gap"] = (m["tau_c"] - m["tau"]).abs()
    m = m.sort_values("gap").drop_duplicates(["instrument_id", "date"])
    if ust is not None:
        m["ust_shift"] = [(f(t, tc) if (f := ust.slope_fn(d)) else np.nan)
                          for d, t, tc in zip(m["date"], m["tau"], m["tau_c"])]
    else:
        m["ust_shift"] = np.nan
    m["raw_err"] = (m["y"] - m["y_conv"]) * 100
    m["adj_err"] = (m["y"] + m["ust_shift"] - m["y_conv"]) * 100
    m["gap_bin"] = pd.cut(m["gap"], [0, 0.25, 0.5, 1, 2, 5], labels=["<3m", "3-6m", "6-12m", "1-2y", "2-5y"])
    m = m.sort_values(["instrument_id", "date"])
    rows = []
    for gb, g in m.groupby("gap_bin", observed=True):
        per = g.groupby("instrument_id").filter(lambda x: len(x) >= 50).groupby("instrument_id")
        ch = {h: g.groupby("instrument_id")["adj_err"].diff(h).abs() for h in (5, 20)}
        rows.append({"gap": gb, "sukuk_days": len(g),
                     "raw_bias_bp": round(g["raw_err"].mean(), 1), "raw_mae_bp": round(g["raw_err"].abs().mean(), 1),
                     "adj_bias_bp": round(g["adj_err"].mean(), 1), "adj_mae_bp": round(g["adj_err"].abs().mean(), 1),
                     "adj_p90_bp": round(g["adj_err"].abs().quantile(.9), 1),
                     "bonds_50d": per.ngroups,
                     "adj_persistent_median_bp": round(per["adj_err"].mean().abs().median(), 1) if per.ngroups else np.nan,
                     "adj_persistent_p90_bp": round(per["adj_err"].mean().abs().quantile(.9), 1) if per.ngroups else np.nan,
                     "adj_err_5d_change_median_bp": round(ch[5].median(), 1),
                     "adj_err_20d_change_median_bp": round(ch[20].median(), 1)})
    return pd.DataFrame(rows)


def tenor_gaps(panel: pd.DataFrame, cfg: dict = TWIN) -> pd.DataFrame:
    rows = []
    tenors = np.array(cfg["std_tenors"], float)
    tau = y = None
    for p, key, date, si, ci in _issuer_days(panel):
        if len(si) < 2 or len(ci) < 2:
            continue
        if tau is None:
            tau, y = p["tau"].to_numpy(), p["y"].to_numpy()
        st, sy = _curve(tau[si], y[si])
        ct, cy = _curve(tau[ci], y[ci])
        if len(st) < 2 or len(ct) < 2:
            continue
        for t in tenors:
            if st[0] <= t <= st[-1] and ct[0] <= t <= ct[-1]:
                ys, yc = np.interp(t, st, sy), np.interp(t, ct, cy)
                rows.append({"parent_key": key, "date": date, "tenor": int(t), "y_sukuk": ys,
                             "y_conv": yc, "gap_bp": (ys - yc) * 100})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def newey_west_mean(x: np.ndarray, lags: int) -> tuple[float, float]:
    """Mean and its Newey-West (Bartlett kernel) standard error."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return (float(x.mean()) if n else np.nan), np.nan
    e = x - x.mean()
    lags = min(lags, n - 1)
    var = e @ e / n
    for L in range(1, lags + 1):
        var += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean()), float(np.sqrt(max(var, 0) / n))


def issuer_daily(b: pd.DataFrame, methods=None) -> pd.DataFrame:
    """Issuer-day mean basis using `methods` (default TWIN["main_methods"]; "all" = every match)."""
    methods = TWIN["main_methods"] if methods is None else methods
    methods = [methods] if isinstance(methods, str) and methods != "all" else methods
    d = b if methods == "all" else b[b["match_method"].isin(methods)]
    return (d.groupby(["parent_key", "parent_name", "sovereign", "country", "date"])
             .agg(basis_bp=("basis_bp", "mean"), n_sukuk=("instrument_id", "nunique"),
                  mean_tau=("tau", "mean"))
             .reset_index())


def issuer_stats(daily: pd.DataFrame, b: pd.DataFrame, cfg: dict = TWIN) -> pd.DataFrame:
    rows = []
    for (key, name, sov, country), g in daily.groupby(["parent_key", "parent_name", "sovereign", "country"]):
        if len(g) < cfg["min_issuer_days"]:
            continue
        g = g.sort_values("date")
        m, se = newey_west_mean(g["basis_bp"].to_numpy(), cfg["nw_lags"])
        sub = b[(b.parent_key == key) & b.match_method.isin(cfg.get("main_methods", ["interp"]))
                & b.date.isin(g["date"])]
        rows.append({
            "issuer": name, "country": country, "sovereign": sov,
            "first_date": g["date"].min().date(), "last_date": g["date"].max().date(),
            "days": len(g), "sukuk_bonds": sub["instrument_id"].nunique(),
            "mean_basis_bp": round(m, 1), "nw_se_bp": round(se, 1),
            "nw_t": round(m / se, 2) if se and se > 0 else np.nan,
            "median_basis_bp": round(g["basis_bp"].median(), 1),
            "p25_bp": round(g["basis_bp"].quantile(.25), 1), "p75_bp": round(g["basis_bp"].quantile(.75), 1),
            "share_negative_days": round((g["basis_bp"] < 0).mean(), 2),
            "median_bracket_width_y": round(sub.loc[sub.match_method == "interp", "bracket_width"].median(), 1),
            "share_nearest_adj": round((sub["match_method"] == "nearest_adj").mean(), 2),
        })
    return pd.DataFrame(rows).sort_values("days", ascending=False).reset_index(drop=True)


def cross_issuer(stats: pd.DataFrame) -> dict:
    """Treat each issuer's mean as one observation (avoids KSA/Bahrain dominating)."""
    x = stats["mean_basis_bp"].to_numpy(float)
    n = len(x)
    if n < 2:
        return {"issuers": n}
    se = x.std(ddof=1) / np.sqrt(n)
    return {"issuers": n, "mean_of_issuer_means_bp": round(x.mean(), 1), "se_bp": round(se, 1),
            "t": round(x.mean() / se, 2), "median_of_issuer_means_bp": round(float(np.median(x)), 1),
            "issuers_negative": int((x < 0).sum())}
