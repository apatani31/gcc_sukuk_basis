"""How far the sub-IG result reaches: bond structure and dependence on individual governments.

structure_table compares LSEG's sinkable/callable flags and modified duration with a bullet bond of the
same coupon and maturity: an amortising sukuk matched on final maturity would look rich on an upward-sloping
curve, which is the pattern the sub-IG result reports. The other functions rerun the level gap (issuer-month
basis on the sub-IG flag, clustered by obligor group) leaving out governments, periods and bonds, and run an
exact permutation test over which governments are labelled sub-IG.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .config import TWIN
from .inference import wild_cluster_bootstrap
from .mechanism import add_rating_flags


def level_panel(basis: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Issuer-month mean basis with the MAIN rating flag (`sub`); unrated obligors dropped."""
    x = basis[basis["match_method"].isin(TWIN["main_methods"])].copy()
    x["month"] = x["date"].dt.strftime("%Y-%m")
    m = x.groupby(["parent_key", "month"])["basis_bp"].mean().rename("basis").reset_index()
    m = add_rating_flags(m, ratings).dropna(subset=["sub_rating"])
    return m.assign(sub=m["sub_rating"].astype(float))


def gap_row(m: pd.DataFrame, label: str, B: int = 9999) -> dict:
    w = wild_cluster_bootstrap("basis ~ sub", m, "sub", "government", B=B)
    return {"sample": label, "sub_ig_mean_bp": round(m.loc[m["sub"] == 1, "basis"].mean(), 1),
            "ig_mean_bp": round(m.loc[m["sub"] == 0, "basis"].mean(), 1), "gap_bp": round(w["coef"], 1),
            "p_wild_government": round(w["p_wild"], 4), "obligor_months": w["n_obs"], "governments": w["clusters"],
            "sub_ig_governments": m.loc[m["sub"] == 1, "government"].nunique()}


def leave_one_government_out(m: pd.DataFrame, B: int = 9999) -> pd.DataFrame:
    return pd.DataFrame([gap_row(m[m["government"] != g], f"Without {g}", B) for g in sorted(m["government"].unique())])


def period_splits(m: pd.DataFrame, B: int = 9999) -> pd.DataFrame:
    cuts = (("Before 2021", m["month"] < "2021"), ("2021 onward", m["month"] >= "2021"),
            ("2023 onward", m["month"] >= "2023"), ("Excluding 2020", ~m["month"].str.startswith("2020")))
    return pd.DataFrame([gap_row(m[mask], label, B) for label, mask in cuts])


def permutation_test(m: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Exact test: compare the governments ever sub-IG with every same-sized set of governments.

    The statistic is the unweighted mean of the labelled governments' mean basis minus that of the others, so
    each government counts once however many months it has. The smallest attainable p is 1 / assignments."""
    means = m.groupby("government")["basis"].mean()
    treated = sorted(m.loc[m["sub"] == 1, "government"].unique())
    rows = [{"governments": " + ".join(c), "difference_bp": means[list(c)].mean() - means.drop(list(c)).mean()}
            for c in combinations(means.index, len(treated))]
    t = pd.DataFrame(rows).sort_values("difference_bp").reset_index(drop=True)
    stat = means[treated].mean() - means.drop(treated).mean()
    p = float((t["difference_bp"].abs() >= abs(stat) - 1e-9).mean())
    summary = {"sub_ig_governments": " + ".join(treated), "governments": len(means), "assignments": len(t),
               "difference_bp": round(stat, 1), "p_two_sided": round(p, 3), "smallest_possible_p": round(1 / len(t), 3)}
    return summary, t.assign(difference_bp=t["difference_bp"].round(1))


def bullet_modified_duration(coupon: float, yld: float, years: float, freq: int = 2) -> float:
    """Modified duration of a bullet bond (coupon and yield in percent, `years` to maturity)."""
    if not years > 0 or pd.isna(coupon) or pd.isna(yld):
        return np.nan
    t = years - np.arange(int(np.ceil(years * freq))) / freq
    t = t[t > 0]
    df = (1 + yld / 100 / freq) ** (-t * freq)
    cash = np.full(len(t), coupon / freq)
    cash[0] += 100                                    # t[0] is the maturity date
    return float((cash * df * t).sum() / (cash * df).sum() / (1 + yld / 100 / freq))


def duration_ratio(b: pd.DataFrame, min_years: float = 1.0) -> pd.DataFrame:
    """Add `ratio` = LSEG modified duration / bullet duration for bonds with `min_years` left.

    Needs columns mod_duration, md_date, maturity_date, coupon_rate, mid_yield (coupon used if no yield)."""
    d = b.dropna(subset=["mod_duration", "md_date"]).copy()
    years = (pd.to_datetime(d["maturity_date"]) - pd.to_datetime(d["md_date"])).dt.days / 365.25
    yld = d["mid_yield"].fillna(d["coupon_rate"])
    d["bullet"] = [bullet_modified_duration(c, y, t) for c, y, t in zip(d["coupon_rate"], yld, years)]
    d["ratio"] = d["mod_duration"].astype(float) / d["bullet"]
    return d[years > min_years].dropna(subset=["ratio"])


def structure_table(flags: pd.DataFrame, groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per group of bonds. `flags`: isin, is_sinkable, is_callable, is_putable, mod_duration, md_date."""
    rows = []
    for label, bonds in groups.items():
        b = bonds.merge(flags, on="isin", how="left")
        r = duration_ratio(b)
        rows.append({"group": label, "bonds": len(b), "flag_found": int(b["is_sinkable"].notna().sum()),
                     "sinkable": int((b["is_sinkable"] == True).sum()),  # noqa: E712 (nullable booleans)
                     "callable": int((b["is_callable"] == True).sum()),  # noqa: E712
                     "putable": int((b["is_putable"] == True).sum()),  # noqa: E712
                     "duration_tested": len(r), "ratio_min": round(r["ratio"].min(), 3) if len(r) else np.nan,
                     "ratio_median": round(r["ratio"].median(), 3) if len(r) else np.nan,
                     "ratio_max": round(r["ratio"].max(), 3) if len(r) else np.nan})
    return pd.DataFrame(rows)
