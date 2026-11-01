"""Deal-level weak-credit classification for the primary-market check (task 9)."""
import numpy as np
import pandas as pd
import pytest

from src import config as C
from src.data_quality import classify_deals
from src.ratings import is_sub_ig, load_ratings, status_at

needs_file = pytest.mark.skipif(not C.SOVEREIGN_RATINGS_PATH.exists(), reason="sovereign_ratings.csv not present")


@pytest.fixture(scope="module")
def ratings():
    return load_ratings(C.SOVEREIGN_RATINGS_PATH)


def _main(r, gov, day):
    return status_at(r, gov, pd.Timestamp(day))["sub_main"]


def _lowest(r, gov, day):
    return status_at(r, gov, pd.Timestamp(day))["sub_lowest"]


@needs_file
def test_oman_2021_deals_sub_ig_and_2025_deal_ig_under_main(ratings):
    # reference dates of the 2021-01-25 and 2021-06-15 deals; and of the 2025-10-17 sukuk
    assert _main(ratings, "Oman", "2021-01-18") == 1
    assert _main(ratings, "Oman", "2021-06-08") == 1
    assert _main(ratings, "Oman", "2025-10-10") == 0       # S&P BBB- and Moody's Baa3: IG at 2 of 3


@needs_file
def test_oman_2018_deals_ig_under_main_but_sub_ig_under_lowest(ratings):
    # On the file, in 2018 only S&P (BB) was below IG; Moody's (Baa2/Baa3) and Fitch (BBB-) were IG.
    # MAIN needs two agencies below, so these deals are IG; the lowest-rating rule makes them sub-IG.
    for ref in ("2018-01-10", "2018-10-24"):
        assert _main(ratings, "Oman", ref) == 0
        assert _lowest(ratings, "Oman", ref) == 1
    assert _main(ratings, "Oman", "2019-01-10") == 1       # after Fitch's cut to BB+ (2018-12-18)


@needs_file
def test_sharjah_ig_under_main_always_and_sub_ig_under_lowest_from_2022_07_19(ratings):
    for day in pd.date_range("2016-01-15", "2026-10-15", freq="MS"):
        assert _main(ratings, "Sharjah", day) == 0
    assert _lowest(ratings, "Sharjah", "2022-07-18") == 0
    assert _lowest(ratings, "Sharjah", "2022-07-19") == 1
    assert _lowest(ratings, "Sharjah", "2026-06-01") == 1


@needs_file
def test_bahrain_and_bapco_sub_ig_under_main_since_2016_06_28(ratings):
    for day in pd.date_range("2016-06-28", "2026-10-28", freq="MS"):
        assert _main(ratings, "Bahrain", day) == 1
    nip = pd.DataFrame({"parent_key": ["bahrain kingdom", "bapco energies"], "curve_date": pd.to_datetime(["2020-05-07"] * 2),
                        "curve_yield": np.nan, "curve_tau": np.nan, "nip_bp": [-50.0, -30.0], "off_market": False})
    from src.ratings import ISSUER_GOVERNMENT
    d = classify_deals(nip, ratings, ISSUER_GOVERNMENT, pd.DataFrame(), None, C.PRIMARY_MARKET)
    assert list(d["sub_MAIN"]) == [1, 1] and list(d["government"]) == ["Bahrain", "Bahrain"]


def test_rating_row_dated_after_the_reference_date_is_not_used():
    r = pd.DataFrame({"government": "X", "agency": ["S&P", "Moody's", "S&P"],
                      "date": pd.to_datetime(["2016-01-01", "2016-01-01", "2020-06-10"]),
                      "rating": ["BB", "Ba1", "BBB"]})
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    assert status_at(r, "X", pd.Timestamp("2020-06-09"))["sub_main"] == 1   # upgrade not yet known
    assert status_at(r, "X", pd.Timestamp("2020-06-10"))["sub_main"] == 0   # 2 rate, 1 below: not both -> IG
    assert status_at(r, "X", pd.Timestamp("2020-06-10"))["sub_lowest"] == 1
    assert status_at(r, "X", pd.Timestamp("2015-12-31"))["agencies_rating"] == 0


def test_spread_rule_uses_cds_then_conventional_spread():
    class Ust:
        def row(self, day):
            return np.array([1.0, 10.0]), np.array([4.0, 4.0])   # flat 4% curve
    cds = pd.DataFrame({"Bahrain": [300.0]}, index=pd.to_datetime(["2024-01-02"]))
    nip = pd.DataFrame({"parent_key": ["bahrain kingdom", "emirate sharjah"],
                        "curve_date": pd.to_datetime(["2024-01-05", "2024-01-05"]),
                        "curve_yield": [np.nan, 5.2], "curve_tau": [np.nan, 5.0], "nip_bp": [-40.0, -20.0],
                        "off_market": False})
    d = classify_deals(nip, None, {}, cds, Ust(), C.PRIMARY_MARKET)
    assert d.loc[0, "spread_ref_bp"] == 300 and d.loc[0, "sub_Robustness B"] == 1
    assert d.loc[1, "spread_ref_bp"] == pytest.approx(120) and d.loc[1, "sub_Robustness B"] == 0
    assert d.loc[1, "sub_Legacy"] == 1 and np.isnan(d.loc[1, "sub_MAIN"])
