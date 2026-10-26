import numpy as np
import pandas as pd

from src.shocks import detect_shocks, shock_scores

CFG = {"oil_ric": "OIL", "equity_ric": "EQ", "horizon_days": 1, "z": 3.0, "vol_window": 60,
       "net_of_equity": True, "cluster_days": 20, "start": "2000-01-01"}


def _market(oil_jumps: dict, eq_jumps: dict | None = None, n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    r_eq = rng.normal(0, 0.01, n)
    for i, j in (eq_jumps or {}).items():
        r_eq[i] += j
    r_oil = 1.0 * r_eq + rng.normal(0, 0.004, n)  # oil normally co-moves with equity (beta ~1)
    for i, j in oil_jumps.items():
        r_oil[i] += j
    return pd.DataFrame({"OIL": 60 * np.exp(np.cumsum(r_oil)), "EQ": 3000 * np.exp(np.cumsum(r_eq))}, index=idx)


def test_detects_isolated_jump_with_sign():
    s = detect_shocks(shock_scores(_market({200: 0.08, 300: -0.08}), CFG), CFG)
    assert list(s["sign"]) == ["up", "down"]
    assert list(s["date"]) == list(pd.bdate_range("2020-01-01", periods=400)[[200, 300]])


def test_cluster_keeps_largest_move_not_first():
    s = detect_shocks(shock_scores(_market({200: 0.05, 205: 0.10}), CFG), CFG)
    assert len(s) == 1
    assert s.iloc[0]["date"] == pd.bdate_range("2020-01-01", periods=400)[205]


def test_spaced_shocks_do_not_chain_into_one_episode():
    # 18 trading days apart each: chaining would merge all three into one.
    idx = pd.bdate_range("2020-01-01", periods=400)
    s = detect_shocks(shock_scores(_market({200: -0.06, 218: 0.10, 236: -0.06}), CFG), CFG)
    assert idx[218] in list(s["date"]) and (s["sign"] == "up").any()


def test_equity_driven_day_is_not_an_oil_shock():
    s = detect_shocks(shock_scores(_market({}, {250: 0.08}), CFG), CFG)
    assert len(s) == 0
    gross = detect_shocks(shock_scores(_market({}, {250: 0.08}), {**CFG, "net_of_equity": False}),
                          {**CFG, "net_of_equity": False})
    assert pd.bdate_range("2020-01-01", periods=400)[250] in list(gross["date"])


def test_minimum_move_size_is_required():
    # A 3% jump is a big z in this low-vol series but fails a 5% size floor.
    m = _market({200: 0.03})
    assert len(detect_shocks(shock_scores(m, CFG), {**CFG, "min_abs_ret_pct": 0.0})) >= 1
    assert len(detect_shocks(shock_scores(m, CFG), {**CFG, "min_abs_ret_pct": 5.0})) == 0


def test_shock_day_excluded_from_its_own_volatility():
    sc = shock_scores(_market({200: 0.08}), CFG)
    day = pd.bdate_range("2020-01-01", periods=400)[200]
    assert sc.loc[day, "z"] > 5  # a jump included in its own sd would shrink the z-score
