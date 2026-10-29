# Secondary-market data quality and a primary-market check

Generated 2026-10-29. Bonds: the twin-curve set (fixed coupon, at least USD 100m, one line per bond) of the twin issuers.

## a. How stale are sukuk quotes?

Per bond, 2019 onward (bonds with 100+ days): share of days the mid price did not change, median bid-ask in price cents, first-order autocorrelation of daily yield changes (positive = sluggish quotes; negative = bounce or noise), median absolute daily yield change, and the share priced from Tradeweb `=TE` rather than a composite RIC (coverage_report.csv).


| group | bonds | unchanged_mid_share | bid_ask_cents | ar1_yield_change | abs_daily_change_bp | tradeweb_share |
|---|---|---|---|---|---|---|
| Conventional | 186 | 0.015 | 40.9 | -0.011 | 3.0 | 0.21 |
| Sukuk | 84 | 0.079 | 38.75 | -0.097 | 3.0 | 0.167 |


**By price source:**


| group | price_source | bonds | unchanged_mid_share | ar1_yield_change |
|---|---|---|---|---|
| Conventional | Composite / other | 147 | 0.007 | -0.0 |
| Conventional | Tradeweb =TE | 39 | 0.092 | -0.119 |
| Sukuk | Composite / other | 70 | 0.079 | -0.095 |
| Sukuk | Tradeweb =TE | 14 | 0.076 | -0.157 |


## b. Do sukuk marks lag the conventional curve?

Daily sukuk yield change on the same-day and lagged (1-5 days) change in the matched conventional yield. Standard errors clustered by month. Sizeable lag coefficients mean sukuk marks update slowly; a *total* below 1 means sukuk move less even after a week.


| group | obs | same_day | same_day_t | lags_1_5_sum | lags_t | total |
|---|---|---|---|---|---|---|
| All twin issuers | 49570 | 0.472 | 15.4 | 0.151 | 11.1 | 0.623 |
| Weak credits (Bahrain, Oman, BAPCO, Sharjah) | 19017 | 0.43 | 9.5 | 0.134 | 7.4 | 0.564 |
| Other issuers | 30553 | 0.53 | 24.6 | 0.202 | 9.3 | 0.732 |
| KSA government | 12714 | 0.814 | 36.5 | 0.074 | 5.2 | 0.888 |


**Pass-through after oil shocks vs normal days, up to 120 business days** (slope of the sukuk-leg change on the conventional-leg change; normal days exclude windows around shocks):


| horizon_days | sample | n_shock | beta_shock | corr_shock | n_normal | beta_normal | corr_normal | diff | diff_ci90 |
|---|---|---|---|---|---|---|---|---|---|
| 5 | All shocks | 204 | 0.68 | 0.95 | 2897 | 0.61 | 0.73 | 0.07 | [-0.03, 0.21] |
| 5 | Shocks ex-2020 | 185 | 0.64 | 0.81 | 2897 | 0.61 | 0.73 | 0.03 | [-0.06, 0.16] |
| 5 | 2020 shocks only | 19 | 0.69 | 0.97 | 2897 | 0.61 | 0.73 | 0.08 | [-0.04, 0.25] |
| 20 | All shocks | 203 | 0.69 | 0.94 | 717 | 0.77 | 0.87 | -0.08 | [-0.15, -0.00] |
| 20 | Shocks ex-2020 | 183 | 0.66 | 0.83 | 717 | 0.77 | 0.87 | -0.11 | [-0.20, 0.04] |
| 20 | 2020 shocks only | 20 | 0.7 | 0.98 | 717 | 0.77 | 0.87 | -0.07 | [-0.14, 0.03] |
| 60 | All shocks | 201 | 0.71 | 0.95 | 159 | 0.8 | 0.87 | -0.09 | [-0.17, 0.01] |
| 60 | Shocks ex-2020 | 184 | 0.81 | 0.93 | 159 | 0.8 | 0.87 | 0.01 | [-0.08, 0.10] |
| 60 | 2020 shocks only | 17 | 0.63 | 0.98 | 159 | 0.8 | 0.87 | -0.17 | [-0.26, -0.05] |
| 120 | All shocks | 166 | 0.77 | 0.95 | 40 | 0.77 | 0.86 | -0.0 | [-0.13, 0.11] |
| 120 | Shocks ex-2020 | 151 | 0.83 | 0.93 | 40 | 0.77 | 0.86 | 0.05 | [-0.08, 0.17] |
| 120 | 2020 shocks only | 15 | 0.66 | 0.99 | 40 | 0.77 | 0.86 | -0.11 | [-0.24, 0.01] |


## c. Does the CDS effect reverse?

Monthly basis change on the CDS change (per 100bp) and its six lags. If the same-month effect were a stale-quote artefact, the lags would undo it (share_reversed near 1). `net` is the cumulative effect after six months.


| sample | months | same_month_per_100bp | t_same | lags_1_6_sum | t_lags | net_per_100bp | share_reversed |
|---|---|---|---|---|---|---|---|
| Pooled (all issuers with CDS) | 721 | -31.8 | -3.27 | 14.5 | 1.24 | -17.3 | 0.46 |
| Oman government | 90 | -57.2 | -8.03 | 26.6 | 2.96 | -30.7 | 0.46 |
| Bahrain government | 79 | -14.3 | -3.27 | -3.6 | -0.39 | -17.9 | -0.25 |
| BAPCO | 60 | -32.6 | -3.13 | -41.8 | -1.03 | -74.4 | -1.28 |
| Weak credits pooled | 229 | -39.4 | -4.37 | 14.7 | 1.1 | -24.7 | 0.37 |


