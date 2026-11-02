# How far the sub-IG result reaches

Generated 2026-11-02. Level gap: issuer-month basis on the MAIN sub-IG flag, clustered by obligor group, 9,999 wild bootstrap draws.

## a. Are any sukuk amortising?

An amortising sukuk has a shorter average life than its final maturity. Matched to a bullet conventional bond of the same final maturity on an upward-sloping curve, it would look rich, and the bias would be largest for weak credits with steep curves. LSEG's sinkable flag comes from the Search API (the TR.Fi structure fields are denied on this login). As a second test, the ratio compares LSEG's modified duration with a bullet bond of the same coupon and maturity (bonds with over a year left, as of the pull date): near 1 means bullet.

| group | bonds | flag_found | sinkable | callable | putable | duration_tested | ratio_min | ratio_median | ratio_max |
|---|---|---|---|---|---|---|---|---|---|
| Twin sukuk | 68 | 68 | 0 | 9 | 0 | 54 | 0.992 | 0.998 | 1.001 |
| Twin sukuk, Bahrain and Oman | 17 | 17 | 0 | 0 | 0 | 12 | 0.993 | 0.998 | 1.0 |
| Conventional bonds of twin issuers | 189 | 189 | 0 | 46 | 1 | 138 | 0.963 | 0.999 | 1.033 |
| Conventional, Bahrain and Oman | 42 | 42 | 0 | 0 | 0 | 26 | 0.989 | 1.0 | 1.01 |
| Control: Emirates airline sukuk (known amortising) | 3 | 3 | 3 | 0 | 0 | 1 | 0.635 | 0.635 | 0.635 |


**Reading.** No twin sukuk is flagged sinkable (68 of 68 checked), and the 54 with a duration test sit at 0.992 to 1.001 of a bullet. 
The control shows both tests can detect amortisation: 3 of 3 Emirates airline sukuk lines are flagged sinkable, and the duration ratio is 0.64 for the 1 control bond still long enough to test. Duration only covers live bonds, so matured sukuk rest on the flag alone. No prospectus has been read for this check.
Calls cannot explain the sub-IG gap: Bahrain and Oman have 0 callable sukuk and 0 callable conventional bonds flagged, and removing all callable bonds leaves the gap in section d.

## b. Dependence on individual governments

| sample | sub_ig_mean_bp | ig_mean_bp | gap_bp | p_wild_government | obligor_months | governments | sub_ig_governments |
|---|---|---|---|---|---|---|---|
| Without Abu Dhabi | -67.6 | -9.0 | -58.6 | 0.0617 | 844 | 6 | 2 |
| Without Bahrain | -63.2 | -9.4 | -53.9 | 0.3084 | 747 | 6 | 1 |
| Without Dubai | -67.6 | -11.2 | -56.4 | 0.0741 | 754 | 6 | 2 |
| Without KSA | -67.6 | -13.9 | -53.7 | 0.0631 | 616 | 6 | 2 |
| Without Oman | -69.6 | -9.2 | -60.3 | 0.1815 | 814 | 6 | 1 |
| Without Qatar | -67.6 | -9.4 | -58.2 | 0.0367 | 912 | 6 | 2 |
| Without Sharjah | -67.6 | -5.5 | -62.1 | 0.0068 | 857 | 6 | 2 |


The size of the gap survives dropping either sub-IG government (-54bp without Bahrain, -60bp without Oman), but significance does not (p = 0.308 and 0.181). Those two rows have one sub-IG government each, a case where the wild cluster bootstrap is unreliable, so read them as showing that one government cannot establish the result.

**Permutation test.** With only two sub-IG governments, a test that does not rely on cluster asymptotics is useful: compare them with every other pair of governments.

| sub_ig_governments | governments | assignments | difference_bp | p_two_sided | smallest_possible_p |
|---|---|---|---|---|---|
| Bahrain + Oman | 7 | 21 | -44.6 | 0.048 | 0.048 |


| governments | difference_bp |
|---|---|
| Bahrain + Oman | -44.6 |
| Bahrain + Sharjah | -41.1 |
| Oman + Sharjah | -26.5 |
| Abu Dhabi + Bahrain | -18.9 |
| Bahrain + Qatar | -16.9 |


