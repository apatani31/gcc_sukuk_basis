import pandas as pd
import pytest

from src.robustness import bullet_modified_duration, duration_ratio, permutation_test, structure_table


def panel(means: dict[str, float], treated=("A", "B")) -> pd.DataFrame:
    return pd.DataFrame([{"government": g, "basis": b, "sub": float(g in treated)} for g, b in means.items()])


def test_permutation_most_extreme_pair_gets_the_floor_p():
    s, t = permutation_test(panel({"A": -70, "B": -50, "C": -5, "D": -4, "E": -3, "F": -2, "G": -1}))
    assert s["assignments"] == 21
    assert s["p_two_sided"] == s["smallest_possible_p"] == pytest.approx(1 / 21, abs=1e-3)
    assert t.iloc[0]["governments"] == "A + B"
    assert s["difference_bp"] == pytest.approx(-60 - (-3))


def test_permutation_not_extreme_when_labels_are_uninformative():
    s, _ = permutation_test(panel({"A": -3, "B": -4, "C": -70, "D": -50, "E": -5, "F": -2, "G": -1}))
    assert s["p_two_sided"] > 0.5


def test_bullet_duration_zero_coupon_and_par():
    assert bullet_modified_duration(0.0, 4.0, 5.0) == pytest.approx(5 / 1.02)
    # one period left: the only cash flow is at maturity
    assert bullet_modified_duration(4.0, 4.0, 0.5) == pytest.approx(0.5 / 1.02)
    assert bullet_modified_duration(5.0, 5.0, 10.0) == pytest.approx(7.79, abs=0.01)   # textbook par bond


def test_duration_ratio_and_structure_table_separate_an_amortiser():
    bonds = pd.DataFrame({"isin": ["BUL", "AMO", "OLD"], "coupon_rate": [5.0, 5.0, 5.0], "mid_yield": [5.0, float("nan"), 5.0],
                          "maturity_date": pd.to_datetime(["2036-01-01", "2036-01-01", "2026-06-01"])})
    bul = bullet_modified_duration(5.0, 5.0, 10.0)
    flags = pd.DataFrame({"isin": ["BUL", "AMO", "OLD"], "is_sinkable": pd.array([False, True, False], dtype="boolean"),
                          "is_callable": pd.array([False, False, True], dtype="boolean"),
                          "is_putable": pd.array([False, False, False], dtype="boolean"),
                          "mod_duration": [bul, bul * 0.6, 0.4], "md_date": pd.to_datetime(["2026-01-01"] * 3)})
    r = duration_ratio(bonds.merge(flags, on="isin"))
    assert list(r["isin"]) == ["BUL", "AMO"]                                           # under a year left is dropped
    assert r["ratio"].iloc[0] == pytest.approx(1.0, abs=0.01) and r["ratio"].iloc[1] == pytest.approx(0.6, abs=0.01)
    row = structure_table(flags, {"all": bonds}).iloc[0]
    assert (row.bonds, row.sinkable, row.callable, row.duration_tested) == (3, 1, 1, 2)
