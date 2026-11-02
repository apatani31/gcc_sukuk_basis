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
              min_days: int = 100, status: pd.DataFrame | None = None, min_days_split: int = 60):
    """Per-bond staleness metrics and their medians by sukuk/conventional.

    With `status` (parent_key, month 'YYYY-MM', sub_main), also returns a third table that splits each
    bond's days by its issuer-month credit status (weak credit = sub-IG under the MAIN rule that month);
    daily changes are computed on the full series before the split."""
    summ, r, w = _staleness_core(timeseries_dir, bonds, coverage, start, min_days)
    if status is None:
        return summ, r
    w = w.merge(bonds[["instrument_id", "parent_key", "is_sukuk"]], on="instrument_id")
    w["month"] = w["date"].dt.strftime("%Y-%m")
    w = w.merge(status, on=["parent_key", "month"], how="left").dropna(subset=["sub_main"])
    rows = []
    for (k, s), b in w.groupby(["instrument_id", "sub_main"]):
        if len(b) < min_days_split:
            continue
        rows.append({"instrument_id": k, "is_sukuk": b["is_sukuk"].iat[0], "weak": bool(s),
                     "unchanged_mid_share": b["dmid"].eq(0).mean(),
                     "bid_ask_cents_median": ((b["ask_price"] - b["bid_price"]) * 100).median(),
                     "ar1_daily_yield_change": b["dy"].autocorr()})
    x = pd.DataFrame(rows)
    by_credit = (x.assign(group=x["is_sukuk"].map({True: "Sukuk", False: "Conventional"}),
                          credit=x["weak"].map({True: "Weak credit (sub-IG month, MAIN)", False: "Other"}))
                 .groupby(["credit", "group"]).agg(bond_segments=("instrument_id", "size"),
                                                   unchanged_mid_share=("unchanged_mid_share", "median"),
                                                   bid_ask_cents=("bid_ask_cents_median", "median"),
                                                   ar1_yield_change=("ar1_daily_yield_change", "median"))
                 .round(3).reset_index())
    return summ, r, by_credit


def _staleness_core(timeseries_dir, bonds: pd.DataFrame, coverage: pd.DataFrame, start: str, min_days: int):
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
    w["dmid"] = w.groupby("instrument_id")["mid"].diff()
    w["dy"] = w.groupby("instrument_id")["y"].diff()
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
    return summ, r, w


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
               "yield_at_issue": b.yield_at_issue, "nip_bp": np.nan, "match_method": "no curve", "curve_date": pd.NaT,
               "curve_yield": np.nan, "curve_tau": np.nan}
        if len(c):
            day = c["date"].max()
            cc = c[c["date"] == day]
            slope = ust.slope_fn(day) if ust is not None else None
            # remaining maturity of the new bond on the curve date, matched as twin.py does
            tau = (b.maturity_date - day).days / 365.25
            m = match_day(np.array([tau]), np.array([b.yield_at_issue]), cc["tau"].to_numpy(),
                          cc["y"].to_numpy(), TWIN, slope)
            if m and m[0][2] in TWIN["main_methods"]:
                rec.update(nip_bp=(b.yield_at_issue - m[0][1]) * 100, match_method=m[0][2], curve_date=day,
                           curve_yield=m[0][1], curve_tau=tau)
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


