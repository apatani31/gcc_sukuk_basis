"""Rule-based oil shock definition, applied mechanically to daily Brent.

Rule (parameters in config.SHOCK):
    r_t      = log(Brent_t / Brent_{t-h})                 h = horizon_days
    e_t      = r_t - beta_t * spx_t                       beta_t = rolling OLS beta, lagged
    z_t      = e_t / sd(e over the previous vol_window days)
    trigger  = |z_t| >= z  AND  |r_t| >= min_abs_ret_pct   (unusual AND economically large)
    episodes = per sign, greedy: keep the largest |z|, then the next largest
               that is > cluster_days trading days from every kept same-sign
               shock; shocks with an opposite-sign shock inside their window
               are flagged (opposite_shock_within_window)

Vol scaling makes "a big move" mean the same thing in calm and turbulent years
(a 5% day in 2019 is rarer than a 5% day in 2022). Netting out the S&P keeps
global risk-off days from counting as oil shocks.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MARKET_RICS, SHOCK

log = logging.getLogger(__name__)


def pull_market(out_path: Path, start: str = "2012-01-01", end: str | None = None) -> pd.DataFrame:
    """Daily close for MARKET_RICS via ld.get_history (needs an open session)."""
    from .session import call_api, ld

    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    cols = {}
    for ric, fld in MARKET_RICS.items():
        frames = []
        for a, b in _year_chunks(start, end, 7):
            h = call_api(ld.get_history, ric, fields=[fld], interval="daily", start=a, end=b)
            if h is not None and fld in h:
                frames.append(h[fld])
        s = pd.concat(frames)
        cols[ric] = pd.to_numeric(s[~s.index.duplicated()], errors="coerce")
        log.info("Market %s: %d days", ric, len(cols[ric]))
    df = pd.DataFrame(cols)
    df.index.name = "date"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return df


def _year_chunks(start: str, end: str, years: int):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    while s <= e:
        z = min(s + pd.DateOffset(years=years) - pd.Timedelta(days=1), e)
        yield s.strftime("%Y-%m-%d"), z.strftime("%Y-%m-%d")
        s = z + pd.Timedelta(days=1)


def shock_scores(market: pd.DataFrame, cfg: dict = SHOCK) -> pd.DataFrame:
    """Daily oil return, equity-netted return and z-score on the oil trading calendar."""
    oil = market[cfg["oil_ric"]].dropna()
    oil = oil[oil > 0]
    h, w = cfg["horizon_days"], cfg["vol_window"]
    r = np.log(oil).diff(h)
    eq = np.log(market[cfg["equity_ric"]].ffill()).reindex(oil.index).diff(h).fillna(0.0)
    if cfg["net_of_equity"]:
        beta = (r.rolling(w).cov(eq) / eq.rolling(w).var()).shift(h)
        e = r - beta * eq
    else:
        beta = pd.Series(np.nan, index=r.index)
        e = r
    sd = e.rolling(w).std().shift(h)  # history strictly before the shock window
    return pd.DataFrame({"brent": oil, "ret": r, "equity_ret": eq, "beta": beta,
                         "oil_specific_ret": e, "z": e / sd})


def detect_shocks(scores: pd.DataFrame, cfg: dict = SHOCK) -> pd.DataFrame:
    s = scores.loc[cfg["start"]:].dropna(subset=["z"])
    big = s["ret"].abs() >= cfg.get("min_abs_ret_pct", 0.0) / 100
    trig = s.index[(s["z"].abs() >= cfg["z"]) & big]
    if len(trig) == 0:
        return pd.DataFrame(columns=["date", "sign", "z", "ret_pct", "equity_ret_pct", "brent", "n_trigger_days"])
    # Greedy, non-chaining selection, run separately for up and down moves:
    # largest |z| first, then any same-sign trigger more than cluster_days
    # trading days from every same-sign shock already kept. Merging "triggers
    # within N days of each other" would chain turbulent spells into one long
    # episode; mixing signs would date a spike-then-crash at whichever leg was
    # bigger. Up and down are different events (disruption vs reversal).
    pos = pd.Series(s.index.get_indexer(trig), index=trig)
    zt = s.loc[trig, "z"]
    kept: list[pd.Timestamp] = []
    for sign_mask in (zt > 0, zt < 0):
        chosen: list[pd.Timestamp] = []
        for d in zt[sign_mask].abs().sort_values(ascending=False).index:
            if all(abs(pos[d] - pos[k]) > cfg["cluster_days"] for k in chosen):
                chosen.append(d)
        kept += chosen
    kept = sorted(kept)
    rows = []
    for best in kept:
        r = s.loc[best]
        same = np.sign(zt) == np.sign(r["z"])
        near = (pos - pos[best]).abs().to_numpy() <= cfg["cluster_days"]
        opposite = [k for k in kept if np.sign(s.loc[k, "z"]) != np.sign(r["z"])
                    and abs(pos[k] - pos[best]) <= cfg["cluster_days"]]
        rows.append({"date": best, "sign": "up" if r["z"] > 0 else "down", "z": round(r["z"], 2),
                     "ret_pct": round(100 * r["ret"], 2), "equity_ret_pct": round(100 * r["equity_ret"], 2),
                     "brent": round(r["brent"], 2), "n_trigger_days": int((same.to_numpy() & near).sum()),
                     "opposite_shock_within_window": bool(opposite),
                     "opposite_shock_dates": "; ".join(f"{k:%Y-%m-%d}" for k in opposite)})
    return pd.DataFrame(rows)


def add_coverage(shocks: pd.DataFrame, issuer_daily: pd.DataFrame, pre: int = 5, post: int = 20,
                 min_days: int = 15) -> pd.DataFrame:
    """How many twin-curve issuers have usable basis data around each shock."""
    out = shocks.copy()
    names = []
    for d in out["date"]:
        w = issuer_daily[(issuer_daily["date"] >= d - pd.tseries.offsets.BDay(pre + 5))
                         & (issuer_daily["date"] <= d + pd.tseries.offsets.BDay(post))]
        n = w.groupby("parent_name")["date"].nunique()
        names.append(sorted(n[n >= min_days].index))
    out["issuers_covered"] = [len(n) for n in names]
    out["issuer_names"] = ["; ".join(n) for n in names]
    return out
