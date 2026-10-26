"""Yield to maturity at issue for fixed-rate bonds.

Convention (stated in summary.md): settlement = issue date, so the issue
price is both clean and dirty (accrual starts at issue). Coupons are scheduled
backward from maturity at the coupon frequency; an odd first period pays
coupon x year-fraction(issue, first coupon). Discounting is street convention
with compounding at the coupon frequency, the first exponent being the
fraction of a regular period. Day count defaults to 30/360 (US bond basis)
because the export does not carry it.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .config import DEFAULT_DAY_COUNT, FIXED_COUPON_TYPES, FREQUENCY_MAP, ZERO_COUPON_TYPES

log = logging.getLogger(__name__)


def days_30_360(d1: date, d2: date) -> int:
    """30/360 US bond basis day count."""
    dd1, dd2 = min(d1.day, 30), d2.day
    if dd1 == 30 and dd2 == 31:
        dd2 = 30
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (dd2 - dd1)


def year_fraction(d1: date, d2: date, basis: str = DEFAULT_DAY_COUNT) -> float:
    if basis == "30/360":
        return days_30_360(d1, d2) / 360.0
    if basis == "ACT/365":
        return (d2 - d1).days / 365.0
    if basis == "ACT/360":
        return (d2 - d1).days / 360.0
    raise ValueError(f"Unsupported day count {basis!r}")


def coupon_schedule(issue: date, maturity: date, freq: int) -> list[date]:
    """Coupon dates after issue up to and including maturity, rolled back from maturity."""
    months = 12 // freq
    dates, k = [], 0
    while True:
        d = (pd.Timestamp(maturity) - pd.DateOffset(months=months * k)).date()
        if d <= issue:
            break
        dates.append(d)
        k += 1
    return sorted(dates)


def cash_flows(coupon: float, issue: date, maturity: date, freq: int,
               basis: str = DEFAULT_DAY_COUNT) -> tuple[np.ndarray, np.ndarray]:
    """Return (exponents in periods, cash flows per 100 face)."""
    sched = coupon_schedule(issue, maturity, freq)
    months = 12 // freq
    prev = (pd.Timestamp(sched[0]) - pd.DateOffset(months=months)).date()
    period = year_fraction(prev, sched[0], basis)
    first_frac = year_fraction(issue, sched[0], basis) / period
    t = first_frac + np.arange(len(sched))
    cf = np.full(len(sched), coupon / freq)
    cf[0] = coupon * year_fraction(issue, sched[0], basis)  # odd first coupon accrues from issue
    cf[-1] += 100.0
    return t, cf


def price_from_yield(y: float, coupon: float, issue: date, maturity: date, freq: int,
                     basis: str = DEFAULT_DAY_COUNT) -> float:
    t, cf = cash_flows(coupon, issue, maturity, freq, basis)
    return float(np.sum(cf / (1 + y / freq) ** t))


def ytm(price: float, coupon: float, issue: date, maturity: date, freq: int,
        basis: str = DEFAULT_DAY_COUNT) -> float:
    """Annualized YTM (decimal, compounded at freq). freq=0 means zero coupon (annual compounding)."""
    if freq == 0:
        yrs = year_fraction(issue, maturity, basis)
        if yrs <= 0:
            raise ValueError("zero-length life")
        return (100.0 / price) ** (1 / yrs) - 1
    f = lambda y: price_from_yield(y, coupon, issue, maturity, freq, basis) - price
    return brentq(f, -0.5, 2.0, xtol=1e-12)


def _row_yield(r: pd.Series) -> tuple[float, str | None]:
    ct = r.get("coupon_type")
    if r.get("instrument_class", "bond") != "bond":
        return np.nan, "not_a_bond"
    if pd.isna(r.get("maturity_date")):
        return np.nan, "perpetual_or_no_maturity"
    if pd.isna(r.get("issue_price")):
        return np.nan, "missing_issue_price"
    if r["maturity_date"] <= r["issue_date"]:
        return np.nan, "maturity_not_after_issue"
    if ct in ZERO_COUPON_TYPES:
        try:
            return ytm(r["issue_price"], 0.0, r["issue_date"].date(), r["maturity_date"].date(), 0), None
        except ValueError:
            return np.nan, "solver_failed"
    if ct not in FIXED_COUPON_TYPES:
        return np.nan, "not_fixed_rate" if isinstance(ct, str) else "missing_coupon_type"
    if pd.isna(r.get("coupon_rate")):
        return np.nan, "missing_coupon"
    freq = FREQUENCY_MAP.get(r.get("coupon_frequency"))
    if not freq:
        return np.nan, "missing_or_unsupported_frequency"
    try:
        return ytm(r["issue_price"], r["coupon_rate"], r["issue_date"].date(),
                   r["maturity_date"].date(), freq), None
    except ValueError:
        return np.nan, "solver_failed"


def add_yield_at_issue(df: pd.DataFrame) -> pd.DataFrame:
    """Adds yield_at_issue (percent), yield_at_issue_source and yield_at_issue_flag."""
    df = df.copy()
    lseg = df["yield_at_issue_lseg"] if "yield_at_issue_lseg" in df else pd.Series(np.nan, index=df.index)
    lseg = pd.to_numeric(lseg, errors="coerce")
    computed = df.apply(_row_yield, axis=1, result_type="expand")
    computed.columns = ["_y", "_flag"]
    df["yield_at_issue"] = lseg
    df["yield_at_issue_source"] = np.where(lseg.notna(), "lseg", None)
    use_calc = lseg.isna() & computed["_y"].notna()
    df.loc[use_calc, "yield_at_issue"] = computed.loc[use_calc, "_y"] * 100
    df.loc[use_calc, "yield_at_issue_source"] = "computed"
    df["yield_at_issue_flag"] = np.where(df["yield_at_issue"].isna(), computed["_flag"], None)
    df["yield_at_issue_day_count"] = np.where(use_calc, DEFAULT_DAY_COUNT + " (assumed)", None)
    log.info("Yield at issue: %d lseg, %d computed, flags: %s",
             int(lseg.notna().sum()), int(use_calc.sum()),
             df["yield_at_issue_flag"].value_counts().to_dict())
    return df
