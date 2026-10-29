"""Drivers of the sukuk discount: interbank funding, sukuk supply, and a PCA factor view.

Usage:
    .venv\\Scripts\\python run_drivers.py --session platform   # refresh interbank fixings, then analyse
    .venv\\Scripts\\python run_drivers.py                      # reuse data/market/interbank_3m.parquet

Needs: run_twin.py and run_credit.py outputs (twin basis, sovereign CDS).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as C
from src.credit import add_drivers, build_panel, within_issuer_drivers
from src.drivers import (basis_matrix, factor_regression, interbank_spread_monthly, issuance_monthly, pca,
                         pull_interbank)
from src.summary import _md
from src.twin import load_panel
from src.twin_report import CONV_C, INK, INK2, SUKUK_C, SURFACE, _style

log = logging.getLogger("run_drivers")
IB_PATH = C.DATA_DIR / "market" / "interbank_3m.parquet"
PCA_WINDOWS = [("Main: Jul 2021 - Sep 2026", "2021-07", "2026-09", 0.9),
               ("Robustness: Jan 2023 - Sep 2026", "2023-01", "2026-09", 0.9)]


def monthly_drivers(market: pd.DataFrame, cds: pd.DataFrame, ib: pd.DataFrame, issuance: pd.DataFrame) -> pd.DataFrame:
    """GCC-wide monthly drivers for the factor regressions."""
    mk = market.astype(float).copy()
    mk.index = pd.to_datetime(mk.index)
    mm = mk[["LCOc1", ".VIX", "US10YT=RR", ".DXY"]].resample("ME").mean()
    mm.columns = ["brent", "vix", "ust10y", "dxy"]
    c = cds.astype(float).copy()
    c.index = pd.to_datetime(c.index)
    mm["cds_avg"] = c.resample("ME").mean().mean(axis=1)
    mm.index = mm.index.to_period("M")
    ibw = ib.pivot(index="month", columns="country", values="ib_spread")
    mm["ib_spread_avg"] = ibw[[k for k in ibw.columns if k != "Kuwait"]].mean(axis=1)  # KWD is basket-pegged
    iss = issuance.groupby("month")["sukuk_12m_bn"].sum()
    mm["log_gcc_sukuk_12m"] = np.log1p(iss)
    return mm


def chart_pc1(res: dict, drivers: pd.DataFrame, out: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = res["scores"]["PC1"]
    t = s.index.to_timestamp()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, facecolor=SURFACE,
                             gridspec_kw={"height_ratios": [3, 2]})
    ax = axes[0]
    _style(ax)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.plot(t, s.values, color=SUKUK_C, linewidth=2)
    ax.set_title(f"{title}: first common factor of the twin-curve basis "
                 f"({res['share']['PC1']:.0%} of variance); higher = discount narrower", fontsize=10,
                 color=INK, loc="left")
    ax2 = axes[1]
    _style(ax2)
    cds = drivers["cds_avg"].reindex(s.index)
    ax2.plot(t, cds.values, color=CONV_C, linewidth=2)
    ax2.set_title("Average GCC sovereign 5y CDS (bp), for comparison", fontsize=9, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", choices=["desktop", "platform"], help="refresh interbank fixings first")
    p.add_argument("--data", type=Path, default=C.DATA_DIR / "USD")
    a = p.parse_args(argv)
    C.setup_logging("run_drivers")

    if a.session:
        from src.session import lseg_session
        with lseg_session(a.session):
            interbank = pull_interbank(IB_PATH)
    elif IB_PATH.exists():
        interbank = pd.read_parquet(IB_PATH)
    else:
        log.error("No interbank data at %s; run with --session platform first", IB_PATH)
        return 1

    out = a.data / "analysis" / "drivers"
    out.mkdir(parents=True, exist_ok=True)
    ust = pd.read_parquet(C.TWIN["ust_curve_path"]).astype(float).sort_index()
    cds = pd.read_parquet(C.DATA_DIR / "market" / "sovereign_cds.parquet")
    market = pd.read_parquet(C.DATA_DIR / "market" / "market_daily.parquet")
    uni = pd.read_parquet(a.data / "interim" / "universe_final.parquet")
    basis = pd.read_parquet(a.data / "analysis" / "twin_basis_obs.parquet")
    bonds = load_panel(uni, a.data / "timeseries")

    ib = interbank_spread_monthly(interbank, ust)
    issuance = issuance_monthly(uni)
    panel = add_drivers(build_panel(basis, bonds, cds, ust), ib, issuance, market)
    reg = within_issuer_drivers(panel)
    drivers = monthly_drivers(market, cds, ib, issuance)

    pca_tables, fac_tables = [], []
    for label, start, end, cov in PCA_WINDOWS:
        X = basis_matrix(panel, start, end, min_coverage=cov)
        if X.shape[1] < 3 or len(X) < 24:
            log.warning("PCA window %s too thin (%s)", label, X.shape)
            continue
        res = pca(X)
        dres = pca(X.diff().dropna())
        pca_tables.append((label, X, res, dres))
        lv = factor_regression(res["scores"]["PC1"], drivers.reindex(X.index))
        dd = drivers.reindex(X.index).diff()
        ch = factor_regression(dres["scores"]["PC1"], dd.reindex(dres["scores"].index))
        fac_tables.append((label, lv, ch))
        if label.startswith("Main"):
            chart_pc1(res, drivers, out / "drivers_pc1.png", "Jul 2021 - Sep 2026")

    panel.assign(month=panel["month"].astype(str)).to_csv(out / "drivers_panel_issuer_month.csv", index=False)
    reg.to_csv(out / "drivers_within_issuer.csv", index=False)
    drivers.assign(month=drivers.index.astype(str)).to_csv(out / "drivers_monthly_gcc.csv", index=False)
    issuance.assign(month=issuance["month"].astype(str)).to_csv(out / "issuance_by_country_month.csv", index=False)

    ib_tbl = ib.assign(year=ib["month"].dt.year).groupby(["year", "country"])["ib_spread"].mean().unstack().round(0)
    iss_tbl = issuance.assign(year=issuance["month"].dt.year).groupby(["year", "country"])["sukuk_usd_bn"].sum().unstack().round(1)
    L = ["# Drivers of the sukuk discount: funding, supply and a common factor\n",
         f"Generated {date.today():%Y-%m-%d}.\n",
         "## New variables\n",
         "- **Interbank spread (bp):** local 3-month fixing minus the 3-month US Treasury bill (SAIBOR "
         "`SASAR3MD=`, EIBOR `DXAED3MD=`, QIBOR `QAQAR3MD=`, BHIBOR `BHIBOR3M=`, KIBOR `KIBOR3M=`, Oman "
         "`OMOMR3MD=CBOX`). All six currencies are pegged to the USD (Kuwait to a basket), so the spread "
         "measures local funding tightness for the banks that hold most sukuk. Matched to issuers by "
         "country of risk. Kuwait is left out of the GCC average because of its basket peg.",
         "- **Sukuk issuance:** USD sukuk issued by country of risk, from the security universe (one line per "
         "bond), trailing 12 months, in logs. Also the sukuk share of all USD bond issuance. **USD only:** "
         "local-currency sukuk (large in Saudi Arabia) are not in the universe.",
         "- **Global controls:** monthly Brent, VIX, 10-year US Treasury yield.\n",
         "### Interbank spread by year (bp)\n", _md(ib_tbl.reset_index()),
         "\n### USD sukuk issuance by year (bn)\n", _md(iss_tbl.reset_index()),
         "\n## Panel regressions (issuer fixed effects)\n",
         "`coef_per_1sd_bp` = change in basis (bp) for a one-standard-deviation rise in the variable, so "
         "variables can be compared. CDS per 100bp = coef_raw x 100. Same sample in every row.\n\n",
         _md(reg),
         "\n## Common factor (PCA on the issuer-by-month basis)\n",
         "Each column (issuer) is demeaned and standardized, so every issuer counts equally and only movements "
         "over time matter. The panel must be balanced, so only issuers observed in at least 90% of months "
         "enter (short gaps of up to 2 months are interpolated). *Changes* runs the PCA on monthly changes, "
         "which avoids trends driving the result.\n",
         "> **Sukuk issuance is not a finding.** In levels, GCC sukuk issuance looks like the strongest single "
         "driver of the factor (t of about 8 to 10). In monthly changes the effect is zero, and in the issuer "
         "panel it is insignificant and flips sign with month fixed effects. Both series trend over 2021-2026, "
         "so the levels result is most likely a shared trend, not a supply effect. Do not cite it as evidence.\n"]
    for (label, X, res, dres), (_, lv, ch) in zip(pca_tables, fac_tables):
        share = pd.DataFrame({"component": res["share"].index[:4],
                              "variance_share_levels": res["share"].values[:4].round(2),
                              "variance_share_changes": dres["share"].values[:4].round(2)})
        L += [f"\n### {label}: {X.shape[1]} issuers, {len(X)} months\n",
              "Issuers: " + "; ".join(X.columns) + "\n\n", _md(share),
              "\nPC1 loadings (levels / changes):\n\n",
              _md(pd.DataFrame({"issuer": res["loadings"].index,
                                "PC1_levels": res["loadings"]["PC1"].round(2).values,
                                "PC1_changes": dres["loadings"]["PC1"].reindex(res["loadings"].index).round(2).values})),
              "\nWhat moves PC1? Coefficients are per one standard deviation of each driver (Newey-West t, 3 lags). "
              "A positive coefficient means the driver narrows the discount (moves the basis toward zero).\n\n"
              "**Levels:**\n\n", _md(lv), "\n**Monthly changes:**\n\n", _md(ch)]
    L += ["\n![PC1](drivers_pc1.png)\n",
          "\n## Caveats\n",
          "- The PCA uses 6 issuers (8 in the robustness window) over about 5 years, so it shows whether there "
          "is a common component, not a precise decomposition.",
          "- Level regressions on trending series (CDS fell a lot after 2022) can show spurious relationships. "
          "Read the changes regressions as the stricter test.",
          "- The issuance variable covers USD issuance only, and its levels relationship with the factor is a "
          "shared trend (see the note above).",
          "- Interbank fixings are matched by country, so Abu Dhabi, Dubai and Sharjah issuers share EIBOR.\n"]
    (out / "drivers_results.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Panel regressions:\n%s", reg.to_string(index=False))
    for (label, X, res, dres), (_, lv, ch) in zip(pca_tables, fac_tables):
        log.info("%s: %s, PC1 share levels %.2f changes %.2f", label, X.shape, res["share"]["PC1"], dres["share"]["PC1"])
        log.info("levels:\n%s\nchanges:\n%s", lv.to_string(index=False), ch.to_string(index=False))
    log.info("Wrote %s", out / "drivers_results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
