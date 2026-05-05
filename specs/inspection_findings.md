# Inspection findings — AVRI vs existing metrics
_Generated 2026-05-05 14:10 from BigQuery materialized tables._
## 1. Distribution comparison
**AVRI distribution:**
| avri_color   |   n |   avg_avri |   min_avri |   max_avri |   avg_cr |   avg_um |   avg_dm |   avg_th |
|:-------------|----:|-----------:|-----------:|-----------:|---------:|---------:|---------:|---------:|
| green        | 533 |       95.4 |       75.3 |      100.0 |     97.7 |     99.7 |     97.2 |     83.6 |
| yellow       |  63 |       57.9 |       50.0 |       74.4 |     77.2 |     98.8 |     69.2 |     40.8 |
| red          | 134 |       19.6 |        0.2 |       47.3 |      7.9 |      1.6 |     39.5 |     44.5 |
| onboarding   |  36 |      nan   |      nan   |      nan   |    nan   |    nan   |    nan   |    nan   |

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
| ACC-00774    | Energy             |        314500 |              59.8 |         89.4 |                 29.6 |      100.0 |      100.0 |      100.0 |       47.2 |        0.7 | False                     | red            | green        |
| ACC-00750    | Energy             |         40500 |              59.8 |         89.4 |                 29.6 |      100.0 |      100.0 |      100.0 |       47.2 |        0.7 | False                     | red            | green        |

## 4. Shelfware-like accounts (ARR > $100K, ≤5 active days in 90)
The classic case: paid customers not using the product. ARR-based metrics show them as healthy revenue; AVRI correctly scores them red.
| account_id   | industry           |   arr_dollars |   util_pct |   active_days_90 |   naive_chs_score |   avri_score | avri_color   |   cr_score |   um_score |   dm_score |   th_score |
|:-------------|:-------------------|--------------:|-----------:|-----------------:|------------------:|-------------:|:-------------|-----------:|-----------:|-----------:|-----------:|
| ACC-00202    | Financial Services |       3587500 |        0.0 |                0 |              40.0 |         19.5 | red          |        0.0 |        0.0 |        0.0 |       97.3 |
| ACC-00269    | Manufacturing      |       1095500 |        0.0 |                0 |              10.0 |          5.4 | red          |        0.0 |        0.0 |        0.0 |       27.2 |
| ACC-00866    | Government         |        217700 |        0.0 |                0 |              40.0 |         18.7 | red          |        0.0 |        0.0 |        0.0 |       93.6 |

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
| ACC-00310    | Manufacturing      |         51300 |      100.0 |      100.0 |      100.0 |       29.1 |       85.8 |         50.0 |              56.2 | yellow       | red            |
| ACC-00749    | Tech               |        492300 |      100.0 |      100.0 |      100.0 |       29.2 |       85.8 |         50.0 |              54.6 | yellow       | red            |
| ACC-00026    | Healthcare         |        165300 |      100.0 |      100.0 |      100.0 |       28.5 |       85.7 |         50.0 |              78.2 | yellow       | yellow         |
| ACC-00575    | Manufacturing      |         42500 |      100.0 |      100.0 |      100.0 |       28.1 |       85.6 |         50.0 |              57.1 | yellow       | red            |
| ACC-00315    | Financial Services |         15200 |      100.0 |      100.0 |      100.0 |       25.7 |       85.1 |         50.0 |              61.7 | yellow       | red            |
| ACC-00437    | Government         |         78100 |      100.0 |      100.0 |      100.0 |       25.6 |       85.1 |         50.0 |              52.5 | yellow       | red            |
| ACC-00292    | Financial Services |         65200 |      100.0 |      100.0 |      100.0 |       24.6 |       84.9 |         50.0 |              60.5 | yellow       | red            |
| ACC-00330    | Telecom            |         31500 |      100.0 |      100.0 |      100.0 |       24.4 |       84.9 |         50.0 |              51.0 | yellow       | red            |
| ACC-00581    | Healthcare         |         31000 |      100.0 |      100.0 |      100.0 |       23.1 |       84.6 |         50.0 |              59.3 | yellow       | red            |
| ACC-00996    | Tech               |         59700 |      100.0 |      100.0 |      100.0 |       22.0 |       84.4 |         50.0 |              62.4 | yellow       | red            |

