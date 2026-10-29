"""Time-varying sovereign ratings and sub-investment-grade classification (NEXT_PROMPT task 8).

Input: data/market/sovereign_ratings.csv with columns government, agency, date, rating, source.
One row per rating action (or the rating in force at the sample start). LSEG rating-history
fields are not entitled on this login (TR.IssuerRating / TR.GR.Rating: access denied), so the
file is supplied by hand; nothing here invents ratings.

Rule (task 8b): an obligor-month is sub-IG if at least two of the three agencies rate the
government below BBB- (S&P, Fitch) / Baa3 (Moody's). With only one agency rating a government,
that agency decides, and the month is flagged `single_agency`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SP_FITCH = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
            "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D", "SD", "RD"]
MOODYS = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3",
          "Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]
AGENCIES = ("S&P", "Moody's", "Fitch")
NOT_RATED = {"NR", "WR", "WD", ""}   # agency does not rate the government (from that date): not counted

# obligor (parent_key) -> government whose rating applies (owners for state companies)
ISSUER_GOVERNMENT = {
    "arabia kingdom saudi": "KSA", "arabian oil saudi": "KSA", "fund investment public": "KSA",
    "bank national saudi": "KSA", "banque fransi saudi": "KSA",
    "bahrain kingdom": "Bahrain", "bapco energies": "Bahrain",
    "oman sultanate": "Oman", "electricity oman transmission": "Oman",
    "qatar state": "Qatar",
    "abu bank dhabi first": "Abu Dhabi", "diversified global holding mamoura": "Abu Dhabi",
    "dubai emirate": "Dubai", "dubai investment": "Dubai", "dp world": "Dubai",
    "aerospace dae dubai enterprise": "Dubai",
    "emirate sharjah": "Sharjah",
}
GOVERNMENTS = ["Oman", "Bahrain", "Sharjah", "KSA", "Qatar", "Abu Dhabi", "Dubai", "Kuwait"]


def is_sub_ig(agency: str, rating: str) -> bool | None:
    """True if the rating is below investment grade on that agency's scale (outlook suffixes ignored);
    None if the agency does not rate the government (NR / WR / WD)."""
    r = str(rating).strip().split()[0].rstrip("*") if str(rating).strip() else ""
    if r in NOT_RATED or r.lower() == "nan":
        return None
    if agency == "Moody's":
        if r not in MOODYS:
            raise ValueError(f"Unknown Moody's rating {rating!r}")
        return MOODYS.index(r) > MOODYS.index("Baa3")
    if r not in SP_FITCH:
        raise ValueError(f"Unknown {agency} rating {rating!r}")
    return SP_FITCH.index(r) > SP_FITCH.index("BBB-")


def load_ratings(path: Path) -> pd.DataFrame:
    r = pd.read_csv(path, parse_dates=["date"])
    need = {"government", "agency", "date", "rating", "source"}
    missing = need - set(r.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns {sorted(missing)}")
    bad = set(r["agency"]) - set(AGENCIES)
    if bad:
        raise ValueError(f"Unknown agencies {bad}; use {AGENCIES}")
    r["sub_ig"] = [is_sub_ig(a, x) for a, x in zip(r["agency"], r["rating"])]
    return r.sort_values(["government", "agency", "date"]).reset_index(drop=True)


def monthly_status(ratings: pd.DataFrame, months: pd.PeriodIndex) -> pd.DataFrame:
    """government x month: agencies rating, agencies below IG, and the 2-of-3 sub-IG flag.

    Each agency's rating is carried forward from its action date. A rating action applies from the
    month *after* it is published (so the month of the action is not treated as already re-rated);
    a rating dated on the 1st of a month (the rating in force at the sample start) applies that month."""
    rows = []
    for gov, g in ratings.groupby("government"):
        status = {}
        for ag, a in g.groupby("agency"):
            # encode: 1 = below IG, 0 = IG, -1 = not rated; carry forward, then -1 -> missing,
            # so a withdrawal (NR) ends the agency's previous rating instead of being skipped over
            code = a["sub_ig"].map(lambda v: -1.0 if v is None or pd.isna(v) else float(bool(v)))
            # dated on the 1st (e.g. the rating in force at the sample start) -> applies that month;
            # any other date -> applies from the following month
            start = a["date"].dt.to_period("M") + (a["date"].dt.day > 1).astype(int).values
            s = pd.Series(code.values, index=pd.PeriodIndex(start, freq="M"))
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s = s.reindex(months.union(s.index)).ffill().reindex(months)
            status[ag] = s.where(s >= 0)
        df = pd.DataFrame(status, index=months)
        n_rated = df.notna().sum(axis=1)
        n_below = (df == 1).sum(axis=1)
        sub = np.where(n_rated >= 2, n_below >= 2, np.where(n_rated == 1, n_below == 1, np.nan))
        rows.append(pd.DataFrame({"government": gov, "month": months, "agencies_rating": n_rated.values,
                                  "agencies_below_ig": n_below.values, "sub_ig": sub,
                                  "single_agency": (n_rated == 1).values}))
    return pd.concat(rows, ignore_index=True)


def template(path: Path, oman_known: list[tuple[str, str, str]]) -> None:
    """Write a fill-in template: one row per government x agency for the start-of-sample rating, plus
    the known Oman actions supplied by the user."""
    rows = [{"government": g, "agency": a, "date": "2016-01-01", "rating": "", "source": ""}
            for g in GOVERNMENTS for a in AGENCIES]
    rows += [{"government": "Oman", "agency": a, "date": d, "rating": r, "source": "supplied by user"}
             for a, d, r in oman_known]
    pd.DataFrame(rows).to_csv(path, index=False)