# ---------------------------------------------------------------------------
# d (continued). Classifying deals as weak credit at their reference date
# ---------------------------------------------------------------------------
def classify_deals(nip: pd.DataFrame, ratings: pd.DataFrame | None, issuer_gov: dict, cds_daily: pd.DataFrame,
                   ust: UstCurve | None, cfg: dict) -> pd.DataFrame:
    """Add weak-credit flags (1 = weak, 0 = other, NaN = unclassifiable) under each rule.

    Reference date = the curve date already used for the premium (last trading day at least lead_bdays
    business days before the issue date), a proxy for the pricing date.
      sub_MAIN, sub_Robustness A : sovereign rating status on the reference date (ratings.status_at)
      sub_Robustness B           : spread_ref_bp > threshold; the government's 5y CDS (last print within
                                   cds_max_staleness_days), else the issuer's conventional curve yield at the
                                   deal's maturity minus the US Treasury yield at that maturity
      sub_Legacy                 : the old fixed list
    """
    from .ratings import status_at

    from .config import ISSUER_SOVEREIGN

    n = nip.copy()
    n["government"] = n["parent_key"].map(issuer_gov)
    n["ref_date"] = n["curve_date"]
    if "issue_date" in n:   # deals with no usable curve: same proxy for the pricing date, issue date minus the lead
        n["ref_date"] = n["ref_date"].fillna(n["issue_date"] - pd.tseries.offsets.BDay(cfg["lead_bdays"]))
    rows = []
    cds = cds_daily.astype(float).sort_index()
    for r in n.itertuples():
        rec = {"sub_MAIN": np.nan, "sub_Robustness A": np.nan, "agencies_rating": np.nan,
               "agencies_below_ig": np.nan, "spread_ref_bp": np.nan, "spread_source": ""}
        if pd.notna(r.ref_date):
            if ratings is not None and isinstance(r.government, str):
                st = status_at(ratings, r.government, r.ref_date)
                rec.update({"sub_MAIN": st["sub_main"], "sub_Robustness A": st["sub_lowest"],
                            "agencies_rating": st["agencies_rating"], "agencies_below_ig": st["agencies_below_ig"]})
            sov = ISSUER_SOVEREIGN.get(r.parent_key)
            if isinstance(sov, str) and sov in cds:
                s = cds[sov].loc[:r.ref_date].dropna()
                if len(s) and (r.ref_date - s.index[-1]).days <= cfg["cds_max_staleness_days"]:
                    rec.update(spread_ref_bp=float(s.iloc[-1]), spread_source=f"{sov} 5y CDS")
            if np.isnan(rec["spread_ref_bp"]) and pd.notna(r.curve_yield) and ust is not None:
                row = ust.row(r.ref_date)
                if row is not None:
                    rec.update(spread_ref_bp=(r.curve_yield - float(np.interp(r.curve_tau, *row))) * 100,
                               spread_source="issuer conventional spread over UST")
        rows.append(rec)
    n = pd.concat([n.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    n["sub_Robustness B"] = np.where(n["spread_ref_bp"].notna(),
                                     (n["spread_ref_bp"] > cfg["spread_threshold_bp"]).astype(float), np.nan)
    n["sub_Legacy"] = n["parent_key"].isin(cfg["legacy_weak"]).astype(float)
    return n


RULES = ("MAIN", "Robustness A", "Robustness B", "Legacy")


def rule_summary(deals: pd.DataFrame, rules=RULES, exclude_gov: str = "Bahrain") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Market deals only. Returns (group table, one-line summary per rule and sample).

    Group table: rule x sample x weak/other x sukuk/conventional: bonds, mean, median.
    Summary: weak-credit sukuk median and n, weak-credit conventional median, sukuk-minus-conventional
    (medians), other issuers' sukuk median, Welch t of weak-credit vs other sukuk, unclassified deals."""
    from scipy import stats

    d = deals.dropna(subset=["nip_bp"])
    d = d[~d["off_market"]] if "off_market" in d else d
    groups, summ = [], []
    for rule in rules:
        col = f"sub_{rule}"
        for sample, dd in (("All issuers", d), (f"Excluding {exclude_gov} (government and BAPCO)",
                                                 d[d["government"] != exclude_gov])):
            unclassified = int(dd[col].isna().sum())
            c = dd.dropna(subset=[col])
            for (w, s), g in c.groupby([c[col].astype(bool), "is_sukuk"]):
                groups.append({"rule": rule, "sample": sample, "credit": "Weak credit" if w else "Other",
                               "bond": "Sukuk" if s else "Conventional", "bonds": len(g),
                               "mean_bp": round(g["nip_bp"].mean(), 1), "median_bp": round(g["nip_bp"].median(), 1)})
            ws = c[(c[col] == 1) & c["is_sukuk"]]["nip_bp"]
            wc = c[(c[col] == 1) & ~c["is_sukuk"]]["nip_bp"]
            os_ = c[(c[col] == 0) & c["is_sukuk"]]["nip_bp"]
            t = stats.ttest_ind(ws, os_, equal_var=False).statistic if len(ws) > 1 and len(os_) > 1 else np.nan
            summ.append({"rule": rule, "sample": sample, "weak_sukuk_n": len(ws),
                         "weak_sukuk_median_bp": round(ws.median(), 1) if len(ws) else np.nan,
                         "weak_conv_n": len(wc), "weak_conv_median_bp": round(wc.median(), 1) if len(wc) else np.nan,
                         "weak_sukuk_minus_conv_bp": round(ws.median() - wc.median(), 1) if len(ws) and len(wc) else np.nan,
                         "other_sukuk_n": len(os_), "other_sukuk_median_bp": round(os_.median(), 1) if len(os_) else np.nan,
                         "welch_t_weak_vs_other_sukuk": round(t, 2) if pd.notna(t) else np.nan,
                         "unclassified_deals": unclassified})
    return pd.DataFrame(groups), pd.DataFrame(summ)


def changes_vs_legacy(deals: pd.DataFrame, rules=("MAIN", "Robustness A", "Robustness B")) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Market deals whose classification differs from the legacy list: counts by issuer and the deal list."""
    d = deals.dropna(subset=["nip_bp"])
    d = d[~d["off_market"]] if "off_market" in d else d
    counts, lists = [], []
    for rule in rules:
        col = f"sub_{rule}"
        diff = d[d[col].notna() & (d[col] != d["sub_Legacy"])]
        unc = d[d[col].isna()]
        for issuer, g in d.groupby("issuer"):
            ch = diff[diff["issuer"] == issuer]
            un = unc[unc["issuer"] == issuer]
            if len(ch) or len(un):
                counts.append({"rule": rule, "issuer": issuer, "deals": len(g),
                               "weak_to_other": int((ch["sub_Legacy"] == 1).sum()),
                               "other_to_weak": int((ch["sub_Legacy"] == 0).sum()), "unclassified": len(un)})
        if len(diff):
            lists.append(pd.DataFrame({
                "rule": rule, "issuer": diff["issuer"].values,
                "issue_date": diff["issue_date"].dt.strftime("%Y-%m-%d").values,
                "ref_date": diff["ref_date"].dt.strftime("%Y-%m-%d").values,
                "bond": np.where(diff["is_sukuk"], "Sukuk", "Conventional"),
                "legacy": np.where(diff["sub_Legacy"] == 1, "Weak", "Other"),
                "now": np.where(diff[col] == 1, "Weak", "Other"),
                "nip_bp": diff["nip_bp"].round(1).values}))
    lst = (pd.concat(lists, ignore_index=True).sort_values(["rule", "issue_date", "issuer"]).reset_index(drop=True)
           if lists else pd.DataFrame())
    return pd.DataFrame(counts), lst


def issuer_month_status(ratings: pd.DataFrame, issuer_gov: dict, keys, months) -> pd.DataFrame:
    """MAIN rule by issuer-month (parent_key, month 'YYYY-MM', sub_main) via ratings.monthly_status."""
    from .ratings import monthly_status

    ms = monthly_status(ratings, pd.PeriodIndex(months, freq="M"))
    ms["month"] = ms["month"].astype(str)
    rows = [{"parent_key": k, "government": issuer_gov.get(k)} for k in keys]
    m = pd.DataFrame(rows).merge(ms[["government", "month", "sub_ig"]], on="government", how="left")
    return m.rename(columns={"sub_ig": "sub_main"})[["parent_key", "month", "sub_main"]]


# ---------------------------------------------------------------------------
# e. Selection check: do deals with no usable curve differ?
# ---------------------------------------------------------------------------
def add_treasury_spread(deals: pd.DataFrame, ust: UstCurve) -> pd.DataFrame:
    """spread_bp = yield at issue minus the US Treasury yield at the deal's tenor on its reference date
    (linear interpolation on that day's curve). Needs no issuer curve, so every deal has one."""
    d = deals.copy()
    vals = []
    for r in d.itertuples():
        row = ust.row(r.ref_date) if pd.notna(r.ref_date) else None
        vals.append((r.yield_at_issue - float(np.interp(r.tenor_at_issue, *row))) * 100 if row is not None else np.nan)
    d["spread_bp"] = vals
    d["matched"] = d["nip_bp"].notna()
    d["issue_year"] = d["issue_date"].dt.year
    return d


def _band(values: pd.Series, bands: dict) -> pd.Series:
    out = pd.Series(index=values.index, dtype=object)
    for label, (lo, hi) in bands.items():
        out[(values > lo) & (values <= hi)] = label
    return out


def match_rates(deals: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Share of market deals with a usable curve, by credit x bond type, year, tenor and issuer (MAIN rule),
    plus the reason for deals with no usable curve."""
    d = deals[~deals["off_market"]].copy()
    d["credit"] = d["sub_MAIN"].map({1.0: "Sub-IG", 0.0: "IG"}).fillna("Unclassified (multilateral)")
    d["bond"] = np.where(d["is_sukuk"], "sukuk", "conventional")
    d["year_band"] = pd.Series(pd.NA, index=d.index, dtype=object)
    yrs = d["issue_year"]
    for label, (lo, hi) in cfg["year_bands"].items():
        d.loc[yrs.between(lo, hi), "year_band"] = label
    d["tenor_band"] = _band(d["tenor_at_issue"], cfg["tenor_bands"])
    rows = []

    def add(dim, group, g):
        rows.append({"dimension": dim, "group": group, "deals": len(g), "matched": int(g["matched"].sum()),
                     "match_rate": round(g["matched"].mean(), 3)})

    add("All market deals", "All", d)
    for c, g in d.groupby("credit"):
        add("Credit (MAIN)", c, g)
    for (c, b), g in d[d["sub_MAIN"].notna()].groupby(["credit", "bond"]):
        add("Credit x bond", f"{c} {b}", g)
    for label in cfg["year_bands"]:
        add("Issue year", label, d[d["year_band"] == label])
    for label in cfg["tenor_bands"]:
        add("Tenor", label, d[d["tenor_band"] == label])
    for key, g in d.groupby("parent_key"):
        add("Issuer", g["issuer"].mode().iat[0], g)
    reasons = (d.assign(reason=np.where(d["matched"], "matched", d["match_method"]))
               .groupby("reason").agg(deals=("matched", "size"), median_tenor=("tenor_at_issue", "median"),
                                      median_issue_year=("issue_year", "median"),
                                      sub_ig_deals=("sub_MAIN", lambda s: int((s == 1).sum())))
               .round(1).reset_index())
    return pd.DataFrame(rows), reasons


def curve_free_regressions(deals: pd.DataFrame, B: int = 9999) -> pd.DataFrame:
    """spread_bp ~ sukuk + sukuk:sub_ig + C(parent_key) + C(issue_year) + tenor + tenor2, on all, matched and
    unmatched market deals. Errors clustered by issuer (obligor), plus a restricted wild cluster bootstrap by
    government for sukuk:sub_ig. Implied sukuk minus conventional: `sukuk` for IG deals, the sum for sub-IG."""
    import statsmodels.formula.api as smf

    from .inference import wild_cluster_bootstrap

    d = deals[~deals["off_market"]].dropna(subset=["spread_bp", "sub_MAIN", "government"]).copy()
    d["sukuk"] = d["is_sukuk"].astype(float)
    d["sub_ig"] = d["sub_MAIN"].astype(float)
    d["tenor"] = d["tenor_at_issue"]
    d["tenor2"] = d["tenor"] ** 2
    d["year_fe"] = d["issue_year"].astype(str)
    f = "spread_bp ~ sukuk + sukuk:sub_ig + C(parent_key) + C(year_fe) + tenor + tenor2"
    rows = []
    for name, dd in (("All deals", d), ("Matched deals", d[d["matched"]]), ("Unmatched deals", d[~d["matched"]])):
        rec = {"sample": name, "deals": len(dd), "sukuk_deals": int(dd["sukuk"].sum()),
               "sub_ig_deals": int((dd["sub_ig"] == 1).sum()),
               "sub_ig_sukuk": int(((dd["sub_ig"] == 1) & (dd["sukuk"] == 1)).sum()), "issuers": dd["parent_key"].nunique()}
        identified = rec["sub_ig_sukuk"] > 0 and ((dd["sub_ig"] == 1) & (dd["sukuk"] == 0)).any()
        if identified:
            r = smf.ols(f, dd).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dd["parent_key"])[0]})
            tt = r.t_test("sukuk + sukuk:sub_ig = 0")
            w = wild_cluster_bootstrap(f, dd, "sukuk:sub_ig", "government", B=B)
            rec.update(ig_sukuk_minus_conv_bp=round(r.params["sukuk"], 1), ig_t=round(r.tvalues["sukuk"], 2),
                       sub_ig_sukuk_minus_conv_bp=round(float(tt.effect[0]), 1),
                       sub_ig_t=round(float(tt.tvalue[0][0]), 2),
                       interaction_bp=round(r.params["sukuk:sub_ig"], 1),
                       interaction_t_cluster=round(r.tvalues["sukuk:sub_ig"], 2),
                       interaction_p_cluster=round(float(r.pvalues["sukuk:sub_ig"]), 3),
                       interaction_t_government=round(w["t_cr1"], 2),
                       interaction_p_wild_government=round(w["p_wild"], 3), government_clusters=w["clusters"],
                       sub_ig_governments=dd.loc[dd["sub_ig"] == 1, "government"].nunique())
        rows.append(rec)
    return pd.DataFrame(rows)


def curve_free_medians(deals: pd.DataFrame) -> pd.DataFrame:
    """Median Treasury spread at issue by credit (MAIN) x bond type x matched / unmatched."""
    d = deals[~deals["off_market"]].dropna(subset=["spread_bp", "sub_MAIN"])
    rows = []
    for (s, k, m), g in d.groupby(["sub_MAIN", "is_sukuk", "matched"]):
        rows.append({"credit": "Sub-IG" if s == 1 else "IG", "bond": "Sukuk" if k else "Conventional",
                     "sample": "Matched" if m else "Unmatched", "deals": len(g),
                     "median_spread_bp": round(g["spread_bp"].median(), 1),
                     "median_tenor": round(g["tenor_at_issue"].median(), 1)})
    return pd.DataFrame(rows).sort_values(["credit", "bond", "sample"]).reset_index(drop=True)