## 8. Region rollup
| region   |   csm_count |   account_count |   scored_account_count |   book_arr_dollars |   region_avri_dollar_weighted |   region_avri_equal_weighted |   green_count |   yellow_count |   red_count |   onboarding_count |   capacity_expansion_accounts |   floor_rule_accounts |   avg_tenure_days |   cold_start_accounts |   renewal_imminent_accounts |   at_risk_renewals_90d |   book_rv_dollars |   scored_arr_dollars |   realization_rate |   unrealized_total_dollars |   unrealized_cr_dollars |   unrealized_um_dollars |   unrealized_dm_dollars |   unrealized_th_dollars |   unrealized_floor_dollars |
|:---------|------------:|----------------:|-----------------------:|-------------------:|------------------------------:|-----------------------------:|--------------:|---------------:|------------:|-------------------:|------------------------------:|----------------------:|------------------:|----------------------:|----------------------------:|-----------------------:|------------------:|---------------------:|-------------------:|---------------------------:|------------------------:|------------------------:|------------------------:|------------------------:|---------------------------:|
| EMEA     |          11 |             169 |                    159 |          100262300 |                          85.9 |                         79.2 |           120 |              9 |          30 |                 10 |                            17 |                    23 |             228.0 |                    27 |                          24 |                      5 |        86166425.7 |          100262300.0 |                0.9 |                 14095874.3 |               2616006.7 |               2616742.0 |               1545962.0 |               4585865.1 |                  2744837.4 |
| APAC     |           5 |              73 |                     71 |           18512900 |                          82.4 |                         85.3 |            59 |              6 |           6 |                  2 |                             3 |                     6 |             219.0 |                    15 |                          10 |                      1 |        15262372.6 |           18512900.0 |                0.8 |                  3250527.4 |                867922.5 |                724726.0 |                348299.5 |                997501.0 |                   313562.9 |
| AMER     |          34 |             524 |                    500 |          186228200 |                          71.8 |                         76.9 |           354 |             48 |          98 |                 24 |                            31 |                    65 |             212.0 |                   119 |                          69 |                     14 |       133694064.4 |          186228200.0 |                0.7 |                 52534135.6 |              16502062.4 |              16074756.4 |               7325369.3 |              10313617.8 |                  2343233.0 |

## 9. Top & bottom CSMs (dollar-weighted AVRI)
| pos    | csm_id   | csm_name           | region   | segment    |   account_count |   book_arr_dollars |   csm_avri_dollar_weighted |   green_count |   yellow_count |   red_count |
|:-------|:---------|:-------------------|:---------|:-----------|----------------:|-------------------:|---------------------------:|--------------:|---------------:|------------:|
| BOTTOM | CSM-032  | David Caldwell     | AMER     | Mid-Market |              27 |            2210000 |                       54.4 |            17 |              3 |           5 |
| BOTTOM | CSM-017  | Denise Boyd        | AMER     | Mid-Market |              20 |            1501000 |                       52.7 |            13 |              0 |           5 |
| BOTTOM | CSM-019  | Phillip Meyers     | AMER     | Enterprise |               8 |           17427400 |                       48.8 |             5 |              1 |           2 |
| BOTTOM | CSM-045  | Brandon Richardson | AMER     | Mid-Market |              11 |             700200 |                       41.4 |             8 |              0 |           3 |
| BOTTOM | CSM-044  | Katrina Anderson   | AMER     | Enterprise |              10 |            6753900 |                       38.3 |             5 |              2 |           3 |
| TOP    | CSM-047  | Jason Jennings     | EMEA     | Enterprise |               9 |            7855000 |                       95.9 |             8 |              0 |           1 |
| TOP    | CSM-033  | Scott Smith        | EMEA     | Enterprise |              11 |           12733700 |                       95.5 |             9 |              0 |           1 |
| TOP    | CSM-034  | Mary Cox           | EMEA     | Mid-Market |              12 |            1669300 |                       95.4 |             9 |              1 |           1 |
| TOP    | CSM-037  | Jill Freeman       | EMEA     | Enterprise |              17 |           27838700 |                       95.1 |            14 |              0 |           2 |
| TOP    | CSM-039  | Spencer Ortiz      | AMER     | Enterprise |               9 |            5523800 |                       92.8 |             7 |              0 |           0 |

## 10. AVRI distribution by tenure bucket
Cold-start accounts (<90 days) legitimately can't be assessed by momentum-based pillars. Their distribution should be reported separately from mature accounts. If cold_start accounts skew red, that's mostly the level-guard firing on a thin tenure window — not a real renewal risk signal.
| tenure_bucket     | avri_color   |   n |   avg_avri |   avg_arr |
|:------------------|:-------------|----:|-----------:|----------:|
| cold_start (<90d) | green        |  56 |       87.2 |  203471.0 |
| cold_start (<90d) | yellow       |  35 |       63.1 |  308317.0 |
| cold_start (<90d) | red          |  34 |       28.8 |  735021.0 |
| cold_start (<90d) | onboarding   |  36 |      nan   |       0.0 |
| mature (270d+)    | green        | 203 |       95.7 |  457322.0 |
| mature (270d+)    | yellow       |   9 |       54.4 |  964589.0 |
| mature (270d+)    | red          |  55 |       16.1 |  476391.0 |
| ramping (90-270d) | green        | 274 |       96.8 |  404032.0 |
| ramping (90-270d) | yellow       |  19 |       50.0 |  317816.0 |
| ramping (90-270d) | red          |  45 |       17.0 |  296991.0 |

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

## 12. v1.3 Activation Grace Period status
New in v1.3: each contract has a 90-day activation grace window. A contract is excluded from CR's denominator until it has either hit 15% of monthly commit in cumulative usage OR been signed for 90+ days. Accounts with all contracts in grace are flagged `onboarding` with NULL scores; they don't drag the CSM's average down during ramp.
| grace_status                       |   n |   avg_arr |   avg_tenure_days |   avg_grace_contracts |
|:-----------------------------------|----:|----------:|------------------:|----------------------:|
| fully activated                    | 727 |  419119.0 |             225.0 |                   0.0 |
| all-grace (onboarding)             |  36 |       0.0 |              29.0 |                   1.0 |
| mixed (some activated, some grace) |   3 |  101267.0 |             201.0 |                   1.0 |

