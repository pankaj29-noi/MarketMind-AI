# BENCHMARK_REPORT — CSV Analytics (deterministic SQL ground truth)

**Date:** 2026-09-21 03:32:26
**Rows:** 3000
**Questions:** 50 (10 easy / 10 medium / 15 hard / 15 very_hard)
**Session:** `bench_ec479933` table `bench_ds_3000`

## Pipeline micro timings

| Stage | ms |
|---|---:|
| DuckDB register CSV | 213.05 |
| Rich schema profile (cold) | 15.94 |
| Rich schema profile (cached) | 0.00 |
| Profile fingerprint | `500a3c015ba368fea53b283f` |

## Accuracy (ground-truth SQL execution)

| Metric | Value |
|---|---:|
| Executed OK | **50/50** (100.0%) |
| Failure rate | 0.0% |
| Avg SQL latency | 0.744 ms |
| p95 SQL latency | 2.570 ms |
| Max SQL latency | 3.553 ms |

### By difficulty

| Difficulty | OK | Avg ms |
|---|---:|---:|
| easy | 10/10 | 0.272 |
| medium | 10/10 | 0.421 |
| hard | 15/15 | 1.116 |
| very_hard | 15/15 | 0.903 |

## Notes

- This report measures **DuckDB SQL correctness + latency** for the 50-question suite.
- Expected answers are produced by the listed `expected_sql` (deterministic), not by an LLM.
- End-to-end NL→SQL LLM accuracy / LLM-calls-per-question are tracked separately when running the agent pipeline.
- Cache hit rate for NL answers: N/A in this SQL-only harness (schema cache cold/cached shown above).

## Failures

None.

## Per-question results

- **E01** [easy] OK 0.09ms rows=1 — How many rows are in the dataset?
- **E02** [easy] OK 0.117ms rows=1 — What is the sum of Data_value?
- **E03** [easy] OK 0.102ms rows=1 — What is the average Data_value?
- **E04** [easy] OK 0.28ms rows=1 — How many distinct Series_title_2 values are there?
- **E05** [easy] OK 1.414ms rows=3 — List distinct STATUS values.
- **E06** [easy] OK 0.115ms rows=1 — What is the minimum Period?
- **E07** [easy] OK 0.112ms rows=1 — What is the maximum Period?
- **E08** [easy] OK 0.113ms rows=1 — How many rows have null Suppressed?
- **E09** [easy] OK 0.278ms rows=1 — Count rows where UNITS is Dollars.
- **E10** [easy] OK 0.101ms rows=1 — What is the maximum Data_value?
- **M01** [medium] OK 0.372ms rows=5 — Top 5 Series_title_2 by sum of Data_value.
- **M02** [medium] OK 0.315ms rows=4 — Average Data_value by Series_title_1, top 5.
- **M03** [medium] OK 0.493ms rows=3 — Row counts by STATUS.
- **M04** [medium] OK 0.157ms rows=1 — Total Data_value for Sales (operating income).
- **M05** [medium] OK 0.675ms rows=2 — Count of distinct Period values per Series_title_3.
- **M06** [medium] OK 1.033ms rows=5 — Bottom 5 industries by total Data_value.
- **M07** [medium] OK 0.275ms rows=2 — Average Magnitude by Group.
- **M08** [medium] OK 0.289ms rows=3 — How many rows per Series_title_4?
- **M09** [medium] OK 0.314ms rows=1 — Sum Data_value where Period >= 2019.
- **M10** [medium] OK 0.283ms rows=3 — Top 3 Series_title_1 by row count.
- **H01** [hard] OK 0.352ms rows=10 — For Sales (operating income), top 10 industries by total Data_value.
- **H02** [hard] OK 0.648ms rows=11 — Yearly total Data_value using floor(Period) as year.
- **H03** [hard] OK 2.17ms rows=10 — Industries with average Data_value above the overall average.
- **H04** [hard] OK 3.553ms rows=3 — Percentage of rows by STATUS.
- **H05** [hard] OK 3.058ms rows=11 — Top industry per year by sum of Data_value.
- **H06** [hard] OK 1.132ms rows=5 — Share of total Data_value for top 5 industries.
- **H07** [hard] OK 1.125ms rows=2 — Median Data_value by Series_title_3.
- **H08** [hard] OK 0.365ms rows=1 — Count industries with total Data_value over 1 million.
- **H09** [hard] OK 0.669ms rows=11 — YoY change in total Data_value by year.
- **H10** [hard] OK 0.337ms rows=5 — Top 5 industries for Operating profit by total Data_value.
- **H11** [hard] OK 0.972ms rows=10 — Coefficient of variation of Data_value by industry (top 10 by CV).
- **H12** [hard] OK 0.601ms rows=1 — Duplicate Series_reference + Period combinations count.
- **H13** [hard] OK 0.513ms rows=2 — Average Data_value for Current vs other Series_title_3.
- **H14** [hard] OK 0.501ms rows=10 — Rank industries by total Data_value and keep ranks 1-10.
- **H15** [hard] OK 0.743ms rows=4 — Null Data_value rate by Series_title_1.
- **V01** [very_hard] OK 0.675ms rows=10 — Top 10 industries by Sales revenue share of total sales, keep share > 2%.
- **V02** [very_hard] OK 1.105ms rows=55 — Per year top 5 industries by Data_value with year share percent.
- **V03** [very_hard] OK 0.719ms rows=10 — Industries with >= 20 rows whose avg Data_value exceeds overall avg, ranked by avg.
- **V04** [very_hard] OK 1.757ms rows=4 — For each Series_title_1, top industry by total and its contribution percent within that metric.
- **V05** [very_hard] OK 0.93ms rows=10 — Last six distinct Period values: top 10 industries by sum, exclude industries with fewer than 3 rows in window.
- **V06** [very_hard] OK 1.11ms rows=10 — Compare each industry average order-like Data_value to overall average; show only those > overall and share of total > 1%.
- **V07** [very_hard] OK 0.614ms rows=11 — Rolling year totals: for each year, sum of that year and previous year Data_value totals.
- **V08** [very_hard] OK 0.416ms rows=11 — Within Construction industry, yearly share of that industry total across years.
- **V09** [very_hard] OK 0.824ms rows=6 — Top-N within Group: for each Group, top 3 Series_title_2 by sum Data_value.
- **V10** [very_hard] OK 1.051ms rows=20 — Sales vs Operating profit totals by industry for industries present in both; ratio sales/profit.
- **V11** [very_hard] OK 0.657ms rows=10 — Exclude Magnitude != 6; among remaining, top 10 industries by sum with cumulative share.
- **V12** [very_hard] OK 0.49ms rows=8 — Multi-condition: Period between 2018 and 2021, UNITS=Dollars, STATUS=F; top 8 industries by avg Data_value with n>=5.
- **V13** [very_hard] OK 0.732ms rows=3 — Percentile: industries whose total is above the 90th percentile of industry totals.
- **V14** [very_hard] OK 0.675ms rows=10 — Nested aggregation: average of yearly totals per industry, then top 10 industries by that average yearly total.
- **V15** [very_hard] OK 1.793ms rows=10 — Find top 10 suppliers-like industries by revenue in recent periods, exclude n<5, compute share of total, compare avg to overall avg, keep share>2%.
