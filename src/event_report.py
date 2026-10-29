"""Tables, charts and event_study.md for the oil-shock event study."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .event_study import (VARS, across_events, bond_paths, build_episodes, episode_changes, event_means,
                          oil_vol, passthrough, placebo_event_means, placebo_test, vol_bins)
from .summary import _md
from .twin_report import CONV_C, GRID, INK, INK2, SUKUK_C, SURFACE, _style

KEY_TAUS = [0, 1, 5, 10, 20]
LABEL = {"d_basis": "Basis", "d_sukuk": "Sukuk leg", "d_conv": "Conventional leg"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def chart_basis(results: dict, out: Path, title: str) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True, facecolor=SURFACE)
    for ax, sign in zip(axes, ["up", "down"]):
        r = results[sign]
        a, band = r["agg"], r["placebo"]["d_basis"]
        _style(ax)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.axvline(0, color=GRID, linewidth=1)
        if len(band):
            ax.fill_between(band["tau"], band["d_basis_p05"], band["d_basis_p95"], color=GRID, alpha=0.9,
                            linewidth=0, label="90% placebo band (median)")
        ax.plot(a["tau"], a["d_basis_mean"], color=SUKUK_C, linewidth=1, linestyle="--", label="Mean")
        ax.plot(a["tau"], a["d_basis_median"], color=SUKUK_C, linewidth=2, marker="o", markersize=3.5,
                label="Median")
        n = int(a["n_shocks"].max()) if len(a) else 0
        ax.set_title(f"Oil {'up' if sign == 'up' else 'down'}-shocks (n = {n})", fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Business days from shock", color=INK2, fontsize=9)
    axes[0].set_ylabel("Change in basis vs day -1 (bp)", color=INK2, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
    fig.suptitle(title, fontsize=11, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def chart_legs(results: dict, out: Path) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=SURFACE)
    for ax, sign in zip(axes, ["up", "down"]):
        a = results[sign]["agg"]
        _style(ax)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.axvline(0, color=GRID, linewidth=1)
        ax.plot(a["tau"], a["d_conv_mean"], color=CONV_C, linewidth=2, label="Conventional (matched)")
        ax.plot(a["tau"], a["d_sukuk_mean"], color=SUKUK_C, linewidth=2, label="Sukuk")
        for col, lab in (("d_conv_mean", "Conventional"), ("d_sukuk_mean", "Sukuk")):
            if len(a):
                ax.annotate(lab, (a["tau"].iloc[-1], a[col].iloc[-1]), xytext=(4, 0), textcoords="offset points",
                            fontsize=8, color=INK2, va="center")
        ax.set_title(f"Oil {sign}-shocks: yield change vs day -1 (bp)", fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Business days from shock", color=INK2, fontsize=9)
        ax.set_xlim(-5, 25)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK2, loc="best")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _key_table(agg: dict) -> pd.DataFrame:
    rows = []
    for sign in ("up", "down", "pooled"):
        a = agg[sign]["agg"].set_index("tau")
        pl = {v: agg[sign]["placebo"][v].set_index("tau") for v in VARS}
        for tau in KEY_TAUS:
            if tau not in a.index:
                continue
            n = int(a.loc[tau, "n_shocks"])
            r = {"shock": sign, "tau": tau, "n_shocks": n, "issuer_shocks": int(a.loc[tau, "issuer_shocks"]),
                 "basis mean": round(a.loc[tau, "d_basis_mean"], 1),
                 "basis median": round(a.loc[tau, "d_basis_median"], 1),
                 "basis <0": f"{int(a.loc[tau, 'd_basis_n_neg'])}/{n}",
                 "basis t (mean)": round(a.loc[tau, "d_basis_t"], 2)}
            p = pl["d_basis"].loc[tau, "d_basis_placebo_p"] if tau in pl["d_basis"].index else np.nan
            r["basis placebo p (median)"] = round(p, 3)
            mde = pl["d_basis"].loc[tau, "d_basis_mde80"] if tau in pl["d_basis"].index else np.nan
            r["basis MDE 80% (bp)"] = round(mde, 1)
            for v in ("d_sukuk", "d_conv"):
                r[f"{LABEL[v]} mean"] = round(a.loc[tau, f"{v}_mean"], 1)
                r[f"{LABEL[v]} median"] = round(a.loc[tau, f"{v}_median"], 1)
            rows.append(r)
    return pd.DataFrame(rows)


def run_sample(obs: pd.DataFrame, shocks: pd.DataFrame, placebo_ev: pd.DataFrame, pre: int, post: int) -> dict:
    """Up, down, and pooled (down-shock changes multiplied by -1 = response to an oil-price rise)."""
    res = {}
    empty = pd.DataFrame(columns=["event_id", "tau", *VARS, "n_issuers"])
    for sign in ("up", "down", "pooled"):
        ev = shocks if sign == "pooled" else shocks[shocks["sign"] == sign]
        paths = bond_paths(obs, ev, pre, post) if len(ev) else pd.DataFrame()
        em = event_means(paths) if len(paths) else empty.copy()
        flip = ev.set_index("event_id")["sign"].map({"up": 1.0, "down": -1.0})
        if sign == "pooled" and len(em):
            em = em.copy()
            em[list(VARS)] = em[list(VARS)].mul(em["event_id"].map(flip), axis=0)
        agg = across_events(em)
        have = ev[ev["event_id"].isin(em["event_id"].unique())]
        signs = have["sign"].map({"up": 1.0, "down": -1.0}).to_numpy() if sign == "pooled" else None
        res[sign] = {"paths": paths, "events": em, "agg": agg,
                     "placebo": {v: placebo_test(agg, placebo_ev, have["vol_bin"].to_numpy(), v, signs)
                                 for v in VARS}}
    return res


def write_event_report(obs: pd.DataFrame, shocks: pd.DataFrame, market: pd.DataFrame | None, out_dir: Path,
                       rule: str, pre: int = 5, post: int = 20) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    shocks = shocks.copy()
    shocks["date"] = pd.to_datetime(shocks["date"])
    shocks["event_id"] = shocks["date"].dt.strftime("%Y-%m-%d") + "_" + shocks["sign"]
    vol = oil_vol(market)
    span = vol.loc[obs["date"].min():obs["date"].max()].dropna()
    edges = span.quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    shocks["vol_bin"] = vol_bins(vol, shocks["date"], edges)
    placebo_ev = placebo_event_means(obs, shocks["date"], vol, edges, pre=pre, post=post)

    main = run_sample(obs, shocks, placebo_ev, pre, post)
    clean_shocks = shocks[~shocks["opposite_shock_within_window"].astype(bool)]
    clean = run_sample(obs, clean_shocks, placebo_ev, pre, post)
    ex2020_shocks = shocks[shocks["date"].dt.year != 2020]
    ex2020 = run_sample(obs, ex2020_shocks, placebo_ev, pre, post)
    episodes = episode_changes(obs, build_episodes(shocks), market, pre, post)
    all_paths = pd.concat([main[s]["paths"] for s in ("up", "down")], ignore_index=True)
    pt = pd.concat([passthrough(all_paths, obs, shocks["date"], h) for h in (5, 20)], ignore_index=True)

    # Per-shock table
    per = []
    for sign in ("up", "down"):
        em = main[sign]["events"]
        for eid, g in em.groupby("event_id"):
            g = g.set_index("tau")
            s = shocks.set_index("event_id").loc[eid]
            per.append({"date": f"{s['date']:%Y-%m-%d}", "sign": sign, "brent_pct": s["ret_pct"], "z": s["z"],
                        "overlap": "yes" if s["opposite_shock_within_window"] else "",
                        "issuers": int(g["n_issuers"].max()),
                        **{f"d_basis_{t}d": round(g.loc[t, "d_basis"], 1) if t in g.index else np.nan for t in (5, 20)},
                        **{f"d_{l}_20d": round(g.loc[20, f"d_{l}"], 1) if 20 in g.index else np.nan
                           for l in ("sukuk", "conv")}})
    per = pd.DataFrame(per).sort_values("date")

    # Sovereign vs other at +20
    split = []
    for sign in ("up", "down"):
        p = main[sign]["paths"]
        if p.empty:
            continue
        p20 = p[p["tau"] == 20].groupby(["event_id", "parent_key", "sovereign"])[list(VARS)].mean().reset_index()
        for sov, g in p20.groupby("sovereign"):
            e = g.groupby("event_id")[list(VARS)].mean()
            split.append({"shock": sign, "group": "Sovereign" if sov else "Quasi-sov / corporate",
                          "n_shocks": len(e), "issuer_shocks": len(g),
                          **{f"{LABEL[v]} +20d (bp)": round(e[v].mean(), 1) for v in VARS},
                          "basis t": round(e["d_basis"].mean() / (e["d_basis"].std(ddof=1) / np.sqrt(len(e))), 2)
                          if len(e) > 1 else np.nan})
    split = pd.DataFrame(split)

    key_main, key_clean, key_ex = _key_table(main), _key_table(clean), _key_table(ex2020)
    key_main.to_csv(out_dir / "event_key_main.csv", index=False)
    key_clean.to_csv(out_dir / "event_key_clean.csv", index=False)
    key_ex.to_csv(out_dir / "event_key_ex2020.csv", index=False)
    pt.to_csv(out_dir / "event_passthrough.csv", index=False)
    per.to_csv(out_dir / "event_per_shock.csv", index=False)
    episodes.to_csv(out_dir / "event_episodes.csv", index=False)
    pd.concat([main[s]["paths"].assign(shock=s) for s in ("up", "down")]).to_parquet(
        out_dir / "event_bond_paths.parquet", index=False)
    for s in ("up", "down"):
        main[s]["agg"].to_csv(out_dir / f"event_paths_{s}.csv", index=False)
    chart_basis(main, out_dir / "event_basis.png",
                "Twin-curve basis around oil shocks (all shocks): sukuk minus same-maturity conventional yield")
    chart_basis(clean, out_dir / "event_basis_clean.png",
                "Twin-curve basis around oil shocks (no opposite-sign shock in window)")
    chart_legs(main, out_dir / "event_legs.png")

    L = ["# Oil shocks and the twin curves: event study\n",
         f"Generated {date.today():%Y-%m-%d}. Shock rule: {rule}.\n",
         "## Design\n",
         f"- **Window:** {pre} business days before to {post} after each shock (day 0 = shock day). Each "
         "matched sukuk's change is measured against its own last observation before the shock (day -1 or "
         "earlier, down to day -5).",
         "- **Measures (bp):** *basis* = sukuk yield minus the issuer's conventional yield interpolated at "
         "the same maturity; *sukuk leg* = the sukuk's own yield; *conventional leg* = that matched "
         "conventional yield. Basis change = sukuk leg change minus conventional leg change.",
         "- **Aggregation:** bonds, then issuer mean, then shock mean, then the mean across shocks. Each shock "
         "counts once.",
         "- **Inference:** *t* uses the cross-shock standard error of the mean. Because a few 2020 shocks "
         "dominate the means (see shock by shock), the main test uses the **median across shocks**, the "
         "count of shocks with a negative change, and a volatility-matched placebo. For the placebo, up to "
         "1,000 random business days at least 25 business days from any shock are sorted into quintiles of "
         "trailing 20-day Brent volatility. Each bootstrap draw (4,000) pairs every shock with a placebo "
         "day from its own volatility quintile and takes the median. Matching matters: shocks cluster in "
         "turbulent markets (no shock falls in the calmest quintile, 12 of 26 in the most volatile). The "
         "grey band in the charts is the matched placebo's 90% range for the median.",
         "- **Pass-through:** the slope of the sukuk-leg change on the conventional-leg change, across "
         "issuer-shocks, compared with the same slope on normal days (non-overlapping 5- and 20-day changes "
         "away from shocks). A slope of 1 means the curves move together one for one. Below 1, sukuk are a "
         "damped version of the conventional curve.",
         "- **Pooled:** all shocks together, with down-shock changes multiplied by -1. It reads as the "
         "response to an oil-price *rise* and tests one hypothesis with all 26 shocks: does the basis move "
         "with oil? This assumes up and down responses are symmetric, which the separate rows let you check.",
         "- **Robustness:** (1) *clean* subset: shocks with no opposite-sign shock inside the window; "
         "(2) *episodes*: shocks less than 20 business days apart are chained, and the net change runs from "
         "before the first shock to 20 days after the last.\n",
         "## Key findings (computed)\n",
         *_findings(key_main, key_ex, pt),
         "\n## How the twin curves co-move: pass-through, shocks vs normal days\n",
         _md(pt),
         "\n## Main results (all shocks)\n",
         "![basis](event_basis.png)\n",
         _md(key_main),
         "\n![legs](event_legs.png)\n",
         "\n## Robustness 0: excluding 2020\n",
         f"{len(ex2020_shocks)} shocks ({int((ex2020_shocks.sign == 'up').sum())} up, "
         f"{int((ex2020_shocks.sign == 'down').sum())} down).\n\n",
         _md(key_ex),
         "\n## Robustness 1: clean shocks only (no opposite-sign shock in window)\n",
         f"{len(clean_shocks)} of {len(shocks)} shocks "
         f"({int((clean_shocks.sign == 'up').sum())} up, {int((clean_shocks.sign == 'down').sum())} down).\n",
         "![basis clean](event_basis_clean.png)\n",
         _md(key_clean),
         "\n## Robustness 2: multi-shock episodes (net effect)\n",
         "Linked shocks are chained. Changes run from the last observation before the first shock to the "
         "last observation within 20 business days after the last shock. Each issuer counts once per "
         "episode. `brent_net_pct` is the Brent move over the same span.\n\n",
         _md(episodes),
         "\n## Sovereign vs quasi-sovereign / corporate (+20 days)\n", _md(split),
         "\n## Shock by shock\n", _md(per),
         "\n## Reading the results\n",
         "- A **negative basis change** means the sukuk yield fell relative to the issuer's conventional "
         "curve, or rose less: sukuk outperformed. A positive change means sukuk underperformed.",
         "- The legs show *which* curve moved. Both legs also include moves in US Treasury yields, which "
         "cancel in the basis.",
         "\n## Caveats\n",
         "- Few shocks (9 up, 17 down), and only 3-4 issuers before 2021. Pre-2021 shocks rest mainly on "
         "KSA, Bahrain, Oman and Dubai.",
         "- Shocks are defined from price moves, so anticipated events (pre-announced OPEC cuts) are not "
         "included by design.",
         "- Some geopolitical episodes produce shocks of both signs within weeks (Russia-Ukraine 2022, "
         "Israel-Iran 2025, 2020, 2026). Each is treated as a separate surprise, with the clean-subset and "
         "episode checks above.",
         "- The basis inherits the twin-curve caveats: linear interpolation, mid yields, and matching by "
         "obligor name.",
         "\nFiles: `event_key_main.csv`, `event_key_clean.csv`, `event_per_shock.csv`, `event_episodes.csv`, "
         "`event_paths_up.csv`, `event_paths_down.csv`, `event_bond_paths.parquet`.\n"]
    (out_dir / "event_study.md").write_text("\n".join(L), encoding="utf-8")
    return {"main": key_main, "clean": key_clean, "ex2020": key_ex, "passthrough": pt, "episodes": episodes,
            "per": per, "split": split}


def _findings(key_main: pd.DataFrame, key_ex: pd.DataFrame, pt: pd.DataFrame) -> list[str]:
    """Plain statements generated from the tables (no hand-typed numbers)."""
    out = []
    k = key_main.set_index(["shock", "tau"])
    e = key_ex.set_index(["shock", "tau"])
    for sign in ("down", "up"):
        for tau in (5, 20):
            if (sign, tau) not in k.index:
                continue
            r = k.loc[(sign, tau)]
            x = e.loc[(sign, tau)] if (sign, tau) in e.index else None
            out.append(f"- **Oil {sign}-shocks, +{tau} days:** basis mean {r['basis mean']:+.1f}bp, median "
                       f"{r['basis median']:+.1f}bp, negative in {r['basis <0']} shocks, placebo p (median) "
                       f"{r['basis placebo p (median)']:.2f}"
                       + (f"; excluding 2020: mean {x['basis mean']:+.1f}bp, median {x['basis median']:+.1f}bp."
                          if x is not None else "."))
    for h in (5, 20):
        a = pt[(pt["horizon_days"] == h) & (pt["sample"] == "Shocks ex-2020")]
        if len(a):
            a = a.iloc[0]
            out.append(f"- **Pass-through at {h} days:** sukuk move {a['beta_shock']:.2f}bp per 1bp of the "
                       f"matched conventional yield after shocks (ex-2020) vs {a['beta_normal']:.2f} on normal "
                       f"days; difference {a['diff']:+.2f}, 90% CI {a['diff_ci90']}.")
    mde = [f"{s} +{t}d: {k.loc[(s, t), 'basis MDE 80% (bp)']:.1f}bp" for s in ("up", "down", "pooled")
           for t in (5, 20) if (s, t) in k.index]
    out.append("- **Minimum detectable effect (80% power, two-sided 5%, median across shocks):** "
               + "; ".join(mde) + ". Smaller true median basis responses than these could go undetected. The "
               "pooled figure is per oil-price *rise* (down-shocks sign-flipped).")
    return out
