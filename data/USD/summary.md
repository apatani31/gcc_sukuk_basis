# GCC sukuk vs conventional: feasibility summary

Generated 2026-10-24. Run: currency=USD start=2010-01-01 countries=Saudi Arabia,United Arab Emirates,Qatar,Kuwait,Bahrain,Oman issue_year=all sukuk_only=False

## Universe

All rows after filters, by instrument class (money_market = CDs and CP, excluded from the comparison):

| instrument_class | conventional | sukuk |
|---|---|---|
| bond | 2384 | 523 |
| money_market | 9548 | 0 |
| other | 37 | 0 |


Bonds only: **2895 lines**, which collapse to **2495 distinct bonds** once RegS/144A twin lines are merged (`is_primary_line`). The counts below use distinct bonds.

| all | sukuk | conventional | total |
|---|---|---|---|
| all | 456 | 2039 | 2495 |


**Excluded for review: 12 conventional-file lines that look like sukuk** (issued by a sukuk vehicle but tagged as a plain Note/Bond, with no Islamic flag). Flag: `possible_sukuk_mislabel`. Confirm each in Workspace and move it if needed:


| issuer_name | isin | instrument_type | issue_date | maturity_date | borrower |
|---|---|---|---|---|---|
| Sharjah Sukuk Programme Ltd | XS3218685769 | Note | 2025-10-27 | 2029-10-29 | Emirate of Sharjah |
| Sharjah Sukuk Programme Ltd | XS2982058070 | Note | 2025-02-03 | 2032-02-03 | Emirate of Sharjah |
| Cbb International Sukuk Programme Company WLL | XS3070648988 | Note | 2025-05-07 | 2033-07-07 |  |
| Oman Sovereign Sukuk SAOC | XS3290534588 | Note | 2026-02-10 | 2036-02-11 |  |
| QIB Sukuk Ltd | XS2582389669 | Note | 2024-02-14 | 2028-02-22 | Qatar Islamic Bank (Q.P.S.C) |
| DAE Sukuk (DIFC) Ltd | XS2938644387 | Note | 2025-01-13 | 2029-11-21 |  |
| Mumtaz Sukuk Ltd | XS3058826820 | Bond | 2025-04-24 | 2040-04-24 |  |
| Mumtaz Sukuk Ltd | XS3226583972 | Bond | 2025-12-18 | 2040-12-31 |  |
| QIB Sukuk Ltd | XS3244710813 | Note | 2025-12-04 | 2030-06-12 | Qatar Islamic Bank (Q.P.S.C) |
| SNB Sukuk Ltd | XS3238403268 | Note | 2025-07-18 | 2036-07-18 |  |
| ADCB Islamic Finance (Cayman) Ltd | XS1216003746 | Note | 2015-04-15 | 2045-04-15 | Abu Dhabi Commercial Bank PJSC |
| ADCB Islamic Finance (Cayman) Ltd | XS1371901684 | Note | 2016-02-23 | 2046-02-23 | Abu Dhabi Commercial Bank PJSC |


### By country of risk
| country_of_risk | sukuk | conventional | total |
|---|---|---|---|
| Bahrain | 27 | 43 | 70 |
| Kuwait | 22 | 33 | 55 |
| Oman | 12 | 36 | 48 |
| Qatar | 48 | 337 | 385 |
| Saudi Arabia | 170 | 169 | 339 |
| United Arab Emirates | 177 | 1421 | 1598 |


### By issuer type
| issuer_type | sukuk | conventional | total |
|---|---|---|---|
| Agency | 54 | 34 | 88 |
| Corporate | 402 | 1838 | 2240 |
| Govt/Treasury/Central Bank | 0 | 109 | 109 |
| Other Gov/Supra | 0 | 58 | 58 |


Note: Workspace tags sovereign sukuk SPVs (e.g. KSA Sukuk Ltd) as *Agency* or *Corporate*, not *Govt/Treasury*, so issuer type understates sovereign sukuk. Use the sovereign check below.


### By issue year
| issue_year | sukuk | conventional | total |
|---|---|---|---|
| 2010 | 5 | 29 | 34 |
| 2011 | 8 | 24 | 32 |
| 2012 | 16 | 107 | 123 |
| 2013 | 11 | 89 | 100 |
| 2014 | 16 | 83 | 99 |
| 2015 | 10 | 72 | 82 |
| 2016 | 21 | 162 | 183 |
| 2017 | 10 | 157 | 167 |
| 2018 | 14 | 150 | 164 |
| 2019 | 27 | 170 | 197 |
| 2020 | 36 | 134 | 170 |
| 2021 | 29 | 101 | 130 |
| 2022 | 23 | 89 | 112 |
| 2023 | 42 | 91 | 133 |
| 2024 | 57 | 173 | 230 |
| 2025 | 88 | 241 | 329 |
| 2026 | 43 | 167 | 210 |


