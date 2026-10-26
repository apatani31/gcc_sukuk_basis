import numpy as np
import pandas as pd
import pytest

from src.event_study import across_events, bond_paths, build_episodes, event_means


def _obs(dates, basis, y_s, y_c, iid="S1", key="k"):
    return pd.DataFrame({"parent_key": key, "parent_name": key, "sovereign": False, "instrument_id": iid,
                         "date": dates, "basis_bp": basis, "y_sukuk": y_s, "y_conv": y_c,
                         "match_method": "interp"})


def test_changes_are_vs_own_pre_shock_baseline_in_bp():
    d = pd.bdate_range("2024-01-01", periods=40)
    shock = d[10]
    y_c = np.full(40, 5.00)
    y_s = np.full(40, 4.90)
    y_c[10:] = 5.30   # conventional +30bp on the shock day
    y_s[10:] = 5.10   # sukuk +20bp
    obs = _obs(d, (y_s - y_c) * 100, y_s, y_c)
    p = bond_paths(obs, pd.DataFrame({"event_id": ["e"], "date": [shock]}), pre=5, post=20)
    at0 = p[p["tau"] == 0].iloc[0]
    assert at0["d_conv"] == pytest.approx(30) and at0["d_sukuk"] == pytest.approx(20)
    assert at0["d_basis"] == pytest.approx(-10)  # sukuk outperformed
    assert p["tau"].min() == -5 and p["tau"].max() == 20
    assert p.loc[p["tau"] < 0, "d_basis"].abs().max() == pytest.approx(0)


def test_each_shock_weighs_equally_regardless_of_issuer_count():
    d = pd.bdate_range("2024-01-01", periods=80)
    e1, e2 = d[10], d[50]
    rows = []
    # event 1: one issuer, basis -40 after shock; event 2: three issuers, basis 0
    rows.append(_obs(d, np.where(d >= e1, -40.0, 0.0), 5, 5, iid="A", key="a"))
    for k in "bcd":
        rows.append(_obs(d, np.zeros(80), 5, 5, iid=k.upper(), key=k))
    obs = pd.concat(rows)
    obs = obs[~((obs["parent_key"] != "a") & (obs["date"] < d[40]))]  # b,c,d only around event 2
    obs = obs[~((obs["parent_key"] == "a") & (obs["date"] >= d[40]))]
    ev = event_means(bond_paths(obs, pd.DataFrame({"event_id": ["e1", "e2"], "date": [e1, e2]}), 5, 20))
    agg = across_events(ev).set_index("tau")
    assert agg.loc[5, "d_basis_mean"] == pytest.approx(-20)  # (-40 + 0) / 2, not (-40 + 0*3) / 4
    assert agg.loc[5, "n_shocks"] == 2


def test_passthrough_recovers_damping_slope():
    from src.event_study import passthrough
    rng = np.random.default_rng(1)
    d = pd.bdate_range("2023-01-01", periods=300)
    y_c = 5 + np.cumsum(rng.normal(0, 0.03, 300))
    y_s = 4.9 + 0.7 * (y_c - 5) + rng.normal(0, 0.002, 300)   # sukuk = 0.7 x conventional moves
    obs = _obs(d, (y_s - y_c) * 100, y_s, y_c)
    shocks = pd.DataFrame({"event_id": ["e1", "e2", "e3"], "date": d[[60, 150, 240]]})
    paths = bond_paths(obs, shocks, 5, 20)
    pt = passthrough(paths, obs, shocks["date"], horizon=5, n_boot=50)
    assert pt.loc[pt["sample"] == "All shocks", "beta_normal"].iloc[0] == pytest.approx(0.7, abs=0.05)


def test_method_switch_inside_window_is_dropped():
    d = pd.bdate_range("2024-01-01", periods=40)
    obs = _obs(d, np.zeros(40), np.full(40, 5.0), np.full(40, 5.0))
    obs.loc[obs.index[15:], "match_method"] = "nearest_adj"   # switches after the shock (day 10)
    obs.loc[obs.index[15:], "y_conv"] = 5.4                   # would look like a +40bp jump
    p = bond_paths(obs, pd.DataFrame({"event_id": ["e"], "date": [d[10]]}), 5, 20)
    assert p["tau"].max() == 4 and p["d_conv"].abs().max() == 0


def test_episodes_chain_close_shocks_only():
    s = pd.DataFrame({"date": pd.to_datetime(["2022-03-01", "2022-03-09", "2022-08-01"]),
                      "sign": ["up", "down", "down"]})
    e = build_episodes(s, link_bdays=20)
    assert list(e["episode"]) == [1, 1, 2]
