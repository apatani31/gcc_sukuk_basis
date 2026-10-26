"""Daily price/yield history per instrument via ld.get_history.

Each instrument is pulled on its own (date-windowed) and written to
data/history/_parts/<id>.parquet, with its status in _manifest.csv, so an
interrupted run resumes where it stopped. consolidate() then builds the tidy
long table (date, isin, ric, field, value) partitioned by issue_year, and
coverage() writes the per-instrument coverage report.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from .config import GOOD_COVERAGE_PCT, HISTORY_FIELDS, HISTORY_WINDOW_YEARS, ISIN_RIC_SUFFIXES, MIN_OBS_FLAG
from .session import _is_transient, call_api, ld

log = logging.getLogger(__name__)
TIDY_COLS = ["date", "isin", "ric", "field", "value"]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _windows(start: date, end: date, years: int):
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    while s <= e:
        w_end = min(s + pd.DateOffset(years=years) - pd.Timedelta(days=1), e)
        yield s.date(), w_end.date()
        s = w_end + pd.Timedelta(days=1)


def probe_history_fields(ric: str) -> list[str]:
    """Return the HISTORY_FIELDS this entitlement returns for one known-liquid RIC."""
    res = call_api(ld.get_history, ric, fields=list(HISTORY_FIELDS), interval="daily", count=30)
    got = [f for f in HISTORY_FIELDS if f in res.columns and res[f].notna().any()]
    missing = [f for f in HISTORY_FIELDS if f not in got]
    if missing:
        log.warning("History fields not returned for %s on this entitlement: %s", ric, missing)
    if not got:
        raise RuntimeError(f"No history fields returned for probe RIC {ric}; check pricing entitlement.")
    log.info("History fields available: %s", got)
    return got


def fetch_one(ric: str, isin: str | None, start: date, end: date, fields: list[str]) -> pd.DataFrame:
    frames = []
    for w_start, w_end in _windows(start, end, HISTORY_WINDOW_YEARS):
        res = call_api(ld.get_history, ric, fields=fields, interval="daily",
                       start=w_start.isoformat(), end=w_end.isoformat())
        if res is not None and not res.empty:
            frames.append(res)
    if not frames:
        return pd.DataFrame(columns=TIDY_COLS)
    wide = pd.concat(frames)
    wide = wide[~wide.index.duplicated(keep="last")]
    wide.index.name = "date"
    wide = wide[[c for c in fields if c in wide.columns]].apply(pd.to_numeric, errors="coerce")
    if "MID_PRICE" not in wide or wide["MID_PRICE"].isna().all():
        if {"BID", "ASK"} <= set(wide.columns):
            wide["mid_price_derived"] = (wide["BID"] + wide["ASK"]) / 2
    tidy = wide.rename(columns=HISTORY_FIELDS).reset_index().melt(
        id_vars="date", var_name="field", value_name="value").dropna(subset=["value"])
    tidy["date"] = pd.to_datetime(tidy["date"]).dt.tz_localize(None).dt.normalize()
    tidy["isin"] = isin
    tidy["ric"] = ric
    return tidy[TIDY_COLS]


def candidate_rics(row: pd.Series) -> list[str]:
    """Price sources to try, best first (see ISIN_RIC_SUFFIXES in config)."""
    ric, isin = row.get("ric"), row.get("isin")
    out = []
    if isinstance(ric, str) and row.get("ric_source") == "export":
        out.append(ric)
    if isinstance(isin, str):
        out += [f"{isin}{s}" for s in ISIN_RIC_SUFFIXES]
    if isinstance(ric, str):
        out.append(ric)
    return list(dict.fromkeys(out))


def _window_for(row: pd.Series, start: date) -> tuple[date, date] | None:
    s = max(row["issue_date"].date(), start) if pd.notna(row["issue_date"]) else start
    e = date.today()
    if pd.notna(row["maturity_date"]):
        e = min(e, row["maturity_date"].date())
    return (s, e) if s <= e else None


def pull_history(universe: pd.DataFrame, out_dir: Path, start: date, force: bool = False,
                 probe_ric: str = "SASUKSK4202=") -> pd.DataFrame:
    parts = out_dir / "_parts"
    parts.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "_manifest.csv"
    manifest = (pd.read_csv(manifest_path) if manifest_path.exists() and not force
                else pd.DataFrame(columns=["instrument_id", "ric", "status", "n_rows", "error"]))
    done = set(manifest.loc[manifest["status"].isin(["ok", "empty"]), "instrument_id"])

    todo = universe[~universe["instrument_id"].isin(done)] if not force else universe
    log.info("History: %d to pull, %d already done", len(todo), len(done))
    if todo.empty:
        return manifest

    fields = probe_history_fields(probe_ric)
    records, retry = [], []

    def _run(row) -> dict:
        win = _window_for(row, start)
        cands = candidate_rics(row)
        rec = {"instrument_id": row["instrument_id"], "ric": None, "status": "", "n_rows": 0,
               "n_days": 0, "tried": " ".join(cands), "error": ""}
        if win is None:
            rec.update(status="empty", error="no window (matured before start)")
            return rec
        if not cands:
            rec.update(status="no_ric", error="no RIC or ISIN to try")
            return rec
        expected = max(len(pd.bdate_range(win[0], win[1])), 1)
        best, best_ric, errors, transient = None, None, [], False
        for ric in cands:
            try:
                tidy = fetch_one(ric, row["isin"], win[0], win[1], fields)
            except Exception as exc:
                errors.append(f"{ric}: {str(exc).splitlines()[-1][:120]}")
                transient |= _is_transient(exc)
                continue
            if best is None or tidy["date"].nunique() > best["date"].nunique():
                best, best_ric = tidy, ric
            if 100 * best["date"].nunique() / expected >= GOOD_COVERAGE_PCT:
                break
        if best is None and transient:
            raise RuntimeError("; ".join(errors))  # network-type failure: retry later
        best = best if best is not None else pd.DataFrame(columns=TIDY_COLS)
        best.to_parquet(parts / f"{_safe(row['instrument_id'])}.parquet", index=False)
        n_days = best["date"].nunique()
        status = "ok" if n_days else ("no_permission" if any("ermission" in e for e in errors) else "empty")
        rec.update(ric=best_ric, status=status, n_rows=len(best), n_days=n_days, error=" | ".join(errors)[:500])
        return rec

    for _, row in tqdm(todo.iterrows(), total=len(todo), desc="history"):
        try:
            records.append(_run(row))
        except Exception as exc:
            log.warning("History failed for %s: %s", row["instrument_id"], exc)
            retry.append(row)
    for row in retry:  # one final retry pass
        try:
            records.append(_run(row))
        except Exception as exc:
            log.error("History failed again for %s: %s", row["instrument_id"], exc)
            records.append({"instrument_id": row["instrument_id"], "ric": None, "status": "failed",
                            "n_rows": 0, "n_days": 0, "tried": " ".join(candidate_rics(row)),
                            "error": str(exc)[:500]})
    manifest = pd.concat([manifest[~manifest["instrument_id"].isin([r["instrument_id"] for r in records])],
                          pd.DataFrame(records)], ignore_index=True)
    manifest.to_csv(manifest_path, index=False)
    log.info("History status: %s", manifest["status"].value_counts().to_dict())
    return manifest


def consolidate(universe: pd.DataFrame, history_dir: Path, out_path: Path) -> pd.DataFrame:
    parts = history_dir / "_parts"
    ids = universe["instrument_id"].tolist()
    frames = []
    for iid in ids:
        p = parts / f"{_safe(iid)}.parquet"
        if p.exists():
            d = pd.read_parquet(p)
            if len(d):
                d["instrument_id"] = iid
                frames.append(d)
    if not frames:
        log.warning("No history rows to consolidate")
        return pd.DataFrame(columns=TIDY_COLS + ["instrument_id"])
    tidy = pd.concat(frames, ignore_index=True)
    tidy = tidy.merge(universe[["instrument_id", "issue_year", "is_sukuk"]], on="instrument_id", how="left")
    tidy["issue_year"] = tidy["issue_year"].astype("Int64").astype(str)
    if out_path.exists():
        import shutil
        shutil.rmtree(out_path)
    pq.write_to_dataset(pa.Table.from_pandas(tidy, preserve_index=False), root_path=str(out_path),
                        partition_cols=["issue_year"])
    log.info("Wrote %d tidy rows to %s", len(tidy), out_path)
    return tidy


def coverage(universe: pd.DataFrame, tidy: pd.DataFrame, start: date,
             manifest: pd.DataFrame | None = None) -> pd.DataFrame:
    price_like = tidy[tidy["field"].isin(["mid_price", "bid_price", "mid_price_derived", "mid_yield", "bid_yield"])]
    g = price_like.groupby("instrument_id")
    stats = pd.DataFrame({"price_ric": g["ric"].first(), "first_date": g["date"].min(),
                          "last_date": g["date"].max(), "n_obs": g["date"].nunique()})
    cov = universe[["instrument_id", "isin", "ric", "issuer_name", "is_sukuk", "issue_date",
                    "maturity_date"]].merge(stats, left_on="instrument_id", right_index=True, how="left")
    if manifest is not None and len(manifest):
        cov = cov.merge(manifest[["instrument_id", "status", "tried"]].rename(columns={"status": "history_status"}),
                        on="instrument_id", how="left")
    cov["n_obs"] = cov["n_obs"].fillna(0).astype(int)

    def _bdays(r):
        win = _window_for(r, start)
        return len(pd.bdate_range(win[0], win[1])) if win else 0

    cov["expected_bdays"] = cov.apply(_bdays, axis=1)
    cov["pct_bdays_populated"] = np.where(cov["expected_bdays"] > 0,
                                          (100 * cov["n_obs"] / cov["expected_bdays"]).round(1), np.nan)
    cov["has_ric"] = cov["price_ric"].notna() | cov["ric"].notna()
    cov[f"flag_lt_{MIN_OBS_FLAG}_obs"] = cov["n_obs"] < MIN_OBS_FLAG
    return cov


def pull_benchmarks(rics: list[str], out_path: Path, start: date) -> None:
    if not rics:
        log.info("BENCHMARK_RICS is empty in config.py; skipping benchmark curves")
        return
    fields = probe_history_fields(rics[0])
    frames = []
    for ric in rics:
        try:
            frames.append(fetch_one(ric, None, start, date.today(), fields))
        except Exception as exc:
            log.error("Benchmark %s failed: %s", ric, exc)
    if frames:
        pd.concat(frames, ignore_index=True).to_parquet(out_path, index=False)
        log.info("Wrote benchmarks to %s", out_path)
