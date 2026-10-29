"""Event study of the twin-curve basis and its two legs around oil shocks.

For each shock and each matched sukuk (interpolated matches only):
    event time tau   = business days from the shock date (shock day = 0)
    baseline         = the sukuk's last observation in tau in [-pre, -1]
    change at tau    = value(tau) - baseline, in bp, for
                       basis  (sukuk yield - matched conventional yield),
                       sukuk  (the sukuk's own yield),
                       conv   (the matched conventional yield at the same maturity)
Measuring every change against the bond's own baseline avoids composition
effects when bonds enter or leave the sample inside a window.

Aggregation: bonds -> issuer mean -> shock mean -> mean across shocks, so each
shock counts once (later shocks with 11 issuers do not dominate earlier ones
with 4). Inference uses (a) the cross-shock standard error and (b) a placebo
distribution built from random non-shock dates, which does not rely on
asymptotics with only 9 up / 17 down shocks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TWIN

VARS = {"d_basis": "basis_bp", "d_sukuk": "y_sukuk", "d_conv": "y_conv"}
MDE_MULT = 1.959964 + 0.841621   # z(0.975) + z(0.80): normal-approximation minimum detectable effect


def _event_time(dates: pd.Series, event_date: pd.Timestamp) -> np.ndarray:
    d = dates.values.astype("datetime64[D]")
    e = np.datetime64(event_date.date())
    return np.where(d >= e, np.busday_count(e, d), -np.busday_count(d, e))


def main_matches(obs: pd.DataFrame) -> pd.DataFrame:
    """Keep the matches used in the main twin-curve sample (TWIN["main_methods"])."""
    return obs[obs["match_method"].isin(TWIN["main_methods"])]


def bond_paths(obs: pd.DataFrame, events: pd.DataFrame, pre: int = 5, post: int = 20) -> pd.DataFrame:
    """One row per (event, sukuk, tau) with changes vs the sukuk's pre-shock baseline.

    Only observations matched with the same method as the baseline are kept, so a
    switch between interpolation and adjusted-nearest cannot create a fake jump."""
    obs = main_matches(obs)
    out = []
    for ev in events.itertuples(index=False):
        lo = ev.date - pd.tseries.offsets.BDay(pre + 2)
        hi = ev.date + pd.tseries.offsets.BDay(post + 2)
        w = obs[(obs["date"] >= lo) & (obs["date"] <= hi)].copy()
        if w.empty:
            continue
        w["tau"] = _event_time(w["date"], ev.date)
        w = w[(w["tau"] >= -pre) & (w["tau"] <= post)]
        base = (w[w["tau"] <= -1].sort_values("tau").groupby("instrument_id").last())
        w = w[w["instrument_id"].isin(base.index)]
        w = w[w["match_method"].to_numpy() == w["instrument_id"].map(base["match_method"]).to_numpy()]
        if w.empty:
            continue
        for new, col in VARS.items():
            scale = 1.0 if col == "basis_bp" else 100.0
            w[new] = (w[col] - w["instrument_id"].map(base[col])) * scale
        w["event_id"] = ev.event_id
        out.append(w[["event_id", "parent_key", "parent_name", "sovereign", "instrument_id", "tau",
                      *VARS]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def event_means(paths: pd.DataFrame) -> pd.DataFrame:
    """Bond -> issuer -> event means at each tau."""
    iss = paths.groupby(["event_id", "parent_key", "sovereign", "tau"])[list(VARS)].mean().reset_index()
    ev = iss.groupby(["event_id", "tau"]).agg(**{v: (v, "mean") for v in VARS},
                                               n_issuers=("parent_key", "nunique")).reset_index()
    return ev


def across_events(ev: pd.DataFrame, taus=None) -> pd.DataFrame:
    rows = []
    for tau, g in ev.groupby("tau"):
        if taus is not None and tau not in taus:
            continue
        r = {"tau": tau, "n_shocks": g["event_id"].nunique(), "issuer_shocks": int(g["n_issuers"].sum())}
        for v in VARS:
            x = g[v].dropna().to_numpy()
            m = x.mean() if len(x) else np.nan
            se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
            r.update({f"{v}_mean": m, f"{v}_se": se, f"{v}_t": m / se if se and se > 0 else np.nan,
                      f"{v}_median": np.median(x) if len(x) else np.nan,
                      f"{v}_n_neg": int((x < 0).sum())})
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Pass-through: how much the sukuk leg moves per 1bp of the conventional leg
# ---------------------------------------------------------------------------
def _beta(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.cov(x, y)[0, 1] / np.var(x, ddof=1)) if len(x) > 2 and np.var(x) > 0 else np.nan


def passthrough(paths: pd.DataFrame, obs: pd.DataFrame, shock_dates, horizon: int, exclude_days: int = 40,
                n_boot: int = 2000, seed: int = 3) -> pd.DataFrame:
    """beta of d_sukuk on d_conv at `horizon` days after shocks vs on normal days.

    Shock sample: issuer-level changes at tau = horizon (one per issuer-shock).
    Normal sample: non-overlapping `horizon`-day changes per issuer on days more
    than `exclude_days` calendar days from any shock. Bootstrap resamples
    issuer-shocks and issuer-periods independently for a CI on the difference."""
    rng = np.random.default_rng(seed)
    s = (paths[paths["tau"] == horizon].groupby(["event_id", "parent_key"])[["d_sukuk", "d_conv"]].mean()
         .reset_index())
    s["is2020"] = s["event_id"].str.startswith("2020")
    o = main_matches(obs).sort_values(["instrument_id", "date"]).copy()
    o["dS"] = o.groupby("instrument_id")["y_sukuk"].diff(horizon) * 100
    o["dC"] = o.groupby("instrument_id")["y_conv"].diff(horizon) * 100
    same = o.groupby("instrument_id")["match_method"].shift(horizon) == o["match_method"]
    o.loc[~same, ["dS", "dC"]] = np.nan  # no changes across a matching-method switch
    near = np.zeros(len(o), bool)
    for d in pd.to_datetime(shock_dates):
        near |= ((o["date"] >= d - pd.Timedelta(days=exclude_days // 4))
                 & (o["date"] <= d + pd.Timedelta(days=exclude_days))).to_numpy()
    n = o[~near].dropna(subset=["dS", "dC"]).groupby(["parent_key", "date"])[["dS", "dC"]].mean().reset_index()
    n = n.groupby("parent_key", group_keys=False).apply(lambda g: g.iloc[::horizon])  # non-overlapping
    normal = (n["dC"].to_numpy(), n["dS"].to_numpy())
    rows = []
    for label, g in (("All shocks", s), ("Shocks ex-2020", s[~s["is2020"]]), ("2020 shocks only", s[s["is2020"]])):
        x, y = g["d_conv"].to_numpy(), g["d_sukuk"].to_numpy()
        b_s, b_n = _beta(x, y), _beta(*normal)
        diffs = []
        for _ in range(n_boot):
            i = rng.integers(0, len(x), len(x))
            j = rng.integers(0, len(normal[0]), len(normal[0]))
            diffs.append(_beta(x[i], y[i]) - _beta(normal[0][j], normal[1][j]))
        diffs = np.array(diffs)
        rows.append({"horizon_days": horizon, "sample": label, "n_shock": len(x),
                     "beta_shock": round(b_s, 2), "corr_shock": round(float(np.corrcoef(x, y)[0, 1]), 2),
                     "n_normal": len(normal[0]), "beta_normal": round(b_n, 2),
                     "corr_normal": round(float(np.corrcoef(*normal)[0, 1]), 2),
                     "diff": round(b_s - b_n, 2), "diff_ci90": f"[{np.nanpercentile(diffs, 5):.2f}, "
                                                               f"{np.nanpercentile(diffs, 95):.2f}]"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Placebo
# ---------------------------------------------------------------------------
def oil_vol(market: pd.DataFrame, window: int = 20) -> pd.Series:
    """Trailing realized Brent volatility, known before the day (shifted one day)."""
    b = market["LCOc1"].dropna()
    b = b[b > 0]
    return np.log(b).diff().rolling(window).std().shift(1)


def vol_bins(vol: pd.Series, dates, edges: np.ndarray) -> np.ndarray:
    v = vol.reindex(pd.DatetimeIndex(dates), method="ffill").to_numpy()
    return np.digitize(v, edges)


def placebo_event_means(obs: pd.DataFrame, shock_dates: pd.Series, vol: pd.Series | None = None,
                        edges: np.ndarray | None = None, n_dates: int = 1000, pre: int = 5, post: int = 20,
                        exclude_bdays: int = 25, seed: int = 7) -> pd.DataFrame:
    """Event-level mean paths for random business days away from every shock.

    With vol/edges, each placebo event carries the oil-volatility bin of its
    date, so placebo_test can match shocks to placebo days of similar turbulence
    (shocks cluster in volatile markets, so unmatched calm-day placebos are too
    narrow)."""
    rng = np.random.default_rng(seed)
    o = main_matches(obs)
    cal = pd.bdate_range(o["date"].min() + pd.tseries.offsets.BDay(pre + 2),
                         o["date"].max() - pd.tseries.offsets.BDay(post + 2))
    near = np.zeros(len(cal), bool)
    for d in pd.to_datetime(shock_dates):
        near |= np.abs(np.busday_count(cal.values.astype("datetime64[D]"),
                                       np.datetime64(d.date()))) <= exclude_bdays
    pool = cal[~near]
    dates = pd.DatetimeIndex(rng.choice(pool, size=min(n_dates, len(pool)), replace=False)).sort_values()
    events = pd.DataFrame({"event_id": [f"placebo_{i}" for i in range(len(dates))], "date": dates})
    p = bond_paths(o, events, pre, post)
    if not len(p):
        return pd.DataFrame()
    ev = event_means(p)
    bins = vol_bins(vol, dates, edges) if vol is not None and edges is not None else np.zeros(len(dates), int)
    ev["vol_bin"] = ev["event_id"].map(dict(zip(events["event_id"], bins)))
    return ev


def placebo_test(observed: pd.DataFrame, placebo_ev: pd.DataFrame, shock_bins, var: str,
                 signs=None, n_boot: int = 4000, seed: int = 11, stat: str = "median") -> pd.DataFrame:
    """Volatility-matched bootstrap: for each shock, draw a placebo event from the
    same oil-volatility bin; summarize over shocks with `stat` (median by
    default, so one extreme shock such as March 2020 cannot drive the test),
    flipping sign where `signs` is -1. Returns the 90% band and a two-sided p."""
    rng = np.random.default_rng(seed)
    shock_bins = np.asarray(shock_bins)
    signs = np.ones(len(shock_bins)) if signs is None else np.asarray(signs, float)
    rows = []
    for tau, g in placebo_ev.groupby("tau"):
        g = g.dropna(subset=[var])
        by_bin = {b: gg[var].to_numpy() for b, gg in g.groupby("vol_bin")}
        if len(shock_bins) == 0 or any(len(by_bin.get(b, [])) < 3 for b in shock_bins):
            continue
        draws = np.column_stack([rng.choice(by_bin[b], size=n_boot) * s for b, s in zip(shock_bins, signs)])
        sims = np.median(draws, axis=1) if stat == "median" else draws.mean(axis=1)
        obs = observed.loc[observed["tau"] == tau, f"{var}_{stat}"]
        o = float(obs.iloc[0]) if len(obs) else np.nan
        centred = sims - sims.mean()
        p = float((np.abs(centred) >= abs(o - sims.mean())).mean()) if not np.isnan(o) else np.nan
        sd = float(sims.std(ddof=1))
        rows.append({"tau": tau, f"{var}_p05": np.percentile(sims, 5), f"{var}_p95": np.percentile(sims, 95),
                     f"{var}_placebo_p": p, f"{var}_placebo_sd": sd,
                     # smallest true effect detected with 80% power by a two-sided 5% test on this statistic
                     f"{var}_mde80": MDE_MULT * sd})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Episodes (linked opposite-sign shocks)
# ---------------------------------------------------------------------------
def build_episodes(shocks: pd.DataFrame, link_bdays: int = 20) -> pd.DataFrame:
    """Chain shocks less than link_bdays apart into episodes (singletons stay alone)."""
    s = shocks.sort_values("date").reset_index(drop=True)
    d = s["date"].values.astype("datetime64[D]")
    gap = np.r_[np.inf, np.busday_count(d[:-1], d[1:])]
    s["episode"] = np.cumsum(gap > link_bdays)
    return s


def episode_changes(obs: pd.DataFrame, episodes: pd.DataFrame, market: pd.DataFrame | None,
                    pre: int = 5, post: int = 20) -> pd.DataFrame:
    """Net change from before the first shock to post days after the last, per multi-shock episode."""
    o = main_matches(obs)
    rows = []
    for ep, g in episodes.groupby("episode"):
        if len(g) < 2:
            continue
        first, last = g["date"].min(), g["date"].max()
        start = first - pd.tseries.offsets.BDay(pre)
        end = last + pd.tseries.offsets.BDay(post)
        w = o[(o["date"] >= start) & (o["date"] <= end)]
        before = w[w["date"] < first].sort_values("date").groupby("instrument_id").last()
        after = w[w["date"] > last].sort_values("date").groupby("instrument_id").last()
        ids = before.index.intersection(after.index)
        if not len(ids):
            continue
        ch = pd.DataFrame({"parent_key": before.loc[ids, "parent_key"],
                           "d_basis": after.loc[ids, "basis_bp"] - before.loc[ids, "basis_bp"],
                           "d_sukuk": (after.loc[ids, "y_sukuk"] - before.loc[ids, "y_sukuk"]) * 100,
                           "d_conv": (after.loc[ids, "y_conv"] - before.loc[ids, "y_conv"]) * 100})
        iss = ch.groupby("parent_key").mean()
        brent = np.nan
        if market is not None:
            b = market["LCOc1"].dropna()
            b0, b1 = b[b.index < first], b[b.index <= end]
            if len(b0) and len(b1):
                brent = 100 * (b1.iloc[-1] / b0.iloc[-1] - 1)
        rows.append({"episode": f"{first:%Y-%m-%d} to {last:%Y-%m-%d}",
                     "shocks": " ".join(f"{d:%d%b}{'+' if s == 'up' else '-'}" for d, s in zip(g["date"], g["sign"])),
                     "brent_net_pct": round(brent, 1), "issuers": len(iss),
                     "d_basis_bp": round(iss["d_basis"].mean(), 1), "d_sukuk_bp": round(iss["d_sukuk"].mean(), 1),
                     "d_conv_bp": round(iss["d_conv"].mean(), 1),
                     "issuers_basis_down": int((iss["d_basis"] < 0).sum())})
    return pd.DataFrame(rows)