## 13. v2.0 Realized Value — org headline
RV = ARR × AVRI/100 (linear). Onboarding accounts contribute 0 by definition; their ARR is reported separately and not part of the realization-rate denominator. The realization rate answers, in one number, the executive question: *"of every dollar booked, how much is being actively realized?"*
|   n_total |   n_scored |   n_grace |   total_arr_m |   total_rv_m |   total_unrealized_m |   realization_rate |
|----------:|-----------:|----------:|--------------:|-------------:|---------------------:|-------------------:|
|       766 |        730 |        36 |         305.0 |        235.1 |                 69.9 |                0.8 |

## 14. v2.0 Realized Value — pillar attribution of unrealized $
Unrealized $ decomposes cleanly across the four pillars (and floor-rule residual). Each column = `Σ ARR × weight × (100 − pillar_score) / 100`. The five contributions sum to total unrealized $ within rounding. This is the data behind the lobby's pillar heatmap.
|   unrealized_cr_m |   unrealized_um_m |   unrealized_dm_m |   unrealized_th_m |   unrealized_floor_m |
|------------------:|------------------:|------------------:|------------------:|---------------------:|
|              20.0 |              19.4 |               9.2 |              15.9 |                  5.4 |

## 15. v2.0 Realized Value — by region
Realization rate, total RV, and pillar-decomposition of unrealized $ at the region grain. Drill in the dashboard for CSM and account level.
| region   |   account_count |   book_arr_m |   book_rv_m |   unrealized_m |   realization_pct |   unr_cr_m |   unr_um_m |   unr_dm_m |   unr_th_m |   unr_floor_m |
|:---------|----------------:|-------------:|------------:|---------------:|------------------:|-----------:|-----------:|-----------:|-----------:|--------------:|
| AMER     |             524 |        186.2 |       133.7 |           52.5 |              71.8 |       16.5 |       16.1 |        7.3 |       10.3 |           2.3 |
| EMEA     |             169 |        100.3 |        86.2 |           14.1 |              85.9 |        2.6 |        2.6 |        1.6 |        4.6 |           2.7 |
| APAC     |              73 |         18.5 |        15.3 |            3.2 |              82.4 |        0.9 |        0.7 |        0.3 |        1.0 |           0.3 |

## 16. v2.0 Renewal landmines — top 15 unrealized-$ accounts
Largest single-account contributions to the total unrealized-$ figure. These are the operationally important accounts: high ARR, low AVRI, biggest dollar weight. The deck's case-card stories are pulled from this list.
| account_id   | industry           | rep_id   |       arr |        rv |   unrealized |   avri | avri_color   |
|:-------------|:-------------------|:---------|----------:|----------:|-------------:|-------:|:-------------|
| ACC-00047    | Healthcare         | CSM-010  | 8000000.0 | 2376000.0 |    5624000.0 |   29.7 | red          |
| ACC-00291    | Government         | CSM-019  | 7310200.0 | 2046856.0 |    5263344.0 |   28.0 | red          |
| ACC-00212    | Tech               | CSM-021  | 6225700.0 | 1643585.0 |    4582115.0 |   26.4 | red          |
| ACC-00226    | Tech               | CSM-023  | 8000000.0 | 4000000.0 |    4000000.0 |   50.0 | yellow       |
| ACC-00036    | Financial Services | CSM-019  | 5023700.0 | 1798485.0 |    3225215.0 |   35.8 | red          |
| ACC-00218    | Tech               | CSM-044  | 3601000.0 |  446524.0 |    3154476.0 |   12.4 | red          |
| ACC-00202    | Financial Services | CSM-012  | 3587500.0 |  699563.0 |    2887938.0 |   19.5 | red          |
| ACC-00132    | Telecom            | CSM-036  | 2436800.0 |  285106.0 |    2151694.0 |   11.7 | red          |
| ACC-00034    | Retail             | CSM-020  | 2393500.0 |  658213.0 |    1735288.0 |   27.5 | red          |
| ACC-00186    | Manufacturing      | CSM-020  | 1698500.0 |  324414.0 |    1374087.0 |   19.1 | red          |
| ACC-00096    | Retail             | CSM-020  | 2538000.0 | 1269000.0 |    1269000.0 |   50.0 | yellow       |
| ACC-00038    | Manufacturing      | CSM-015  | 1498700.0 |  247286.0 |    1251415.0 |   16.5 | red          |
| ACC-00269    | Manufacturing      | CSM-022  | 1095500.0 |   59157.0 |    1036343.0 |    5.4 | red          |
| ACC-00227    | Retail             | CSM-003  | 1832900.0 |  916450.0 |     916450.0 |   50.0 | yellow       |
| ACC-00833    | Manufacturing      | CSM-032  |  800000.0 |   90400.0 |     709600.0 |   11.3 | red          |

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
