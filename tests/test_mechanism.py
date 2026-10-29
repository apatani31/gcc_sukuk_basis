import numpy as np
import pandas as pd
import pytest

from src.mechanism import hinge, issuer_ratings, spline_profile, structure_tables


def test_spline_profile_recovers_planted_kink():
    rng = np.random.default_rng(1)
    cds = rng.uniform(30, 300, 400)
    basis = -5 - 40 * np.maximum(cds - 150, 0) / 100 + rng.normal(0, 2, 400)
    d = pd.DataFrame({"cds": cds, "cds100": cds / 100, "basis": basis, "parent_key": "a"})
    p = spline_profile(d, range(60, 260, 10), fe=False, min_side=20)
    best = p[p["best"]].iloc[0]
    assert best.kink_bp == pytest.approx(150, abs=10)
    assert best.slope_above_per_100bp == pytest.approx(-40, abs=4)
    assert abs(best.slope_below_per_100bp) < 4


def test_hinge():
    assert list(hinge(pd.Series([50.0, 150.0, 250.0]), 100)) == [0.0, 50.0, 150.0]


def test_issuer_ratings_moodys_then_bond_grade_fallback():
    u = pd.DataFrame({
        "parent_key": ["a", "a", "b", "c"], "instrument_class": "bond",
        "moodys_issuer_rating": ["B2", "WR", None, None], "moodys_issue_rating": ["B2", None, "Aa3", None],
        "bond_grade": [None, None, None, "High Yield"]})
    r = issuer_ratings(u, ["a", "b", "c"]).set_index("parent_key")
    assert r.loc["a", "sub_ig"] and not r.loc["b", "sub_ig"] and r.loc["c", "sub_ig"]
    assert r.loc["c", "rating_source"] == "LSEG bond grade"


def test_structure_within_issuer_is_relative_to_issuer_mean():
    bm = pd.DataFrame({"instrument_id": ["s1", "s2", "s3"], "parent_name": ["X", "X", "Y"],
                       "structure": ["Ijara", "Hybrid Sukuk", "Ijara"], "basis": [-30.0, -10.0, -50.0]})
    overall, within = structure_tables(bm)
    w = within.set_index("structure")
    assert list(within["parent_name"].unique()) == ["X"]          # Y uses one structure only
    assert w.loc["Ijara", "vs_issuer_mean_bp"] == pytest.approx(-10)
