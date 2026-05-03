# Inspection findings — AVRI vs existing metrics
_Generated 2026-05-03 10:03 from BigQuery materialized tables._
## 1. Distribution comparison
**AVRI distribution:**
| avri_color   |   n |   avg_avri |   min_avri |   max_avri |   avg_cr |   avg_um |   avg_dm |   avg_th |
|:-------------|----:|-----------:|-----------:|-----------:|---------:|---------:|---------:|---------:|
| green        | 532 |       95.4 |       75.3 |      100.0 |     97.7 |     99.7 |     97.1 |     83.6 |
| yellow       |  64 |       58.1 |       50.0 |       74.4 |     76.4 |     98.8 |     69.7 |     41.3 |
| red          | 170 |       18.5 |        0.0 |       47.3 |      6.8 |      1.6 |     33.7 |     46.3 |

**Naive CHS distribution (same accounts, same data):**
| naive_color   |   n |   avg_score |
|:--------------|----:|------------:|
| green         | 451 |        88.5 |
| yellow        | 167 |        64.5 |
| red           | 148 |        29.3 |

## 2. Where naive CHS is fooled (CHS > AVRI by 15+)
These are accounts the existing metric thinks are healthy but AVRI flags. These are the deck's strongest 'no single metric works' examples.
| account_id   | industry           |   arr_dollars |   tenure_days |   naive_chs_score |   avri_score |   gap_chs_minus_avri |   cr_score |   um_score |   dm_score |   th_score |   util_pct |   active_days_90 | floor_rule_triggered   | latest_color   | avri_color   |
|:-------------|:-------------------|--------------:|--------------:|------------------:|-------------:|---------------------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------------:|:-----------------------|:---------------|:-------------|
| ACC-00193    | Government         |        343700 |           183 |              48.1 |         17.2 |                 30.9 |        0.4 |        0.0 |       44.4 |       41.1 |        0.0 |               40 | False                  | green          | red          |
| ACC-00026    | Healthcare         |        165300 |           130 |              78.2 |         50.0 |                 28.2 |      100.0 |      100.0 |      100.0 |       28.5 |        0.8 |               90 | True                   | yellow         | yellow       |
| ACC-00335    | Healthcare         |         81100 |           146 |              41.4 |         13.3 |                 28.1 |        0.2 |        0.0 |       12.2 |       54.0 |        0.0 |               11 | False                  | green          | red          |
| ACC-00985    | Financial Services |         68500 |           332 |              43.4 |         16.7 |                 26.7 |        0.3 |        0.0 |       18.9 |       64.3 |        0.0 |               17 | False                  | green          | red          |
| ACC-00311    | Energy             |         76600 |           288 |              61.1 |         34.6 |                 26.5 |        5.3 |        3.7 |      100.0 |       59.7 |        0.0 |               90 | False                  | green          | red          |
| ACC-00609    | Financial Services |         46300 |           174 |              76.0 |         50.0 |                 26.0 |      100.0 |      100.0 |      100.0 |       19.9 |        0.8 |               90 | True                   | yellow         | yellow       |
| ACC-00470    | Financial Services |         38300 |           324 |              43.4 |         17.9 |                 25.5 |        0.3 |        0.0 |       14.4 |       74.7 |        0.0 |               13 | False                  | green          | red          |
| ACC-00687    | Retail             |         76000 |           155 |              61.1 |         35.9 |                 25.2 |        5.4 |        2.8 |      100.0 |       67.2 |        0.0 |               90 | False                  | green          | red          |
| ACC-00395    | Education          |          5000 |           510 |              40.0 |         15.9 |                 24.1 |        0.0 |        0.0 |        0.0 |       79.7 |        0.0 |                0 | False                  | green          | red          |
| ACC-00815    | Financial Services |         17400 |            94 |              40.0 |         16.5 |                 23.5 |        0.0 |        0.0 |        0.0 |       82.6 |        0.0 |                0 | False                  | green          | red          |

