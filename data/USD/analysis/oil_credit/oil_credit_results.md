# Oil through credit

Generated 2026-10-29. Shocks: `oil_shocks_z3_min5pct_h1.csv` (same as the basis event study).

## a. Do oil shocks move sovereign CDS?

Outcome: change in each government's 5y CDS (bp) from its last level before the shock. *Average of sovereigns* averages the six CDS changes per shock, then summarizes across shocks (each shock counts once). *Pooled* flips down-shocks, so it reads as the response to an oil-price **rise** (negative = CDS falls = credit improves). Placebo p and MDE come from the same volatility-matched placebo as the basis study (median across shocks).


**Reading:**

- **Oil up-shocks, +5 days:** average sovereign CDS mean +4.5bp, median +5.9bp, CDS rose in 7/9 shocks, placebo p 0.000.
- **Oil down-shocks, +5 days:** average sovereign CDS mean +7.3bp, median -0.5bp, CDS rose in 8/17 shocks, placebo p 0.742.
- The up-shocks in this sample (2018-12-26, 2019-09-16, 2020-04-01, 2020-05-05, 2022-03-01, 2025-06-13, 2026-03-06, 2026-04-29, 2026-07-13) include several regional geopolitical events (the 2019 Abqaiq attack, Russia's 2022 invasion of Ukraine, the June 2025 Israel-Iran war) alongside supply/demand episodes (December 2018, April-May 2020). The causes of the 2026 shocks are not classified here. If CDS rises after oil up-shocks, conflict risk can outweigh the fiscal benefit of a higher oil price, so signing shocks by oil price alone mixes two channels; read the pooled (sign-flipped) rows with that in mind.


| sample | unit | shock | tau | n_shocks | mean_bp | median_bp | t_mean | rises | placebo_p_median | mde80_bp |
|---|---|---|---|---|---|---|---|---|---|---|
| All shocks | average of sovereigns | up | 0 | 9 | 3.6 | 0.8 | 1.7 | 6/9 | 0.045 | 1.0 |
| All shocks | average of sovereigns | up | 1 | 9 | 1.8 | 1.1 | 0.96 | 8/9 | 0.054 | 1.9 |
| All shocks | average of sovereigns | up | 5 | 9 | 4.5 | 5.9 | 1.27 | 7/9 | 0.0 | 4.2 |
| All shocks | average of sovereigns | up | 10 | 9 | 4.6 | 8.5 | 0.94 | 7/9 | 0.001 | 7.0 |
| All shocks | average of sovereigns | up | 20 | 9 | -1.8 | -0.3 | -0.24 | 4/9 | 0.318 | 10.7 |
| All shocks | average of sovereigns | down | 0 | 17 | -0.5 | -0.0 | -0.61 | 7/17 | 0.976 | 0.5 |
| All shocks | average of sovereigns | down | 1 | 17 | 0.2 | -0.2 | 0.2 | 8/17 | 0.968 | 1.3 |
| All shocks | average of sovereigns | down | 5 | 17 | 7.3 | -0.5 | 0.99 | 8/17 | 0.742 | 2.9 |
| All shocks | average of sovereigns | down | 10 | 17 | 9.7 | -0.4 | 0.83 | 8/17 | 0.351 | 4.7 |
| All shocks | average of sovereigns | down | 20 | 17 | 9.2 | 1.1 | 0.77 | 9/17 | 0.112 | 8.0 |
| All shocks | average of sovereigns | pooled | 0 | 26 | 1.6 | 0.5 | 1.7 | 16/26 | 0.006 | 0.3 |
| All shocks | average of sovereigns | pooled | 1 | 26 | 0.5 | 0.3 | 0.47 | 17/26 | 0.211 | 0.8 |
| All shocks | average of sovereigns | pooled | 5 | 26 | -3.2 | 1.3 | -0.64 | 16/26 | 0.14 | 2.1 |
| All shocks | average of sovereigns | pooled | 10 | 26 | -4.8 | 0.8 | -0.61 | 16/26 | 0.822 | 3.6 |
| All shocks | average of sovereigns | pooled | 20 | 26 | -6.6 | -0.7 | -0.81 | 12/26 | 0.522 | 7.2 |
| Clean (no opposite-sign shock in window) | average of sovereigns | up | 0 | 1 | -0.0 | -0.0 |  | 0/1 | 0.893 | 5.9 |
| Clean (no opposite-sign shock in window) | average of sovereigns | up | 1 | 1 | 1.1 | 1.1 |  | 1/1 | 0.375 | 7.8 |
| Clean (no opposite-sign shock in window) | average of sovereigns | up | 5 | 1 | 3.1 | 3.1 |  | 1/1 | 0.331 | 14.3 |
| Clean (no opposite-sign shock in window) | average of sovereigns | up | 10 | 1 | 8.6 | 8.6 |  | 1/1 | 0.185 | 20.3 |
| Clean (no opposite-sign shock in window) | average of sovereigns | up | 20 | 1 | -0.3 | -0.3 |  | 0/1 | 0.491 | 28.6 |
| Clean (no opposite-sign shock in window) | average of sovereigns | down | 0 | 10 | -0.3 | -0.0 | -0.53 | 4/10 | 0.795 | 0.7 |
| Clean (no opposite-sign shock in window) | average of sovereigns | down | 1 | 10 | -0.1 | 0.2 | -0.1 | 5/10 | 0.3 | 1.4 |
| Clean (no opposite-sign shock in window) | average of sovereigns | down | 5 | 10 | 2.4 | 0.0 | 0.7 | 5/10 | 0.515 | 3.1 |
| Clean (no opposite-sign shock in window) | average of sovereigns | down | 10 | 10 | 1.3 | 0.3 | 0.33 | 5/10 | 0.406 | 5.3 |
| Clean (no opposite-sign shock in window) | average of sovereigns | down | 20 | 10 | 3.2 | 7.2 | 0.71 | 6/10 | 0.004 | 8.0 |
| Clean (no opposite-sign shock in window) | average of sovereigns | pooled | 0 | 11 | 0.3 | 0.0 | 0.53 | 6/11 | 0.847 | 0.6 |
| Clean (no opposite-sign shock in window) | average of sovereigns | pooled | 1 | 11 | 0.2 | 0.2 | 0.2 | 6/11 | 0.985 | 1.3 |
| Clean (no opposite-sign shock in window) | average of sovereigns | pooled | 5 | 11 | -1.9 | 0.5 | -0.6 | 6/11 | 0.974 | 3.1 |
| Clean (no opposite-sign shock in window) | average of sovereigns | pooled | 10 | 11 | -0.4 | 0.4 | -0.1 | 6/11 | 0.744 | 5.3 |
| Clean (no opposite-sign shock in window) | average of sovereigns | pooled | 20 | 11 | -2.9 | -7.0 | -0.72 | 4/11 | 0.006 | 8.0 |
| Excluding 2020 | average of sovereigns | up | 0 | 7 | 2.0 | 0.8 | 1.92 | 5/7 | 0.062 | 1.1 |
| Excluding 2020 | average of sovereigns | up | 1 | 7 | 3.6 | 1.4 | 2.46 | 7/7 | 0.044 | 2.0 |
| Excluding 2020 | average of sovereigns | up | 5 | 7 | 4.9 | 5.9 | 1.98 | 6/7 | 0.002 | 4.7 |
| Excluding 2020 | average of sovereigns | up | 10 | 7 | 7.8 | 8.5 | 1.94 | 6/7 | 0.003 | 7.7 |
| Excluding 2020 | average of sovereigns | up | 20 | 7 | 3.2 | -0.3 | 0.74 | 3/7 | 0.393 | 11.2 |
| Excluding 2020 | average of sovereigns | down | 0 | 14 | -1.2 | -0.7 | -1.72 | 5/14 | 0.029 | 0.6 |
| Excluding 2020 | average of sovereigns | down | 1 | 14 | -1.1 | -0.4 | -1.19 | 5/14 | 0.72 | 1.4 |
| Excluding 2020 | average of sovereigns | down | 5 | 14 | -0.4 | -1.3 | -0.12 | 5/14 | 0.684 | 3.2 |
| Excluding 2020 | average of sovereigns | down | 10 | 14 | -2.5 | -1.0 | -0.66 | 6/14 | 0.634 | 5.3 |
| Excluding 2020 | average of sovereigns | down | 20 | 14 | -2.0 | 0.1 | -0.54 | 7/14 | 0.224 | 8.4 |
| Excluding 2020 | average of sovereigns | pooled | 0 | 21 | 1.5 | 0.8 | 2.56 | 14/21 | 0.002 | 0.4 |
| Excluding 2020 | average of sovereigns | pooled | 1 | 21 | 1.9 | 1.1 | 2.39 | 16/21 | 0.012 | 0.9 |
| Excluding 2020 | average of sovereigns | pooled | 5 | 21 | 1.9 | 1.7 | 0.87 | 15/21 | 0.105 | 2.4 |
| Excluding 2020 | average of sovereigns | pooled | 10 | 21 | 4.2 | 1.5 | 1.5 | 14/21 | 0.482 | 4.0 |
| Excluding 2020 | average of sovereigns | pooled | 20 | 21 | 2.4 | -0.3 | 0.86 | 10/21 | 0.633 | 7.4 |


**By sovereign (all shocks, +5 and +20 business days):**


| sample | unit | shock | tau | n_shocks | mean_bp | median_bp | t_mean | rises | placebo_p_median | mde80_bp |
|---|---|---|---|---|---|---|---|---|---|---|
| All shocks | KSA | up | 5 | 8 | 7.6 | 3.5 | 1.76 | 6/8 | 0.026 | 4.6 |
| All shocks | KSA | up | 20 | 9 | 1.2 | -3.0 | 0.19 | 2/9 | 0.677 | 9.2 |
| All shocks | KSA | down | 5 | 16 | 3.9 | -0.9 | 0.66 | 7/16 | 0.46 | 3.0 |
| All shocks | KSA | down | 20 | 17 | 2.2 | -1.0 | 0.41 | 7/17 | 0.742 | 6.3 |
| All shocks | KSA | pooled | 5 | 24 | -0.0 | 1.2 | -0.01 | 17/24 | 0.148 | 2.0 |
| All shocks | KSA | pooled | 20 | 26 | -1.0 | -1.0 | -0.25 | 12/26 | 0.407 | 5.3 |
| All shocks | Bahrain | up | 5 | 7 | 15.3 | 0.9 | 2.06 | 6/7 | 0.379 | 7.8 |
| All shocks | Bahrain | up | 20 | 8 | 8.5 | 4.4 | 0.91 | 6/8 | 0.263 | 20.4 |
| All shocks | Bahrain | down | 5 | 13 | 15.2 | -0.1 | 0.69 | 6/13 | 0.929 | 4.0 |
| All shocks | Bahrain | down | 20 | 13 | 20.4 | 1.0 | 0.71 | 7/13 | 0.378 | 13.7 |
| All shocks | Bahrain | pooled | 5 | 20 | -4.5 | 0.2 | -0.31 | 13/20 | 0.148 | 2.1 |
| All shocks | Bahrain | pooled | 20 | 21 | -9.4 | 1.1 | -0.52 | 12/21 | 0.646 | 10.0 |
| All shocks | Qatar | up | 5 | 8 | 4.3 | 4.1 | 0.82 | 6/8 | 0.008 | 3.4 |
| All shocks | Qatar | up | 20 | 9 | -1.2 | -0.5 | -0.23 | 4/9 | 0.854 | 7.1 |
| All shocks | Qatar | down | 5 | 16 | 1.4 | -1.1 | 0.4 | 6/16 | 0.132 | 2.0 |
| All shocks | Qatar | down | 20 | 17 | 1.3 | -4.0 | 0.24 | 6/17 | 0.072 | 4.8 |
| All shocks | Qatar | pooled | 5 | 24 | 0.5 | 1.6 | 0.18 | 17/24 | 0.022 | 1.3 |
| All shocks | Qatar | pooled | 20 | 26 | -1.3 | 2.5 | -0.32 | 15/26 | 0.074 | 3.5 |
| All shocks | Abu Dhabi | up | 5 | 8 | 3.9 | 4.2 | 1.04 | 6/8 | 0.003 | 2.7 |
| All shocks | Abu Dhabi | up | 20 | 9 | -0.0 | 0.5 | -0.01 | 5/9 | 0.422 | 6.8 |
| All shocks | Abu Dhabi | down | 5 | 16 | 0.9 | -0.3 | 0.33 | 6/16 | 0.232 | 1.4 |
| All shocks | Abu Dhabi | down | 20 | 17 | 0.8 | -0.0 | 0.16 | 7/17 | 0.686 | 5.1 |
| All shocks | Abu Dhabi | pooled | 5 | 24 | 0.7 | 1.8 | 0.3 | 17/24 | 0.002 | 0.9 |
| All shocks | Abu Dhabi | pooled | 20 | 26 | -0.5 | 0.3 | -0.15 | 15/26 | 0.971 | 3.8 |
| All shocks | Dubai | up | 5 | 8 | 2.9 | 0.2 | 1.62 | 5/8 | 0.22 | 3.8 |
| All shocks | Dubai | up | 20 | 9 | -4.2 | 0.8 | -0.38 | 6/9 | 0.222 | 11.2 |
| All shocks | Dubai | down | 5 | 16 | 8.5 | 0.0 | 0.9 | 10/16 | 0.279 | 2.3 |
| All shocks | Dubai | down | 20 | 17 | 8.1 | 0.0 | 0.65 | 9/17 | 0.392 | 7.6 |
| All shocks | Dubai | pooled | 5 | 24 | -4.7 | -0.0 | -0.74 | 12/24 | 0.342 | 0.9 |
| All shocks | Dubai | pooled | 20 | 26 | -6.7 | 0.6 | -0.76 | 15/26 | 0.913 | 4.8 |
| All shocks | Oman | up | 5 | 7 | 0.8 | 6.9 | 0.07 | 5/7 | 0.021 | 8.7 |
| All shocks | Oman | up | 20 | 6 | -31.2 | -13.1 | -1.4 | 2/6 | 0.4 | 20.2 |
| All shocks | Oman | down | 5 | 14 | 5.9 | -0.4 | 0.94 | 7/14 | 0.646 | 5.7 |
| All shocks | Oman | down | 20 | 13 | 37.4 | 2.7 | 1.23 | 7/13 | 0.102 | 14.3 |
| All shocks | Oman | pooled | 5 | 21 | -3.7 | 0.8 | -0.7 | 12/21 | 0.8 | 4.6 |
| All shocks | Oman | pooled | 20 | 19 | -35.5 | -6.5 | -1.65 | 8/19 | 0.031 | 10.5 |


## b. Implied basis response vs the direct estimate

Implied = (mean sign-adjusted CDS change across shocks) x (within-issuer CDS slope with the liquidity control). The 90% interval bootstraps shocks for the first factor and governments (pairs cluster bootstrap, six CDS series) for the slope. *Direct* is the pooled sign-adjusted basis response from event_study.md, with its minimum detectable effect.


| tau | shocks | oil_to_cds_bp | oil_to_cds_ci90 | cds_to_basis_bp_per_100bp | slope_ci90 | implied_basis_bp | implied_ci90 | direct_basis_mean_bp | direct_basis_median_bp | direct_mde80_bp |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 26 | -3.2 | [-12.4, 3.6] | -22.0 | [-31.3, 9.2] | 0.71 | [-0.82, 2.77] | 4.9 | 0.6 | 3.1 |
| 20 | 26 | -6.6 | [-21.9, 4.5] | -22.0 | [-31.3, 9.2] | 1.46 | [-1.15, 4.85] | 1.0 | -0.8 | 4.9 |


If the implied response is small relative to the direct estimate's MDE, the null in the basis event study is what the credit channel predicts: oil shocks move CDS too little, for too short a time, to show up in the basis.

## d. Fiscal stress (Brent minus fiscal breakeven)

Skipped: `data/market/fiscal_breakeven.csv` (country, year, breakeven_usd, source) was not supplied, and breakeven values are not invented.


## Caveats

- The slope is an average across issuers. The within-issuer slope is concentrated in sub-investment-grade issuers (mechanism_results.md), so their implied response would be larger than the average.
- Oman's CDS starts in August 2017, so the 2016-2017 shocks use five sovereigns.
