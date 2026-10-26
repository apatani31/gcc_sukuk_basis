# GCC sukuk vs conventional bonds: LSEG data pipeline

Huntsman capstone. Builds a security-level universe of GCC USD sukuk and
conventional bonds (issued 2010 onward, active and matured), computes yield at
issue, pulls daily price/yield history from LSEG, and writes a feasibility
summary for a within-issuer "twin curves" comparison.

The universe comes from three Workspace *Search Results* exports
(`Sukuk.xlsx`, `Conv_1.xlsx` = issued 2020-2026, `Conv_2.xlsx` = 2010-2019),
not from `ld.discovery.search`. LSEG is called only to resolve missing RICs,
probe optional TR fields, and pull history.

## What is in this repository

Code, tests, and the written results: reports (`*.md`), charts (`*.png`) and
summary-statistic tables under `data/USD/` and `data/market/oil_shocks_*.csv`.
**Raw LSEG data is not included**: daily bond prices and yields, the security
universe, sovereign CDS, Brent and the other market series, interbank rates,
and bond-level or issuer-month panels. LSEG's licence does not allow
republishing it. To regenerate everything, run the steps below with your own
LSEG login. The three universe inputs are Workspace "Search Results" exports
(`Sukuk.xlsx`, `Conv_1.xlsx`, `Conv_2.xlsx`), passed with
`--sukuk-file` / `--conv-file`.

## Setup (Windows, once)

The project lives in a short path on purpose: Windows long-path support is off
on this machine, and pip fails inside deeply nested folders.

```bash
git clone https://github.com/apatani31/gcc_sukuk_basis.git gcc_sukuk
cd gcc_sukuk
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

Credentials: copy `secrets.env.example` to `secrets.env` (gitignored) and fill it
in, or set the same names as environment variables (these take precedence).

| Session | Needs | Notes |
|---|---|---|
| `desktop` | `LSEG_APP_KEY` | Workspace must be running and signed in on this PC |
| `platform` | `LSEG_APP_KEY`, `LSEG_USERNAME`, `LSEG_PASSWORD` | RDP machine ID |

**Use `--session platform`.** Tested 2026-10-24: the Workspace web login
(email + password + app key) opens a platform session. A desktop session needs
the installed Workspace desktop app, and the browser version does not provide
the local API.

Credentials are passed to the library's session-definition API only. They are
never printed, and a log filter masks them if they ever reach a log line.

## Run steps

```bash
# 1. Session smoke test: one field for one ISIN plus 5 days of history, prints OK
.venv/Scripts/python check_session.py --session desktop

# 2. Unit tests (yield-at-issue maths, name matching)
.venv/Scripts/python -m pytest -q

# 3. Offline run: universe, yield at issue, summary (no LSEG calls)
.venv/Scripts/python run_all.py --skip-history --skip-enrich

# 4. Small live slice: one country, one issue year -> data/slice_USD_Qatar_2019/
.venv/Scripts/python run_all.py --session desktop --country Qatar --issue-year 2019

