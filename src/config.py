"""Central configuration: paths, field lists, filters and tunables.

Anything you are expected to edit by hand is marked with "EDIT ME".
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SECRETS_FILE = PROJECT_ROOT / "secrets.env"

# ---------------------------------------------------------------------------
# Universe inputs (Workspace "Search Results" exports). EDIT ME if paths move.
# ---------------------------------------------------------------------------
DOWNLOADS = Path.home() / "Downloads"
DEFAULT_SUKUK_FILES = [DOWNLOADS / "Sukuk.xlsx"]
DEFAULT_CONV_FILES = [DOWNLOADS / "Conv_1.xlsx", DOWNLOADS / "Conv_2.xlsx"]
EXPORT_SHEET = "Search Results"

GCC_COUNTRIES = [
    "Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman",
]

# ISO code -> "Principal Currency" label used in the Workspace export.
CURRENCY_LABELS = {
    "USD": "US Dollar",
    "AED": "UAE Dirham",
    "SAR": "Saudi Riyal",
    "QAR": "Qatari Riyal",
    "KWD": "Kuwaiti Dinar",
    "BHD": "Bahraini Dinar",
    "OMR": "Omani Rial",
}

# Instrument Type values treated as tradable bonds for the comparison. Money
# market paper (CDs, CP) and exotic lines are kept in the "all" file but are
# marked out of scope.
BOND_INSTRUMENT_TYPES = {"Note", "Bond", "Capital Security", "Debenture"}
MONEY_MARKET_INSTRUMENT_TYPES = {
    "Certificate of Deposit", "Certificate of Deposit - Institutional", "Commercial Paper",
}

# ---------------------------------------------------------------------------
# Yield at issue
# ---------------------------------------------------------------------------
# Day count is not in the export, so computed yields ASSUME 30/360 (the
# standard for USD Eurobonds and USD 144A corporates). Stated in summary.md.
DEFAULT_DAY_COUNT = "30/360"
FIXED_COUPON_TYPES = {"Plain Vanilla Fixed Coupon"}
ZERO_COUPON_TYPES = {"Zero Coupon", "Discount"}
FREQUENCY_MAP = {"Annually": 1, "Semiannually": 2, "Quarterly": 4, "Monthly": 12, "At maturity": 0}

# ---------------------------------------------------------------------------
# Optional ld.get_data enrichment. These TR names are UNVERIFIED candidates:
# enrich.probe_fields() tests each one on a few ISINs and only keeps the ones
# your entitlement accepts (results in data/field_probe.csv). EDIT ME with names
# confirmed in the Workspace Data Item Browser.
# ---------------------------------------------------------------------------
ENRICH_FIELD_CANDIDATES = {
    "yield_at_issue_lseg": ["TR.FiIssueYield", "TR.FiYieldAtIssue"],
    "day_count_lseg": ["TR.FiDayCountBasis", "TR.FiAccrualBasis"],
    "ultimate_parent_lseg": ["TR.FiUltimateParent", "TR.UltimateParent"],
}
ENRICH_CHUNK_SIZE = 500

# ---------------------------------------------------------------------------
# Time series (ld.get_history)
# ---------------------------------------------------------------------------
# Real-time/interday pricing field -> tidy field name. Fields your entitlement
# does not return are dropped with a log line after a one-RIC probe.
HISTORY_FIELDS = {
    "BID": "bid_price",
    "ASK": "ask_price",
    "MID_PRICE": "mid_price",
    "B_YLD_1": "bid_yield",
    "A_YLD_1": "ask_yield",
    "MID_YLD_1": "mid_yield",
}
# Price sources tried per bond, in order: export RIC, then "<ISIN><suffix>" for
# each suffix here, then the convert_symbols RIC. The source with the most days
# wins (one source per bond). Tested on this entitlement: "=TE" (Tradeweb) has
# full issue-to-maturity history for matured bonds; "=" and "=RRPS" are not
# permissioned; single-dealer quotes (=BCLQ, =MFID, =TBLS) are not permissioned.
ISIN_RIC_SUFFIXES = ["=TE"]
GOOD_COVERAGE_PCT = 90.0  # stop trying further sources once a source covers this share of business days
HISTORY_WINDOW_YEARS = 5         # split long histories; API caps at 10k points/request
MIN_SECONDS_BETWEEN_CALLS = 0.25  # Workspace limit is ~5 requests/second
MIN_OBS_FLAG = 20

# EDIT ME: sovereign benchmark curve RICs, to be supplied later, e.g.
# ["SA5YT=RR", "QA10YT=RR"]. Left empty on purpose.
BENCHMARK_RICS: list[str] = []

# ---------------------------------------------------------------------------
# Twin-curve matching
# ---------------------------------------------------------------------------
SIMILAR_TENOR_YEARS = 2.0  # |maturity_sukuk - maturity_conv| within this counts as a twin pair

# Jurisdiction -> substrings matched against the normalized parent key.
SOVEREIGNS = {
    "KSA": ["arabia kingdom saudi"],
    "Qatar": ["qatar state"],
    "Oman": ["oman sultanate"],
    "Bahrain": ["bahrain kingdom"],
    "Sharjah": ["emirate sharjah"],
    "Abu Dhabi": ["abu dhabi emirate"],
    "Kuwait": ["kuwait state"],
    "Dubai": ["dubai emirate"],
    "UAE (federal)": ["arab emirates united"],
}


# ---------------------------------------------------------------------------
# Twin-curve analysis (src/twin.py)
# ---------------------------------------------------------------------------
TWIN = {
    "coupon_types": ["Plain Vanilla Fixed Coupon"],
    "min_amount_usd": 100e6,       # drop small private placements (stale quotes)
    "min_tau": 1.0,                # years to maturity; pull-to-par distorts the last year
    "max_tau": 30.0,
    "yield_bounds": (0.0, 25.0),   # percent
    "outlier_pp": 1.5,             # drop if |y - 21-day rolling median| exceeds this (percentage points)
    "stale_run_days": 5,           # drop days ending a run of this many identical mid prices
    "max_stale_share": 0.5,        # drop bonds whose price is unchanged on more than this share of days
    "nearest_max_gap": 1.0,        # nearest-neighbour fallback: max |tau_sukuk - tau_conv| in years
    # Nearest matches are shifted along the US Treasury curve to the sukuk's maturity
    # (y_conv + UST(tau_sukuk) - UST(tau_conv)). Validated on interpolated cases: at 3-12m
    # gaps the persistent per-bond error is ~2bp median (p90 ~10bp); error in 5/20-day
    # changes ~1-2bp. See twin_matching_validation.csv.
    "ust_curve_path": DATA_DIR / "market" / "ust_curve.parquet",
    "main_methods": ["interp", "nearest_adj"],
    # Excluded issuers (parent_key): Emirates' sukuk are amortizing aircraft financings,
    # so a yield to final maturity is not comparable with bullet bonds.
    "exclude_parents": ["emirates"],
    "max_bracket_width": 10.0,     # robustness: interpolation brackets no wider than this
    "std_tenors": [3, 5, 7, 10],
    "nw_lags": 20,                 # Newey-West lags (business days) for per-issuer t-stats
    "min_issuer_days": 20,
}


# ---------------------------------------------------------------------------
# Oil shock definition (src/shocks.py)
# ---------------------------------------------------------------------------
# A shock is a day on which the Brent front-month log return, net of the part
# explained by the same-day S&P 500 return, is at least `z` standard deviations
# of its own trailing `vol_window`-day history, AND the raw Brent move is at
# least `min_abs_ret_pct` percent. Up and down moves are selected
# separately: largest |z| first, then any same-sign trigger more than
# `cluster_days` trading days from those already kept.
MARKET_RICS = {"LCOc1": "TRDPRC_1", "LCOc12": "TRDPRC_1", ".SPX": "TRDPRC_1", ".VIX": "TRDPRC_1",
               "US10YT=RR": "YLDTOMAT", ".DXY": "TRDPRC_1"}
SHOCK = {
    "oil_ric": "LCOc1",
    "equity_ric": ".SPX",
    "horizon_days": 1,      # return horizon in trading days (5 = weekly robustness)
    "z": 3.0,
    "min_abs_ret_pct": 5.0, # AND the raw Brent move must be at least this large (economic size)
    "vol_window": 250,     # ~1 trading year, lagged one day so the shock day is excluded
    "net_of_equity": True,  # strip the S&P-explained part (rolling beta) so global risk-off days don't count
    "cluster_days": 20,     # matches the +20 day event window, so windows don't overlap
    "start": "2017-01-01",
}


# ---------------------------------------------------------------------------
# Credit-stress analysis (src/credit.py)
# ---------------------------------------------------------------------------
# Sovereign 5y USD CDS, field MID_SPREAD (bp). Verified on this login 2026-10-25.
# Oman's =R series only starts 2025-08, so the =MG contributor (from 2017-08) is used.
# No Sharjah or UAE-federal CDS was found.
CDS_RICS = {
    "KSA": "SAGV5YUSAC=R", "Bahrain": "BHGV5YUSAC=R", "Qatar": "QAGV5YUSAC=R",
    "Abu Dhabi": "ABUU5YUSAC=R", "Dubai": "DUBA5YUSAC=R", "Oman": "OMGV5YUSAC=MG",
}
# Issuer (parent_key) -> sovereign whose CDS measures its credit environment.
# Government-related entities map to their owner; issuers with no clean match
# (Sharjah: no CDS; Arab Energy Fund: multilateral) are left out of CDS regressions.
ISSUER_SOVEREIGN = {
    "arabia kingdom saudi": "KSA", "arabian oil saudi": "KSA", "fund investment public": "KSA",
    "bank national saudi": "KSA", "banque fransi saudi": "KSA",
    "bahrain kingdom": "Bahrain", "bapco energies": "Bahrain",
    "oman sultanate": "Oman", "electricity oman transmission": "Oman",
    "qatar state": "Qatar",
    "abu bank dhabi first": "Abu Dhabi", "diversified global holding mamoura": "Abu Dhabi",
    "dubai emirate": "Dubai", "dubai investment": "Dubai", "dp world": "Dubai",
    "aerospace dae dubai enterprise": "Dubai",
}


# Local 3-month interbank fixings (percent), verified on this login 2026-10-25.
# country_of_risk -> (RIC, field). All six currencies are pegged to the USD, so
# the panel uses the spread over the 3-month US Treasury bill (local funding tightness).
INTERBANK_RICS = {
    "Saudi Arabia": ("SASAR3MD=", "FIXING_1"),       # SAIBOR
    "United Arab Emirates": ("DXAED3MD=", "FIXING_1"),  # EIBOR
    "Qatar": ("QAQAR3MD=", "FIXING_1"),              # QIBOR
    "Bahrain": ("BHIBOR3M=", "FIXING_1"),            # BHIBOR
    "Kuwait": ("KIBOR3M=", "ASK"),                   # KIBOR (offer side)
    "Oman": ("OMOMR3MD=CBOX", "FIXING_1"),           # Central Bank of Oman fixing, from 2017-07
}


# ---------------------------------------------------------------------------
# Time-varying ratings (NEXT_PROMPT task 8)
# ---------------------------------------------------------------------------
# LSEG rating-history fields are not entitled on this login (checked 2026-10-29), so
# sovereign_ratings.csv is supplied by hand (see src/ratings.py for the format).
SOVEREIGN_RATINGS_PATH = DATA_DIR / "market" / "sovereign_ratings.csv"
# Oman upgrades to investment grade, as supplied by the user (month precision).
OMAN_UPGRADES = [("S&P", "2024-09", "BBB-"), ("Moody's", "2025-07", "Baa3"), ("Fitch", "2025-12", "BBB-")]
CDS_SUB_IG_BP = 150.0   # CDS-based alternative: an obligor-month is "sub-IG" if its government's CDS > 150bp


@dataclass
class RunConfig:
    session: str = "desktop"
    currency: str = "USD"
    start: date = date(2010, 1, 1)
    sukuk_only: bool = False
    skip_history: bool = False
    skip_enrich: bool = False
    force: bool = False
    countries: list[str] = field(default_factory=lambda: list(GCC_COUNTRIES))
    issue_year: int | None = None
    limit: int | None = None
    all_lines: bool = False
    sukuk_files: list[Path] = field(default_factory=lambda: list(DEFAULT_SUKUK_FILES))
    conv_files: list[Path] = field(default_factory=lambda: list(DEFAULT_CONV_FILES))
    out_dir: Path = DATA_DIR

    @property
    def is_slice(self) -> bool:
        return self.issue_year is not None or set(self.countries) != set(GCC_COUNTRIES)


# ---------------------------------------------------------------------------
# Credentials and logging
# ---------------------------------------------------------------------------
_SECRET_KEYS = ("LSEG_APP_KEY", "LSEG_USERNAME", "LSEG_PASSWORD")


def load_secrets() -> dict[str, str]:
    """Return credentials from env vars, falling back to secrets.env. Never log the result."""
    values: dict[str, str] = {}
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() in _SECRET_KEYS and v.strip():
                values[k.strip()] = v.strip().strip('"').strip("'")
    for k in _SECRET_KEYS:
        if os.environ.get(k):
            values[k] = os.environ[k]
    return values


class _RedactFilter(logging.Filter):
    """Masks any credential value that would otherwise reach a log line."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets = [v for v in load_secrets().values() if len(v) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            msg = record.getMessage()
            for s in self._secrets:
                msg = msg.replace(s, "***")
            record.msg, record.args = msg, None
        return True


def setup_logging(name: str = "pipeline") -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    redact = _RedactFilter()
    for h in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        h.addFilter(redact)
        root.addHandler(h)
    # The LSEG library is chatty at INFO and can echo request details.
    logging.getLogger("lseg").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return log_path
