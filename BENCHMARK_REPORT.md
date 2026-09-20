# BENCHMARK_REPORT — CSV Analytics (deterministic SQL ground truth)

**Date:** 2026-09-21 03:54:22  
**Rows:** 3000  
**Questions:** 100 (20 easy / 25 medium / 30 hard / 25 very_hard)  
**Session:** `bench_92fa2b14` table `bench_ds_3000`  

## Pipeline micro timings

| Stage | ms |
|---|---:|
| DuckDB register CSV | 416.13 |
| Rich schema profile (cold) | 33.00 |
| Rich schema profile (cached) | 0.00 |
| Profile fingerprint | `500a3c015ba368fea53b283f` |

## Accuracy (ground-truth SQL execution)

| Metric | Value |
|---|---:|
| Executed OK | **100/100** (100.0%) |
| Failure rate | 0.0% |
| Avg SQL latency | 0.776 ms |
| p95 SQL latency | 2.468 ms |
| Max SQL latency | 5.636 ms |

### By difficulty

| Difficulty | OK | Avg ms |
|---|---:|---:|
| easy | 20/20 | 0.234 |
| medium | 25/25 | 0.625 |
| hard | 30/30 | 1.036 |
| very_hard | 25/25 | 1.050 |

## Notes

- This report measures **DuckDB SQL correctness + latency** for the 100-question suite.
- Expected answers are produced by the listed `expected_sql` (deterministic), not by an LLM.
- End-to-end NL→SQL LLM accuracy / LLM-calls-per-question are tracked separately when running the agent pipeline.
- Cache hit rate for NL answers: N/A in this SQL-only harness (schema cache cold/cached shown above).

## Failures

None.

## Per-question results