| government | mean_basis_bp |
|---|---|
| Bahrain | -69.6 |
| Oman | -48.7 |
| Sharjah | -43.6 |
| Abu Dhabi | -12.0 |
| Qatar | -9.0 |
| KSA | -4.0 |
| Dubai | -3.9 |


Bahrain + Oman is the most extreme of 21 pairs, so p = 0.048, which is also the lowest value this test can give with 7 governments. The evidence is therefore at most about 1 in 21, whatever a bootstrap p-value says. The next pair is Bahrain + Sharjah (-41.1bp): Sharjah, investment grade under the rule, is close to Oman. Oman's mean mixes its sub-IG and investment-grade months.

## c. Over time

| sample | sub_ig_mean_bp | ig_mean_bp | gap_bp | p_wild_government | obligor_months | governments | sub_ig_governments |
|---|---|---|---|---|---|---|---|
| Before 2021 | -62.1 | 13.8 | -75.9 | 0.0458 | 169 | 4 | 2 |
| 2021 onward | -69.4 | -13.7 | -55.8 | 0.053 | 755 | 7 | 2 |
| 2023 onward | -50.9 | -13.7 | -37.2 | 0.1391 | 559 | 7 | 2 |
| Excluding 2020 | -65.9 | -10.1 | -55.8 | 0.0556 | 879 | 7 | 2 |


The gap is persistent but not stable: it is smaller in recent years, and its significance is sensitive to the period. Report it as a range, not as a fixed number of basis points.

## d. Which bonds are compared

| sample | sub_ig_mean_bp | ig_mean_bp | gap_bp | p_wild_government | obligor_months | governments | sub_ig_governments |
|---|---|---|---|---|---|---|---|
| Baseline | -67.6 | -9.4 | -58.2 | 0.0378 | 924 | 7 | 2 |
| Conventional curves from senior unsecured bonds only | -67.6 | -9.5 | -58.1 | 0.0394 | 924 | 7 | 2 |
| DEWA bond removed from Dubai's conventional curve | -67.6 | -9.4 | -58.2 | 0.0377 | 924 | 7 | 2 |
| Bonds LSEG flags as callable removed, both sides | -67.6 | -7.8 | -59.8 | 0.0417 | 697 | 7 | 2 |
| Sukuk-days priced 97-103 | -62.4 | -11.3 | -51.1 | 0.052 | 613 | 7 | 2 |
| All bond-days priced 95-105, both sides | -60.8 | -8.2 | -52.6 | 0.0333 | 617 | 7 | 2 |


The near-par rows limit coupon and price effects. The sukuk-only row filters the sukuk side alone; the both-sides row rebuilds the curves from bonds priced 95-105.

## e. Primary market: length of the lead

| lead_bdays | weak_sukuk_median_bp | weak_sukuk_n | weak_sukuk_n_ex_bahrain | weak_conv_median_bp | weak_conv_n | weak_sukuk_minus_conv_bp | other_sukuk_median_bp |
|---|---|---|---|---|---|---|---|
| 2 | -56.2 | 15 | 1 | 12.2 | 23 | -68.3 | -2.3 |
| 5 | -55.2 | 15 | 1 | 18.6 | 23 | -73.9 | -3.0 |
| 10 | -55.8 | 14 | 1 | 25.3 | 23 | -81.0 | 1.6 |
| 20 | -42.8 | 15 | 1 | 13.5 | 23 | -56.3 | 0.5 |


The sign and rough size of the new-issue premium do not depend on the 5-day lead (weak-credit sukuk median -42.8bp to -56.2bp, smallest at 20 days). Non-Bahraini weak-credit sukuk at any lead: at most 1.

## What this supports

- Supported: sukuk trade richer in Bahrain and Oman than in investment-grade issuers in secondary quotes, and in Bahrain at issue. The checks here find no sign that amortisation, calls, seniority or the lead cause it; limiting to near-par bonds trims the gap slightly but does not remove it.
- Not established: that sub-IG status itself, rather than something else specific to these two governments, drives it. Two treated governments cannot separate the two, and Sharjah shows a premium without the rating.
