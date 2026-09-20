"""
Deterministic SQL benchmark for ~3k-row business financial CSV.

Ground truth is computed by executing expected_sql against DuckDB — not fabricated.
LLM end-to-end accuracy is measured separately when providers are available.
"""
from __future__ import annotations

from typing import Any, Dict, List

TABLE = "{table}"

# difficulty: easy | medium | hard | very_hard
BENCHMARK_QUESTIONS: List[Dict[str, Any]] = [
    # --- 10 easy ---
    {
        "id": "E01",
        "difficulty": "easy",
        "question": "How many rows are in the dataset?",
        "expected_sql": f"SELECT COUNT(*) AS row_count FROM {TABLE}",
    },
    {
        "id": "E02",
        "difficulty": "easy",
        "question": "What is the sum of Data_value?",
        "expected_sql": f'SELECT SUM("Data_value") AS total_data_value FROM {TABLE}',
    },
    {
        "id": "E03",
        "difficulty": "easy",
        "question": "What is the average Data_value?",
        "expected_sql": f'SELECT AVG("Data_value") AS avg_data_value FROM {TABLE}',
    },
    {
        "id": "E04",
        "difficulty": "easy",
        "question": "How many distinct Series_title_2 values are there?",
        "expected_sql": f'SELECT COUNT(DISTINCT "Series_title_2") AS n FROM {TABLE}',
    },
    {
        "id": "E05",
        "difficulty": "easy",
        "question": "List distinct STATUS values.",
        "expected_sql": f'SELECT DISTINCT "STATUS" AS status FROM {TABLE} ORDER BY 1',
    },
    {
        "id": "E06",
        "difficulty": "easy",
        "question": "What is the minimum Period?",
        "expected_sql": f'SELECT MIN("Period") AS min_period FROM {TABLE}',
    },
    {
        "id": "E07",
        "difficulty": "easy",
        "question": "What is the maximum Period?",
        "expected_sql": f'SELECT MAX("Period") AS max_period FROM {TABLE}',
    },
    {
        "id": "E08",
        "difficulty": "easy",
        "question": "How many rows have null Suppressed?",
        "expected_sql": f'SELECT COUNT(*) AS null_suppressed FROM {TABLE} WHERE "Suppressed" IS NULL',
    },
    {
        "id": "E09",
        "difficulty": "easy",
        "question": "Count rows where UNITS is Dollars.",
        "expected_sql": f"SELECT COUNT(*) AS n FROM {TABLE} WHERE \"UNITS\" = 'Dollars'",
    },
    {
        "id": "E10",
        "difficulty": "easy",
        "question": "What is the maximum Data_value?",
        "expected_sql": f'SELECT MAX("Data_value") AS max_val FROM {TABLE}',
    },
    # --- 10 medium ---
    {
        "id": "M01",
        "difficulty": "medium",
        "question": "Top 5 Series_title_2 by sum of Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY total DESC
            LIMIT 5
        ''',
    },
    {
        "id": "M02",
        "difficulty": "medium",
        "question": "Average Data_value by Series_title_1, top 5.",
        "expected_sql": f'''
            SELECT "Series_title_1" AS metric, AVG("Data_value") AS avg_val
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY avg_val DESC
            LIMIT 5
        ''',
    },
    {
        "id": "M03",
        "difficulty": "medium",
        "question": "Row counts by STATUS.",
        "expected_sql": f'''
            SELECT "STATUS" AS status, COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
        ''',
    },
    {
        "id": "M04",
        "difficulty": "medium",
        "question": "Total Data_value for Sales (operating income).",
        "expected_sql": f'''
            SELECT SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Series_title_1" = 'Sales (operating income)'
              AND "Data_value" IS NOT NULL
        ''',
    },
    {
        "id": "M05",
        "difficulty": "medium",
        "question": "Count of distinct Period values per Series_title_3.",
        "expected_sql": f'''
            SELECT "Series_title_3" AS adj, COUNT(DISTINCT "Period") AS n_periods
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n_periods DESC
        ''',
    },
    {
        "id": "M06",
        "difficulty": "medium",
        "question": "Bottom 5 industries by total Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY total ASC
            LIMIT 5
        ''',
    },
    {
        "id": "M07",
        "difficulty": "medium",
        "question": "Average Magnitude by Group.",
        "expected_sql": f'''
            SELECT "Group" AS grp, AVG("Magnitude") AS avg_mag
            FROM {TABLE}
            GROUP BY 1
            ORDER BY avg_mag DESC
        ''',
    },
    {
        "id": "M08",
        "difficulty": "medium",
        "question": "How many rows per Series_title_4?",
        "expected_sql": f'''
            SELECT "Series_title_4" AS series4, COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
        ''',
    },
    {
        "id": "M09",
        "difficulty": "medium",
        "question": "Sum Data_value where Period >= 2019.",
        "expected_sql": f'''
            SELECT SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Period" >= 2019 AND "Data_value" IS NOT NULL
        ''',
    },
    {
        "id": "M10",
        "difficulty": "medium",
        "question": "Top 3 Series_title_1 by row count.",
        "expected_sql": f'''
            SELECT "Series_title_1" AS metric, COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 3
        ''',
    },
    # --- 15 hard ---
    {
        "id": "H01",
        "difficulty": "hard",
        "question": "For Sales (operating income), top 10 industries by total Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Series_title_1" = 'Sales (operating income)'
              AND "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY total DESC
            LIMIT 10
        ''',
    },
    {
        "id": "H02",
        "difficulty": "hard",
        "question": "Yearly total Data_value using floor(Period) as year.",
        "expected_sql": f'''
            SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY yr
        ''',
    },
    {
        "id": "H03",
        "difficulty": "hard",
        "question": "Industries with average Data_value above the overall average.",
        "expected_sql": f'''
            WITH overall AS (
              SELECT AVG("Data_value") AS overall_avg FROM {TABLE} WHERE "Data_value" IS NOT NULL
            )
            SELECT s."Series_title_2" AS industry, AVG(s."Data_value") AS industry_avg, o.overall_avg
            FROM {TABLE} s CROSS JOIN overall o
            WHERE s."Data_value" IS NOT NULL
            GROUP BY 1, o.overall_avg
            HAVING AVG(s."Data_value") > o.overall_avg
            ORDER BY industry_avg DESC
        ''',
    },
    {
        "id": "H04",
        "difficulty": "hard",
        "question": "Percentage of rows by STATUS.",
        "expected_sql": f'''
            SELECT "STATUS" AS status,
                   COUNT(*) AS n,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
        ''',
    },
    {
        "id": "H05",
        "difficulty": "hard",
        "question": "Top industry per year by sum of Data_value.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr,
                     "Series_title_2" AS industry,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            )
            SELECT yr, industry, total
            FROM agg
            QUALIFY RANK() OVER (PARTITION BY yr ORDER BY total DESC) = 1
            ORDER BY yr
        ''',
    },
    {
        "id": "H06",
        "difficulty": "hard",
        "question": "Share of total Data_value for top 5 industries.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            top5 AS (
              SELECT * FROM agg ORDER BY total DESC LIMIT 5
            ),
            grand AS (SELECT SUM(total) AS grand_total FROM agg)
            SELECT t.industry, t.total,
                   ROUND(100.0 * t.total / NULLIF(g.grand_total, 0), 2) AS share_pct
            FROM top5 t CROSS JOIN grand g
            ORDER BY t.total DESC
        ''',
    },
    {
        "id": "H07",
        "difficulty": "hard",
        "question": "Median Data_value by Series_title_3.",
        "expected_sql": f'''
            SELECT "Series_title_3" AS adj, MEDIAN("Data_value") AS median_val
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY median_val DESC
        ''',
    },
    {
        "id": "H08",
        "difficulty": "hard",
        "question": "Count industries with total Data_value over 1 million.",
        "expected_sql": f'''
            SELECT COUNT(*) AS n FROM (
              SELECT "Series_title_2"
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
              HAVING SUM("Data_value") > 1000000
            ) t
        ''',
    },
    {
        "id": "H09",
        "difficulty": "hard",
        "question": "YoY change in total Data_value by year.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total,
                   total - LAG(total) OVER (ORDER BY yr) AS yoy_change
            FROM yearly
            ORDER BY yr
        ''',
    },
    {
        "id": "H10",
        "difficulty": "hard",
        "question": "Top 5 industries for Operating profit by total Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Series_title_1" = 'Operating profit'
              AND "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY total DESC
            LIMIT 5
        ''',
    },
    {
        "id": "H11",
        "difficulty": "hard",
        "question": "Coefficient of variation of Data_value by industry (top 10 by CV).",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry,
                   STDDEV_SAMP("Data_value") / NULLIF(AVG("Data_value"), 0) AS cv,
                   COUNT(*) AS n
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            HAVING COUNT(*) >= 5
            ORDER BY cv DESC NULLS LAST
            LIMIT 10
        ''',
    },
    {
        "id": "H12",
        "difficulty": "hard",
        "question": "Duplicate Series_reference + Period combinations count.",
        "expected_sql": f'''
            SELECT COUNT(*) AS duplicate_groups FROM (
              SELECT "Series_reference", "Period", COUNT(*) AS n
              FROM {TABLE}
              GROUP BY 1, 2
              HAVING COUNT(*) > 1
            ) d
        ''',
    },
    {
        "id": "H13",
        "difficulty": "hard",
        "question": "Average Data_value for Current vs other Series_title_3.",
        "expected_sql": f'''
            SELECT CASE WHEN "Series_title_3" = 'Current' THEN 'Current' ELSE 'Other' END AS bucket,
                   AVG("Data_value") AS avg_val,
                   COUNT(*) AS n
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        ''',
    },
    {
        "id": "H14",
        "difficulty": "hard",
        "question": "Rank industries by total Data_value and keep ranks 1-10.",
        "expected_sql": f'''
            SELECT industry, total, rnk FROM (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS total,
                     RANK() OVER (ORDER BY SUM("Data_value") DESC) AS rnk
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ) t
            WHERE rnk <= 10
            ORDER BY rnk
        ''',
    },
    {
        "id": "H15",
        "difficulty": "hard",
        "question": "Null Data_value rate by Series_title_1.",
        "expected_sql": f'''
            SELECT "Series_title_1" AS metric,
                   COUNT(*) AS n,
                   SUM(CASE WHEN "Data_value" IS NULL THEN 1 ELSE 0 END) AS nulls,
                   ROUND(100.0 * SUM(CASE WHEN "Data_value" IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_pct
            FROM {TABLE}
            GROUP BY 1
            ORDER BY null_pct DESC
        ''',
    },
    # --- 15 very hard ---
    {
        "id": "V01",
        "difficulty": "very_hard",
        "question": "Top 10 industries by Sales revenue share of total sales, keep share > 2%.",
        "expected_sql": f'''
            WITH sales AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS revenue
              FROM {TABLE}
              WHERE "Series_title_1" = 'Sales (operating income)'
                AND "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            ranked AS (
              SELECT industry, revenue,
                     SUM(revenue) OVER () AS total_rev,
                     RANK() OVER (ORDER BY revenue DESC) AS rnk,
                     ROUND(100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0), 2) AS share_pct
              FROM sales
            )
            SELECT industry, revenue, share_pct, rnk
            FROM ranked
            WHERE rnk <= 10 AND share_pct > 2
            ORDER BY revenue DESC
        ''',
    },
    {
        "id": "V02",
        "difficulty": "very_hard",
        "question": "Per year top 5 industries by Data_value with year share percent.",
        "expected_sql": f'''
            WITH base AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr,
                     "Series_title_2" AS industry,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            ranked AS (
              SELECT *, SUM(total) OVER (PARTITION BY yr) AS year_total,
                     RANK() OVER (PARTITION BY yr ORDER BY total DESC) AS rnk
              FROM base
            )
            SELECT yr, industry, total,
                   ROUND(100.0 * total / NULLIF(year_total, 0), 2) AS year_share_pct
            FROM ranked
            WHERE rnk <= 5
            ORDER BY yr, total DESC
        ''',
    },
    {
        "id": "V03",
        "difficulty": "very_hard",
        "question": "Industries with >= 20 rows whose avg Data_value exceeds overall avg, ranked by avg.",
        "expected_sql": f'''
            WITH overall AS (
              SELECT AVG("Data_value") AS overall_avg FROM {TABLE} WHERE "Data_value" IS NOT NULL
            )
            SELECT s."Series_title_2" AS industry,
                   COUNT(*) AS n,
                   AVG(s."Data_value") AS industry_avg,
                   o.overall_avg,
                   AVG(s."Data_value") - o.overall_avg AS vs_overall
            FROM {TABLE} s CROSS JOIN overall o
            WHERE s."Data_value" IS NOT NULL
            GROUP BY 1, o.overall_avg
            HAVING COUNT(*) >= 20 AND AVG(s."Data_value") > o.overall_avg
            ORDER BY industry_avg DESC
        ''',
    },
    {
        "id": "V04",
        "difficulty": "very_hard",
        "question": "For each Series_title_1, top industry by total and its contribution percent within that metric.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_1" AS metric,
                     "Series_title_2" AS industry,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            ranked AS (
              SELECT *, SUM(total) OVER (PARTITION BY metric) AS metric_total,
                     RANK() OVER (PARTITION BY metric ORDER BY total DESC) AS rnk
              FROM agg
            )
            SELECT metric, industry, total,
                   ROUND(100.0 * total / NULLIF(metric_total, 0), 2) AS contrib_pct
            FROM ranked
            WHERE rnk = 1
            ORDER BY total DESC
        ''',
    },
    {
        "id": "V05",
        "difficulty": "very_hard",
        "question": "Last six distinct Period values: top 10 industries by sum, exclude industries with fewer than 3 rows in window.",
        "expected_sql": f'''
            WITH periods AS (
              SELECT DISTINCT "Period" AS p FROM {TABLE} ORDER BY p DESC LIMIT 6
            ),
            windowed AS (
              SELECT t.*
              FROM {TABLE} t
              JOIN periods p ON t."Period" = p.p
              WHERE t."Data_value" IS NOT NULL
            ),
            agg AS (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS revenue,
                     COUNT(*) AS n
              FROM windowed
              GROUP BY 1
              HAVING COUNT(*) >= 3
            )
            SELECT industry, revenue, n
            FROM agg
            ORDER BY revenue DESC
            LIMIT 10
        ''',
    },
    {
        "id": "V06",
        "difficulty": "very_hard",
        "question": "Compare each industry average order-like Data_value to overall average; show only those > overall and share of total > 1%.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     AVG("Data_value") AS avg_val,
                     SUM("Data_value") AS revenue,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            stats AS (
              SELECT AVG("Data_value") AS overall_avg,
                     SUM("Data_value") AS grand_total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
            )
            SELECT a.industry, a.avg_val, a.revenue, a.n, s.overall_avg,
                   ROUND(100.0 * a.revenue / NULLIF(s.grand_total, 0), 2) AS share_pct
            FROM agg a CROSS JOIN stats s
            WHERE a.avg_val > s.overall_avg
              AND 100.0 * a.revenue / NULLIF(s.grand_total, 0) > 1
            ORDER BY a.revenue DESC
        ''',
    },
    {
        "id": "V07",
        "difficulty": "very_hard",
        "question": "Rolling year totals: for each year, sum of that year and previous year Data_value totals.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total,
                   total + COALESCE(LAG(total) OVER (ORDER BY yr), 0) AS rolling_2y
            FROM yearly
            ORDER BY yr
        ''',
    },
    {
        "id": "V08",
        "difficulty": "very_hard",
        "question": "Within Construction industry, yearly share of that industry total across years.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Series_title_2" = 'Construction' AND "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total,
                   ROUND(100.0 * total / NULLIF(SUM(total) OVER (), 0), 2) AS share_of_industry_pct
            FROM yearly
            ORDER BY yr
        ''',
    },
    {
        "id": "V09",
        "difficulty": "very_hard",
        "question": "Top-N within Group: for each Group, top 3 Series_title_2 by sum Data_value.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Group" AS grp, "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            )
            SELECT grp, industry, total
            FROM agg
            QUALIFY RANK() OVER (PARTITION BY grp ORDER BY total DESC) <= 3
            ORDER BY grp, total DESC
        ''',
    },
    {
        "id": "V10",
        "difficulty": "very_hard",
        "question": "Sales vs Operating profit totals by industry for industries present in both; ratio sales/profit.",
        "expected_sql": f'''
            WITH sales AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS sales
              FROM {TABLE}
              WHERE "Series_title_1" = 'Sales (operating income)' AND "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            profit AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS profit
              FROM {TABLE}
              WHERE "Series_title_1" = 'Operating profit' AND "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT s.industry, s.sales, p.profit,
                   ROUND(s.sales / NULLIF(p.profit, 0), 4) AS sales_to_profit
            FROM sales s
            JOIN profit p USING (industry)
            ORDER BY s.sales DESC
            LIMIT 20
        ''',
    },
    {
        "id": "V11",
        "difficulty": "very_hard",
        "question": "Exclude Magnitude != 6; among remaining, top 10 industries by sum with cumulative share.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Magnitude" = 6 AND "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            ranked AS (
              SELECT industry, total,
                     RANK() OVER (ORDER BY total DESC) AS rnk,
                     SUM(total) OVER (ORDER BY total DESC ROWS UNBOUNDED PRECEDING) AS cum_total,
                     SUM(total) OVER () AS grand
              FROM agg
            )
            SELECT industry, total, rnk,
                   ROUND(100.0 * cum_total / NULLIF(grand, 0), 2) AS cum_share_pct
            FROM ranked
            WHERE rnk <= 10
            ORDER BY rnk
        ''',
    },
    {
        "id": "V12",
        "difficulty": "very_hard",
        "question": "Multi-condition: Period between 2018 and 2021, UNITS=Dollars, STATUS=F; top 8 industries by avg Data_value with n>=5.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry,
                   AVG("Data_value") AS avg_val,
                   COUNT(*) AS n
            FROM {TABLE}
            WHERE "Period" BETWEEN 2018 AND 2021
              AND "UNITS" = 'Dollars'
              AND "STATUS" = 'F'
              AND "Data_value" IS NOT NULL
            GROUP BY 1
            HAVING COUNT(*) >= 5
            ORDER BY avg_val DESC
            LIMIT 8
        ''',
    },
    {
        "id": "V13",
        "difficulty": "very_hard",
        "question": "Percentile: industries whose total is above the 90th percentile of industry totals.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            thr AS (
              SELECT QUANTILE_CONT(total, 0.9) AS p90 FROM agg
            )
            SELECT a.industry, a.total, t.p90
            FROM agg a CROSS JOIN thr t
            WHERE a.total > t.p90
            ORDER BY a.total DESC
        ''',
    },
    {
        "id": "V14",
        "difficulty": "very_hard",
        "question": "Nested aggregation: average of yearly totals per industry, then top 10 industries by that average yearly total.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT "Series_title_2" AS industry,
                     CAST(FLOOR("Period") AS INTEGER) AS yr,
                     SUM("Data_value") AS year_total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            )
            SELECT industry, AVG(year_total) AS avg_yearly_total, COUNT(*) AS years_observed
            FROM yearly
            GROUP BY 1
            ORDER BY avg_yearly_total DESC
            LIMIT 10
        ''',
    },
    {
        "id": "V15",
        "difficulty": "very_hard",
        "question": "Find top 10 suppliers-like industries by revenue in recent periods, exclude n<5, compute share of total, compare avg to overall avg, keep share>2%.",
        "expected_sql": f'''
            WITH recent AS (
              SELECT * FROM {TABLE}
              WHERE "Period" >= (SELECT MAX("Period") - 2 FROM {TABLE})
                AND "Data_value" IS NOT NULL
            ),
            agg AS (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS revenue,
                     AVG("Data_value") AS avg_val,
                     COUNT(*) AS n
              FROM recent
              GROUP BY 1
              HAVING COUNT(*) >= 5
            ),
            stats AS (
              SELECT SUM(revenue) AS grand, AVG(avg_val) AS overall_avg_of_avgs FROM agg
            ),
            overall AS (
              SELECT AVG("Data_value") AS overall_avg FROM recent
            )
            SELECT a.industry, a.revenue, a.avg_val, a.n,
                   ROUND(100.0 * a.revenue / NULLIF(s.grand, 0), 2) AS share_pct,
                   o.overall_avg,
                   a.avg_val - o.overall_avg AS avg_vs_overall
            FROM agg a CROSS JOIN stats s CROSS JOIN overall o
            WHERE 100.0 * a.revenue / NULLIF(s.grand, 0) > 2
            ORDER BY a.revenue DESC
            LIMIT 10
        ''',
    },
]


assert len(BENCHMARK_QUESTIONS) == 50
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "easy") == 10
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "medium") == 10
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "hard") == 15
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "very_hard") == 15
