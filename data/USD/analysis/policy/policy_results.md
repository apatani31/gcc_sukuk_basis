# Policy numbers: what is the sukuk discount worth?

Generated 2026-10-29. As of 2026-10-23.

## a. Annual coupon saving by issuer

Saving (USD m a year) = USD sukuk outstanding (maturity after the as-of date; perpetuals excluded) x minus the mean basis / 10,000. A negative basis means the sukuk yields less than the same issuer's conventional curve at the same maturity, so the issuer pays that much less coupon on its sukuk. The 90% interval uses the Newey-West standard error of the issuer's daily basis (20 lags). Trailing 12 months = the year to the as-of date; issuers without 20 matched days in that year show blank.


| issuer | outstanding_usd_bn | trailing12m_days | basis_12m_bp | saving_12m_usd_m | saving_12m_ci90 | basis_full_bp | saving_full_usd_m | saving_full_ci90 |
|---|---|---|---|---|---|---|---|---|
| Bahrain, Kingdom of (Government) | 10.65 | 261 | -42.0 | 44.8 | [32.7, 56.8] | -56.0 | 59.6 | [54.7, 64.5] |
| Sharjah, Emirate Of | 8.45 | 261 | -32.5 | 27.4 | [22.6, 32.3] | -43.4 | 36.7 | [32.6, 40.7] |
| BAPCO Energies BSCC Closed | 2.35 | 253 | -48.3 | 11.4 | [7.1, 15.6] | -92.1 | 21.6 | [18.7, 24.6] |
| Public Investment Fund | 10.25 | 261 | -7.3 | 7.5 | [3.8, 11.2] | -8.5 | 8.7 | [6.7, 10.7] |
| Oman, Sultanate of (Government) | 2.75 | 261 | -19.6 | 5.4 | [4.6, 6.2] | -55.3 | 15.2 | [13.2, 17.2] |
| DP World Ltd | 1.5 | 261 | -20.9 | 3.1 | [1.9, 4.4] | -29.8 | 4.5 | [3.5, 5.4] |
| Qatar, State of (Government) | 3.0 | 250 | -8.9 | 2.7 | [1.3, 4.0] | -8.9 | 2.7 | [1.3, 4.0] |
| Mamoura Diversified Global Holding PJSC | 2.0 | 261 | -11.5 | 2.3 | [1.5, 3.1] | -18.7 | 3.7 | [3.3, 4.2] |
| The Saudi National Bank SJSC | 2.1 | 61 | -4.2 | 0.9 | [0.3, 1.4] | -5.0 | 1.1 | [0.6, 1.5] |
| Saudi Arabia, Kingdom of (Government) | 33.25 | 261 | -0.3 | 0.9 | [-2.3, 4.0] | -2.9 | 9.6 | [7.5, 11.8] |
| First Abu Dhabi Bank PJSC | 3.1 | 261 | -1.8 | 0.6 | [-1.1, 2.2] | -7.6 | 2.4 | [1.6, 3.1] |
| Oman Electricity Transmission Company S.A.O.C | 0.75 | 239 | -4.5 | 0.3 | [0.1, 0.5] | -4.5 | 0.3 | [0.1, 0.5] |
| Arab Energy Fund | 1.0 | 93 | 5.9 | -0.6 | [-1.9, 0.7] | -2.7 | 0.3 | [-0.4, 1.0] |
| Saudi Arabian Oil Co | 9.0 | 261 | 1.7 | -1.6 | [-3.2, 0.0] | -6.9 | 6.2 | [4.4, 8.0] |
| Banque Saudi Fransi SJSC | 2.35 | 261 | 11.7 | -2.8 | [-4.5, -1.0] | 3.0 | -0.7 | [-1.5, 0.1] |
| Dubai Aerospace Enterprise (DAE) Ltd | 0.65 | 0 |  |  |  | -9.0 | 0.6 | [0.1, 1.0] |
| Dubai, Emirate of | 2.7 | 0 |  |  |  | 35.4 | -9.6 | [-10.7, -8.4] |
| Investment Corporation Of Dubai | 1.0 | 0 |  |  |  | -21.6 | 2.2 | [1.5, 2.8] |


Sum across issuers: **102m a year** at trailing-12-month bases, **165m** at full-sample bases. Sums ignore the interval width and cross-issuer correlation.

![savings](policy_savings.png)

## b. Counterfactual: sovereigns with no USD sukuk

**Out-of-sample extrapolation.** The models are fitted on 15 issuers' mean basis (Dubai govt excluded, as in mechanism_results.md) and applied to each sovereign's current CDS (mean of the last 21 days) or snapshot rating. Kuwait CDS: `KWGV5YUSAC=R`. UAE federal has no CDS series on this login, so only the rating model applies. Saving per USD 1bn issued = minus the predicted basis x USD 0.1m per bp. Prediction intervals (90%) include the cross-issuer residual spread, which is large.


| name | cds | sub_ig | rating |
|---|---|---|---|
| Kuwait | 60.1 | False | A1 |
| Abu Dhabi | 37.4 | False | Aa2 |
| UAE (federal) |  | False | Aa2 |



| sovereign | current_cds_bp | model | predicted_basis_bp | pred_interval_90 | saving_per_usd_1bn_m | saving_interval_90 | fit_issuers |
|---|---|---|---|---|---|---|---|
| Kuwait | 60.1 | IG vs sub-IG dummy | -9.5 | [-46.1, 27.2] | 0.95 | [-2.72, 4.61] | 14 |
| Kuwait | 60.1 | CDS spline (kink 70bp) | -8.3 | [-31.9, 15.4] | 0.83 | [-1.54, 3.19] | 15 |
| Kuwait | 60.1 | Linear CDS | -10.1 | [-35.4, 15.2] | 1.01 | [-1.52, 3.54] | 15 |
| Abu Dhabi | 37.4 | IG vs sub-IG dummy | -9.5 | [-46.1, 27.2] | 0.95 | [-2.72, 4.61] | 14 |
| Abu Dhabi | 37.4 | CDS spline (kink 70bp) | -13.1 | [-38.9, 12.7] | 1.31 | [-1.27, 3.89] | 15 |
| Abu Dhabi | 37.4 | Linear CDS | -3.2 | [-28.9, 22.4] | 0.32 | [-2.24, 2.89] | 15 |
| UAE (federal) |  | IG vs sub-IG dummy | -9.5 | [-46.1, 27.2] | 0.95 | [-2.72, 4.61] | 14 |


**Reading:** these sovereigns are investment grade with low CDS, the region where the fitted models predict a small discount (the investment-grade issuers in the sample, such as KSA and Qatar, average single digits). The intervals are wide and include zero, so expect a saving of a few bp at most.

## Caveats

- The saving applies today's basis to bonds issued years ago. It measures the current relative cost, not the saving each bond achieved at issue (see the primary-market check in data_quality_results.md).
- Secondary-market sukuk quotes are staler than conventional ones (data_quality_results.md), so part of the measured discount may be quote smoothing.
- Outstanding amounts are USD only, from the security universe.
