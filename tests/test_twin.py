import numpy as np
import pandas as pd
import pytest

from src.twin import clean_panel, match_day, newey_west_mean, sukuk_basis

CFG = {"nearest_max_gap": 1.0, "yield_bounds": (0, 25), "min_tau": 1, "max_tau": 30, "outlier_pp": 1.5,
       "stale_run_days": 5, "max_stale_share": 0.5}


def test_interpolates_between_bracketing_conventional_bonds():
    # Conventional 2y @ 4%, 6y @ 6%; sukuk at 5y yields 5.2% -> conv(5y) = 5.5%, basis -30bp.
    out = match_day(np.array([5.0]), np.array([5.2]), np.array([2.0, 6.0]), np.array([4.0, 6.0]), CFG)
    i, yc, method, lo, hi, n = out[0]
    assert method == "interp" and yc == pytest.approx(5.5) and (lo, hi) == (2.0, 6.0)


def test_no_extrapolation_but_nearest_within_one_year():
    c_tau, c_y = np.array([2.0, 6.0]), np.array([4.0, 6.0])
    near = match_day(np.array([6.8]), np.array([6.1]), c_tau, c_y, CFG)
    assert near[0][2] == "nearest" and near[0][1] == 6.0
    assert match_day(np.array([9.0]), np.array([6.5]), c_tau, c_y, CFG) == []


def test_nearest_match_is_shifted_by_treasury_slope():
    # Nearest conventional bond is 0.5y longer; UST curve rises 10bp per year -> shift down 5bp.
    slope = lambda a, b: 0.10 * (a - b)
    out = match_day(np.array([6.5]), np.array([6.0]), np.array([2.0, 7.0]), np.array([4.0, 6.3]), CFG,
                    ust_slope=slope)
    assert out[0][2] == "interp" and out[0][1] == pytest.approx(6.07)  # inside [2, 7]: slope unused
    out = match_day(np.array([7.5]), np.array([6.0]), np.array([2.0, 7.0]), np.array([4.0, 6.3]), CFG,
                    ust_slope=slope)
    assert out[0][2] == "nearest_adj" and out[0][1] == pytest.approx(6.35)


def test_duplicate_conventional_tenors_are_averaged():
    out = match_day(np.array([3.0]), np.array([5.0]), np.array([2.0, 4.0, 4.0]), np.array([4.0, 5.0, 7.0]), CFG)
    assert out[0][1] == pytest.approx((4.0 + 6.0) / 2)


def test_sukuk_basis_end_to_end_sign():
    d = pd.Timestamp("2024-01-02")
    panel = pd.DataFrame({
        "parent_key": "k", "parent_name": "Issuer", "date": d, "country_of_risk": "Bahrain", "isin": list("ABC"),
        "instrument_id": list("ABC"), "is_sukuk": [True, False, False], "tau": [5.0, 2.0, 6.0],
        "y": [5.2, 4.0, 6.0]})
    b = sukuk_basis(panel, CFG)
    assert len(b) == 1 and b.loc[0, "basis_bp"] == pytest.approx(-30.0)


def test_newey_west_zero_lags_matches_iid_se():
    x = np.array([1.0, 3.0, 2.0, 5.0, 4.0])
    m, se = newey_west_mean(x, 0)
    assert m == pytest.approx(3.0)
    assert se == pytest.approx(np.sqrt(((x - 3) ** 2).mean() / len(x)))


def test_newey_west_widens_se_for_autocorrelated_series():
    x = np.repeat([1.0, -1.0], 50)  # long runs = strong positive autocorrelation
    assert newey_west_mean(x, 10)[1] > newey_west_mean(x, 0)[1]


def test_clean_panel_drops_stale_runs_and_bad_yields():
    dates = pd.bdate_range("2024-01-01", periods=30)
    w = pd.DataFrame({"instrument_id": "A", "date": dates, "tau": 5.0, "y": 5.0 + np.arange(30) * 0.001,
                      "mid_price": 100 + np.arange(30) * 0.01})
    w.loc[10:16, "mid_price"] = 99.0   # 7 identical prices
    w.loc[20, "y"] = -1.0             # invalid yield
    out = clean_panel(w, CFG)
    assert -1.0 not in out["y"].values
    assert len(out) < 29 and len(out) >= 29 - 4  # tail of the stale run removed
