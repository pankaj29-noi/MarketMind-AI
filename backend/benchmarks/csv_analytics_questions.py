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
    # --- +10 easy (E11–E20) ---
    {
        "id": "E11",
        "difficulty": "easy",
        "question": "What is the median Data_value?",
        "expected_sql": f'SELECT MEDIAN("Data_value") AS median_data_value FROM {TABLE}',
    },
    {
        "id": "E12",
        "difficulty": "easy",
        "question": "How many distinct Series_title_1 values are there?",
        "expected_sql": f'SELECT COUNT(DISTINCT "Series_title_1") AS n FROM {TABLE}',
    },
    {
        "id": "E13",
        "difficulty": "easy",
        "question": "List distinct UNITS values.",
        "expected_sql": f'SELECT DISTINCT "UNITS" AS units FROM {TABLE} ORDER BY 1',
    },
    {
        "id": "E14",
        "difficulty": "easy",
        "question": "Count rows where Data_value is not null.",
        "expected_sql": f'SELECT COUNT(*) AS n FROM {TABLE} WHERE "Data_value" IS NOT NULL',
    },
    {
        "id": "E15",
        "difficulty": "easy",
        "question": "What is the sum of Magnitude?",
        "expected_sql": f'SELECT SUM("Magnitude") AS total_magnitude FROM {TABLE}',
    },
    {
        "id": "E16",
        "difficulty": "easy",
        "question": "How many distinct Series_reference values?",
        "expected_sql": f'SELECT COUNT(DISTINCT "Series_reference") AS n FROM {TABLE}',
    },
    {
        "id": "E17",
        "difficulty": "easy",
        "question": "Minimum Data_value in the dataset.",
        "expected_sql": f'SELECT MIN("Data_value") AS min_data_value FROM {TABLE}',
    },
    {
        "id": "E18",
        "difficulty": "easy",
        "question": "Count rows where STATUS is F.",
        "expected_sql": f'''SELECT COUNT(*) AS n FROM {TABLE} WHERE "STATUS" = 'F' ''',
    },
    {
        "id": "E19",
        "difficulty": "easy",
        "question": "Average Magnitude across all rows.",
        "expected_sql": f'SELECT AVG("Magnitude") AS avg_magnitude FROM {TABLE}',
    },
    {
        "id": "E20",
        "difficulty": "easy",
        "question": "How many distinct Group values?",
        "expected_sql": f'SELECT COUNT(DISTINCT "Group") AS n FROM {TABLE}',
    },
    # --- +15 medium (M11–M25) ---
    {
        "id": "M11",
        "difficulty": "medium",
        "question": "Top 10 Series_title_2 by average Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, AVG("Data_value") AS avg_val
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY avg_val DESC
            LIMIT 10
        ''',
    },
    {
        "id": "M12",
        "difficulty": "medium",
        "question": "Row counts by Series_title_3.",
        "expected_sql": f'''
            SELECT "Series_title_3" AS t3, COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
        ''',
    },
    {
        "id": "M13",
        "difficulty": "medium",
        "question": "Sum Data_value by STATUS.",
        "expected_sql": f'''
            SELECT "STATUS", SUM("Data_value") AS total
            FROM {TABLE}
            GROUP BY 1
            ORDER BY total DESC
        ''',
    },
    {
        "id": "M14",
        "difficulty": "medium",
        "question": "Top 5 Series_title_1 by sum of Data_value.",
        "expected_sql": f'''
            SELECT "Series_title_1" AS title, SUM("Data_value") AS total
            FROM {TABLE}
            GROUP BY 1
            ORDER BY total DESC
            LIMIT 5
        ''',
    },
    {
        "id": "M15",
        "difficulty": "medium",
        "question": "Average Data_value for Period >= 2020.",
        "expected_sql": f'SELECT AVG("Data_value") AS avg_val FROM {TABLE} WHERE "Period" >= 2020',
    },
    {
        "id": "M16",
        "difficulty": "medium",
        "question": "Count distinct Series_title_2 per STATUS.",
        "expected_sql": f'''
            SELECT "STATUS", COUNT(DISTINCT "Series_title_2") AS n_industries
            FROM {TABLE}
            GROUP BY 1
            ORDER BY 1
        ''',
    },
    {
        "id": "M17",
        "difficulty": "medium",
        "question": "Bottom 5 Series_title_2 by sum of Data_value (non-null).",
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
        "id": "M18",
        "difficulty": "medium",
        "question": "Total Data_value by Series_title_4.",
        "expected_sql": f'''
            SELECT "Series_title_4" AS t4, SUM("Data_value") AS total
            FROM {TABLE}
            GROUP BY 1
            ORDER BY total DESC
        ''',
    },
    {
        "id": "M19",
        "difficulty": "medium",
        "question": "How many rows per Magnitude value?",
        "expected_sql": f'''
            SELECT "Magnitude", COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY "Magnitude"
        ''',
    },
    {
        "id": "M20",
        "difficulty": "medium",
        "question": "Max Data_value by Series_title_1.",
        "expected_sql": f'''
            SELECT "Series_title_1" AS title, MAX("Data_value") AS max_val
            FROM {TABLE}
            GROUP BY 1
            ORDER BY max_val DESC
        ''',
    },
    {
        "id": "M21",
        "difficulty": "medium",
        "question": "Share of rows by UNITS as percentage.",
        "expected_sql": f'''
            SELECT "UNITS",
                   COUNT(*) AS n,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
        ''',
    },
    {
        "id": "M22",
        "difficulty": "medium",
        "question": "Top 3 STATUS values by row count.",
        "expected_sql": f'''
            SELECT "STATUS", COUNT(*) AS n
            FROM {TABLE}
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 3
        ''',
    },
    {
        "id": "M23",
        "difficulty": "medium",
        "question": "Sum Data_value where Series_title_3 = Current.",
        "expected_sql": f'''
            SELECT SUM("Data_value") AS total
            FROM {TABLE}
            WHERE "Series_title_3" = 'Current'
        ''',
    },
    {
        "id": "M24",
        "difficulty": "medium",
        "question": "Average Period by Series_title_2, top 5.",
        "expected_sql": f'''
            SELECT "Series_title_2" AS industry, AVG("Period") AS avg_period
            FROM {TABLE}
            GROUP BY 1
            ORDER BY avg_period DESC
            LIMIT 5
        ''',
    },
    {
        "id": "M25",
        "difficulty": "medium",
        "question": "Distinct Period count by STATUS.",
        "expected_sql": f'''
            SELECT "STATUS", COUNT(DISTINCT "Period") AS n_periods
            FROM {TABLE}
            GROUP BY 1
            ORDER BY 1
        ''',
    },
    # --- +15 hard (H16–H30) ---
    {
        "id": "H16",
        "difficulty": "hard",
        "question": "Industries with total Data_value above the overall median industry total.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            med AS (SELECT MEDIAN(total) AS m FROM agg)
            SELECT a.industry, a.total, med.m AS median_total
            FROM agg a CROSS JOIN med
            WHERE a.total > med.m
            ORDER BY a.total DESC
        ''',
    },
    {
        "id": "H17",
        "difficulty": "hard",
        "question": "YoY percent change in total Data_value by year.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total,
                   LAG(total) OVER (ORDER BY yr) AS prev_total,
                   ROUND(100.0 * (total - LAG(total) OVER (ORDER BY yr))
                         / NULLIF(LAG(total) OVER (ORDER BY yr), 0), 2) AS yoy_pct
            FROM yearly
            ORDER BY yr
        ''',
    },
    {
        "id": "H18",
        "difficulty": "hard",
        "question": "Top 5 industries contributing more than 5% of total Data_value.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            grand AS (SELECT SUM(total) AS g FROM agg)
            SELECT a.industry, a.total,
                   ROUND(100.0 * a.total / NULLIF(g.g, 0), 2) AS share_pct
            FROM agg a CROSS JOIN grand g
            WHERE 100.0 * a.total / NULLIF(g.g, 0) > 5
            ORDER BY a.total DESC
            LIMIT 5
        ''',
    },
    {
        "id": "H19",
        "difficulty": "hard",
        "question": "For each year, the industry with highest sum Data_value (window rank).",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr,
                     "Series_title_2" AS industry,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            )
            SELECT yr, industry, total
            FROM yearly
            QUALIFY RANK() OVER (PARTITION BY yr ORDER BY total DESC) = 1
            ORDER BY yr
        ''',
    },
    {
        "id": "H20",
        "difficulty": "hard",
        "question": "Industries where average Data_value is below overall average but total is in top 10.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     AVG("Data_value") AS avg_val,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            overall AS (SELECT AVG("Data_value") AS oavg FROM {TABLE} WHERE "Data_value" IS NOT NULL),
            ranked AS (
              SELECT a.*, RANK() OVER (ORDER BY a.total DESC) AS rnk
              FROM agg a
            )
            SELECT r.industry, r.avg_val, r.total, o.oavg
            FROM ranked r CROSS JOIN overall o
            WHERE r.rnk <= 10 AND r.avg_val < o.oavg
            ORDER BY r.total DESC
        ''',
    },
    {
        "id": "H21",
        "difficulty": "hard",
        "question": "STATUS values whose share of total Data_value exceeds 20%.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "STATUS", SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            grand AS (SELECT SUM(total) AS g FROM agg)
            SELECT a.STATUS, a.total,
                   ROUND(100.0 * a.total / NULLIF(g.g, 0), 2) AS share_pct
            FROM agg a CROSS JOIN grand g
            WHERE 100.0 * a.total / NULLIF(g.g, 0) > 20
            ORDER BY a.total DESC
        ''',
    },
    {
        "id": "H22",
        "difficulty": "hard",
        "question": "Running total of yearly Data_value ordered by year.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total,
                   SUM(total) OVER (ORDER BY yr ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
            FROM yearly
            ORDER BY yr
        ''',
    },
    {
        "id": "H23",
        "difficulty": "hard",
        "question": "Top 3 Series_title_1 within each STATUS by sum Data_value.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "STATUS", "Series_title_1" AS title, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            )
            SELECT STATUS, title, total
            FROM agg
            QUALIFY RANK() OVER (PARTITION BY STATUS ORDER BY total DESC) <= 3
            ORDER BY STATUS, total DESC
        ''',
    },
    {
        "id": "H24",
        "difficulty": "hard",
        "question": "Coefficient of variation of Data_value by Series_title_1 (top 5 by CV).",
        "expected_sql": f'''
            SELECT "Series_title_1" AS title,
                   STDDEV_SAMP("Data_value") / NULLIF(AVG("Data_value"), 0) AS cv
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            HAVING COUNT(*) >= 5
            ORDER BY cv DESC NULLS LAST
            LIMIT 5
        ''',
    },
    {
        "id": "H25",
        "difficulty": "hard",
        "question": "Years where total Data_value decreased versus previous year.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            )
            SELECT yr, total, LAG(total) OVER (ORDER BY yr) AS prev_total
            FROM yearly
            QUALIFY total < LAG(total) OVER (ORDER BY yr)
            ORDER BY yr
        ''',
    },
    {
        "id": "H26",
        "difficulty": "hard",
        "question": "Industries with at least 20 rows and average Data_value above overall average.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     COUNT(*) AS n,
                     AVG("Data_value") AS avg_val
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            overall AS (SELECT AVG("Data_value") AS oavg FROM {TABLE} WHERE "Data_value" IS NOT NULL)
            SELECT a.industry, a.n, a.avg_val, o.oavg
            FROM agg a CROSS JOIN overall o
            WHERE a.n >= 20 AND a.avg_val > o.oavg
            ORDER BY a.avg_val DESC
        ''',
    },
    {
        "id": "H27",
        "difficulty": "hard",
        "question": "Percentage of total Data_value for top 3 industries combined.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            top3 AS (
              SELECT SUM(total) AS top_total FROM (
                SELECT total FROM agg ORDER BY total DESC LIMIT 3
              )
            ),
            grand AS (SELECT SUM(total) AS g FROM agg)
            SELECT ROUND(100.0 * t.top_total / NULLIF(g.g, 0), 2) AS top3_share_pct
            FROM top3 t CROSS JOIN grand g
        ''',
    },
    {
        "id": "H28",
        "difficulty": "hard",
        "question": "Duplicate Series_reference + Period + Series_title_1 combinations count.",
        "expected_sql": f'''
            SELECT COUNT(*) AS duplicate_group_count FROM (
              SELECT "Series_reference", "Period", "Series_title_1", COUNT(*) AS c
              FROM {TABLE}
              GROUP BY 1, 2, 3
              HAVING COUNT(*) > 1
            )
        ''',
    },
    {
        "id": "H29",
        "difficulty": "hard",
        "question": "Median Data_value by year.",
        "expected_sql": f'''
            SELECT CAST(FLOOR("Period") AS INTEGER) AS yr, MEDIAN("Data_value") AS median_val
            FROM {TABLE}
            WHERE "Data_value" IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        ''',
    },
    {
        "id": "H30",
        "difficulty": "hard",
        "question": "Industries ranked by share of total with cumulative share (pareto).",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            ranked AS (
              SELECT industry, total,
                     total / SUM(total) OVER () AS share,
                     SUM(total) OVER (ORDER BY total DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                       / SUM(total) OVER () AS cum_share
              FROM agg
            )
            SELECT industry, total,
                   ROUND(100.0 * share, 2) AS share_pct,
                   ROUND(100.0 * cum_share, 2) AS cum_share_pct
            FROM ranked
            ORDER BY total DESC
        ''',
    },
    # --- +10 very_hard (V16–V25) ---
    {
        "id": "V16",
        "difficulty": "very_hard",
        "question": "Top 5 industries by revenue share among those with >=10 rows; keep only share>3%; compare avg to overall avg.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS revenue,
                     AVG("Data_value") AS avg_val,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
              HAVING COUNT(*) >= 10
            ),
            grand AS (SELECT SUM(revenue) AS g, AVG(avg_val) AS unused FROM agg),
            overall AS (SELECT AVG("Data_value") AS oavg FROM {TABLE} WHERE "Data_value" IS NOT NULL)
            SELECT a.industry, a.revenue, a.avg_val, a.n,
                   ROUND(100.0 * a.revenue / NULLIF(g.g, 0), 2) AS share_pct,
                   o.oavg,
                   a.avg_val - o.oavg AS vs_overall
            FROM agg a CROSS JOIN grand g CROSS JOIN overall o
            WHERE 100.0 * a.revenue / NULLIF(g.g, 0) > 3
            ORDER BY a.revenue DESC
            LIMIT 5
        ''',
    },
    {
        "id": "V17",
        "difficulty": "very_hard",
        "question": "Find industries whose yearly total increased YoY while row count decreased YoY (latest year vs prior).",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT "Series_title_2" AS industry,
                     CAST(FLOOR("Period") AS INTEGER) AS yr,
                     SUM("Data_value") AS total,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            paired AS (
              SELECT industry, yr, total, n,
                     LAG(total) OVER (PARTITION BY industry ORDER BY yr) AS prev_total,
                     LAG(n) OVER (PARTITION BY industry ORDER BY yr) AS prev_n
              FROM yearly
            )
            SELECT industry, yr, total, prev_total, n, prev_n
            FROM paired
            WHERE prev_total IS NOT NULL
              AND total > prev_total
              AND n < prev_n
            ORDER BY industry, yr
        ''',
    },
    {
        "id": "V18",
        "difficulty": "very_hard",
        "question": "Per STATUS, top industry by revenue and its contribution percent to that STATUS total.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "STATUS", "Series_title_2" AS industry, SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            ranked AS (
              SELECT *,
                     SUM(total) OVER (PARTITION BY STATUS) AS status_total,
                     RANK() OVER (PARTITION BY STATUS ORDER BY total DESC) AS rnk
              FROM agg
            )
            SELECT STATUS, industry, total, status_total,
                   ROUND(100.0 * total / NULLIF(status_total, 0), 2) AS contrib_pct
            FROM ranked
            WHERE rnk = 1
            ORDER BY STATUS
        ''',
    },
    {
        "id": "V19",
        "difficulty": "very_hard",
        "question": "Industries above overall average Data_value but below overall average Magnitude, with n>=5.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     AVG("Data_value") AS avg_val,
                     AVG("Magnitude") AS avg_mag,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            overall AS (
              SELECT AVG("Data_value") AS oavg, AVG("Magnitude") AS omag
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
            )
            SELECT a.industry, a.avg_val, a.avg_mag, a.n, o.oavg, o.omag
            FROM agg a CROSS JOIN overall o
            WHERE a.n >= 5 AND a.avg_val > o.oavg AND a.avg_mag < o.omag
            ORDER BY a.avg_val DESC
        ''',
    },
    {
        "id": "V20",
        "difficulty": "very_hard",
        "question": "Nested: average of per-STATUS industry totals, then industries whose average STATUS-total exceeds overall average of those.",
        "expected_sql": f'''
            WITH base AS (
              SELECT "STATUS", "Series_title_2" AS industry, SUM("Data_value") AS status_total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            ind AS (
              SELECT industry, AVG(status_total) AS avg_status_total
              FROM base
              GROUP BY 1
            ),
            overall AS (SELECT AVG(avg_status_total) AS o FROM ind)
            SELECT i.industry, i.avg_status_total, o.o AS overall_avg
            FROM ind i CROSS JOIN overall o
            WHERE i.avg_status_total > o.o
            ORDER BY i.avg_status_total DESC
        ''',
    },
    {
        "id": "V21",
        "difficulty": "very_hard",
        "question": "Top 3 industries per year by share of that year's total Data_value.",
        "expected_sql": f'''
            WITH yearly AS (
              SELECT CAST(FLOOR("Period") AS INTEGER) AS yr,
                     "Series_title_2" AS industry,
                     SUM("Data_value") AS total
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1, 2
            ),
            scored AS (
              SELECT yr, industry, total,
                     total / SUM(total) OVER (PARTITION BY yr) AS share,
                     RANK() OVER (PARTITION BY yr ORDER BY total DESC) AS rnk
              FROM yearly
            )
            SELECT yr, industry, total, ROUND(100.0 * share, 2) AS share_pct
            FROM scored
            WHERE rnk <= 3
            ORDER BY yr, rnk
        ''',
    },
    {
        "id": "V22",
        "difficulty": "very_hard",
        "question": "Regions-like Series_title_2 contributing >15% of total while having fewer rows than overall average rows-per-industry.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS revenue,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
            ),
            stats AS (
              SELECT SUM(revenue) AS grand, AVG(n) AS avg_n FROM agg
            )
            SELECT a.industry, a.revenue, a.n,
                   ROUND(100.0 * a.revenue / NULLIF(s.grand, 0), 2) AS share_pct,
                   s.avg_n
            FROM agg a CROSS JOIN stats s
            WHERE 100.0 * a.revenue / NULLIF(s.grand, 0) > 15
              AND a.n < s.avg_n
            ORDER BY a.revenue DESC
        ''',
    },
    {
        "id": "V23",
        "difficulty": "very_hard",
        "question": "Among Series_title_1 with at least 50 rows, top 5 by average order-like Data_value vs overall average.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_1" AS title,
                     COUNT(*) AS n,
                     AVG("Data_value") AS avg_val
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
              HAVING COUNT(*) >= 50
            ),
            overall AS (SELECT AVG("Data_value") AS oavg FROM {TABLE} WHERE "Data_value" IS NOT NULL)
            SELECT a.title, a.n, a.avg_val, o.oavg, a.avg_val - o.oavg AS delta
            FROM agg a CROSS JOIN overall o
            ORDER BY a.avg_val DESC
            LIMIT 5
        ''',
    },
    {
        "id": "V24",
        "difficulty": "very_hard",
        "question": "Multi-condition: top 10 industries last 3 period-years, n>=5, share>2%, avg above overall avg.",
        "expected_sql": f'''
            WITH recent AS (
              SELECT * FROM {TABLE}
              WHERE "Period" >= (SELECT MAX("Period") - 3 FROM {TABLE})
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
            grand AS (SELECT SUM(revenue) AS g FROM agg),
            overall AS (SELECT AVG("Data_value") AS oavg FROM recent)
            SELECT a.industry, a.revenue, a.avg_val, a.n,
                   ROUND(100.0 * a.revenue / NULLIF(g.g, 0), 2) AS share_pct,
                   o.oavg
            FROM agg a CROSS JOIN grand g CROSS JOIN overall o
            WHERE 100.0 * a.revenue / NULLIF(g.g, 0) > 2
              AND a.avg_val > o.oavg
            ORDER BY a.revenue DESC
            LIMIT 10
        ''',
    },
    {
        "id": "V25",
        "difficulty": "very_hard",
        "question": "Paraphrase: highest revenue suppliers-like industries excluding those with fewer than 8 observations, showing each share of total.",
        "expected_sql": f'''
            WITH agg AS (
              SELECT "Series_title_2" AS industry,
                     SUM("Data_value") AS revenue,
                     COUNT(*) AS n
              FROM {TABLE}
              WHERE "Data_value" IS NOT NULL
              GROUP BY 1
              HAVING COUNT(*) >= 8
            ),
            grand AS (SELECT SUM(revenue) AS g FROM agg)
            SELECT a.industry, a.revenue, a.n,
                   ROUND(100.0 * a.revenue / NULLIF(g.g, 0), 2) AS share_pct
            FROM agg a CROSS JOIN grand g
            ORDER BY a.revenue DESC
            LIMIT 10
        ''',
    },
]


assert len(BENCHMARK_QUESTIONS) == 100
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "easy") == 20
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "medium") == 25
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "hard") == 30
assert sum(1 for q in BENCHMARK_QUESTIONS if q["difficulty"] == "very_hard") == 25
