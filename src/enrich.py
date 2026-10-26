"""Light-touch LSEG enrichment of the export-based universe.

1. resolve_rics: bonds without a Preferred RIC in the export (mostly matured
   lines) get one via ld.discovery.convert_symbols, so they can be priced.
2. probe_fields / fetch_fields: test candidate TR fields (config) on a few
   ISINs, then pull only the ones the entitlement accepts, in chunks.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ENRICH_CHUNK_SIZE, ENRICH_FIELD_CANDIDATES
from .session import call_api, ld

log = logging.getLogger(__name__)


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def resolve_rics(df: pd.DataFrame, chunk: int = ENRICH_CHUNK_SIZE) -> pd.DataFrame:
    df = df.copy()
    df["ric_source"] = np.where(df["ric"].notna(), "export", None)
    need = df.loc[df["ric"].isna() & df["isin"].notna() & (df["instrument_class"] == "bond"), "isin"]
    isins = sorted(need.unique())
    log.info("Resolving RICs for %d ISINs without one", len(isins))
    found: dict[str, str] = {}
    failed: list[list[str]] = []
    SymbolTypes = ld.discovery.SymbolTypes

    def _convert(batch: list[str]) -> None:
        for state in ("Active", "Inactive"):
            todo = [i for i in batch if i not in found]
            if not todo:
                return
            res = call_api(ld.discovery.convert_symbols, todo, from_symbol_type=SymbolTypes.ISIN,
                           to_symbol_types=[SymbolTypes.RIC], asset_state=state)
            if res is None or res.empty:
                continue
            col = next((c for c in res.columns if c.upper() == "RIC"), res.columns[-1])
            for isin, ric in res[col].dropna().items():
                found.setdefault(str(isin), str(ric))

    for batch in _chunks(isins, chunk):
        try:
            _convert(batch)
        except Exception as exc:
            log.warning("convert_symbols chunk failed (%d ISINs): %s", len(batch), exc)
            failed.append(batch)
    for batch in failed:  # one more pass for failed chunks
        try:
            _convert(batch)
        except Exception as exc:
            log.error("convert_symbols chunk failed again, giving up (%d ISINs): %s", len(batch), exc)

    fill = df["ric"].isna() & df["isin"].map(found).notna()
    df.loc[fill, "ric"] = df.loc[fill, "isin"].map(found)
    df.loc[fill, "ric_source"] = "convert_symbols"
    log.info("Resolved %d of %d missing RICs", int(fill.sum()), len(isins))
    return df


def probe_fields(sample_isins: list[str], out_csv: Path) -> dict[str, str]:
    """Return {column_name: working TR field}; writes every attempt to out_csv."""
    rows, chosen = [], {}
    for col, candidates in ENRICH_FIELD_CANDIDATES.items():
        for fld in candidates:
            try:
                res = call_api(ld.get_data, sample_isins, [fld], attempts=2)
                vals = res.iloc[:, 1:].stack().dropna() if res is not None and res.shape[1] > 1 else []
                ok = len(vals) > 0
                rows.append({"column": col, "tr_field": fld, "status": "ok" if ok else "empty",
                             "sample": str(list(vals)[:3])})
            except Exception as exc:
                ok = False
                rows.append({"column": col, "tr_field": fld, "status": "error", "sample": str(exc)[:200]})
            log.info("Probe %s -> %s", fld, rows[-1]["status"])
            if ok:
                chosen[col] = fld
                break
        if col not in chosen:
            log.warning("No working TR field for %s (tried %s). Column left empty; confirm a name in "
                        "the Data Item Browser and add it to ENRICH_FIELD_CANDIDATES.", col, candidates)
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return chosen


def fetch_fields(df: pd.DataFrame, fields: dict[str, str], chunk: int = ENRICH_CHUNK_SIZE) -> pd.DataFrame:
    df = df.copy()
    for col in fields:
        df[col] = np.nan
    if not fields:
        return df
    isins = sorted(df["isin"].dropna().unique())
    tr = list(fields.values())
    results, failed = [], []

    def _get(batch):
        res = call_api(ld.get_data, batch, tr)
        res.columns = ["isin"] + list(fields.keys())
        return res

    for batch in _chunks(isins, chunk):
        try:
            results.append(_get(batch))
        except Exception as exc:
            log.warning("get_data chunk failed (%d ISINs): %s", len(batch), exc)
            failed.append(batch)
    for batch in failed:
        try:
            results.append(_get(batch))
        except Exception as exc:
            log.error("get_data chunk failed again (%d ISINs): %s", len(batch), exc)
    if results:
        got = pd.concat(results).drop_duplicates("isin").set_index("isin")
        for col in fields:
            df[col] = df["isin"].map(got[col])
    return df