- **E01** [easy] OK 0.115ms rows=1 — How many rows are in the dataset?
- **E02** [easy] OK 0.122ms rows=1 — What is the sum of Data_value?
- **E03** [easy] OK 0.104ms rows=1 — What is the average Data_value?
- **E04** [easy] OK 0.29ms rows=1 — How many distinct Series_title_2 values are there?
- **E05** [easy] OK 1.344ms rows=3 — List distinct STATUS values.
- **E06** [easy] OK 0.118ms rows=1 — What is the minimum Period?
- **E07** [easy] OK 0.109ms rows=1 — What is the maximum Period?
- **E08** [easy] OK 0.106ms rows=1 — How many rows have null Suppressed?
- **E09** [easy] OK 0.484ms rows=1 — Count rows where UNITS is Dollars.
- **E10** [easy] OK 0.096ms rows=1 — What is the maximum Data_value?
- **M01** [medium] OK 0.374ms rows=5 — Top 5 Series_title_2 by sum of Data_value.
- **M02** [medium] OK 0.353ms rows=4 — Average Data_value by Series_title_1, top 5.
- **M03** [medium] OK 0.518ms rows=3 — Row counts by STATUS.
- **M04** [medium] OK 0.156ms rows=1 — Total Data_value for Sales (operating income).
- **M05** [medium] OK 0.619ms rows=2 — Count of distinct Period values per Series_title_3.
- **M06** [medium] OK 0.496ms rows=5 — Bottom 5 industries by total Data_value.
- **M07** [medium] OK 0.316ms rows=2 — Average Magnitude by Group.
- **M08** [medium] OK 0.284ms rows=3 — How many rows per Series_title_4?
- **M09** [medium] OK 0.365ms rows=1 — Sum Data_value where Period >= 2019.
- **M10** [medium] OK 0.317ms rows=3 — Top 3 Series_title_1 by row count.
- **H01** [hard] OK 0.386ms rows=10 — For Sales (operating income), top 10 industries by total Data_value.
- **H02** [hard] OK 0.673ms rows=11 — Yearly total Data_value using floor(Period) as year.
- **H03** [hard] OK 3.784ms rows=10 — Industries with average Data_value above the overall average.
- **H04** [hard] OK 3.919ms rows=3 — Percentage of rows by STATUS.
- **H05** [hard] OK 3.627ms rows=11 — Top industry per year by sum of Data_value.
- **H06** [hard] OK 1.28ms rows=5 — Share of total Data_value for top 5 industries.
- **H07** [hard] OK 0.434ms rows=2 — Median Data_value by Series_title_3.
- **H08** [hard] OK 0.407ms rows=1 — Count industries with total Data_value over 1 million.
- **H09** [hard] OK 0.942ms rows=11 — YoY change in total Data_value by year.
- **H10** [hard] OK 0.39ms rows=5 — Top 5 industries for Operating profit by total Data_value.
- **H11** [hard] OK 1.021ms rows=10 — Coefficient of variation of Data_value by industry (top 10 by CV).
- **H12** [hard] OK 0.512ms rows=1 — Duplicate Series_reference + Period combinations count.
- **H13** [hard] OK 0.543ms rows=2 — Average Data_value for Current vs other Series_title_3.
- **H14** [hard] OK 0.518ms rows=10 — Rank industries by total Data_value and keep ranks 1-10.
- **H15** [hard] OK 1.0ms rows=4 — Null Data_value rate by Series_title_1.
- **V01** [very_hard] OK 0.77ms rows=10 — Top 10 industries by Sales revenue share of total sales, keep share > 2%.
- **V02** [very_hard] OK 1.141ms rows=55 — Per year top 5 industries by Data_value with year share percent.
- **V03** [very_hard] OK 0.687ms rows=10 — Industries with >= 20 rows whose avg Data_value exceeds overall avg, ranked by avg.
- **V04** [very_hard] OK 1.404ms rows=4 — For each Series_title_1, top industry by total and its contribution percent within that metric.
- **V05** [very_hard] OK 2.498ms rows=10 — Last six distinct Period values: top 10 industries by sum, exclude industries with fewer than 3 rows in window.
- **V06** [very_hard] OK 1.203ms rows=10 — Compare each industry average order-like Data_value to overall average; show only those > overall and share of total > 1%.
- **V07** [very_hard] OK 1.274ms rows=11 — Rolling year totals: for each year, sum of that year and previous year Data_value totals.
- **V08** [very_hard] OK 0.818ms rows=11 — Within Construction industry, yearly share of that industry total across years.
- **V09** [very_hard] OK 0.832ms rows=6 — Top-N within Group: for each Group, top 3 Series_title_2 by sum Data_value.
- **V10** [very_hard] OK 1.204ms rows=20 — Sales vs Operating profit totals by industry for industries present in both; ratio sales/profit.
- **V11** [very_hard] OK 0.835ms rows=10 — Exclude Magnitude != 6; among remaining, top 10 industries by sum with cumulative share.
- **V12** [very_hard] OK 0.566ms rows=8 — Multi-condition: Period between 2018 and 2021, UNITS=Dollars, STATUS=F; top 8 industries by avg Data_value with n>=5.
- **V13** [very_hard] OK 0.687ms rows=3 — Percentile: industries whose total is above the 90th percentile of industry totals.
- **V14** [very_hard] OK 0.815ms rows=10 — Nested aggregation: average of yearly totals per industry, then top 10 industries by that average yearly total.
- **V15** [very_hard] OK 1.899ms rows=10 — Find top 10 suppliers-like industries by revenue in recent periods, exclude n<5, compute share of total, compare avg to overall avg, keep share>2%.
- **E11** [easy] OK 0.226ms rows=1 — What is the median Data_value?
- **E12** [easy] OK 0.317ms rows=1 — How many distinct Series_title_1 values are there?
- **E13** [easy] OK 0.295ms rows=1 — List distinct UNITS values.
- **E14** [easy] OK 0.102ms rows=1 — Count rows where Data_value is not null.
- **E15** [easy] OK 0.09ms rows=1 — What is the sum of Magnitude?
- **E16** [easy] OK 0.266ms rows=1 — How many distinct Series_reference values?
- **E17** [easy] OK 0.094ms rows=1 — Minimum Data_value in the dataset.
- **E18** [easy] OK 0.111ms rows=1 — Count rows where STATUS is F.
- **E19** [easy] OK 0.081ms rows=1 — Average Magnitude across all rows.
- **E20** [easy] OK 0.202ms rows=1 — How many distinct Group values?
- **M11** [medium] OK 0.39ms rows=10 — Top 10 Series_title_2 by average Data_value.
- **M12** [medium] OK 0.322ms rows=2 — Row counts by Series_title_3.
- **M13** [medium] OK 0.192ms rows=3 — Sum Data_value by STATUS.
- **M14** [medium] OK 0.541ms rows=4 — Top 5 Series_title_1 by sum of Data_value.
- **M15** [medium] OK 0.175ms rows=1 — Average Data_value for Period >= 2020.
- **M16** [medium] OK 0.541ms rows=3 — Count distinct Series_title_2 per STATUS.
- **M17** [medium] OK 0.419ms rows=5 — Bottom 5 Series_title_2 by sum of Data_value (non-null).
- **M18** [medium] OK 0.343ms rows=3 — Total Data_value by Series_title_4.
- **M19** [medium] OK 1.798ms rows=1 — How many rows per Magnitude value?
- **M20** [medium] OK 0.375ms rows=4 — Max Data_value by Series_title_1.
- **M21** [medium] OK 0.392ms rows=1 — Share of rows by UNITS as percentage.
- **M22** [medium] OK 0.2ms rows=3 — Top 3 STATUS values by row count.
- **M23** [medium] OK 0.159ms rows=1 — Sum Data_value where Series_title_3 = Current.
- **M24** [medium] OK 0.347ms rows=5 — Average Period by Series_title_2, top 5.
- **M25** [medium] OK 5.636ms rows=3 — Distinct Period count by STATUS.
- **H16** [hard] OK 0.96ms rows=15 — Industries with total Data_value above the overall median industry total.
- **H17** [hard] OK 0.657ms rows=11 — YoY percent change in total Data_value by year.
- **H18** [hard] OK 0.953ms rows=5 — Top 5 industries contributing more than 5% of total Data_value.
- **H19** [hard] OK 1.354ms rows=11 — For each year, the industry with highest sum Data_value (window rank).
- **H20** [hard] OK 0.889ms rows=0 — Industries where average Data_value is below overall average but total is in top 10.
- **H21** [hard] OK 0.626ms rows=2 — STATUS values whose share of total Data_value exceeds 20%.
- **H22** [hard] OK 0.937ms rows=11 — Running total of yearly Data_value ordered by year.
- **H23** [hard] OK 1.013ms rows=6 — Top 3 Series_title_1 within each STATUS by sum Data_value.
- **H24** [hard] OK 0.699ms rows=4 — Coefficient of variation of Data_value by Series_title_1 (top 5 by CV).
- **H25** [hard] OK 0.525ms rows=5 — Years where total Data_value decreased versus previous year.
- **H26** [hard] OK 0.647ms rows=10 — Industries with at least 20 rows and average Data_value above overall average.
- **H27** [hard] OK 0.698ms rows=1 — Percentage of total Data_value for top 3 industries combined.
- **H28** [hard] OK 0.568ms rows=1 — Duplicate Series_reference + Period + Series_title_1 combinations count.
- **H29** [hard] OK 0.392ms rows=11 — Median Data_value by year.
- **H30** [hard] OK 0.714ms rows=31 — Industries ranked by share of total with cumulative share (pareto).
- **V16** [very_hard] OK 0.924ms rows=5 — Top 5 industries by revenue share among those with >=10 rows; keep only share>3%; compare avg to overall avg.
- **V17** [very_hard] OK 1.648ms rows=24 — Find industries whose yearly total increased YoY while row count decreased YoY (latest year vs prior).
- **V18** [very_hard] OK 0.864ms rows=2 — Per STATUS, top industry by revenue and its contribution percent to that STATUS total.
- **V19** [very_hard] OK 0.947ms rows=0 — Industries above overall average Data_value but below overall average Magnitude, with n>=5.
- **V20** [very_hard] OK 0.886ms rows=10 — Nested: average of per-STATUS industry totals, then industries whose average STATUS-total exceeds overall average of those.
- **V21** [very_hard] OK 1.102ms rows=33 — Top 3 industries per year by share of that year's total Data_value.
- **V22** [very_hard] OK 0.786ms rows=0 — Regions-like Series_title_2 contributing >15% of total while having fewer rows than overall average rows-per-industry.
- **V23** [very_hard] OK 0.558ms rows=4 — Among Series_title_1 with at least 50 rows, top 5 by average order-like Data_value vs overall average.
- **V24** [very_hard] OK 1.192ms rows=10 — Multi-condition: top 10 industries last 3 period-years, n>=5, share>2%, avg above overall avg.
- **V25** [very_hard] OK 0.708ms rows=10 — Paraphrase: highest revenue suppliers-like industries excluding those with fewer than 8 observations, showing each share of total.
