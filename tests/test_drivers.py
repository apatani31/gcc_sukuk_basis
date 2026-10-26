import numpy as np
import pandas as pd
import pytest

from src.drivers import basis_matrix, issuance_monthly, pca


def test_pca_finds_a_planted_common_factor_with_positive_sign():
    rng = np.random.default_rng(0)
    f = np.cumsum(rng.normal(0, 1, 120))
    idx = pd.period_range("2016-01", periods=120, freq="M")
    x = pd.DataFrame({f"i{k}": 2 * f + rng.normal(0, 0.5, 120) for k in range(5)}, index=idx)
    res = pca(x)
    assert res["share"]["PC1"] > 0.9
    assert (res["loadings"]["PC1"] > 0).all()
    assert np.corrcoef(res["scores"]["PC1"], f)[0, 1] > 0.95


def test_basis_matrix_keeps_covered_issuers_and_fills_short_gaps():
    months = pd.period_range("2022-01", periods=12, freq="M")
    rows = [{"month": m, "parent_name": "A", "basis": float(i)} for i, m in enumerate(months) if i != 5]
    rows += [{"month": m, "parent_name": "B", "basis": 1.0} for m in months[:4]]  # 33% coverage: dropped
    w = basis_matrix(pd.DataFrame(rows), "2022-01", "2022-12", min_coverage=0.8)
    assert list(w.columns) == ["A"] and len(w) == 12
    assert w.loc[pd.Period("2022-06", "M"), "A"] == pytest.approx(5.0)  # interpolated gap


def test_issuance_trailing_12m_and_share():
    u = pd.DataFrame({
        "instrument_class": "bond", "is_primary_line": True, "possible_sukuk_mislabel": False,
        "country_of_risk": "Oman", "is_sukuk": [True, False, True],
        "issue_date": pd.to_datetime(["2024-01-15", "2024-06-15", "2025-03-15"]),
        "amount_issued_usd": [1e9, 3e9, 2e9]})
    m = issuance_monthly(u).set_index("month")
    assert m.loc[pd.Period("2024-06", "M"), "sukuk_12m_bn"] == pytest.approx(1.0)
    assert m.loc[pd.Period("2024-06", "M"), "sukuk_share_12m"] == pytest.approx(0.25)
    assert m.loc[pd.Period("2025-03", "M"), "sukuk_12m_bn"] == pytest.approx(2.0)  # Jan-2024 issue rolled off
