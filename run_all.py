"""End-to-end pipeline: universe -> enrich -> yield at issue -> history -> summary.

Every stage skips its output if it already exists (resume); --force rebuilds.
A slice run (--country / --issue-year) writes to data/slice_<...>/ so it never
collides with the full run.

Examples:
    python run_all.py --skip-history --skip-enrich                 # offline: universe + yields + summary
    python run_all.py --session desktop --country Qatar --issue-year 2019   # small live slice
    python run_all.py --session desktop                            # full job
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src import config as C
from src.universe import apply_filters, data_dictionary, load_universe
from src.yield_calc import add_yield_at_issue

log = logging.getLogger("run_all")


def parse_args(argv=None) -> C.RunConfig:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", choices=["desktop", "platform"], default="desktop")
    p.add_argument("--currency", default="USD", help="USD, AED, SAR, QAR, KWD, BHD, OMR")
    p.add_argument("--start", default="2010-01-01", help="earliest issue date / history start")
    p.add_argument("--sukuk-only", action="store_true")
    p.add_argument("--skip-history", action="store_true")
    p.add_argument("--skip-enrich", action="store_true", help="no LSEG calls for RIC resolution / TR fields")
    p.add_argument("--force", action="store_true", help="rebuild outputs that already exist")
    p.add_argument("--country", action="append", help="country of risk (repeatable); slice run")
    p.add_argument("--issue-year", type=int, help="single issue year; slice run")
    p.add_argument("--limit", type=int, help="cap instruments sent to get_history (testing)")
    p.add_argument("--all-lines", action="store_true", help="price RegS and 144A lines, not one per bond")
    p.add_argument("--sukuk-file", action="append", type=Path)
    p.add_argument("--conv-file", action="append", type=Path)
    p.add_argument("--out", type=Path, default=C.DATA_DIR)
    a = p.parse_args(argv)
    cfg = C.RunConfig(
        session=a.session, currency=a.currency.upper(), start=date.fromisoformat(a.start),
        sukuk_only=a.sukuk_only, skip_history=a.skip_history, skip_enrich=a.skip_enrich, force=a.force,
        countries=a.country or list(C.GCC_COUNTRIES), issue_year=a.issue_year, limit=a.limit,
        all_lines=a.all_lines, out_dir=a.out,
    )
    if a.sukuk_file:
        cfg.sukuk_files = a.sukuk_file
    if a.conv_file:
        cfg.conv_files = a.conv_file
    bad = set(cfg.countries) - set(C.GCC_COUNTRIES)
    if bad:
        p.error(f"unknown country {bad}; choose from {C.GCC_COUNTRIES}")
    return cfg


def out_dir_for(cfg: C.RunConfig) -> Path:
    d = cfg.out_dir / cfg.currency
    if cfg.is_slice:
        tag = "_".join(c.replace(" ", "") for c in cfg.countries) if set(cfg.countries) != set(C.GCC_COUNTRIES) else "all"
        d = cfg.out_dir / f"slice_{cfg.currency}_{tag}_{cfg.issue_year or 'allyears'}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stage(path: Path, cfg: C.RunConfig) -> bool:
    """True if the stage must run."""
    if path.exists() and not cfg.force:
        log.info("Skip (exists): %s", path.relative_to(C.PROJECT_ROOT) if path.is_relative_to(C.PROJECT_ROOT) else path)
        return False
    return True


def main(argv=None) -> int:
    cfg = parse_args(argv)
    log_path = C.setup_logging("run_all")
    out = out_dir_for(cfg)
    interim = out / "interim"
    interim.mkdir(exist_ok=True)
    desc = (f"currency={cfg.currency} start={cfg.start} countries={','.join(cfg.countries)} "
            f"issue_year={cfg.issue_year or 'all'} sukuk_only={cfg.sukuk_only}")
    log.info("Run: %s -> %s (log %s)", desc, out, log_path)

    # 1. Universe from the exports
    p_uni = interim / "universe_filtered.parquet"
    if _stage(p_uni, cfg):
        uni = load_universe(cfg.sukuk_files, cfg.conv_files)
        uni = apply_filters(uni, cfg.currency, cfg.start, cfg.countries, cfg.issue_year, cfg.sukuk_only)
        uni.to_parquet(p_uni, index=False)
    uni = pd.read_parquet(p_uni)
    if uni.empty:
        log.error("Empty universe; stopping.")
        return 1

    # 2. Enrichment (needs a session) and 4. history share one session
    session = None
    need_session = not cfg.skip_enrich or not cfg.skip_history
    p_enr = interim / "universe_enriched.parquet"
    try:
        if need_session:
            from src.session import close_session, open_session
            session = open_session(cfg.session)

        if _stage(p_enr, cfg):
            if cfg.skip_enrich:
                uni["ric_source"] = uni["ric"].notna().map({True: "export", False: None})
            else:
                from src.enrich import fetch_fields, probe_fields, resolve_rics
                uni = resolve_rics(uni)
                sample = uni.loc[uni["instrument_class"] == "bond", "isin"].dropna().head(5).tolist()
                fields = probe_fields(sample, out / "field_probe.csv")
                uni = fetch_fields(uni, fields)
            uni.to_parquet(p_enr, index=False)
        uni = pd.read_parquet(p_enr)

        # 3. Yield at issue + final universe files
        p_all = out / "gcc_universe_all.csv"
        if _stage(p_all, cfg):
            uni = add_yield_at_issue(uni)
            uni[uni.is_sukuk].to_parquet(out / "gcc_universe_sukuk.parquet", index=False)
            if not cfg.sukuk_only:
                uni[~uni.is_sukuk].to_parquet(out / "gcc_universe_conventional.parquet", index=False)
            uni.to_csv(p_all, index=False)
            uni.to_parquet(interim / "universe_final.parquet", index=False)
            data_dictionary(uni).to_csv(out / "data_dictionary.csv", index=False)
            log.info("Universe written: %d rows (%d sukuk, %d conventional)",
                     len(uni), int(uni.is_sukuk.sum()), int((~uni.is_sukuk).sum()))
        uni = pd.read_parquet(interim / "universe_final.parquet")

        # 4. History
        coverage = None
        p_cov = out / "coverage_report.csv"
        if not cfg.skip_history:
            from src.history import consolidate, coverage as make_cov, pull_benchmarks, pull_history
            hist_u = uni[uni["instrument_class"] == "bond"]
            if not cfg.all_lines:
                hist_u = hist_u[hist_u["is_primary_line"]]
            if cfg.limit:
                hist_u = hist_u.head(cfg.limit)
            hist_dir = out / "history"
            manifest = pull_history(hist_u, hist_dir, cfg.start, force=cfg.force)
            tidy = consolidate(hist_u, hist_dir, out / "timeseries")
            coverage = make_cov(hist_u, tidy, cfg.start, manifest)
            coverage.to_csv(p_cov, index=False)
            pull_benchmarks(C.BENCHMARK_RICS, out / "benchmarks.parquet", cfg.start)
        elif p_cov.exists():
            coverage = pd.read_csv(p_cov)
    finally:
        if session is not None:
            close_session(session)

    # 5. Summary (always regenerated; cheap)
    from src.summary import write_summary
    write_summary(uni, coverage, out / "summary.md", desc)
    log.info("Done. Outputs in %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
