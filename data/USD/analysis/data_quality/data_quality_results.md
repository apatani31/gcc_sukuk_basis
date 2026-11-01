# Secondary-market data quality and a primary-market check

Generated 2026-11-01. Bonds: the twin-curve set (fixed coupon, at least USD 100m, one line per bond) of the twin issuers. **Weak credit** in every table means sub-investment grade under the MAIN rule (at least two of S&P, Moody's and Fitch below BBB-/Baa3; see README.md). Sections a to c classify each **issuer-month**; section d classifies each **deal at its reference date**. There is no fixed list of weak issuers: Oman, for example, is a weak credit only while two agencies rate it below investment grade.

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


**By credit status** (each bond's days split by its issuer-month status under MAIN; segments with 60+ days):


| credit | group | bond_segments | unchanged_mid_share | bid_ask_cents | ar1_yield_change |
|---|---|---|---|---|---|
| Other | Conventional | 148 | 0.006 | 34.4 | -0.039 |
| Other | Sukuk | 66 | 0.061 | 26.4 | -0.125 |
| Weak credit (sub-IG month, MAIN) | Conventional | 41 | 0.138 | 75.0 | 0.171 |
| Weak credit (sub-IG month, MAIN) | Sukuk | 18 | 0.144 | 75.0 | -0.001 |


## b. Do sukuk marks lag the conventional curve?

Daily sukuk yield change on the same-day and lagged (1-5 days) change in the matched conventional yield. Standard errors clustered by month. Sizeable lag coefficients mean sukuk marks update slowly; a *total* below 1 means sukuk move less even after a week. Weak-credit rows use sub-IG issuer-months under MAIN.


| group | obs | same_day | same_day_t | lags_1_5_sum | lags_t | total |
|---|---|---|---|---|---|---|
| All twin issuers | 49570 | 0.472 | 15.4 | 0.151 | 11.1 | 0.623 |
| Weak credit issuer-months (MAIN rule) | 14929 | 0.413 | 8.7 | 0.144 | 8.0 | 0.557 |
| Other issuer-months (MAIN rule) | 34027 | 0.541 | 24.4 | 0.18 | 9.5 | 0.722 |
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

Monthly basis change on the CDS change (per 100bp) and its six lags. If the same-month effect were a stale-quote artefact, the lags would undo it (share_reversed near 1). `net` is the cumulative effect after six months. The pooled weak-credit row uses sub-IG issuer-months under MAIN.


| sample | months | same_month_per_100bp | t_same | lags_1_6_sum | t_lags | net_per_100bp | share_reversed |
|---|---|---|---|---|---|---|---|
| Pooled (all issuers with CDS) | 721 | -31.8 | -3.27 | 14.5 | 1.24 | -17.3 | 0.46 |
| Oman government | 90 | -57.2 | -8.03 | 26.6 | 2.96 | -30.7 | 0.46 |
| Bahrain government | 79 | -14.3 | -3.27 | -3.6 | -0.39 | -17.9 | -0.25 |
| BAPCO | 60 | -32.6 | -3.13 | -41.8 | -1.03 | -74.4 | -1.28 |
| Weak credit issuer-months pooled (MAIN rule) | 214 | -39.4 | -4.37 | 14.5 | 1.06 | -24.9 | 0.37 |


## d. Primary market: new-issue premium

For each new fixed-rate bond of a twin issuer with a yield at issue (computed, 30/360, from coupon and issue price), the premium is the yield at issue minus the issuer's conventional curve on the last trading day at least 5 business days before the issue date (within 10 further days), matched at the new bond's maturity with the same rules as twin.py (interpolation, or the US Treasury-adjusted nearest bond within 1 year). New conventional bonds are compared with the issuer's *other* conventional bonds the same way. *Sukuk minus conventional* nets out the ordinary new-issue concession, leaving the primary-market sukuk discount.


Matching status of new issues: {'interp': 140, 'outside curve': 59, 'no curve': 40, 'nearest_adj': 38}.


**Off-market deals excluded** (|premium| > 300bp; e.g. 1% coupon official placements that are not market transactions):


| issuer | isin | issue_date | is_sukuk | tenor_at_issue | yield_at_issue | nip_bp |
|---|---|---|---|---|---|---|
| Bahrain, Kingdom of (Government) | XS2492018713 | 2022-06-21 00:00:00 | False | 10.0 | 1.0 | -620.75 |
| Bahrain, Kingdom of (Government) | XS3282978173 | 2026-02-02 00:00:00 | False | 10.0 | 1.0 | -565.17 |


**Which deals count as weak credit.** Each deal is classified on its **reference date**: the curve date above, a proxy for the pricing date (the export has no pricing date). Rating rows dated after the reference date are not used. State companies take their owner's rating (BAPCO and Bahrain; Oman Electricity Transmission and Oman; Aramco, PIF, SNB, BSF and KSA; DP World, ICD, DAE and Dubai, whose rows are the DEWA proxy; FAB, Mamoura and Abu Dhabi). The multilateral Arab Energy Fund has no government rating, so the rating rules leave it unclassified ({'Arab Energy Fund': 8, 'APICORP Sukuk Ltd': 2}). The MAIN rule was chosen before seeing these results; the others are robustness checks.


**Reading:**

- **Does it hold under all three rules?** Yes: weak-credit sukuk minus weak-credit conventional (medians) is MAIN -73.9bp, Robustness A -57.8bp, Robustness B -65.8bp, a range of -73.9 to -57.8bp.
- **MAIN:** weak-credit sukuk median -55.2bp (n = 15) against +18.6bp for weak-credit conventional bonds (n = 23) and -3.0bp for other issuers' sukuk (Welch t -5.6).
- **Dependence on Bahrain:** without Bahrain and BAPCO, MAIN leaves 1 weak-credit sukuk (median -21.5bp; sukuk-minus-conventional gap -42.1bp). That is too few to test, so under MAIN the primary-market result rests on Bahrain. The rules that classify more non-Bahraini deals as weak give: Robustness A -44.0bp (n = 8 sukuk, Welch t -2.7); Robustness B -45.1bp (n = 5 sukuk, Welch t -1.9). The discount is smaller without Bahrain but keeps its sign.

### MAIN: 2 of 3 agencies below BBB-/Baa3 (both if only two rate; the one if only one rates)

| credit | bond | bonds | mean_bp | median_bp |
|---|---|---|---|---|
| Other | Conventional | 86 | 12.2 | 9.6 |
| Other | Sukuk | 42 | -4.0 | -3.0 |
| Weak credit | Conventional | 23 | 11.9 | 18.6 |
| Weak credit | Sukuk | 15 | -54.0 | -55.2 |



| weak_sukuk_n | weak_sukuk_median_bp | weak_conv_n | weak_conv_median_bp | weak_sukuk_minus_conv_bp | other_sukuk_n | other_sukuk_median_bp | welch_t_weak_vs_other_sukuk | unclassified_deals |
|---|---|---|---|---|---|---|---|---|
| 15 | -55.2 | 23 | 18.6 | -73.9 | 42 | -3.0 | -5.6 | 10 |


### Robustness A: lowest available rating below BBB-/Baa3

| credit | bond | bonds | mean_bp | median_bp |
|---|---|---|---|---|
| Other | Conventional | 82 | 11.9 | 9.2 |
| Other | Sukuk | 35 | -1.0 | -2.6 |
| Weak credit | Conventional | 27 | 13.1 | 19.2 |
| Weak credit | Sukuk | 22 | -42.7 | -38.6 |



| weak_sukuk_n | weak_sukuk_median_bp | weak_conv_n | weak_conv_median_bp | weak_sukuk_minus_conv_bp | other_sukuk_n | other_sukuk_median_bp | welch_t_weak_vs_other_sukuk | unclassified_deals |
|---|---|---|---|---|---|---|---|---|
| 22 | -38.6 | 27 | 19.2 | -57.8 | 35 | -2.6 | -5.61 | 10 |


### Robustness B: credit spread above the threshold: government 5y CDS, else the issuer's conventional spread over US Treasuries at the deal's maturity

| credit | bond | bonds | mean_bp | median_bp |
|---|---|---|---|---|
| Other | Conventional | 86 | 7.6 | 7.8 |
| Other | Sukuk | 40 | -1.7 | -2.7 |
| Weak credit | Conventional | 31 | 12.9 | 19.2 |
| Weak credit | Sukuk | 19 | -47.0 | -46.6 |



| weak_sukuk_n | weak_sukuk_median_bp | weak_conv_n | weak_conv_median_bp | weak_sukuk_minus_conv_bp | other_sukuk_n | other_sukuk_median_bp | welch_t_weak_vs_other_sukuk | unclassified_deals |
|---|---|---|---|---|---|---|---|---|
| 19 | -46.6 | 31 | 19.2 | -65.8 | 40 | -2.7 | -5.58 | 0 |


### Excluding Bahrain (government and BAPCO)

| rule | weak_sukuk_n | weak_sukuk_median_bp | weak_conv_n | weak_conv_median_bp | weak_sukuk_minus_conv_bp | other_sukuk_n | other_sukuk_median_bp | welch_t_weak_vs_other_sukuk | unclassified_deals |
|---|---|---|---|---|---|---|---|---|---|
| MAIN | 1 | -21.5 | 5 | 20.6 | -42.1 | 42 | -3.0 |  | 10 |
| Robustness A | 8 | -23.4 | 9 | 20.6 | -44.0 | 35 | -2.6 | -2.69 | 10 |
| Robustness B | 5 | -24.5 | 13 | 20.6 | -45.1 | 40 | -2.7 | -1.92 | 0 |
| Legacy | 7 | -24.5 | 11 | 25.2 | -49.7 | 38 | -1.7 | -3.01 | 0 |


### Legacy: fixed list (Bahrain, Oman, BAPCO, Sharjah) for the whole sample, comparison only

| credit | bond | bonds | mean_bp | median_bp |
|---|---|---|---|---|
| Other | Conventional | 88 | 7.3 | 7.5 |
| Other | Sukuk | 38 | -0.5 | -1.7 |
| Weak credit | Conventional | 29 | 14.2 | 19.8 |
| Weak credit | Sukuk | 21 | -44.8 | -39.7 |



| weak_sukuk_n | weak_sukuk_median_bp | weak_conv_n | weak_conv_median_bp | weak_sukuk_minus_conv_bp | other_sukuk_n | other_sukuk_median_bp | welch_t_weak_vs_other_sukuk | unclassified_deals |
|---|---|---|---|---|---|---|---|---|
| 21 | -39.7 | 29 | 19.8 | -59.5 | 38 | -1.7 | -5.89 | 0 |


### Deals classified differently from the legacy list

Counts by issuer (market deals). *unclassified* = no government rating under that rule.


| rule | issuer | deals | weak_to_other | other_to_weak | unclassified |
|---|---|---|---|---|---|
| MAIN | APICORP Sukuk Ltd | 2 | 0 | 0 | 2 |
| MAIN | Arab Energy Fund | 8 | 0 | 0 | 8 |
| MAIN | Oman Sovereign Sukuk SAOC | 3 | 2 | 0 | 0 |
| MAIN | Oman, Sultanate of (Government) | 8 | 3 | 0 | 0 |
| MAIN | Sharjah Sukuk Programme Ltd | 4 | 4 | 0 | 0 |
| MAIN | Sharjah, Emirate of | 3 | 3 | 0 | 0 |
| Robustness A | APICORP Sukuk Ltd | 2 | 0 | 0 | 2 |
| Robustness A | Al Jawaher Assets Company SPC | 1 | 0 | 1 | 0 |
| Robustness A | Arab Energy Fund | 8 | 0 | 0 | 8 |
| Robustness A | Oman, Sultanate of (Government) | 8 | 1 | 0 | 0 |
| Robustness A | Sharjah, Emirate of | 3 | 1 | 0 | 0 |
| Robustness B | Oman Sovereign Sukuk SAOC | 3 | 1 | 0 | 0 |
| Robustness B | Saudi Arabia, Kingdom of (Government) | 23 | 0 | 2 | 0 |
| Robustness B | Sharjah Sukuk Programme Ltd | 4 | 1 | 0 | 0 |


**MAIN rule, deal by deal:**


| issuer | issue_date | ref_date | bond | legacy | now | nip_bp |
|---|---|---|---|---|---|---|
| Oman, Sultanate of (Government) | 2017-03-08 | 2017-03-01 | Conventional | Weak | Other | 31.9 |
| Oman, Sultanate of (Government) | 2018-01-17 | 2018-01-10 | Conventional | Weak | Other | 35.1 |
| Oman, Sultanate of (Government) | 2018-01-17 | 2018-01-10 | Conventional | Weak | Other | 20.1 |
| Oman Sovereign Sukuk SAOC | 2018-10-31 | 2018-10-24 | Sukuk | Weak | Other | 16.0 |
| Sharjah, Emirate of | 2021-03-10 | 2021-03-03 | Conventional | Weak | Other | 25.2 |
| Sharjah, Emirate of | 2023-02-23 | 2023-02-16 | Conventional | Weak | Other | 31.0 |
| Sharjah Sukuk Programme Ltd | 2023-09-19 | 2023-09-12 | Sukuk | Weak | Other | -34.6 |
| Sharjah Sukuk Programme Ltd | 2023-12-18 | 2023-12-11 | Sukuk | Weak | Other | -24.5 |
| Sharjah, Emirate of | 2024-03-06 | 2024-02-28 | Conventional | Weak | Other | -6.8 |
| Sharjah Sukuk Programme Ltd | 2024-10-17 | 2024-10-10 | Sukuk | Weak | Other | -39.7 |
| Oman Sovereign Sukuk SAOC | 2025-10-17 | 2025-10-10 | Sukuk | Weak | Other | -22.3 |
| Sharjah Sukuk Programme Ltd | 2025-11-25 | 2025-11-18 | Sukuk | Weak | Other | -25.4 |


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
- Ratings are hand-compiled from public announcements (data/market/sovereign_ratings.csv); Dubai uses the DEWA proxy.
- Staleness metrics depend on the price source (Tradeweb vs composite) as well as on the bond type.
