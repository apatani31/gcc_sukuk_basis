"""Yield-at-issue checks on bonds whose answer can be verified by hand."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.yield_calc import add_yield_at_issue, days_30_360, price_from_yield, ytm


def test_par_bond_yields_its_coupon():
    # 5% semiannual 10y issued at 100: YTM must equal the coupon exactly.
    assert ytm(100.0, 5.0, date(2020, 1, 15), date(2030, 1, 15), 2) == pytest.approx(0.05, abs=1e-10)


def test_one_year_annual_discount_bond():
    # 4% annual, 1 year, price 98: one cash flow of 104, so y = 104/98 - 1 = 6.12245%.
    assert ytm(98.0, 4.0, date(2021, 6, 1), date(2022, 6, 1), 1) == pytest.approx(104 / 98 - 1, abs=1e-10)


def test_two_year_semiannual_premium_bond():
    # 5% semiannual, 2 years, priced at 4% yield:
    # P = 2.5 * (1 - 1.02^-4)/0.02 + 100/1.02^4 = 9.519322 + 92.384543 = 101.903864
    price = 2.5 * (1 - 1.02 ** -4) / 0.02 + 100 / 1.02 ** 4
    assert price == pytest.approx(101.903864, abs=1e-6)
    assert ytm(price, 5.0, date(2019, 3, 1), date(2021, 3, 1), 2) == pytest.approx(0.04, abs=1e-10)


def test_odd_first_period_round_trips():
    # Short first coupon (issue 2020-03-15, coupons 15 Jan/Jul): price -> yield -> price.
    y = ytm(99.25, 4.0, date(2020, 3, 15), date(2025, 1, 15), 2)
    assert price_from_yield(y, 4.0, date(2020, 3, 15), date(2025, 1, 15), 2) == pytest.approx(99.25, abs=1e-9)


def test_30_360_day_count():
    assert days_30_360(date(2020, 1, 31), date(2020, 7, 31)) == 180
    assert days_30_360(date(2020, 3, 15), date(2020, 7, 15)) == 120


def test_flags_and_sources():
    base = dict(issue_date=pd.Timestamp("2020-01-15"), maturity_date=pd.Timestamp("2030-01-15"),
                coupon_rate=5.0, issue_price=100.0, coupon_frequency="Semiannually",
                coupon_type="Plain Vanilla Fixed Coupon")
    df = pd.DataFrame([
        base,
        {**base, "coupon_type": "Fixed Margin over Index"},
        {**base, "maturity_date": pd.NaT},
        {**base, "issue_price": np.nan},
        {**base, "yield_at_issue_lseg": 4.9},
    ])
    out = add_yield_at_issue(df)
    assert out.loc[0, "yield_at_issue"] == pytest.approx(5.0)
    assert out.loc[0, "yield_at_issue_source"] == "computed"
    assert list(out["yield_at_issue_flag"][1:4]) == [
        "not_fixed_rate", "perpetual_or_no_maturity", "missing_issue_price"]
    assert out.loc[4, "yield_at_issue_source"] == "lseg" and out.loc[4, "yield_at_issue"] == 4.9