## 3. Where AVRI rewards what naive CHS misses (AVRI > CHS by 15+)
Often expansion candidates (consistent overage). The naive metric treats high utilization as broken; AVRI correctly treats it as a positive signal.
| account_id   | industry           |   arr_dollars |   naive_chs_score |   avri_score |   gap_avri_minus_chs |   cr_score |   um_score |   dm_score |   th_score |   util_pct | capacity_expansion_flag   | latest_color   | avri_color   |
|:-------------|:-------------------|--------------:|------------------:|-------------:|---------------------:|-----------:|-----------:|-----------:|-----------:|-----------:|:--------------------------|:---------------|:-------------|
| ACC-00876    | Manufacturing      |        245900 |              56.7 |         92.2 |                 35.5 |      100.0 |      100.0 |      100.0 |       61.0 |        0.7 | False                     | red            | green        |
| ACC-00529    | Healthcare         |         31600 |              58.8 |         93.9 |                 35.1 |      100.0 |      100.0 |      100.0 |       69.3 |        0.7 | False                     | red            | green        |
| ACC-00010    | Government         |        552700 |              58.0 |         91.8 |                 33.8 |      100.0 |      100.0 |      100.0 |       58.9 |        0.7 | False                     | red            | green        |
| ACC-00963    | Telecom            |        579400 |              60.0 |         93.6 |                 33.6 |      100.0 |      100.0 |      100.0 |       67.8 |        0.7 | False                     | red            | green        |
| ACC-00829    | Healthcare         |         44600 |              51.4 |         84.5 |                 33.1 |      100.0 |       85.3 |      100.0 |       44.6 |        0.5 | False                     | red            | green        |
| ACC-00924    | Financial Services |         46600 |              58.8 |         91.6 |                 32.8 |      100.0 |      100.0 |      100.0 |       57.8 |        0.7 | False                     | red            | green        |
| ACC-00057    | Retail             |        340200 |              61.9 |         93.9 |                 32.0 |      100.0 |      100.0 |      100.0 |       69.5 |        0.8 | False                     | red            | green        |
| ACC-00970    | Retail             |         73400 |              59.0 |         88.8 |                 29.8 |      100.0 |      100.0 |      100.0 |       44.1 |        0.7 | False                     | red            | green        |
| ACC-00750    | Energy             |         40500 |              59.8 |         89.4 |                 29.6 |      100.0 |      100.0 |      100.0 |       47.2 |        0.7 | False                     | red            | green        |
| ACC-00774    | Energy             |        314500 |              59.8 |         89.4 |                 29.6 |      100.0 |      100.0 |      100.0 |       47.2 |        0.7 | False                     | red            | green        |

## 4. Shelfware-like accounts (ARR > $100K, ≤5 active days in 90)
The classic case: paid customers not using the product. ARR-based metrics show them as healthy revenue; AVRI correctly scores them red.
| account_id   | industry           |   arr_dollars |   util_pct |   active_days_90 |   naive_chs_score |   avri_score | avri_color   |   cr_score |   um_score |   dm_score |   th_score |
|:-------------|:-------------------|--------------:|-----------:|-----------------:|------------------:|-------------:|:-------------|-----------:|-----------:|-----------:|-----------:|
| ACC-00202    | Financial Services |       3587500 |        0.0 |                0 |              40.0 |         19.5 | red          |        0.0 |        0.0 |        0.0 |       97.3 |
| ACC-00269    | Manufacturing      |       1095500 |        0.0 |                0 |              10.0 |          5.4 | red          |        0.0 |        0.0 |        0.0 |       27.2 |
| ACC-00324    | Energy             |        342200 |        0.0 |                0 |              10.0 |          0.0 | red          |        0.0 |        0.0 |        0.0 |        0.0 |
| ACC-00866    | Government         |        217700 |        0.0 |                0 |              40.0 |         18.7 | red          |        0.0 |        0.0 |        0.0 |       93.6 |
| ACC-00222    | Retail             |        188100 |        0.0 |                2 |              27.4 |         12.0 | red          |        5.1 |        0.0 |        2.2 |       50.0 |
| ACC-00632    | Healthcare         |        181900 |        0.0 |                4 |              12.7 |          5.5 | red          |        0.0 |        0.0 |        4.4 |       23.1 |
| ACC-00056    | Retail             |        172100 |        0.0 |                1 |              41.1 |         20.9 | red          |        2.2 |        0.0 |        1.1 |      100.0 |
| ACC-00406    | Retail             |        150100 |        0.0 |                5 |              43.5 |         21.3 | red          |        0.6 |        0.0 |        5.6 |      100.0 |
| ACC-00070    | Manufacturing      |        112100 |        0.0 |                5 |              13.4 |          6.3 | red          |        0.1 |        0.0 |        5.6 |       25.5 |

