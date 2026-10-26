"""Tables, charts and twin_results.md for the twin-curve analysis."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TWIN
from .summary import _md
from .twin import cross_issuer, issuer_daily, issuer_stats

# Light-mode reference palette (dataviz skill): series slots 1-2, text and surface tokens.
SUKUK_C, CONV_C = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def chart_basis_by_issuer(daily: pd.DataFrame, stats: pd.DataFrame, out: Path, top: int = 9) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = stats.head(top)["issuer"].tolist()
    ncol = 3
    nrow = int(np.ceil(len(names) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 2.6 * nrow), sharex=True, facecolor=SURFACE)
    axes = np.atleast_1d(axes).ravel()
    for ax, name in zip(axes, names):
        g = daily[daily["parent_name"] == name].set_index("date")["basis_bp"].sort_index()
        m = g.resample("ME").median()
        _style(ax)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.plot(g.index, g.values, color=SUKUK_C, alpha=0.18, linewidth=0.6)
        ax.plot(m.index, m.values, color=SUKUK_C, linewidth=2)
        st = stats.set_index("issuer").loc[name]
        ax.set_title(f"{name}\nmean {st.mean_basis_bp:+.0f}bp (NW t {st.nw_t:.1f})",
                     fontsize=9, color=INK, loc="left")
    for ax in axes[len(names):]:
        ax.set_visible(False)
    fig.suptitle("Sukuk yield minus the issuer's own conventional curve at the same maturity (bp)\n"
                 "daily (faint) and monthly median (bold); below zero = sukuk yield less",
                 fontsize=11, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def chart_curve_snapshot(panel: pd.DataFrame, b: pd.DataFrame, parent_key: str, day: pd.Timestamp,
                         title: str, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = panel[(panel["parent_key"] == parent_key) & (panel["date"] == day)].sort_values("tau")
    s, c = d[d["is_sukuk"]], d[~d["is_sukuk"]]
    m = b[(b["parent_key"] == parent_key) & (b["date"] == day) & b["match_method"].isin(TWIN["main_methods"])]
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    _style(ax)
    ax.plot(c["tau"], c["y"], color=CONV_C, linewidth=2, marker="o", markersize=5, label="Conventional")
    ax.plot(s["tau"], s["y"], color=SUKUK_C, linewidth=0, marker="o", markersize=7, label="Sukuk",
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    for r in m.itertuples():
        ax.plot([r.tau, r.tau], [r.y_conv, r.y_sukuk], color=INK2, linewidth=0.8, linestyle=":")
    if len(c):
        ax.annotate("Conventional", (c["tau"].iloc[-1], c["y"].iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", color=INK2, fontsize=8, va="center")
    if len(s):
        ax.annotate("Sukuk", (s["tau"].iloc[-1], s["y"].iloc[-1]), xytext=(4, -10),
                    textcoords="offset points", color=INK2, fontsize=8, va="center")
    ax.set_xlabel("Years to maturity", color=INK2, fontsize=9)
    ax.set_ylabel("Mid yield to maturity (%)", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
    ax.set_title(f"{title}, {day:%d %b %Y}: dotted lines are the matched gaps", fontsize=10,
                 color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def write_report(panel: pd.DataFrame, b: pd.DataFrame, gaps: pd.DataFrame, out_dir: Path,
                 cfg: dict = TWIN, validation: pd.DataFrame | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    main_m = cfg["main_methods"]
    daily = issuer_daily(b, main_m)
    stats = issuer_stats(daily, b, cfg)
    main = cross_issuer(stats)

    # Robustness variants
    interp_cfg = {**cfg, "main_methods": ["interp"]}
    interp = b[b["match_method"] == "interp"]
    st_interp = issuer_stats(issuer_daily(interp, ["interp"]), interp, interp_cfg)
    narrow = b[b["match_method"].isin(main_m)
               & ((b["match_method"] != "interp") | (b["bracket_width"] <= cfg["max_bracket_width"]))]
    st_narrow = issuer_stats(issuer_daily(narrow, main_m), narrow, cfg)
    since2020 = b[b["date"] >= "2020-01-01"]
    st_2020 = issuer_stats(issuer_daily(since2020, main_m), since2020, cfg)
    robust = pd.DataFrame([
        {"variant": "Main: interpolation + UST-adjusted nearest (<= 1y)", **main},
        {"variant": "Interpolation only", **cross_issuer(st_interp)},
        {"variant": f"Interpolation brackets <= {cfg['max_bracket_width']:g}y", **cross_issuer(st_narrow)},
        {"variant": "2020 onward only", **cross_issuer(st_2020)},
    ])
    if validation is not None:
        validation.to_csv(out_dir / "twin_matching_validation.csv", index=False)
    if len(gaps):
        gi = gaps.groupby(["parent_key", "tenor"])["gap_bp"].mean().reset_index()
        tenor_tbl = gi.groupby("tenor")["gap_bp"].agg(issuers="size", mean_of_issuer_means_bp="mean",
                                                      median_of_issuer_means_bp="median").round(1).reset_index()
    else:
        tenor_tbl = pd.DataFrame()

    daily["year"] = daily["date"].dt.year
    by_year = daily.pivot_table(index="parent_name", columns="year", values="basis_bp",
                                aggfunc="median").round(0)
    by_year = by_year.loc[[n for n in stats["issuer"] if n in by_year.index]]
    split = stats.groupby("sovereign").apply(lambda g: pd.Series(cross_issuer(g)), include_groups=False)
    split.index = split.index.map({True: "Sovereign", False: "Quasi-sovereign / corporate"})
    split[["issuers", "issuers_negative"]] = split[["issuers", "issuers_negative"]].astype(int)

    b.to_parquet(out_dir / "twin_basis_obs.parquet", index=False)
    daily.to_csv(out_dir / "twin_basis_issuer_daily.csv", index=False)
    stats.to_csv(out_dir / "twin_issuer_stats.csv", index=False)
    gaps.to_csv(out_dir / "twin_tenor_gaps.csv", index=False)
    robust.to_csv(out_dir / "twin_robustness.csv", index=False)

    chart_basis_by_issuer(daily, stats, out_dir / "twin_basis_by_issuer.png")
    snap_key = stats.iloc[0]["issuer"]
    pk = daily.loc[daily["parent_name"] == snap_key, "parent_key"].iloc[0]
    day = daily.loc[daily["parent_key"] == pk, "date"].max()
    chart_curve_snapshot(panel, b, pk, day, snap_key, out_dir / "twin_curve_snapshot.png")

    cl = panel.attrs.get("cleaning", {})
    L = ["# Within-issuer twin-curve analysis: GCC sukuk vs conventional (USD)\n",
         f"Generated {date.today():%Y-%m-%d} from `data/USD/timeseries`.\n",
         "## Method\n",
         "- **Sample:** plain fixed-coupon bonds of at least "
         f"${cfg['min_amount_usd'] / 1e6:.0f}m, one line per bond, issuers with both sukuk and conventional "
         "bonds (same Sukuk Obligor / Borrower). Yield = LSEG mid YTM (bid/ask average where mid is missing).",
         f"- **Cleaning:** {cfg['min_tau']:g}-{cfg['max_tau']:g} years to maturity; yields in "
         f"({cfg['yield_bounds'][0]:g}, {cfg['yield_bounds'][1]:g})%; drop points more than "
         f"{cfg['outlier_pp']}pp from a 21-day rolling median; drop stale runs of {cfg['stale_run_days']}+ "
         f"identical prices and bonds stale on > {cfg['max_stale_share']:.0%} of days. "
         f"Kept {cl.get('kept_obs', 'n/a'):,} of {cl.get('input_obs', 'n/a'):,} bond-days "
         f"(dropped: {', '.join(f'{k} {v:,}' for k, v in cl.items() if k not in ('input_obs', 'kept_obs'))}).",
         "- **Tenor matching:** for each sukuk on each day, the issuer's conventional yields that day are "
         "linearly interpolated at the sukuk's remaining maturity, using only the two conventional bonds "
         "that bracket it (no extrapolation). If no two bonds bracket it, the nearest conventional bond "
         f"within {cfg['nearest_max_gap']:g} year is used, shifted along that day's US Treasury curve to the "
         "sukuk's maturity: y_near + UST(sukuk maturity) - UST(nearest maturity). Share per issuer: "
         "`share_nearest_adj`. **Basis = sukuk yield minus matched conventional yield, in bp.** "
         "Negative means the sukuk yields less than the issuer's own conventional curve.",
         "- **Excluded:** " + (", ".join(cfg.get("exclude_parents", [])) or "none") + " (amortizing aircraft "
         "sukuk: yield to final maturity is not comparable).",
         f"- **Inference:** per issuer, the daily average basis is a time series; its mean has a Newey-West "
         f"standard error ({cfg['nw_lags']} lags). Across issuers, each issuer's mean counts once, so KSA "
         f"and Bahrain do not dominate. Issuers need at least {cfg['min_issuer_days']} matched days.\n",
         "## Headline\n",
         f"Across **{main.get('issuers')} issuers**, the mean of issuer-level mean bases is "
         f"**{main.get('mean_of_issuer_means_bp')}bp** (cross-issuer t = {main.get('t')}; median "
         f"{main.get('median_of_issuer_means_bp')}bp). **{main.get('issuers_negative')} of "
         f"{main.get('issuers')}** issuers have a negative mean basis.\n",
         "![basis by issuer](twin_basis_by_issuer.png)\n",
         "## By issuer\n", _md(stats),
         "\n## Sovereign vs quasi-sovereign / corporate\n", _md(split.reset_index(names="group")),
         "\n## Robustness\n", _md(robust),
         "\n## Matching validation: nearest bond vs interpolation\n",
         "On sukuk-days where interpolation is possible, the nearest conventional bond alone is used and "
         "compared with the interpolated yield. *raw* = nearest yield as is; *adj* = shifted by the US Treasury "
         "slope. *Persistent* = each bond's error averaged over time (bonds with 50+ days), which is what can "
         "bias an issuer's mean basis. *Change* errors are what the event study and pass-through use.\n\n",
         _md(validation) if validation is not None else "_not run_\n",
         "\n## Standard-tenor gaps (both curves interpolated at the tenor)\n",
         "Needs at least two sukuk and two conventional bonds bracketing the tenor on the day.\n\n",
         _md(tenor_tbl),
         "\n## Median daily basis by year (bp)\n", _md(by_year.reset_index()),
         f"\n## Curve snapshot check\n![snapshot](twin_curve_snapshot.png)\n",
         "\n## Caveats\n",
         "- Yields are LSEG mid YTMs, so the basis also picks up coupon and convexity differences "
         "between bonds. These are small at matched maturity but not zero.",
         "- Linear interpolation across wide brackets is crude: see `median_bracket_width_y` and the "
         "narrow-bracket robustness row. Dubai and DP World rely on brackets of about 20 years.",
         "- Secondary-market coverage is essentially 2019 onward. Earlier years have few issuers.",
         "- Some issuers are thin, with one sukuk or under 200 days. Read their t-stats with care.",
         "- Matching is by obligor/borrower name. Sukuk issued through a parent's SPV under a different "
         "obligor name will be missed.",
         "- 12 conventional-file lines that look like sukuk are excluded (see summary.md).",
         "\nFiles: `twin_basis_obs.parquet` (sukuk-day level), `twin_basis_issuer_daily.csv`, "
         "`twin_issuer_stats.csv`, `twin_tenor_gaps.csv`, `twin_robustness.csv`.\n"]
    (out_dir / "twin_results.md").write_text("\n".join(L), encoding="utf-8")
    return main
