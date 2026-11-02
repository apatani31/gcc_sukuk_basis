"""Selection check for new deals with no usable curve (task 11)."""
import numpy as np
import pandas as pd
import pytest

from src import config as C
from src.data_quality import add_treasury_spread, classify_deals, curve_free_regressions, match_rates
from src.ratings import is_sub_ig


class Ust:
    """Upward-sloping curve: 2% at 1y, 4% at 11y (20bp per year)."""

    def row(self, day):
        return np.array([1.0, 11.0]), np.array([2.0, 4.0])


def _ratings():
    r = pd.DataFrame({"government": ["W", "W", "S", "S"], "agency": ["S&P", "Moody's", "S&P", "Moody's"],
                      "date": pd.to_datetime(["2016-01-01"] * 4), "rating": ["BB", "Ba1", "A", "A2"]})
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    return r


def test_classification_is_filled_for_unmatched_deals():
    nip = pd.DataFrame({"parent_key": ["w", "s", "m"], "curve_date": pd.to_datetime([None, None, None]),
                        "issue_date": pd.to_datetime(["2020-03-16"] * 3), "curve_yield": np.nan, "curve_tau": np.nan,
                        "nip_bp": np.nan, "off_market": False})
    d = classify_deals(nip, _ratings(), {"w": "W", "s": "S"}, pd.DataFrame(), None, C.PRIMARY_MARKET)
    assert d.loc[0, "sub_MAIN"] == 1 and d.loc[1, "sub_MAIN"] == 0
    assert np.isnan(d.loc[2, "sub_MAIN"])                               # no government rating: stays unclassified
    assert d.loc[0, "ref_date"] == pd.Timestamp("2020-03-09")           # issue date minus 5 business days


def test_matched_deals_keep_the_curve_date_as_reference():
    nip = pd.DataFrame({"parent_key": ["w"], "curve_date": pd.to_datetime(["2020-03-05"]),
                        "issue_date": pd.to_datetime(["2020-03-16"]), "curve_yield": np.nan, "curve_tau": np.nan,
                        "nip_bp": -10.0, "off_market": False})
    d = classify_deals(nip, _ratings(), {"w": "W"}, pd.DataFrame(), None, C.PRIMARY_MARKET)
    assert d.loc[0, "ref_date"] == pd.Timestamp("2020-03-05")


def test_treasury_spread_is_yield_minus_interpolated_ust():
    d = pd.DataFrame({"ref_date": pd.to_datetime(["2020-03-09"]), "issue_date": pd.to_datetime(["2020-03-16"]),
                      "yield_at_issue": [5.0], "tenor_at_issue": [6.0], "nip_bp": [np.nan]})
    out = add_treasury_spread(d, Ust())
    assert out.loc[0, "spread_bp"] == pytest.approx((5.0 - 3.0) * 100)   # UST at 6y interpolates to 3.0%
    assert not out.loc[0, "matched"] and out.loc[0, "issue_year"] == 2020


def _synthetic(ig=-20.0, extra=-60.0, seed=0, n=400):
    rng = np.random.default_rng(seed)
    gov = rng.integers(0, 6, n)
    # two issuers per government; governments 0 and 1 are sub-IG
    issuer = gov * 2 + rng.integers(0, 2, n)
    sub = (gov < 2).astype(float)
    sukuk = rng.integers(0, 2, n).astype(bool)
    tenor = rng.uniform(3, 30, n)
    year = rng.integers(2017, 2026, n)
    y = 100 + 300 * sub + 5 * issuer + 3 * (year - 2017) + 8 * tenor - 0.1 * tenor ** 2 \
        + sukuk * (ig + extra * sub) + rng.normal(0, 3, n)
    return pd.DataFrame({"spread_bp": y, "sub_MAIN": sub, "is_sukuk": sukuk, "tenor_at_issue": tenor,
                         "issue_year": year, "parent_key": [f"i{i}" for i in issuer],
                         "government": [f"g{g}" for g in gov], "off_market": False,
                         "matched": rng.random(n) < 0.6})


def test_regression_recovers_planted_sukuk_subig_effect():
    r = curve_free_regressions(_synthetic(), B=199).set_index("sample")
    for s in ("All deals", "Matched deals", "Unmatched deals"):
        assert r.loc[s, "ig_sukuk_minus_conv_bp"] == pytest.approx(-20, abs=2)
        assert r.loc[s, "interaction_bp"] == pytest.approx(-60, abs=3)
        assert r.loc[s, "sub_ig_sukuk_minus_conv_bp"] == pytest.approx(-80, abs=3)
    assert r.loc["All deals", "deals"] == 400 and r.loc["All deals", "sub_ig_governments"] == 2


def test_off_market_deals_excluded_from_regression_and_match_rates():
    d = _synthetic()
    d["off_market"] = False
    d.loc[0, "off_market"] = True
    d["match_method"] = np.where(d["matched"], "interp", "no curve")
    d["issuer"] = d["parent_key"]
    assert curve_free_regressions(d, B=99).set_index("sample").loc["All deals", "deals"] == 399
    rates, _ = match_rates(d, C.PRIMARY_MARKET)
    assert rates.set_index("dimension").loc["All market deals", "deals"] == 399
