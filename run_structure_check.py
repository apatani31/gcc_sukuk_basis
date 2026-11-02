"""Pull bond-structure flags and modified duration from LSEG for the amortisation check (LSEG calls).

The TR.Fi* structure fields are denied on this login, so the sinkable, callable and putable flags come from
the Search API and modified duration from TR.ModifiedDuration. Output stays local (data/ is gitignored);
run_robustness.py publishes only summary counts. Covers every bond in the twin panel, plus the sukuk of the
excluded amortising issuer (Emirates) as a positive control.

Usage:
    .venv\\Scripts\\python run_structure_check.py --session platform
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from src import config as C
from src.session import call_api, ld, lseg_session

log = logging.getLogger("run_structure_check")
CHUNK = 50


def pull(isins: list[str]) -> pd.DataFrame:
    flags, dur = [], []
    for i in range(0, len(isins), CHUNK):
        batch = isins[i:i + CHUNK]
        quoted = " ".join(f"'{x}'" for x in batch)
        flags.append(call_api(ld.discovery.search, view=ld.discovery.Views.GOV_CORP_INSTRUMENTS,
                              filter=f"ISIN in ({quoted})", top=500, select="ISIN,IsSinkable,IsCallable,IsPutable"))
        dur.append(call_api(ld.get_data, batch, ["TR.ModifiedDuration", "TR.ModifiedDuration.date"]))
    f = pd.concat(flags, ignore_index=True).drop_duplicates("ISIN").rename(columns={
        "ISIN": "isin", "IsSinkable": "is_sinkable", "IsCallable": "is_callable", "IsPutable": "is_putable"})
    d = pd.concat(dur, ignore_index=True).rename(columns={
        "Instrument": "isin", "Modified Duration": "mod_duration", "Date": "md_date"})
    d["mod_duration"] = pd.to_numeric(d["mod_duration"], errors="coerce")
    d["md_date"] = pd.to_datetime(d["md_date"], errors="coerce", utc=True).dt.tz_localize(None)
    out = pd.DataFrame({"isin": isins}).merge(f, on="isin", how="left").merge(d, on="isin", how="left")
    return out.astype({"is_sinkable": "boolean", "is_callable": "boolean", "is_putable": "boolean"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["desktop", "platform"], default="desktop")
    ap.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = ap.parse_args(argv)
    C.setup_logging("run_structure_check")
    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    keys = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")["parent_key"].unique()
    bonds = uni[(uni["instrument_class"] == "bond") & uni["is_primary_line"] & uni["parent_key"].isin(keys)]
    control = uni[uni["parent_key"].isin(C.TWIN["exclude_parents"]) & uni["is_sukuk"]]
    isins = sorted(set(bonds["isin"].dropna()) | set(control["isin"].dropna()))
    log.info("Querying %d ISINs (%d control)", len(isins), control["isin"].nunique())
    with lseg_session(a.session):
        out = pull(isins)
    path = a.data / "interim" / "structure_flags.parquet"
    out.to_parquet(path, index=False)
    log.info("Wrote %s: %d bonds, %d with flags, %d with duration", path, len(out),
             int(out["is_sinkable"].notna().sum()), int(out["mod_duration"].notna().sum()))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
