"""Load the security universe from the Workspace "Search Results" exports.

Replaces the ld.discovery.search step: the universe comes from the exported
xlsx files. This module normalizes columns, tags sukuk vs conventional,
de-duplicates across files, separates bonds from money-market paper, groups
RegS/144A lines of the same bond, and derives the issuer-parent matching key.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    BOND_INSTRUMENT_TYPES, CURRENCY_LABELS, EXPORT_SHEET, MONEY_MARKET_INSTRUMENT_TYPES,
)

log = logging.getLogger(__name__)

# Export header -> pipeline column name. Ratings come as (value, type) pairs in
# the export; the second header row labels the type column "Actual".
COLUMN_MAP = {
    "Issuer": "issuer_name",
    "Ticker": "ticker",
    "Coupon": "coupon_rate",
    "Maturity": "maturity_date",
    "Issue Date": "issue_date",
    "ISIN": "isin",
    "Preferred RIC": "ric",
    "Principal Currency": "currency",
    "Country of Issue": "country_of_issue",
    "Issuer Type": "issuer_type",
    "Instrument Type": "instrument_type",
    "Coupon Type": "coupon_type",
    "Amount Issued (USD)": "amount_issued_usd",
    "Bond Grade": "bond_grade",
    "Borrower Country": "borrower_country",
    "Borrower": "borrower",
    "Sukuk Structure Type": "sukuk_structure_type",
    "Sukuk Obligor": "sukuk_obligor",
    "Seniority": "seniority",
    "TRBC Sector": "trbc_sector",
    "Domicile": "domicile",
    "Parent Domicile": "parent_domicile",
    "Coupon Frequency": "coupon_frequency",
    "Issue Price": "issue_price",
    "Country of Risk": "country_of_risk",
    "Sukuk Country of Risk": "sukuk_country_of_risk",
    "Moody's Long-term Issuer Rating": "moodys_issuer_rating",
    "Fitch Long-term Issuer Rating": "fitch_issuer_rating",
    "Moody's Long-term Issue Credit Rating": "moodys_issue_rating",
}
RATING_COLS = ["moodys_issuer_rating", "fitch_issuer_rating", "moodys_issue_rating"]
DATE_COLS = ["issue_date", "maturity_date"]
NUMERIC_COLS = ["coupon_rate", "amount_issued_usd", "issue_price"]

# Fields requested in the original brief that the export does not carry.
UNAVAILABLE_FIELDS = {
    "day_count_basis": "Not in export. Computed yields assume 30/360 (USD Eurobond convention).",
    "ultimate_parent": "Not in export. Proxy: parent_name = Sukuk Obligor, else Borrower, else Issuer.",
    "yield_at_issue": "Not in export. Computed in yield_calc (see yield_at_issue_source).",
    "active_matured_status": "Not in export. Derived: status_derived = matured if maturity < run date.",
    "domicile": "Available as 'Domicile'.",
}


def _read_export(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=EXPORT_SHEET, header=None, dtype=object)
    header = raw.iloc[0].tolist()
    cols, last = [], None
    for i, h in enumerate(header):
        if isinstance(h, str) and h.strip():
            last = h.strip()
            cols.append(last)
        elif last and "Rating" in last:
            cols.append(f"{last}__type")  # the "Actual" column after each rating
        else:
            cols.append(f"__blank{i}")
    df = raw.iloc[2:].copy()  # rows 0-1 are the two-line header
    df.columns = cols
    df = df.loc[:, [c for c in cols if not c.startswith("__blank")]]
    df = df.dropna(how="all")
    unknown = [c for c in df.columns if c not in COLUMN_MAP and not c.endswith("__type")]
    if unknown:
        log.warning("%s: unmapped columns kept as-is: %s", path.name, unknown)
    rename = dict(COLUMN_MAP)
    rename.update({f"{k}__type": f"{v}_type" for k, v in COLUMN_MAP.items() if "Rating" in k})
    df = df.rename(columns=rename)
    df["source_file"] = path.name
    log.info("Read %s: %d rows", path.name, len(df))
    return df


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.mask(df.isin(["--", ""]))
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    obj_cols = [c for c in df.columns if c not in DATE_COLS + NUMERIC_COLS and c != "is_sukuk"]
    for c in obj_cols:
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else (np.nan if pd.isna(v) else str(v)))
    return df


_LEGAL_SUFFIXES = {
    "pjsc", "qpsc", "qsc", "qscp", "sjsc", "scjsc", "kscp", "ksc", "kpsc", "bsc", "saog", "saoc", "spc",
    "llc", "ltd", "limited", "plc", "co", "company", "corp", "corporation", "inc", "the", "of", "and",
    "government", "psc", "pjs", "cjsc", "jsc", "sa", "c", "closed", "qspc", "qpjsc", "sakp", "sak",
    "kscc", "kpscc", "wll", "bscc", "spv",
}


def parent_key(name: object) -> str | float:
    """Order-insensitive normalized name so 'Sharjah, Emirate Of' == 'Emirate of Sharjah'."""
    if not isinstance(name, str) or not name.strip():
        return np.nan
    tokens = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace(".", "")).split()
    tokens = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(sorted(tokens)) if tokens else np.nan


def _instrument_class(row: pd.Series) -> str:
    if row["is_sukuk"]:
        return "bond"
    it = row["instrument_type"]
    if it in BOND_INSTRUMENT_TYPES:
        return "bond"
    if it in MONEY_MARKET_INSTRUMENT_TYPES:
        return "money_market"
    return "other"


def _instrument_id(df: pd.DataFrame) -> pd.Series:
    # CP/CD programmes reuse ISINs across issues, so ISIN alone is not unique.
    base = df["isin"].fillna(df["ric"]).fillna(
        df["ticker"].fillna("NA") + "|" + df["coupon_rate"].astype(str)
    )
    iid = base + "|" + df["issue_date"].dt.strftime("%Y%m%d").fillna("NA")
    dup = iid.duplicated(keep=False)
    iid[dup] = iid[dup] + "|" + df.loc[dup, "maturity_date"].dt.strftime("%Y%m%d").fillna("PERP")
    return iid


def load_universe(sukuk_files: list[Path], conv_files: list[Path]) -> pd.DataFrame:
    frames = []
    for files, is_sukuk in ((sukuk_files, True), (conv_files, False)):
        for f in files:
            d = _read_export(Path(f))
            d["is_sukuk"] = is_sukuk
            frames.append(d)
    raw_total = sum(len(f) for f in frames)
    df = _clean(pd.concat(frames, ignore_index=True))

    key = ["isin", "ric", "issue_date", "maturity_date", "coupon_rate", "issuer_name", "is_sukuk"]
    n_dups = int(df.duplicated(subset=key).sum())
    df = df.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    assert len(df) == raw_total - n_dups, "row accounting mismatch after de-duplication"
    log.info("Combined %d raw rows, dropped %d exact cross-file duplicates -> %d", raw_total, n_dups, len(df))

    clash = set(df.loc[df.is_sukuk, "isin"].dropna()) & set(df.loc[~df.is_sukuk, "isin"].dropna())
    if clash:
        log.warning("%d ISINs appear in both sukuk and conventional files: %s", len(clash), sorted(clash)[:10])

    df["instrument_id"] = _instrument_id(df)
    assert df["instrument_id"].is_unique, "instrument_id is not unique"
    df["instrument_class"] = df.apply(_instrument_class, axis=1)

    # One economic bond is often listed twice (RegS XS... and 144A US...).
    df["bond_key"] = (
        df["ticker"].fillna(df["issuer_name"]).fillna("NA") + "|"
        + df["coupon_rate"].round(4).astype(str) + "|"
        + df["issue_date"].dt.strftime("%Y%m%d").fillna("NA") + "|"
        + df["maturity_date"].dt.strftime("%Y%m%d").fillna("PERP")
    )
    pref = (
        df["isin"].fillna("").str.startswith("XS").astype(int) * 2 + df["ric"].notna().astype(int)
    )
    order = df.assign(_p=pref).sort_values(["bond_key", "_p"], ascending=[True, False])
    df["is_primary_line"] = False
    df.loc[order.drop_duplicates("bond_key").index, "is_primary_line"] = True

    df["parent_name"] = df["sukuk_obligor"].where(df["is_sukuk"], np.nan)
    df["parent_name"] = df["parent_name"].fillna(df["borrower"]).fillna(df["issuer_name"])
    df["parent_source"] = np.select(
        [df["is_sukuk"] & df["sukuk_obligor"].notna(), df["borrower"].notna()],
        ["sukuk_obligor", "borrower"], default="issuer_name",
    )
    df["parent_key"] = df["parent_name"].map(parent_key)
    df["issuer_key"] = df["issuer_name"].map(parent_key)

    # Conventional-file lines issued by sukuk vehicles but not tagged Islamic by
    # Workspace. Kept as is_sukuk=False (source label) but excluded from the
    # comparison in summary.md until reviewed by hand.
    df["possible_sukuk_mislabel"] = ~df["is_sukuk"] & (df["instrument_class"] == "bond") & (
        df["issuer_name"].str.contains(r"sukuk|ijara|islamic", case=False, na=False)
        | df["sukuk_structure_type"].notna() | df["sukuk_obligor"].notna()
    )
    if df["possible_sukuk_mislabel"].any():
        log.warning("%d conventional bond lines look like sukuk (see possible_sukuk_mislabel)",
                    int(df["possible_sukuk_mislabel"].sum()))

    df["issue_year"] = df["issue_date"].dt.year.astype("Int64")
    df["tenor_years"] = (df["maturity_date"] - df["issue_date"]).dt.days / 365.25
    today = pd.Timestamp(date.today())
    df["status_derived"] = np.where(
        df["maturity_date"].isna(), "perpetual_or_unknown",
        np.where(df["maturity_date"] < today, "matured", "active"),
    )
    df["has_rating"] = df[RATING_COLS].notna().any(axis=1)
    return df


def apply_filters(df: pd.DataFrame, currency: str, start: date, countries: list[str],
                  issue_year: int | None = None, sukuk_only: bool = False) -> pd.DataFrame:
    label = CURRENCY_LABELS.get(currency.upper(), currency)
    mask = (
        (df["currency"] == label)
        & (df["issue_date"] >= pd.Timestamp(start))
        & (df["country_of_risk"].isin(countries))
    )
    if issue_year is not None:
        mask &= df["issue_year"] == issue_year
    if sukuk_only:
        mask &= df["is_sukuk"]
    out = df[mask].copy()
    log.info("Filters currency=%s start=%s countries=%s year=%s sukuk_only=%s: %d -> %d rows",
             currency, start, len(countries), issue_year, sukuk_only, len(df), len(out))
    if out.empty:
        log.warning("No rows left after filtering. Check that the export holds %s issues.", label)
    return out


def data_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    inv = {v: k for k, v in COLUMN_MAP.items()}
    rows = []
    for c in df.columns:
        src = inv.get(c) or (inv.get(c[:-5], "") + " (rating type)" if c.endswith("_type") and c[:-5] in inv else "derived")
        rows.append({"field": c, "source": src, "status": "available",
                     "fill_rate": round(float(df[c].notna().mean()), 4), "note": ""})
    for f, note in UNAVAILABLE_FIELDS.items():
        if f"{f}_lseg" in df.columns and df[f"{f}_lseg"].notna().any():
            rows.append({"field": f, "source": f"ld.get_data ({f}_lseg)", "status": "available via LSEG",
                         "fill_rate": round(float(df[f"{f}_lseg"].notna().mean()), 4), "note": note})
        elif f not in df.columns and not note.startswith("Available"):
            rows.append({"field": f, "source": "", "status": "unavailable", "fill_rate": 0.0, "note": note})
    return pd.DataFrame(rows)