## 5. Spike-and-drop pattern (high CR, low UM)
Annual utilization looks acceptable but momentum has collapsed. UM pillar catches it.
_(no rows)_


## 6. Consistent overage (110–150% utilization, expansion candidates)
Customers consuming above commit. AVRI rewards this; naive CHS often penalizes.
| account_id   | industry           |   arr_dollars |   util_pct |   cr_score |   um_score |   dm_score |   th_score |   naive_chs_score |   avri_score | avri_color   |
|:-------------|:-------------------|--------------:|-----------:|-----------:|-----------:|-----------:|-----------:|------------------:|-------------:|:-------------|
| ACC-00113    | Retail             |        277300 |        1.3 |      100.0 |       96.8 |      100.0 |       65.3 |             100.0 |         92.1 | green        |
| ACC-00157    | Healthcare         |         57700 |        1.3 |      100.0 |      100.0 |      100.0 |       79.1 |             100.0 |         95.8 | green        |
| ACC-00837    | Energy             |        241000 |        1.3 |      100.0 |      100.0 |      100.0 |       99.8 |             100.0 |        100.0 | green        |
| ACC-00822    | Financial Services |         53300 |        1.3 |      100.0 |      100.0 |      100.0 |       87.2 |             100.0 |         97.4 | green        |
| ACC-00226    | Tech               |       8000000 |        1.3 |      100.0 |      100.0 |      100.0 |       15.1 |              70.0 |         50.0 | yellow       |
| ACC-00811    | Retail             |        169800 |        1.3 |      100.0 |      100.0 |      100.0 |       98.0 |             100.0 |         99.6 | green        |
| ACC-00536    | Tech               |        208100 |        1.3 |      100.0 |      100.0 |      100.0 |       85.1 |             100.0 |         97.0 | green        |
| ACC-00864    | Healthcare         |         22100 |        1.3 |      100.0 |      100.0 |      100.0 |       81.2 |              85.0 |         96.2 | green        |
| ACC-00839    | Energy             |        110700 |        1.3 |      100.0 |      100.0 |      100.0 |       41.1 |              70.0 |         88.2 | green        |
| ACC-00294    | Tech               |        748100 |        1.3 |      100.0 |      100.0 |      100.0 |      100.0 |             100.0 |        100.0 | green        |

## 7. Floor-rule triggered (technical health crisis)
Accounts where TH < 30 forced the AVRI cap. These would be Yellow/Red regardless of how good their consumption looks.
| account_id   | industry           |   arr_dollars |   cr_score |   um_score |   dm_score |   th_score |   avri_raw |   avri_score |   naive_chs_score | avri_color   | latest_color   |
|:-------------|:-------------------|--------------:|-----------:|-----------:|-----------:|-----------:|-----------:|-------------:|------------------:|:-------------|:---------------|
| ACC-00749    | Tech               |        492300 |      100.0 |      100.0 |      100.0 |       29.2 |       85.8 |         50.0 |              54.6 | yellow       | red            |
| ACC-00310    | Manufacturing      |         51300 |      100.0 |      100.0 |      100.0 |       29.1 |       85.8 |         50.0 |              56.2 | yellow       | red            |
| ACC-00026    | Healthcare         |        165300 |      100.0 |      100.0 |      100.0 |       28.5 |       85.7 |         50.0 |              78.2 | yellow       | yellow         |
| ACC-00575    | Manufacturing      |         42500 |      100.0 |      100.0 |      100.0 |       28.1 |       85.6 |         50.0 |              57.1 | yellow       | red            |
| ACC-00315    | Financial Services |         15200 |      100.0 |      100.0 |      100.0 |       25.7 |       85.1 |         50.0 |              61.7 | yellow       | red            |
| ACC-00437    | Government         |         78100 |      100.0 |      100.0 |      100.0 |       25.6 |       85.1 |         50.0 |              52.5 | yellow       | red            |
| ACC-00292    | Financial Services |         65200 |      100.0 |      100.0 |      100.0 |       24.6 |       84.9 |         50.0 |              60.5 | yellow       | red            |
| ACC-00330    | Telecom            |         31500 |      100.0 |      100.0 |      100.0 |       24.4 |       84.9 |         50.0 |              51.0 | yellow       | red            |
| ACC-00581    | Healthcare         |         31000 |      100.0 |      100.0 |      100.0 |       23.1 |       84.6 |         50.0 |              59.3 | yellow       | red            |
| ACC-00996    | Tech               |         59700 |      100.0 |      100.0 |      100.0 |       22.0 |       84.4 |         50.0 |              62.4 | yellow       | red            |

