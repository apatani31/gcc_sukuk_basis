"""Secondary-market data quality and a primary-market check (NEXT_PROMPT task 7).

a. Staleness: unchanged mid prices, bid-ask (price cents), AR(1) of daily
   yield changes and price source, sukuk vs conventional, twin issuers, 2019+.
b. Lead-lag: daily sukuk yield change on same-day and lagged (1-5) matched
   conventional changes; pass-through at 60 and 120 business days.
c. Reversal: monthly basis change on CDS change and its lags 1-6. If the CDS
   effect were a slow-updating-quote artefact, the lags would undo it.
d. Primary market: yield at issue minus the issuer's conventional curve
   (same matching rules as twin.py) 5 business days before the issue date,
   for new sukuk and for new conventional bonds; the difference is the sukuk
   new-issue premium relative to conventional.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from .config import TWIN
from .twin import UstCurve, match_day


# ---------------------------------------------------------------------------
# a. Staleness
# ---------------------------------------------------------------------------
def read_series(timeseries_dir, ids, fields, start: str) -> pd.DataFrame:
    """Read selected instruments/fields/dates with pyarrow filters (never the whole dataset)."""
    dset = ds.dataset(str(timeseries_dir), format="parquet", partitioning="hive")
    f = (ds.field("instrument_id").isin(list(ids)) & ds.field("field").isin(fields)
         & (ds.field("date") >= pd.Timestamp(start)))
    return dset.to_table(columns=["date", "instrument_id", "field", "value"], filter=f).to_pandas()


def staleness(timeseries_dir, bonds: pd.DataFrame, coverage: pd.DataFrame, start: str = "2019-01-01",
              min_days: int = 100) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = bonds["instrument_id"].tolist()
    t = read_series(timeseries_dir, ids, ["mid_price", "bid_price", "ask_price", "mid_yield", "bid_yield",
                                          "ask_yield"], start)
    w = t.pivot_table(index=["instrument_id", "date"], columns="field", values="value", aggfunc="first")
    w = w.reset_index().sort_values(["instrument_id", "date"])
    for c in ("mid_price", "bid_price", "ask_price", "mid_yield", "bid_yield", "ask_yield"):
        if c not in w:
            w[c] = np.nan
    w[["mid_price", "bid_price", "ask_price", "mid_yield", "bid_yield", "ask_yield"]] = \
        w[["mid_price", "bid_price", "ask_price", "mid_yield", "bid_yield", "ask_yield"]].astype(float)
    w["mid"] = w["mid_price"].fillna((w["bid_price"] + w["ask_price"]) / 2)
    w["y"] = w["mid_yield"].fillna((w["bid_yield"] + w["ask_yield"]) / 2)
    rows = []
    for k, b in w.groupby("instrument_id"):
        if len(b) < min_days:
            continue
        dy = b["y"].diff()
        rows.append({"instrument_id": k, "days": len(b), "unchanged_mid_share": b["mid"].diff().eq(0).mean(),
                     "bid_ask_cents_median": ((b["ask_price"] - b["bid_price"]) * 100).median(),
                     "ar1_daily_yield_change": dy.autocorr(), "abs_daily_yield_change_bp_median": (dy.abs() * 100).median()})
    r = pd.DataFrame(rows).merge(bonds[["instrument_id", "is_sukuk", "parent_name"]], on="instrument_id")
    src = coverage.set_index("instrument_id")["price_ric"]
    r["price_source"] = np.where(r["instrument_id"].map(src).fillna("").str.endswith("=TE"), "Tradeweb =TE",
                                 "Composite / other")
    r["group"] = r["is_sukuk"].map({True: "Sukuk", False: "Conventional"})
    summ = (r.groupby("group").agg(bonds=("instrument_id", "size"), unchanged_mid_share=("unchanged_mid_share", "median"),
                                   bid_ask_cents=("bid_ask_cents_median", "median"),
                                   ar1_yield_change=("ar1_daily_yield_change", "median"),
                                   abs_daily_change_bp=("abs_daily_yield_change_bp_median", "median"),
                                   tradeweb_share=("price_source", lambda s: (s == "Tradeweb =TE").mean()))
            .round(3).reset_index())
    return summ, r


# ---------------------------------------------------------------------------
# b. Lead-lag
# ---------------------------------------------------------------------------
def lead_lag(basis: pd.DataFrame, groups: dict, max_lag: int = 5) -> pd.DataFrame:
    import statsmodels.formula.api as smf

    t = basis[basis["match_method"].isin(TWIN["main_methods"])].sort_values(["instrument_id", "date"]).copy()
    g = t.groupby("instrument_id")
    t["ds"] = g["y_sukuk"].diff() * 100
    t["dc"] = g["y_conv"].diff() * 100
    t["gap_days"] = g["date"].diff().dt.days
    t["same_method"] = g["match_method"].shift(1) == t["match_method"]
    lags = [f"dc_l{L}" for L in range(1, max_lag + 1)]
    for L in range(1, max_lag + 1):
        t[f"dc_l{L}"] = t.groupby("instrument_id")["dc"].shift(L)
    d = t[(t["gap_days"] <= 4) & t["same_method"]].dropna(subset=["ds", "dc"] + lags)
    d = d[(d["ds"].abs() < 100) & (d["dc"].abs() < 100)]
    rows = []
    for name, mask in groups.items():
        dd = d[mask(d)]
        if len(dd) < 100:
            continue
        m = smf.ols("ds ~ dc + " + " + ".join(lags), dd).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(dd["date"].dt.to_period("M"))[0]})
        R = np.zeros(len(m.params))
        R[[list(m.params.index).index(x) for x in lags]] = 1
        s = float(R @ m.params.values)
        se = float(np.sqrt(R @ m.cov_params().values @ R))
        rows.append({"group": name, "obs": len(dd), "same_day": round(m.params["dc"], 3),
                     "same_day_t": round(m.tvalues["dc"], 1), "lags_1_5_sum": round(s, 3), "lags_t": round(s / se, 1),
                     "total": round(m.params["dc"] + s, 3)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# c. Reversal
# ---------------------------------------------------------------------------
def reversal(panel: pd.DataFrame, issuers: dict, max_lag: int = 6) -> pd.DataFrame:
    import statsmodels.formula.api as smf

    p = panel.dropna(subset=["basis", "cds"]).sort_values(["parent_key", "month"]).copy()
    mi = pd.PeriodIndex(p["month"], freq="M").astype("int64")
    ok = pd.Series(mi, index=p.index).groupby(p["parent_key"]).diff().eq(1)
    p["db"] = p.groupby("parent_key")["basis"].diff().where(ok)
    p["dcds"] = p.groupby("parent_key")["cds"].diff().where(ok) / 100
    cl = [f"c{L}" for L in range(1, max_lag + 1)]
    for L in range(1, max_lag + 1):
        p[f"c{L}"] = p.groupby("parent_key")["dcds"].shift(L)
    q = p.dropna(subset=["db", "dcds"] + cl)
    rows = []
    for name, mask in issuers.items():
        dd = q[mask(q)]
        if len(dd) < 24:
            continue
        m = smf.ols("db ~ dcds + " + " + ".join(cl), dd).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
        R = np.zeros(len(m.params))
        R[[list(m.params.index).index(c) for c in cl]] = 1
        s = float(R @ m.params.values)
        se = float(np.sqrt(R @ m.cov_params().values @ R))
        rows.append({"sample": name, "months": len(dd), "same_month_per_100bp": round(m.params["dcds"], 1),
                     "t_same": round(m.tvalues["dcds"], 2), "lags_1_6_sum": round(s, 1), "t_lags": round(s / se, 2),
                     "net_per_100bp": round(m.params["dcds"] + s, 1),
                     "share_reversed": round(-s / m.params["dcds"], 2) if m.params["dcds"] else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# d. Primary market
# ---------------------------------------------------------------------------
def new_issue_premia(universe: pd.DataFrame, panel: pd.DataFrame, keys, ust: UstCurve | None,
                     lead_bdays: int = 5, search_bdays: int = 10, start: str = "2016-01-01") -> pd.DataFrame:
    """Yield at issue minus the issuer's conventional curve `lead_bdays` before issue (same rules as twin.py).

    The curve uses only conventional bonds already trading on that day (so a new conventional bond is
    compared with the issuer's *other* conventional bonds)."""
    u = universe[(universe["instrument_class"] == "bond") & universe["is_primary_line"]
                 & ~universe["possible_sukuk_mislabel"] & universe["parent_key"].isin(keys)
                 & universe["coupon_type"].isin(TWIN["coupon_types"]) & universe["maturity_date"].notna()
                 & universe["yield_at_issue"].notna() & (universe["issue_date"] >= pd.Timestamp(start))
                 & (universe["amount_issued_usd"].fillna(0) >= TWIN["min_amount_usd"])]
    conv = panel[~panel["is_sukuk"]][["parent_key", "instrument_id", "date", "tau", "y"]]
    rows = []
    for b in u.itertuples():
        ref = b.issue_date - pd.tseries.offsets.BDay(lead_bdays)
        lo = ref - pd.tseries.offsets.BDay(search_bdays)
        c = conv[(conv["parent_key"] == b.parent_key) & (conv["date"] <= ref) & (conv["date"] >= lo)
                 & (conv["instrument_id"] != b.instrument_id)]
        rec = {"instrument_id": b.instrument_id, "isin": b.isin, "parent_key": b.parent_key,
               "issuer": b.issuer_name, "is_sukuk": bool(b.is_sukuk), "issue_date": b.issue_date,
               "tenor_at_issue": (b.maturity_date - b.issue_date).days / 365.25,
               "yield_at_issue": b.yield_at_issue, "nip_bp": np.nan, "match_method": "no curve", "curve_date": pd.NaT}
        if len(c):
            day = c["date"].max()
            cc = c[c["date"] == day]
            slope = ust.slope_fn(day) if ust is not None else None
            # remaining maturity of the new bond on the curve date, matched as twin.py does
            tau = (b.maturity_date - day).days / 365.25
            m = match_day(np.array([tau]), np.array([b.yield_at_issue]), cc["tau"].to_numpy(),
                          cc["y"].to_numpy(), TWIN, slope)
            if m and m[0][2] in TWIN["main_methods"]:
                rec.update(nip_bp=(b.yield_at_issue - m[0][1]) * 100, match_method=m[0][2], curve_date=day)
            elif m:
                rec["match_method"] = m[0][2] + " (not in main methods)"
            else:
                rec["match_method"] = "outside curve"
        rows.append(rec)
    return pd.DataFrame(rows)


OFF_MARKET_BP = 300.0   # |yield at issue - curve| beyond this = not a market deal (e.g. 1% official placements)


def flag_off_market(nip: pd.DataFrame, limit: float = OFF_MARKET_BP) -> pd.DataFrame:
    n = nip.copy()
    n["off_market"] = n["nip_bp"].abs() > limit
    return n


def premium_by_issuer(nip: pd.DataFrame, cds_monthly: pd.DataFrame, issuer_sov: dict,
                      secondary: pd.DataFrame) -> pd.DataFrame:
    """Median new-issue premium by issuer (off-market deals excluded), sukuk vs conventional."""
    n = flag_off_market(nip).dropna(subset=["nip_bp"])
    n = n[~n["off_market"]].copy()
    n["month"] = n["issue_date"].dt.to_period("M")
    n["gov"] = n["parent_key"].map(issuer_sov)
    n["cds_at_issue"] = [cds_monthly.at[m, g] if isinstance(g, str) and m in cds_monthly.index else np.nan
                         for m, g in zip(n["month"], n["gov"])]
    rows = []
    for key, g in n.groupby("parent_key"):
        s, c = g[g["is_sukuk"]], g[~g["is_sukuk"]]
        sec = secondary[secondary["parent_key"] == key]
        rows.append({"parent_key": key, "issuer": g["issuer"].mode().iat[0],
                     "new_sukuk": len(s), "sukuk_nip_median_bp": round(s["nip_bp"].median(), 1) if len(s) else np.nan,
                     "new_conv": len(c), "conv_nip_median_bp": round(c["nip_bp"].median(), 1) if len(c) else np.nan,
                     "sukuk_minus_conv_bp": round(s["nip_bp"].median() - c["nip_bp"].median(), 1)
                     if len(s) and len(c) else np.nan,
                     "cds_at_sukuk_issue_bp": round(s["cds_at_issue"].mean(), 0) if len(s) else np.nan,
                     "secondary_basis_bp": round(float(sec["mean_basis_bp"].iloc[0]), 1) if len(sec) else np.nan})
    return pd.DataFrame(rows).sort_values("sukuk_nip_median_bp")