## Field fill rates (distinct bonds)

| field | conventional | sukuk |
|---|---|---|
| any rating | 62.3 | 46.3 |
| coupon_frequency | 89.2 | 99.6 |
| coupon_rate | 96.4 | 99.6 |
| issue_price | 91.9 | 98.7 |
| ric | 51.1 | 86.4 |
| yield_at_issue | 44.7 | 77.2 |


Yield at issue source: {'computed': 1263, 'none': 1232}. Unusable cases: {'not_fixed_rate': 959, 'missing_issue_price': 171, 'perpetual_or_no_maturity': 102}.


**Day count assumption:** the export has no day count field, so every computed yield assumes **30/360** (US bond basis, the convention for USD Eurobonds), with settlement on the issue date and compounding at the coupon frequency. Floating, resettable, step and perpetual instruments are flagged rather than computed.


## Time-series coverage

| group | instruments | with_ric | with_any_history | lt_20_obs | median_pct_bdays |
|---|---|---|---|---|---|
| conventional | 2050 | 1082 | 821 | 1252 | 98.1 |
| sukuk | 456 | 406 | 372 | 89 | 99.5 |


## Issuers with both sukuk and conventional bonds (twin-curve candidates)

Matched on `parent_key`: Sukuk Obligor for sukuk, Borrower (else Issuer) for conventional, normalized (case, legal suffixes, word order). Ultimate parent is not in the export, so subsidiaries financed through differently named SPVs may be missed.


**34 issuers** have both; **26** have at least one sukuk/conventional pair with maturities within 2 years.
 **22** still have such a pair when both bonds have at least 20 days of price history (`priced_tenor_pairs`, sorted first). Pair counts are bond-by-bond combinations, so issuers with many notes score high.