## 8. Region rollup
| region   |   csm_count |   account_count |   book_arr_dollars |   region_avri_dollar_weighted |   region_avri_equal_weighted |   green_count |   yellow_count |   red_count |   capacity_expansion_accounts |   floor_rule_accounts |   avg_tenure_days |   cold_start_accounts |   renewal_imminent_accounts |   at_risk_renewals_90d |
|:---------|------------:|----------------:|-------------------:|------------------------------:|-----------------------------:|--------------:|---------------:|------------:|------------------------------:|----------------------:|------------------:|----------------------:|----------------------------:|-----------------------:|
| EMEA     |          11 |             169 |          102224100 |                          84.6 |                         75.3 |           120 |              9 |          40 |                            17 |                    27 |             228.0 |                    27 |                          24 |                      5 |
| APAC     |           5 |              73 |           18574300 |                          82.2 |                         83.1 |            59 |              6 |           8 |                             3 |                     8 |             219.0 |                    15 |                          10 |                      1 |
| AMER     |          34 |             524 |          189855000 |                          70.7 |                         74.1 |           353 |             49 |         122 |                            31 |                    72 |             212.0 |                   119 |                          69 |                     14 |

## 9. Top & bottom CSMs (dollar-weighted AVRI)
| pos    | csm_id   | csm_name           | region   | segment    |   account_count |   book_arr_dollars |   csm_avri_dollar_weighted |   green_count |   yellow_count |   red_count |
|:-------|:---------|:-------------------|:---------|:-----------|----------------:|-------------------:|---------------------------:|--------------:|---------------:|------------:|
| BOTTOM | CSM-032  | David Caldwell     | AMER     | Mid-Market |              27 |            2457100 |                       50.1 |            17 |              3 |           7 |
| BOTTOM | CSM-019  | Phillip Meyers     | AMER     | Enterprise |               8 |           17427400 |                       48.8 |             5 |              1 |           2 |
| BOTTOM | CSM-017  | Denise Boyd        | AMER     | Mid-Market |              20 |            1739800 |                       48.2 |            13 |              0 |           7 |
| BOTTOM | CSM-044  | Katrina Anderson   | AMER     | Enterprise |              10 |            6753900 |                       38.3 |             5 |              2 |           3 |
| BOTTOM | CSM-045  | Brandon Richardson | AMER     | Mid-Market |              11 |             868900 |                       35.5 |             8 |              0 |           3 |
| TOP    | CSM-047  | Jason Jennings     | EMEA     | Enterprise |               9 |            7855000 |                       95.9 |             8 |              0 |           1 |
| TOP    | CSM-037  | Jill Freeman       | EMEA     | Enterprise |              17 |           28163600 |                       94.3 |            14 |              0 |           3 |
| TOP    | CSM-034  | Mary Cox           | EMEA     | Mid-Market |              12 |            1729500 |                       92.3 |             9 |              1 |           2 |
| TOP    | CSM-033  | Scott Smith        | EMEA     | Enterprise |              11 |           13410100 |                       91.1 |             9 |              0 |           2 |
| TOP    | CSM-006  | Jennifer Smith     | AMER     | Mid-Market |              23 |            2514000 |                       89.6 |            20 |              1 |           2 |

## 10. AVRI distribution by tenure bucket
Cold-start accounts (<90 days) legitimately can't be assessed by momentum-based pillars. Their distribution should be reported separately from mature accounts. If cold_start accounts skew red, that's mostly the level-guard firing on a thin tenure window — not a real renewal risk signal.
| tenure_bucket     | avri_color   |   n |   avg_avri |   avg_arr |
|:------------------|:-------------|----:|-----------:|----------:|
| cold_start (<90d) | green        |  56 |       87.2 |  203471.0 |
| cold_start (<90d) | yellow       |  35 |       63.1 |  308317.0 |
| cold_start (<90d) | red          |  70 |       21.4 |  429103.0 |
| mature (270d+)    | green        | 203 |       95.7 |  457322.0 |
| mature (270d+)    | yellow       |   9 |       54.4 |  964589.0 |
| mature (270d+)    | red          |  55 |       16.1 |  476391.0 |
| ramping (90-270d) | green        | 273 |       96.8 |  404945.0 |
| ramping (90-270d) | yellow       |  20 |       51.1 |  326985.0 |
| ramping (90-270d) | red          |  45 |       17.0 |  302707.0 |