# 5. Full job -> data/USD/
.venv/Scripts/python run_all.py --session desktop
```

Flags: `--session desktop|platform`, `--currency USD` (also AED, SAR, QAR, KWD,
BHD, OMR, provided the exports contain those issues), `--start 2010-01-01`,
`--sukuk-only`, `--skip-history`, `--skip-enrich`, `--force`, `--country X`
(repeatable), `--issue-year YYYY`, `--limit N` (cap on instruments priced),
`--all-lines` (price both RegS and 144A lines), `--sukuk-file` / `--conv-file`
(repeatable; defaults are in `~/Downloads`).

**Resume / idempotency:** each stage skips if its output exists. History is
written per instrument to `history/_parts/` with a `_manifest.csv`, so an
interrupted pull continues where it stopped. Use `--force` to rebuild
everything (needed after changing the input files or filters).

## Outputs (`data/USD/`, or `data/slice_.../`)

| File | Contents |
|---|---|
| `gcc_universe_sukuk.parquet`, `gcc_universe_conventional.parquet`, `gcc_universe_all.csv` | Universe with `is_sukuk`, `instrument_class`, `is_primary_line`, `parent_name`, yield-at-issue columns |
| `data_dictionary.csv` | Every column, its source header, fill rate; requested fields missing from the export marked `unavailable` |
| `field_probe.csv` | Which candidate TR fields your entitlement accepted |
| `timeseries/issue_year=YYYY/` | Tidy long table: `date, isin, ric, field, value` (+ `instrument_id`, `is_sukuk`) |
| `coverage_report.csv` | First/last date, n_obs, % of business days populated, `flag_lt_20_obs` |
| `benchmarks.parquet` | Sovereign benchmark curves, once `BENCHMARK_RICS` is filled in `src/config.py` |
| `summary.md` | Feasibility summary |
| `logs/*.log` | Timestamped run logs |

## Twin-curve analysis (offline, after the history pull)

```bash
.venv/Scripts/python run_twin.py
```

Compares each sukuk's daily mid yield with the same issuer's conventional
curve, linearly interpolated at the sukuk's remaining maturity. Where no two
conventional bonds bracket it, the nearest one within 1 year is used, shifted
along the US Treasury curve (`data/market/ust_curve.parquet`). That rule is
validated against interpolation in `twin_matching_validation.csv`. Emirates is
excluded because of its amortizing aircraft sukuk. It writes
`data/USD/analysis/twin_results.md` plus CSVs, `twin_basis_obs.parquet` and two
charts. Method and caveats are documented in the report. Filters and tunables
live in `TWIN` in `src/config.py`. `--min-amount 0` re-runs with small issues
included.

## Oil shock definition

```bash
.venv/Scripts/python run_shocks.py --session platform   # refresh Brent/S&P/VIX/UST/DXY, then detect
.venv/Scripts/python run_shocks.py --z 2.5               # sensitivity variants reuse the saved data
```

A shock is a day when Brent front-month's log return, after removing the part
explained by that day's S&P 500 move (rolling 250-day beta), is at least 3
standard deviations of its own previous 250 days, and the raw Brent move is
at least 5%. Up and down moves are
selected separately, keeping the largest move and then others at least 20
trading days apart. Shocks with an opposite-sign shock inside their window are
flagged. Output: `data/market/oil_shocks_z3_min5pct_h1.csv`. Parameters: `SHOCK` in
`src/config.py`.

## Oil-shock event study

```bash
.venv/Scripts/python run_event_study.py
```

Tracks the twin-curve basis, the sukuk leg and the matched conventional leg
from 5 business days before to 20 after each shock. Every change is measured
against each bond's own pre-shock level, and each shock counts once. It adds
a volatility-matched placebo (median), clean-window, excluding-2020 and
multi-shock-episode checks, and the sukuk-on-conventional pass-through after
shocks compared with normal days. Output: `data/USD/analysis/event_study/event_study.md`.

## Credit stress and the sukuk discount

```bash
.venv/Scripts/python run_credit.py --session platform   # pull sovereign CDS, then analyse
.venv/Scripts/python run_credit.py                       # reuse data/market/sovereign_cds.parquet
```

Builds an issuer-month panel of the twin-curve basis and regresses it on the
issuer's government 5y CDS (an outside credit measure), with a sukuk-minus-
conventional bid-ask control. It reports within-issuer (fixed effects) and
cross-issuer results plus a leave-one-government-out check. CDS codes and the
issuer-to-government map are `CDS_RICS` and `ISSUER_SOVEREIGN` in
`src/config.py`. Output: `data/USD/analysis/credit/credit_results.md`.
`explore_credit_basis.py` is the earlier exploratory version, now superseded.

## Drivers: funding, supply and a common factor

```bash
.venv/Scripts/python run_drivers.py --session platform   # refresh 3m interbank fixings, then analyse
.venv/Scripts/python run_drivers.py                       # reuse data/market/interbank_3m.parquet
```

Adds local interbank spreads (3-month fixing minus the 3-month US bill;
codes in `INTERBANK_RICS`) and USD sukuk issuance by country to the
issuer-month panel. It runs issuer fixed-effects regressions, then a PCA on the
balanced issuer-by-month basis panel and regresses the first factor on GCC-wide
drivers, in levels and in monthly changes. Output:
`data/USD/analysis/drivers/drivers_results.md`.

## Design decisions and data caveats

- **Scope.** About 75% of conventional rows are CDs and commercial paper. They
  stay in `gcc_universe_all.csv` (`instrument_class = money_market`) but are
  excluded from yields, history and the comparison.
- **Unique key.** CP/CD programmes reuse ISINs across issues, so
  `instrument_id` = ISIN + issue date (+ maturity if still ambiguous).
- **RegS/144A twins.** The same bond often appears as an XS and a US ISIN.
  `bond_key` groups them; `is_primary_line` picks one (XS line with a RIC first).
  Counts and history use primary lines.
- **Issuer matching.** Ultimate parent is not in the export. `parent_name`
  is Sukuk Obligor for sukuk, otherwise Borrower, otherwise Issuer, normalized
  for case, legal suffixes and word order.
- **Possible mislabels.** 12 conventional-file lines are issued by sukuk
  vehicles (e.g. Sharjah Sukuk Programme, QIB Sukuk) but tagged Note/Bond with no
  Islamic flag. They are flagged `possible_sukuk_mislabel` and excluded from the
  comparison until checked by hand.
- **Sovereign check.** "Direct" means a sukuk whose obligor is the government,
  or a conventional bond issued in the government's own name. Guaranteed or
  borrower-linked issues (e.g. Waha Aerospace for Abu Dhabi) are listed separately.
- **Yield at issue.** No LSEG yield-at-issue or day-count field is in the
  export. Computed for plain fixed and zero-coupon bonds, **assuming 30/360**,
  settlement on the issue date, and compounding at the coupon frequency.
  Floating, resettable, step, perpetual and missing-price cases are flagged.
  If `field_probe.csv` finds a working TR field, LSEG values take precedence
  (`yield_at_issue_source = lseg`).
- **Price sources.** Many matured bonds have no Preferred RIC in the export.
  For each bond, history tries the export RIC, then `<ISIN>=TE` (Tradeweb), then
  the `convert_symbols` RIC, and keeps the source with the most days (one source
  per bond, recorded as `price_ric` in `coverage_report.csv`). On this
  entitlement, `=TE` has full issue-to-maturity history for matured bonds, the
  `=` and `=RRPS` RICs are not permissioned, and single-dealer quotes (`=BCLQ`,
  `=MFID`, `=TBLS`) return "no permission". Composite RIC depth varies: some
  only start in 2022.
- **Ultimate parent.** `TR.UltimateParent` works (`ultimate_parent_lseg`), but
  it rolls state-owned issuers up to the government (QNB shows as State of
  Qatar). Twin matching therefore keeps the obligor/borrower name.
- **TR fields for yield at issue and day count:** the candidate names tried
  so far do not exist (`field_probe.csv`). Add confirmed names from the Data
  Item Browser to `ENRICH_FIELD_CANDIDATES` in `src/config.py`.
- **History fields** (`BID`, `ASK`, `MID_PRICE`, `B_YLD_1`, `A_YLD_1`,
  `MID_YLD_1`) are probed on one RIC first. Missing ones are dropped with a log
  warning. When `MID_PRICE` is absent, `mid_price_derived = (bid + ask) / 2`.
- **Rate limits.** Calls are spaced 0.25 s apart, retried with exponential
  backoff on transient errors (not on invalid-instrument errors), and failed
  chunks or instruments get one final retry pass.