## d. Primary market: new-issue premium

For each new fixed-rate bond of a twin issuer with a yield at issue (computed, 30/360, from coupon and issue price), the premium is the yield at issue minus the issuer's conventional curve on the last trading day at least 5 business days before the issue date (within 10 further days), matched at the new bond's maturity with the same rules as twin.py (interpolation, or the US Treasury-adjusted nearest bond within 1 year). New conventional bonds are compared with the issuer's *other* conventional bonds the same way. *Sukuk minus conventional* nets out the ordinary new-issue concession, leaving the primary-market sukuk discount.


Matching status of new issues: {'interp': 140, 'outside curve': 59, 'no curve': 40, 'nearest_adj': 38}.


**Off-market deals excluded** (|premium| > 300bp; e.g. 1% coupon official placements that are not market transactions):


| issuer | isin | issue_date | is_sukuk | tenor_at_issue | yield_at_issue | nip_bp |
|---|---|---|---|---|---|---|
| Bahrain, Kingdom of (Government) | XS2492018713 | 2022-06-21 00:00:00 | False | 10.0 | 1.0 | -620.75 |
| Bahrain, Kingdom of (Government) | XS3282978173 | 2026-02-02 00:00:00 | False | 10.0 | 1.0 | -565.17 |


**Weak credits vs other issuers** (market deals only):


| weak | is_sukuk | bonds | mean_bp | median_bp |
|---|---|---|---|---|
| Other issuers | Conventional | 88 | 7.3 | 7.5 |
| Other issuers | Sukuk | 38 | -0.5 | -1.7 |
| Weak credits | Conventional | 29 | 14.2 | 19.8 |
| Weak credits | Sukuk | 21 | -44.8 | -39.7 |



Weak-credit sukuk priced -44.3bp relative to other issuers' sukuk (mean difference, Welch t = -5.9).



**By issuer** (medians; secondary_basis_bp = the issuer's mean twin-curve basis):


| parent_key | issuer | new_sukuk | sukuk_nip_median_bp | new_conv | conv_nip_median_bp | sukuk_minus_conv_bp | cds_at_sukuk_issue_bp | secondary_basis_bp |
|---|---|---|---|---|---|---|---|---|
| bahrain kingdom | Bahrain, Kingdom of (Government) | 13 | -58.4 | 17 | 17.1 | -75.5 | 244.0 | -56.0 |
| banque fransi saudi | BSF Sukuk Company Ltd | 1 | -33.4 | 0 |  |  | 65.0 | 3.0 |
| bapco energies | BAPCO Energies BSCC Closed | 1 | -31.3 | 1 | 19.8 | -51.1 | 217.0 | -92.1 |
| emirate sharjah | Sharjah Sukuk Programme Ltd | 4 | -30.0 | 3 | 25.2 | -55.2 |  | -43.4 |
| oman sultanate | Oman, Sultanate of (Government) | 3 | -21.5 | 8 | 26.1 | -47.6 | 181.0 | -55.3 |
| diversified global holding mamoura | Mdgh Gmtn Rsc Ltd | 2 | -11.8 | 13 | 7.0 | -18.7 | 40.0 | -18.7 |
| abu bank dhabi first | First Abu Dhabi Bank PJSC | 4 | -7.8 | 7 | -1.9 | -5.9 | 44.0 | -7.6 |
| fund investment public | GACI First Investment Co | 6 | -7.2 | 8 | 8.9 | -16.1 | 64.0 | -8.5 |
| qatar state | Qatar, State of (Government) | 1 | -3.8 | 16 | 9.7 | -13.5 | 28.0 | -8.9 |
| electricity oman transmission | Al Jawaher Assets Company SPC | 1 | -0.4 | 0 |  |  | 72.0 | -4.5 |
| arabia kingdom saudi | Saudi Arabia, Kingdom of (Government) | 14 | 0.6 | 23 | 11.4 | -10.7 | 65.0 | -2.9 |
| arabian oil saudi | Saudi Arabian Oil Co | 6 | 1.0 | 9 | 4.2 | -3.3 | 64.0 | -6.9 |
| bank national saudi | SNB Funding Ltd | 1 | 3.6 | 1 | 19.6 | -16.0 | 52.0 | -5.0 |
| arab energy fund | Arab Energy Fund | 2 | 8.9 | 8 | -30.6 | 39.5 |  | -2.7 |
| aerospace dae dubai enterprise | Dae Funding LLC | 0 |  | 1 | 248.8 |  |  | -9.0 |
| dp world | DP World Ltd | 0 |  | 2 | 2.5 |  |  | -29.8 |


Correlation across issuers with the secondary-market basis: sukuk new-issue premium **0.67** (14 issuers); sukuk-minus-conventional premium **0.78** (12 issuers with both).


## Caveats

- Yield at issue is computed (30/360, settlement on the issue date). LSEG secondary yields use their own conventions, so levels can differ by a few bp. The sukuk-minus-conventional difference cancels most of this.
- Pre-2019 price coverage is thin, so early issues often have no curve.
- Staleness metrics depend on the price source (Tradeweb vs composite) as well as on the bond type.
