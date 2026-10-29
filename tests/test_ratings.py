import pandas as pd
import pytest

from src.ratings import is_sub_ig, monthly_status


def test_scale_boundaries():
    assert not is_sub_ig("S&P", "BBB-") and is_sub_ig("S&P", "BB+")
    assert not is_sub_ig("Moody's", "Baa3") and is_sub_ig("Moody's", "Ba1")
    assert is_sub_ig("Fitch", "B+ (stable)") is True
    with pytest.raises(ValueError):
        is_sub_ig("Moody's", "BBB-")


def test_two_of_three_rule_with_oman_style_upgrades():
    # All three sub-IG at the start; S&P upgrades Sep 2024, Moody's Jul 2025, Fitch Dec 2025.
    r = pd.DataFrame({
        "government": "Oman", "agency": ["S&P", "Moody's", "Fitch", "S&P", "Moody's", "Fitch"],
        "date": pd.to_datetime(["2016-01-01"] * 3 + ["2024-09-15", "2025-07-10", "2025-12-05"]),
        "rating": ["BB", "Ba1", "BB+", "BBB-", "Baa3", "BBB-"]})
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    m = monthly_status(r, pd.period_range("2024-08", "2026-01", freq="M")).set_index("month")
    assert m.loc[pd.Period("2024-09", "M"), "sub_ig"] == 1        # action month not yet applied
    assert m.loc[pd.Period("2024-10", "M"), "sub_ig"] == 1        # only S&P is IG: still 2 of 3 below
    assert m.loc[pd.Period("2025-08", "M"), "sub_ig"] == 0        # Moody's follows: IG at 2 of 3
    assert m.loc[pd.Period("2025-08", "M"), "agencies_below_ig"] == 1


def test_not_rated_is_not_counted_and_ends_a_previous_rating():
    assert is_sub_ig("Fitch", "NR") is None
    r = pd.DataFrame({"government": "X", "agency": ["S&P", "Moody's", "Fitch", "Fitch"],
                      "date": pd.to_datetime(["2016-01-01", "2016-01-01", "2016-01-01", "2020-01-15"]),
                      "rating": ["BBB-", "Ba1", "BB", "NR"]})
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    m = monthly_status(r, pd.period_range("2019-12", "2020-03", freq="M")).set_index("month")
    assert m.loc[pd.Period("2019-12", "M"), "sub_ig"] == 1           # Moody's + Fitch below
    assert m.loc[pd.Period("2020-03", "M"), "agencies_rating"] == 2  # Fitch withdrawn
    assert m.loc[pd.Period("2020-03", "M"), "sub_ig"] == 0           # only 1 of 2 below


def test_rating_dated_on_the_first_applies_that_month():
    r = pd.DataFrame({"government": "X", "agency": ["S&P", "Moody's"],
                      "date": pd.to_datetime(["2016-01-01", "2016-01-01"]), "rating": ["BB", "Ba1"]})
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    m = monthly_status(r, pd.period_range("2016-01", periods=2, freq="M"))
    assert (m["agencies_rating"] == 2).all() and (m["sub_ig"] == 1).all()


def test_single_agency_decides_and_is_flagged():
    r = pd.DataFrame({"government": "X", "agency": ["Fitch"], "date": pd.to_datetime(["2016-01-01"]),
                      "rating": ["BB"]})
    r["sub_ig"] = [True]
    m = monthly_status(r, pd.period_range("2020-01", periods=2, freq="M"))
    assert (m["sub_ig"] == 1).all() and m["single_agency"].all()
