"""Does the sukuk discount widen with credit stress? (issuer-month panel)

Dependent variable: the twin-curve basis (sukuk yield minus same-maturity
conventional yield, bp), averaged by issuer and month.

Credit measures:
  cds         sovereign 5y CDS of the issuer's government (config.ISSUER_SOVEREIGN).
              Comes from outside the bond data, so noise in the conventional
              yield cannot feed both sides of the regression.
  spread_conv conventional yield minus the US Treasury yield at the same maturity.
              Kept for comparison only: the conventional yield is in the basis
              too, which biases its slope negative.

Liquidity control:
  liq_gap     sukuk minus conventional median bid-ask (bp of yield) for the
              issuer-month. Wider sukuk bid-asks would also make sukuk yields
              look different, so the discount could be a liquidity effect.

Inference: issuer-clustered standard errors and Driscoll-Kraay (robust to
cross-issuer correlation in the same month). Clusters are few (about 16), so
read t-stats near 2 with care.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CDS_RICS, ISSUER_SOVEREIGN, TWIN

log = logging.getLogger(__name__)


def pull_cds(out_path: Path, start: str = "2016-01-01", end: str | None = None) -> pd.DataFrame:
    """Daily MID_SPREAD (bp) for CDS_RICS via ld.get_history (needs an open session)."""
    from .session import call_api, ld

    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    cols = {}
    for name, ric in CDS_RICS.items():
        h = call_api(ld.get_history, ric, fields=["MID_SPREAD"], interval="daily", start=start, end=end)
        cols[name] = pd.to_numeric(h["MID_SPREAD"], errors="coerce")
        log.info("CDS %s (%s): %d days from %s", name, ric, cols[name].notna().sum(),
                 cols[name].first_valid_index())
    df = pd.DataFrame(cols)
    df.index.name = "date"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return df


def _ust_at(ust: pd.DataFrame, dates: pd.Series, taus: np.ndarray) -> np.ndarray:
    ten = np.array(ust.columns, float)
    U = ust.reindex(pd.DatetimeIndex(dates), method="ffill").to_numpy(float)
    out = np.full(len(taus), np.nan)
    for i, (row, t) in enumerate(zip(U, taus)):
        ok = ~np.isnan(row)
        if ok.sum() >= 2:
            out[i] = np.interp(t, ten[ok], row[ok])
    return out


def build_panel(basis: pd.DataFrame, bond_panel: pd.DataFrame, cds: pd.DataFrame,
                ust: pd.DataFrame) -> pd.DataFrame:
    """Issuer-month panel: basis, CDS, conventional spread, liquidity gap."""
    b = basis[basis["match_method"].isin(TWIN["main_methods"])].copy()
    b["month"] = b["date"].dt.to_period("M")
    b["ust"] = _ust_at(ust, b["date"], b["tau"].to_numpy())
    b["spread_conv"] = (b["y_conv"] - b["ust"]) * 100
    p = (b.groupby(["parent_key", "parent_name", "sovereign", "month"])
          .agg(basis=("basis_bp", "mean"), spread_conv=("spread_conv", "mean"),
               days=("date", "nunique"), sukuk_bonds=("instrument_id", "nunique"),
               country=("country", "first"))
          .reset_index())

    bp = bond_panel.copy()
    bp["ba_bp"] = (bp["bid_yield"] - bp["ask_yield"]) * 100
    bp["month"] = bp["date"].dt.to_period("M")
    ba = bp.groupby(["parent_key", "month", "is_sukuk"])["ba_bp"].median().unstack()
    ba.columns = ["ba_conv" if not c else "ba_sukuk" for c in ba.columns]
    ba["liq_gap"] = ba["ba_sukuk"] - ba["ba_conv"]
    p = p.merge(ba.reset_index(), on=["parent_key", "month"], how="left")

    cm = cds.copy()
    cm.index = pd.to_datetime(cm.index)
    cm = cm.astype(float).resample("ME").mean()
    cm.index = cm.index.to_period("M")
    p["cds_sovereign"] = p["parent_key"].map(ISSUER_SOVEREIGN)
    p["cds"] = [cm.at[m, s] if isinstance(s, str) and m in cm.index else np.nan
                for m, s in zip(p["month"], p["cds_sovereign"])]
    p = p.sort_values(["parent_key", "month"]).reset_index(drop=True)
    p["cds_lag1"] = p.groupby("parent_key")["cds"].shift(1)
    p["t"] = p["month"].astype(str)
    return p


def _fit(formula: str, d: pd.DataFrame, x: str, label: str, B: int = 0) -> dict:
    """Issuer-FE regression row: issuer-clustered and Driscoll-Kraay t, plus (B > 0) restricted wild
    cluster bootstrap p-values by government and by issuer (Webb weights)."""
    import statsmodels.formula.api as smf

    from .inference import wild_cluster_bootstrap

    d = d.dropna(subset=[c for c in ["basis", x, "liq_gap"] if c in formula or c == x])
    if d["parent_key"].nunique() < 3 or len(d) < 20:
        return {"model": label, "n_obs": len(d), "issuers": d["parent_key"].nunique()}
    m = smf.ols(formula, d)
    cl = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["parent_key"])[0]})
    tcodes = pd.factorize(d["t"], sort=True)[0]
    dk = m.fit(cov_type="hac-groupsum", cov_kwds={"time": tcodes, "maxlags": 3})
    out = {"model": label, "n_obs": len(d), "issuers": d["parent_key"].nunique(),
           "slope_per_100bp": round(cl.params[x] * 100, 1),
           "t_cluster_issuer": round(cl.tvalues[x], 2), "t_driscoll_kraay": round(dk.tvalues[x], 2)}
    if B:
        dd = d.assign(cds_sovereign=d["cds_sovereign"].fillna(d["parent_key"]))
        for name, col in (("government", "cds_sovereign"), ("issuer", "parent_key")):
            if dd[col].nunique() >= 3:
                out[f"p_wild_{name}"] = round(wild_cluster_bootstrap(formula, dd, x, col, B=B)["p_wild"], 3)
                out[f"clusters_{name}"] = int(dd[col].nunique())
    if "liq_gap" in formula:
        out["liq_gap_coef"] = round(cl.params["liq_gap"], 2)
        out["liq_gap_t"] = round(cl.tvalues["liq_gap"], 2)
    return out


def add_drivers(p: pd.DataFrame, ib_spread: pd.DataFrame, issuance: pd.DataFrame,
                market: pd.DataFrame) -> pd.DataFrame:
    """Merge country-month interbank spread and issuance, and month-level global controls."""
    p = p.merge(ib_spread, on=["country", "month"], how="left")
    p = p.merge(issuance[["country", "month", "sukuk_12m_bn", "log_sukuk_12m", "sukuk_share_12m"]],
                on=["country", "month"], how="left")
    mk = market.astype(float).copy()
    mk.index = pd.to_datetime(mk.index)
    mm = mk[["LCOc1", ".VIX", "US10YT=RR"]].resample("ME").mean()
    mm.index = mm.index.to_period("M")
    mm.columns = ["brent", "vix", "ust10y"]
    return p.merge(mm.rename_axis("month").reset_index(), on="month", how="left")


def within_issuer_drivers(p: pd.DataFrame) -> pd.DataFrame:
    """Issuer-FE regressions adding local funding, supply and global controls to CDS + liquidity.

    One row per (model, variable); slopes are per one standard deviation of each
    variable so they can be compared, plus CDS per 100bp."""
    import statsmodels.formula.api as smf

    fe = "C(parent_key)"
    base = ["cds", "liq_gap"]
    specs = [
        ("CDS + liquidity (baseline, same sample)", base),
        ("+ interbank spread", base + ["ib_spread"]),
        ("+ sukuk issuance (log, 12m)", base + ["log_sukuk_12m"]),
        ("+ sukuk share of issuance (12m)", base + ["sukuk_share_12m"]),
        ("+ interbank + issuance + global (Brent, VIX, UST10y)",
         base + ["ib_spread", "log_sukuk_12m", "brent", "vix", "ust10y"]),
        ("+ interbank + issuance, month FE (global absorbed)", base + ["ib_spread", "log_sukuk_12m"]),
    ]
    allvars = sorted({v for _, vs in specs for v in vs})
    d = p.dropna(subset=["basis"] + allvars).copy()
    sd = d[allvars].std(ddof=1)
    rows = []
    for label, vs in specs:
        f = f"basis ~ {' + '.join(vs)} + {fe}" + (" + C(t)" if "month FE" in label else "")
        m = smf.ols(f, d)
        cl = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["parent_key"])[0]})
        dk = m.fit(cov_type="hac-groupsum", cov_kwds={"time": pd.factorize(d["t"], sort=True)[0], "maxlags": 3})
        for v in vs:
            rows.append({"model": label, "variable": v,
                         "coef_per_1sd_bp": round(cl.params[v] * sd[v], 1),
                         "coef_raw": round(cl.params[v], 3),
                         "t_cluster_issuer": round(cl.tvalues[v], 2), "t_driscoll_kraay": round(dk.tvalues[v], 2),
                         "n_obs": int(cl.nobs), "issuers": d["parent_key"].nunique()})
    return pd.DataFrame(rows)


def within_issuer(p: pd.DataFrame, B: int = 0) -> pd.DataFrame:
    fe = "C(parent_key)"
    rows = [
        _fit(f"basis ~ spread_conv + {fe}", p, "spread_conv",
             "Conventional spread (mechanically biased, for comparison)"),
        _fit(f"basis ~ cds + {fe}", p, "cds", "Sovereign CDS", B),
        _fit(f"basis ~ cds + liq_gap + {fe}", p, "cds", "Sovereign CDS + liquidity gap", B),
        _fit(f"basis ~ cds_lag1 + liq_gap + {fe}", p, "cds_lag1", "CDS lagged 1 month + liquidity gap", B),
        _fit(f"basis ~ cds + liq_gap + {fe} + C(t)", p, "cds", "CDS + liquidity + month FE", B),
        _fit(f"basis ~ cds + liq_gap + {fe}", p[p["sovereign"]], "cds", "Sovereign issuers only (own CDS)", B),
        _fit(f"basis ~ cds + liq_gap + {fe}", p[p["parent_key"] != "dubai emirate"], "cds",
             "Excluding Dubai govt (20y brackets)", B),
        _fit(f"basis ~ cds + liq_gap + {fe}", p[p["month"].dt.year != 2020], "cds", "Excluding 2020", B),
    ]
    return pd.DataFrame(rows)


def leave_one_sovereign_out(p: pd.DataFrame, iss: pd.DataFrame) -> pd.DataFrame:
    """Issuers sharing a government share its CDS series, so there are only ~6
    independent credit series. Re-estimate dropping one government at a time, and
    cluster standard errors by government as well as by issuer."""
    import statsmodels.formula.api as smf

    rows = []
    for s in [None] + sorted(p["cds_sovereign"].dropna().unique()):
        d = p.dropna(subset=["cds", "liq_gap"])
        d = d if s is None else d[d["cds_sovereign"] != s]
        m = smf.ols("basis ~ cds + liq_gap + C(parent_key)", d)
        fi = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["parent_key"])[0]})
        fs = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cds_sovereign"])[0]})
        x = iss.dropna(subset=["cds"])
        x = x if s is None else x[x["cds_sovereign"] != s]
        xs = smf.ols("basis ~ cds", x).fit(cov_type="HC1")
        rows.append({"dropped": s or "none", "issuers": d["parent_key"].nunique(),
                     "within_slope_per_100bp": round(fi.params["cds"] * 100, 1),
                     "t_cluster_issuer": round(fi.tvalues["cds"], 2),
                     "t_cluster_government": round(fs.tvalues["cds"], 2),
                     "cross_slope_per_100bp": round(xs.params["cds"] * 100, 1), "cross_t": round(xs.tvalues["cds"], 2),
                     "cross_spearman": round(x["basis"].corr(x["cds"], method="spearman"), 2)})
    return pd.DataFrame(rows)


def cross_issuer(p: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    import statsmodels.formula.api as smf

    iss = (p.groupby(["parent_key", "parent_name", "sovereign", "cds_sovereign"], dropna=False)
             .agg(months=("month", "size"), basis=("basis", "mean"), cds=("cds", "mean"),
                  spread_conv=("spread_conv", "mean"), liq_gap=("liq_gap", "mean"),
                  ba_sukuk=("ba_sukuk", "mean"), ba_conv=("ba_conv", "mean"))
             .reset_index().sort_values("cds"))
    rows = []
    for x, label, d in [("spread_conv", "Conventional spread, all issuers", iss),
                        ("cds", "Sovereign CDS", iss.dropna(subset=["cds"])),
                        ("cds", "Sovereign CDS, excluding Dubai govt",
                         iss.dropna(subset=["cds"]).query("parent_key != 'dubai emirate'"))]:
        r = smf.ols(f"basis ~ {x}", d).fit(cov_type="HC1")
        r2 = smf.ols(f"basis ~ {x} + liq_gap", d.dropna(subset=["liq_gap"])).fit(cov_type="HC1")
        rows.append({"model": label, "issuers": len(d), "corr": round(d["basis"].corr(d[x]), 2),
                     "spearman": round(d["basis"].corr(d[x], method="spearman"), 2),
                     "slope_per_100bp": round(r.params[x] * 100, 1), "t_robust": round(r.tvalues[x], 2),
                     "slope_with_liq_control": round(r2.params[x] * 100, 1), "t_with_liq": round(r2.tvalues[x], 2),
                     "liq_gap_coef": round(r2.params["liq_gap"], 2), "liq_gap_t": round(r2.tvalues["liq_gap"], 2)})
    return iss.round(1), pd.DataFrame(rows)
