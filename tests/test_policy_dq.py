import numpy as np
import pandas as pd
import pytest

from src.data_quality import flag_off_market, reversal
from src.policy import outstanding_sukuk, savings


def test_outstanding_excludes_matured_perpetual_and_conventional():
    u = pd.DataFrame({
        "instrument_class": "bond", "is_primary_line": True, "parent_key": "k", "instrument_id": list("abcd"),
        "is_sukuk": [True, True, True, False],
        "maturity_date": pd.to_datetime(["2030-01-01", "2020-01-01", None, "2030-01-01"]),
        "amount_issued_usd": [1e9, 2e9, 5e8, 3e9]})
    o = outstanding_sukuk(u, ["k"], pd.Timestamp("2026-01-01")).iloc[0]
    assert o["outstanding_usd_bn"] == pytest.approx(1.0)
    assert o["perpetual_excluded_usd_bn"] == pytest.approx(0.5)


def test_saving_is_outstanding_times_minus_basis():
    days = pd.bdate_range("2025-06-01", "2026-05-29")
    daily = pd.DataFrame({"parent_key": "k", "parent_name": "K", "date": days, "basis_bp": -50.0})
    stats = pd.DataFrame({"issuer": ["K"], "mean_basis_bp": [-40.0], "nw_se_bp": [2.0]})
    out = pd.DataFrame({"parent_key": ["k"], "outstanding_usd_bn": [2.0]})
    s = savings(daily, stats, out, pd.Timestamp("2026-05-29")).iloc[0]
    assert s["saving_12m_usd_m"] == pytest.approx(10.0)     # USD 2bn x 50bp = USD 10m a year
    assert s["saving_full_usd_m"] == pytest.approx(8.0)


def test_off_market_flag():
    n = flag_off_market(pd.DataFrame({"nip_bp": [-620.0, 15.0, np.nan]}))
    assert list(n["off_market"]) == [True, False, False]


def test_reversal_finds_persistent_effect():
    rng = np.random.default_rng(0)
    months = pd.period_range("2018-01", periods=90, freq="M")
    cds = 200 + np.cumsum(rng.normal(0, 20, 90))
    basis = -0.3 * cds + rng.normal(0, 2, 90)                 # permanent effect: nothing reverses
    p = pd.DataFrame({"parent_key": "k", "month": months.astype(str), "basis": basis, "cds": cds})
    r = reversal(p, {"all": lambda d: d["parent_key"].notna()}).iloc[0]
    assert r["same_month_per_100bp"] == pytest.approx(-30, abs=3)
    assert abs(r["share_reversed"]) < 0.2