| parent | country | n_sukuk | n_conv | sukuk_maturities | conv_maturities | maturity_overlap | tenor_pairs_within_2y | n_sukuk_with_history | n_conv_with_history | priced_tenor_pairs |
|---|---|---|---|---|---|---|---|---|---|---|
| First Abu Dhabi Bank PJSC | United Arab Emirates | 8 | 237 | 2025-2031 | 2015-2062 | 2025-2031 | 467 | 7 | 57 | 122 |
| Saudi Arabia, Kingdom of (Government) | Saudi Arabia | 14 | 33 | 2027-2036 | 2021-2061 | 2027-2036 | 107 | 14 | 33 | 107 |
| Bahrain, Kingdom of (Government) | Bahrain | 15 | 25 | 2018-2034 | 2020-2051 | 2020-2034 | 69 | 14 | 23 | 59 |
| The Saudi National Bank SJSC | Saudi Arabia | 6 | 45 | 2025-2036 | 2024-2035 | 2025-2035 | 66 | 5 | 23 | 28 |
| Public Investment Fund | Saudi Arabia | 6 | 13 | 2027-2036 | 2027-2122 | 2027-2036 | 23 | 6 | 13 | 23 |
| Saudi Arabian Oil Co | Saudi Arabia | 6 | 17 | 2026-2035 | 2025-2070 | 2026-2035 | 20 | 6 | 17 | 20 |
| Sharjah, Emirate Of | United Arab Emirates | 23 | 9 | 2021-2036 | 2025-2051 | 2025-2036 | 44 | 19 | 6 | 15 |
| Arab Energy Fund | Saudi Arabia | 3 | 19 | 2025-2036 | 2021-2032 | 2025-2032 | 15 | 3 | 17 | 13 |
| Mamoura Diversified Global Holding PJSC | United Arab Emirates | 2 | 19 | 2034-2035 | 2024-2053 | 2034-2035 | 9 | 2 | 19 | 9 |
| Mashreqbank PSC | United Arab Emirates | 1 | 204 | 2030-2030 | 2014-2033 | 2030-2030 | 26 | 1 | 25 | 9 |
| Oman, Sultanate of (Government) | Oman | 3 | 13 | 2025-2033 | 2021-2051 | 2025-2033 | 8 | 3 | 12 | 7 |
| Islamic Development Bank | Saudi Arabia | 35 | 2 | 2015-2031 | 2021-2024 | 2021-2024 | 15 | 24 | 1 | 6 |
| Banque Saudi Fransi SJSC | Saudi Arabia | 4 | 16 | 2017-2030 | 2015-2035 | 2017-2030 | 22 | 3 | 4 | 5 |
| Qatar, State of (Government) | Qatar | 2 | 22 | 2018-2035 | 2017-2050 | 2018-2035 | 4 | 2 | 21 | 3 |
| Riyad Bank | Saudi Arabia | 5 | 1 | 2030-2035 | 2036-2036 | none | 2 | 5 | 1 | 2 |
| BAPCO Energies BSCC Closed | Bahrain | 3 | 4 | 2029-2035 | 2024-2028 | none | 2 | 3 | 4 | 2 |
| DP World Ltd | United Arab Emirates | 3 | 7 | 2029-2030 | 2020-2049 | 2029-2030 | 2 | 3 | 6 | 2 |
| Dubai Aerospace Enterprise (DAE) Ltd | United Arab Emirates | 2 | 7 | 2026-2030 | 2020-2028 | 2026-2028 | 2 | 2 | 7 | 2 |
| National Central Cooling Company Pjsc | United Arab Emirates | 2 | 1 | 2025-2030 | 2027-2027 | 2027-2027 | 1 | 2 | 1 | 1 |
| Investment Corporation Of Dubai | United Arab Emirates | 2 | 2 | 2020-2027 | 2024-2026 | 2024-2026 | 1 | 1 | 2 | 1 |
| Emirates | United Arab Emirates | 2 | 2 | 2025-2028 | 2016-2025 | none | 1 | 2 | 1 | 1 |
| Oman Electricity Transmission Company S.A.O.C | Oman | 1 | 3 | 2030-2030 | 2025-2031 | 2030-2030 | 1 | 1 | 3 | 1 |
| Kuwait Finance House Kscp | Kuwait | 6 | 1 | 2029-2031 | perp | none | 0 | 5 | 1 | 0 |
| Dubai, Emirate Of | United Arab Emirates | 5 | 5 | 2017-2030 | 2020-2050 | 2020-2030 | 0 | 4 | 5 | 0 |
| Bahrain Mumtalakat Holding Co Bscc | Bahrain | 2 | 1 | 2021-2027 | 2015-2015 | none | 0 | 2 | 0 | 0 |
| First Gulf Bank PJSC | United Arab Emirates | 2 | 2 | 2016-2017 | 2016-2020 | 2016-2017 | 2 | 0 | 0 | 0 |
| Nama Electricity Distribution Company Saoc | Oman | 2 | 1 | 2027-2031 | 2031-2031 | 2031-2031 | 1 | 2 | 0 | 0 |
| Aldar Properties PJSC | United Arab Emirates | 1 | 2 | 2018-2018 | 2055-2056 | none | 0 | 1 | 2 | 0 |
| Dubai Electricity and Water Authority PJSC | United Arab Emirates | 1 | 2 | 2018-2018 | 2015-2016 | none | 1 | 1 | 0 | 0 |
| Saudi Awwal Bank | Saudi Arabia | 1 | 2 | perp | 2015-2035 | none | 0 | 1 | 1 | 0 |
| Gulf International Bank BSC | Bahrain | 1 | 5 | 2014-2014 | 2017-2029 | none | 0 | 0 | 4 | 0 |
| DAMAC PROPERTIES DUBAI CO P.J.S.C. | United Arab Emirates | 1 | 1 | 2017-2017 | 2017-2017 | 2017-2017 | 1 | 0 | 0 | 0 |
| Oman Telecommunications Company SAOG | Oman | 1 | 1 | 2031-2031 | 2028-2028 | none | 0 | 1 | 1 | 0 |
| Ooredoo Q.P.S.C. | Qatar | 1 | 7 | 2018-2018 | 2021-2043 | none | 0 | 1 | 7 | 0 |


## Direct sovereign issuance check

| sovereign | sukuk | conventional_direct | both_present | sukuk_issuers | conventional_issuers | borrower_linked_not_direct |
|---|---|---|---|---|---|---|
| KSA | 14 | 33 | yes | KSA Ijarah Sukuk Ltd; KSA Sukuk Ltd | Saudi Arabia, Kingdom of (Government) |  |
| Qatar | 2 | 22 | yes | Global Sukuk Ventures QPJSC; SoQ Sukuk A QSC | Qatar, State of (Government) |  |
| Oman | 3 | 13 | yes | Oman Sovereign Sukuk SAOC | Oman, Sultanate of (Government) |  |
| Bahrain | 15 | 25 | yes | CBB International Sukuk Co 7 WLL; Cbb International Sukuk Co 6 WLL; Cbb International Sukuk Company No 3 WLL; Cbb International Sukuk Programme Company WLL | Bahrain, Kingdom of (Government) |  |
| Sharjah | 23 | 9 | yes | Sharjah Sukuk (2) Ltd; Sharjah Sukuk Ltd; Sharjah Sukuk Programme Ltd | Sharjah, Emirate of |  |
| Abu Dhabi | 0 | 24 | NO |  | Emirate of Abu Dhabi | Waha Aerospace BV (1) |
| Kuwait | 0 | 9 | NO |  | Kuwait, State of (Government) |  |
| Dubai | 5 | 5 | yes | Dubai DOF Sukuk Ltd | Dubai, Emirate of | Dubai Electricity and Water Authority PJSC (1) |
| UAE (federal) | 0 | 7 | NO |  | United Arab Emirates (Government) | Dubai, Emirate of (1) |
