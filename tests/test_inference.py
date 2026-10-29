import numpy as np
import pandas as pd
import pytest

from src.inference import WEBB, fmt_p, holm, issuer_slopes, wild_cluster_bootstrap


def test_holm_matches_hand_calculation():
    # sorted p: 0.01, 0.02, 0.04, 0.30 -> x4, x3, x2, x1 = 0.04, 0.06, 0.08, 0.30 (monotone)
    assert holm([0.04, 0.01, 0.30, 0.02]) == pytest.approx([0.08, 0.04, 0.30, 0.06])
    assert holm([0.5, 0.6]).max() <= 1.0


def test_fmt_p():
    assert fmt_p(0.0) == "< 0.001" and fmt_p(0.0153) == "0.015"


def test_webb_weights_have_mean_zero_unit_variance():
    assert WEBB.mean() == pytest.approx(0)
    assert (WEBB ** 2).mean() == pytest.approx(1)


def _panel(beta, G=6, per=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(G):
        common = rng.normal(0, 1, per)            # cluster-level shock: makes iid SEs too small
        x = rng.normal(0, 1, per) + rng.normal(0, 1)
        y = beta * x + 2.0 * g + common + rng.normal(0, 0.5, per)
        rows.append(pd.DataFrame({"y": y, "x": x, "gov": f"g{g}"}))
    return pd.concat(rows, ignore_index=True)


def test_matches_ols_coefficient_and_rejects_strong_effect():
    d = _panel(beta=1.0)
    r = wild_cluster_bootstrap("y ~ x + C(gov)", d, "x", "gov", B=999)
    ols = np.polyfit(d["x"] - d.groupby("gov")["x"].transform("mean"),
                     d["y"] - d.groupby("gov")["y"].transform("mean"), 1)[0]
    assert r["coef"] == pytest.approx(ols, rel=1e-8)
    assert r["clusters"] == 6 and r["p_wild"] < 0.05


def test_null_p_values_are_not_systematically_small():
    ps = [wild_cluster_bootstrap("y ~ x + C(gov)", _panel(beta=0.0, seed=s), "x", "gov", B=199, seed=s)["p_wild"]
          for s in range(30)]
    assert np.mean(np.array(ps) < 0.05) <= 0.2   # nominal 5%; generous bound for 30 draws
    assert np.median(ps) > 0.25


def test_issuer_slopes_levels_and_changes():
    months = pd.period_range("2020-01", periods=30, freq="M")
    cds = np.linspace(100, 300, 30)
    p = pd.DataFrame({"parent_name": "A", "cds_sovereign": "X", "month": months, "cds": cds,
                      "basis": -0.3 * cds + np.sin(np.arange(30))})
    r = issuer_slopes(p).iloc[0]
    assert r["slope_levels_per_100bp"] == pytest.approx(-30, abs=2)
    assert r["months"] == 30
