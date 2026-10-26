"""Feasibility summary (summary.md) for the sukuk vs conventional comparison."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DEFAULT_DAY_COUNT, MIN_OBS_FLAG, SIMILAR_TENOR_YEARS, SOVEREIGNS
from .universe import RATING_COLS


def _md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_\n"
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    body = "".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |\n"
                   for r in df.itertuples(index=False))
    return head + body


def _split(df: pd.DataFrame, by: str) -> pd.DataFrame:
    t = pd.crosstab(df[by], df["is_sukuk"].map({True: "sukuk", False: "conventional"}))
    for c in ("sukuk", "conventional"):
        if c not in t:
            t[c] = 0
    t = t[["sukuk", "conventional"]]
    t["total"] = t.sum(axis=1)
    return t.reset_index()


def twin_issuers(bonds: pd.DataFrame, tol_years: float = SIMILAR_TENOR_YEARS) -> pd.DataFrame:
    rows = []
    for key, g in bonds.dropna(subset=["parent_key"]).groupby("parent_key"):
        s, c = g[g.is_sukuk], g[~g.is_sukuk]
        if s.empty or c.empty:
            continue
        sm, cm = s["maturity_date"].dropna(), c["maturity_date"].dropna()
        lo, hi = max(sm.min(), cm.min()) if len(sm) and len(cm) else pd.NaT, \
            min(sm.max(), cm.max()) if len(sm) and len(cm) else pd.NaT
        def _pairs(s_mat, c_mat) -> int:
            if not len(s_mat) or not len(c_mat):
                return 0
            diff = np.abs(s_mat.values[:, None] - c_mat.values[None, :]) / np.timedelta64(1, "D") / 365.25
            return int((diff <= tol_years).sum())

        pairs = _pairs(sm, cm)
        hist = {}
        if "has_history" in g:
            hs, hc = s[s.has_history], c[c.has_history]
            hist = {"n_sukuk_with_history": len(hs), "n_conv_with_history": len(hc),
                    "priced_tenor_pairs": _pairs(hs["maturity_date"].dropna(), hc["maturity_date"].dropna())}
        rows.append({
            "parent": g["parent_name"].mode().iat[0],
            "country": g["country_of_risk"].mode().iat[0],
            "n_sukuk": len(s), "n_conv": len(c),
            "sukuk_maturities": f"{sm.min():%Y}-{sm.max():%Y}" if len(sm) else "perp",
            "conv_maturities": f"{cm.min():%Y}-{cm.max():%Y}" if len(cm) else "perp",
            "maturity_overlap": f"{lo:%Y}-{hi:%Y}" if pd.notna(lo) and lo <= hi else "none",
            f"tenor_pairs_within_{tol_years:g}y": pairs,
            **hist,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    first = "priced_tenor_pairs" if "priced_tenor_pairs" in out else f"tenor_pairs_within_{tol_years:g}y"
    return out.sort_values([first, "n_sukuk"], ascending=False)


def sovereign_check(bonds: pd.DataFrame) -> pd.DataFrame:
    """Direct = sukuk whose obligor is the sovereign (SPV issuance is the normal
    sovereign sukuk route) or conventional bonds issued in the sovereign's own
    name. Borrower-linked lines (guaranteed entities, funding SPVs) are listed
    separately because they are not direct sovereign credit."""
    rows = []
    for name, keys in SOVEREIGNS.items():
        suk = bonds[bonds.is_sukuk & bonds["parent_key"].isin(keys)]
        conv_direct = bonds[~bonds.is_sukuk & bonds["issuer_key"].isin(keys)]
        conv_linked = bonds[~bonds.is_sukuk & bonds["parent_key"].isin(keys) & ~bonds["issuer_key"].isin(keys)]
        rows.append({
            "sovereign": name,
            "sukuk": len(suk),
            "conventional_direct": len(conv_direct),
            "both_present": "yes" if len(suk) and len(conv_direct) else "NO",
            "sukuk_issuers": "; ".join(sorted(suk["issuer_name"].unique())),
            "conventional_issuers": "; ".join(sorted(conv_direct["issuer_name"].unique())),
            "borrower_linked_not_direct": "; ".join(
                f"{k} ({v})" for k, v in conv_linked["issuer_name"].value_counts().items()),
        })
    return pd.DataFrame(rows)


def write_summary(universe: pd.DataFrame, coverage: pd.DataFrame | None, out_path: Path,
                  run_desc: str) -> None:
    mislabel = universe[universe["possible_sukuk_mislabel"]]
    bonds = universe[(universe["instrument_class"] == "bond") & ~universe["possible_sukuk_mislabel"]]
    primary = bonds[bonds["is_primary_line"]]
    L = [f"# GCC sukuk vs conventional: feasibility summary\n",
         f"Generated {date.today():%Y-%m-%d}. Run: {run_desc}\n"]

    L.append("## Universe\n")
    cls = pd.crosstab(universe["instrument_class"], universe["is_sukuk"].map({True: "sukuk", False: "conventional"}))
    L.append("All rows after filters, by instrument class (money_market = CDs and CP, excluded from the comparison):\n")
    L.append(_md(cls.reset_index()))
    L.append(f"\nBonds only: **{len(bonds)} lines**, which collapse to **{len(primary)} distinct bonds** once "
             "RegS/144A twin lines are merged (`is_primary_line`). The counts below use distinct bonds.\n")
    L.append(_md(_split(primary.assign(all="all"), "all")))
    if len(mislabel):
        L.append(f"\n**Excluded for review: {len(mislabel)} conventional-file lines that look like sukuk** "
                 "(issued by a sukuk vehicle but tagged as a plain Note/Bond, with no Islamic flag). "
                 "Flag: `possible_sukuk_mislabel`. Confirm each in Workspace and move it if needed:\n\n")
        L.append(_md(mislabel[["issuer_name", "isin", "instrument_type", "issue_date", "maturity_date",
                               "borrower"]].assign(issue_date=lambda d: d.issue_date.dt.date,
                                                   maturity_date=lambda d: d.maturity_date.dt.date)))
    L.append("\n### By country of risk\n" + _md(_split(primary, "country_of_risk")))
    L.append("\n### By issuer type\n" + _md(_split(primary, "issuer_type")))
    L.append("\nNote: Workspace tags sovereign sukuk SPVs (e.g. KSA Sukuk Ltd) as *Agency* or *Corporate*, "
             "not *Govt/Treasury*, so issuer type understates sovereign sukuk. Use the sovereign check below.\n")
    L.append("\n### By issue year\n" + _md(_split(primary, "issue_year")))

    L.append("\n## Field fill rates (distinct bonds)\n")
    fill = []
    for label, s in [("coupon_rate", primary["coupon_rate"]), ("issue_price", primary["issue_price"]),
                     ("yield_at_issue", primary["yield_at_issue"]),
                     ("coupon_frequency", primary["coupon_frequency"]),
                     ("any rating", primary[RATING_COLS].notna().any(axis=1).replace(False, np.nan)),
                     ("ric", primary["ric"])]:
        for k, grp in s.groupby(primary["is_sukuk"]):
            fill.append({"field": label, "group": "sukuk" if k else "conventional",
                         "fill_rate_%": round(100 * grp.notna().mean(), 1)})
    L.append(_md(pd.DataFrame(fill).pivot(index="field", columns="group", values="fill_rate_%").reset_index()))
    src = primary["yield_at_issue_source"].fillna("none").value_counts().to_dict()
    flags = primary["yield_at_issue_flag"].dropna().value_counts().to_dict()
    L.append(f"\nYield at issue source: {src}. Unusable cases: {flags}.\n")
    L.append(f"\n**Day count assumption:** the export has no day count field, so every computed yield "
             f"assumes **{DEFAULT_DAY_COUNT}** (US bond basis, the convention for USD Eurobonds), with "
             "settlement on the issue date and compounding at the coupon frequency. Floating, resettable, "
             "step and perpetual instruments are flagged rather than computed.\n")

    L.append("\n## Time-series coverage\n")
    if coverage is None or coverage.empty:
        L.append("History not pulled in this run (`--skip-history`, or the history step has not run yet).\n")
    else:
        cov = coverage.merge(universe[["instrument_id", "is_primary_line"]], on="instrument_id")
        cov = cov[cov["is_primary_line"]]
        rows = []
        for k, g in cov.groupby("is_sukuk"):
            rows.append({"group": "sukuk" if k else "conventional", "instruments": len(g),
                         "with_ric": int(g["has_ric"].sum()), "with_any_history": int((g["n_obs"] > 0).sum()),
                         f"lt_{MIN_OBS_FLAG}_obs": int((g["n_obs"] < MIN_OBS_FLAG).sum()),
                         "median_pct_bdays": g.loc[g["n_obs"] > 0, "pct_bdays_populated"].median()})
        L.append(_md(pd.DataFrame(rows)))

    L.append("\n## Issuers with both sukuk and conventional bonds (twin-curve candidates)\n")
    L.append("Matched on `parent_key`: Sukuk Obligor for sukuk, Borrower (else Issuer) for conventional, "
             "normalized (case, legal suffixes, word order). Ultimate parent is not in the export, so "
             "subsidiaries financed through differently named SPVs may be missed.\n\n")
    tw_in = primary
    if coverage is not None and not coverage.empty:
        n_obs = coverage.set_index("instrument_id")["n_obs"]
        tw_in = primary.assign(has_history=primary["instrument_id"].map(n_obs).fillna(0) >= MIN_OBS_FLAG)
    tw = twin_issuers(tw_in)
    pair_col = f"tenor_pairs_within_{SIMILAR_TENOR_YEARS:g}y"
    if not tw.empty:
        strong = tw[tw[pair_col] > 0]
        L.append(f"**{len(tw)} issuers** have both; **{len(strong)}** have at least one sukuk/conventional "
                 f"pair with maturities within {SIMILAR_TENOR_YEARS:g} years.")
        if "priced_tenor_pairs" in tw:
            priced = tw[tw["priced_tenor_pairs"] > 0]
            L.append(f" **{len(priced)}** still have such a pair when both bonds have at least "
                     f"{MIN_OBS_FLAG} days of price history (`priced_tenor_pairs`, sorted first). "
                     "Pair counts are bond-by-bond combinations, so issuers with many notes score high.")
        L.append("\n\n")
    L.append(_md(tw))

    L.append("\n## Direct sovereign issuance check\n")
    L.append(_md(sovereign_check(primary)))
    out_path.write_text("\n".join(L), encoding="utf-8")