## 11. At-risk renewals (next 90 days, not green)
The most actionable view for a CSM dashboard — accounts whose renewal is imminent and AVRI flags them as Yellow or Red. These are the accounts a CSM should be working *today*.
| account_id   | industry           |   arr_dollars |   days_to_renewal |   tenure_days |   avri_score | avri_color   |   cr_score |   um_score |   dm_score |   th_score | rep_id   |
|:-------------|:-------------------|--------------:|------------------:|--------------:|-------------:|:-------------|-----------:|-----------:|-----------:|-----------:|:---------|
| ACC-00218    | Tech               |       3601000 |                72 |           288 |         12.4 | red          |        0.3 |        0.0 |       45.6 |       15.8 | CSM-044  |
| ACC-00202    | Financial Services |       3587500 |                29 |           527 |         19.5 | red          |        0.0 |        0.0 |        0.0 |       97.3 | CSM-012  |
| ACC-00107    | Tech               |        854000 |                14 |           346 |         25.7 | red          |        5.3 |        3.3 |      100.0 |       15.8 | CSM-036  |
| ACC-00263    | Tech               |        726000 |                90 |           270 |         25.6 | red          |        5.4 |        3.8 |      100.0 |       14.4 | CSM-021  |
| ACC-00244    | Healthcare         |        457800 |                34 |           326 |         31.1 | red          |        5.3 |        3.3 |      100.0 |       42.6 | CSM-036  |
| ACC-00866    | Government         |        217700 |                36 |           488 |         18.7 | red          |        0.0 |        0.0 |        0.0 |       93.6 | CSM-041  |
| ACC-00005    | Telecom            |        162000 |                73 |           407 |         65.0 | yellow       |      100.0 |       63.5 |       47.8 |       31.9 | CSM-035  |
| ACC-00017    | Financial Services |        155800 |                26 |           334 |         19.1 | red          |        0.5 |        0.0 |       37.8 |       57.1 | CSM-047  |
| ACC-00448    | Tech               |        143700 |                34 |           326 |          8.0 | red          |        0.3 |        0.0 |       28.9 |       10.8 | CSM-025  |
| ACC-00311    | Energy             |         76600 |                72 |           288 |         34.6 | red          |        5.3 |        3.7 |      100.0 |       59.7 | CSM-009  |
| ACC-00985    | Financial Services |         68500 |                28 |           332 |         16.7 | red          |        0.3 |        0.0 |       18.9 |       64.3 | CSM-017  |
| ACC-00486    | Government         |         61900 |                 0 |           360 |         33.8 | red          |        5.4 |        3.5 |      100.0 |       55.4 | CSM-032  |
| ACC-00684    | Government         |         58100 |                76 |           284 |         31.9 | red          |        5.3 |        3.9 |      100.0 |       45.6 | CSM-002  |
| ACC-00360    | Government         |         55300 |                42 |           318 |          4.8 | red          |        0.3 |        0.0 |       17.8 |        5.6 | CSM-026  |
| ACC-00631    | Healthcare         |         45700 |                61 |           299 |         22.5 | red          |        5.3 |        3.1 |      100.0 |        0.0 | CSM-038  |

## Recommended next steps
- **Pick 3 deck-story accounts** from sections 4, 5, 6 above. One shelfware,
  one spike-and-drop, one overage. These become the visual narrative on the slide
  titled "No single existing metric handles all four dimensions."
- **Examine the floor-rule triggered list** for false positives. If any look like
  legitimately healthy accounts, the floor rule's threshold may be too aggressive.
- **Compare AVRI distribution to naive CHS distribution.** A meaningful difference
  in shape (more red in AVRI than CHS) is the visual proof that AVRI surfaces risk
  existing metrics hide.
- **Check region rollups against intuition.** If AMER, EMEA, APAC look identical
  on AVRI, the dataset's persona distribution is too uniform across regions.
