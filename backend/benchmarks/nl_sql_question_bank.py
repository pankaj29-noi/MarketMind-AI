"""150-question NL->SQL benchmark bank across five schemas.

Every entry carries ground-truth SQL written independently of the pipeline, so a
question is scored on the numbers it returns rather than on how the answer reads.

kind:
  sql         - must return a result matching expected_sql
  abstain     - dataset cannot answer it; the pipeline must decline
  ambiguous   - more than one valid reading; the pipeline must ask for clarification
  paraphrase  - same intent as another question; must agree with the same ground truth

difficulty distribution: 30 simple / 40 medium / 45 advanced / 35 expert
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

DATASET_FILES = {
    "marketplace_orders": "data/marketmind_demo_marketplace_4000.csv",
    "retail_sales": "data/benchmark/retail_sales.csv",
    "employees": "data/benchmark/employees.csv",
    "products": "data/benchmark/products.csv",
    "subscriptions": "data/benchmark/subscriptions.csv",
}


@dataclass(frozen=True)
class BenchQuestion:
    id: str
    dataset: str
    difficulty: str  # simple | medium | advanced | expert
    question: str
    kind: str = "sql"
    expected_sql: Optional[str] = None
    tags: tuple = ()


Q = BenchQuestion

# ── marketplace (30) ─────────────────────────────────────────────────────────
MARKETPLACE = [
    Q("mk01", "marketplace_orders", "simple", "What is the total revenue?", expected_sql="SELECT SUM(revenue) AS v FROM {t}", tags=("aggregation",)),
    Q("mk02", "marketplace_orders", "simple", "How many orders are there?", expected_sql="SELECT COUNT(*) AS v FROM {t}", tags=("count",)),
    Q("mk03", "marketplace_orders", "simple", "What is the average profit?", expected_sql="SELECT AVG(profit) AS v FROM {t}", tags=("aggregation",)),
    Q("mk04", "marketplace_orders", "simple", "What is the maximum revenue?", expected_sql="SELECT MAX(revenue) AS v FROM {t}", tags=("aggregation",)),
    Q("mk05", "marketplace_orders", "simple", "How many distinct suppliers are there?", expected_sql="SELECT COUNT(DISTINCT supplier_name) AS v FROM {t}", tags=("distinct",)),
    Q("mk06", "marketplace_orders", "medium", "What is the total revenue by customer region?", expected_sql="SELECT customer_region AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("mk07", "marketplace_orders", "medium", "Which customer region has the highest total revenue?", expected_sql="SELECT customer_region AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("ranking",)),
    Q("mk08", "marketplace_orders", "medium", "What are the top 5 suppliers by revenue?", expected_sql="SELECT supplier_name AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("top_n",)),
    Q("mk09", "marketplace_orders", "medium", "What is the average profit by product category?", expected_sql="SELECT product_category AS d, AVG(profit) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("mk10", "marketplace_orders", "medium", "What is the total revenue by sales channel?", expected_sql="SELECT sales_channel AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("mk11", "marketplace_orders", "medium", "How many orders were placed in each order status?", expected_sql="SELECT order_status AS d, COUNT(*) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by", "count")),
    Q("mk12", "marketplace_orders", "medium", "What is the total revenue for the North customer region?", expected_sql="SELECT SUM(revenue) AS v FROM {t} WHERE customer_region = 'North'", tags=("filter",)),
    Q("mk13", "marketplace_orders", "advanced", "What percentage of total revenue comes from the top 10 products?", expected_sql="WITH g AS (SELECT product_name d, SUM(revenue) s FROM {t} WHERE revenue IS NOT NULL GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=10 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total", "top_n")),
    Q("mk14", "marketplace_orders", "advanced", "What share of total profit comes from the top 5 suppliers?", expected_sql="WITH g AS (SELECT supplier_name d, SUM(profit) s FROM {t} WHERE profit IS NOT NULL GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=5 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total",)),
    Q("mk15", "marketplace_orders", "advanced", "Which customer regions have above-average revenue?", expected_sql="WITH g AS (SELECT customer_region d, SUM(revenue) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s > (SELECT AVG(s) FROM g) ORDER BY 2 DESC", tags=("above_average",)),
    Q("mk16", "marketplace_orders", "advanced", "Which product categories have below-average profit?", expected_sql="WITH g AS (SELECT product_category d, SUM(profit) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s < (SELECT AVG(s) FROM g) ORDER BY 2 ASC", tags=("below_average",)),
    Q("mk17", "marketplace_orders", "advanced", "What is the monthly revenue trend?", expected_sql="SELECT strftime(CAST(order_date AS DATE), '%Y-%m') AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("mk18", "marketplace_orders", "advanced", "What is the total revenue by year?", expected_sql="SELECT CAST(strftime(CAST(order_date AS DATE), '%Y') AS INTEGER) AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("mk19", "marketplace_orders", "advanced", "Which suppliers have at least 40 orders?", expected_sql="SELECT supplier_name AS d, COUNT(*) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 40 ORDER BY 2 DESC", tags=("having", "min_sample")),
    Q("mk20", "marketplace_orders", "advanced", "What is the profit margin by product category?", expected_sql="SELECT product_category AS d, ROUND(100.0*SUM(profit)/NULLIF(SUM(revenue),0),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio",)),
    Q("mk21", "marketplace_orders", "expert", "What are the top 3 suppliers by revenue within each customer region?", expected_sql="WITH g AS (SELECT customer_region r, supplier_name s, SUM(revenue) v FROM {t} GROUP BY 1,2), k AS (SELECT r, s, v, ROW_NUMBER() OVER (PARTITION BY r ORDER BY v DESC) rn FROM g) SELECT r, s, v FROM k WHERE rn <= 3 ORDER BY r, v DESC", tags=("top_n_per_group", "window")),
    Q("mk22", "marketplace_orders", "expert", "Which customer regions have above-average revenue but below-average profit?", expected_sql="WITH g AS (SELECT customer_region d, SUM(revenue) rev, SUM(profit) pr FROM {t} GROUP BY 1) SELECT d, rev, pr FROM g WHERE rev > (SELECT AVG(rev) FROM g) AND pr < (SELECT AVG(pr) FROM g) ORDER BY 2 DESC", tags=("multi_condition",)),
    Q("mk23", "marketplace_orders", "expert", "Which suppliers with at least 30 orders have the highest profit margin?", expected_sql="SELECT supplier_name AS d, ROUND(100.0*SUM(profit)/NULLIF(SUM(revenue),0),2) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 30 ORDER BY 2 DESC LIMIT 10", tags=("having", "ratio")),
    Q("mk24", "marketplace_orders", "expert", "What is each customer region's share of total revenue?", expected_sql="SELECT customer_region AS d, ROUND(100.0*SUM(revenue)/(SELECT SUM(revenue) FROM {t}),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("contribution",)),
    Q("mk25", "marketplace_orders", "expert", "Compare total revenue between 2023 and 2024 by customer region", expected_sql="SELECT customer_region AS d, SUM(CASE WHEN strftime(CAST(order_date AS DATE),'%Y')='2023' THEN revenue ELSE 0 END) AS y2023, SUM(CASE WHEN strftime(CAST(order_date AS DATE),'%Y')='2024' THEN revenue ELSE 0 END) AS y2024 FROM {t} GROUP BY 1 ORDER BY 1", tags=("yoy", "conditional_aggregation")),
    Q("mk26", "marketplace_orders", "medium", "Which vendors generated the most sales?", kind="paraphrase", expected_sql="SELECT supplier_name AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("paraphrase", "top_n")),
    Q("mk27", "marketplace_orders", "medium", "Who are the biggest sellers by revenue?", kind="paraphrase", expected_sql="SELECT supplier_name AS d, SUM(revenue) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("paraphrase",)),
    Q("mk28", "marketplace_orders", "simple", "Which supplier has the highest employee satisfaction?", kind="abstain", tags=("abstention",)),
    Q("mk29", "marketplace_orders", "simple", "What is the average customer credit score?", kind="abstain", tags=("abstention",)),
    Q("mk30", "marketplace_orders", "simple", "Show me sales", kind="ambiguous", tags=("ambiguity",)),
]

# ── retail_sales (30) ────────────────────────────────────────────────────────
RETAIL = [
    Q("rt01", "retail_sales", "simple", "What is the total net_sales?", expected_sql="SELECT SUM(net_sales) AS v FROM {t}", tags=("aggregation",)),
    Q("rt02", "retail_sales", "simple", "How many transactions are there?", expected_sql="SELECT COUNT(*) AS v FROM {t}", tags=("count",)),
    Q("rt03", "retail_sales", "simple", "What is the average units per transaction?", expected_sql="SELECT AVG(units) AS v FROM {t}", tags=("aggregation",)),
    Q("rt04", "retail_sales", "simple", "How many distinct stores are there?", expected_sql="SELECT COUNT(DISTINCT store) AS v FROM {t}", tags=("distinct",)),
    Q("rt05", "retail_sales", "simple", "What is the minimum unit_cost?", expected_sql="SELECT MIN(unit_cost) AS v FROM {t}", tags=("aggregation",)),
    Q("rt06", "retail_sales", "simple", "What is the total cogs?", expected_sql="SELECT SUM(cogs) AS v FROM {t}", tags=("aggregation",)),
    Q("rt07", "retail_sales", "medium", "What is the total net_sales by category?", expected_sql="SELECT category AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("rt08", "retail_sales", "medium", "Which store_region has the highest total net_sales?", expected_sql="SELECT store_region AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("ranking",)),
    Q("rt09", "retail_sales", "medium", "What are the top 5 stores by net_sales?", expected_sql="SELECT store AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("top_n",)),
    Q("rt10", "retail_sales", "medium", "What is the total net_sales by channel?", expected_sql="SELECT channel AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("rt11", "retail_sales", "medium", "What is the total net_sales for the Online channel?", expected_sql="SELECT SUM(net_sales) AS v FROM {t} WHERE channel = 'Online'", tags=("filter",)),
    Q("rt12", "retail_sales", "medium", "How many transactions were returned?", expected_sql="SELECT COUNT(*) AS v FROM {t} WHERE returned = 'yes'", tags=("filter", "count")),
    Q("rt13", "retail_sales", "medium", "What is the average net_sales for loyalty members?", expected_sql="SELECT AVG(net_sales) AS v FROM {t} WHERE loyalty_member = 'yes'", tags=("filter",)),
    Q("rt14", "retail_sales", "advanced", "What percentage of total net_sales comes from the top 5 stores?", expected_sql="WITH g AS (SELECT store d, SUM(net_sales) s FROM {t} GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=5 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total",)),
    Q("rt15", "retail_sales", "advanced", "Which categories have above-average net_sales?", expected_sql="WITH g AS (SELECT category d, SUM(net_sales) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s > (SELECT AVG(s) FROM g) ORDER BY 2 DESC", tags=("above_average",)),
    Q("rt16", "retail_sales", "advanced", "What is the monthly net_sales trend?", expected_sql="SELECT strftime(CAST(txn_date AS DATE), '%Y-%m') AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("rt17", "retail_sales", "advanced", "What is the return rate by category?", expected_sql="SELECT category AS d, ROUND(100.0*SUM(CASE WHEN returned='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio", "conditional_aggregation")),
    Q("rt18", "retail_sales", "advanced", "Which stores have at least 200 transactions?", expected_sql="SELECT store AS d, COUNT(*) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 200 ORDER BY 2 DESC", tags=("having", "min_sample")),
    Q("rt19", "retail_sales", "advanced", "What is the gross margin by category?", expected_sql="SELECT category AS d, ROUND(100.0*(SUM(net_sales)-SUM(cogs))/NULLIF(SUM(net_sales),0),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio",)),
    Q("rt20", "retail_sales", "advanced", "What is the total net_sales by year?", expected_sql="SELECT CAST(strftime(CAST(txn_date AS DATE), '%Y') AS INTEGER) AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("rt21", "retail_sales", "advanced", "Which channels have below-average units?", expected_sql="WITH g AS (SELECT channel d, SUM(units) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s < (SELECT AVG(s) FROM g) ORDER BY 2 ASC", tags=("below_average",)),
    Q("rt22", "retail_sales", "expert", "What are the top 3 categories by net_sales within each store_region?", expected_sql="WITH g AS (SELECT store_region r, category c, SUM(net_sales) v FROM {t} GROUP BY 1,2), k AS (SELECT r,c,v, ROW_NUMBER() OVER (PARTITION BY r ORDER BY v DESC) rn FROM g) SELECT r,c,v FROM k WHERE rn<=3 ORDER BY r, v DESC", tags=("top_n_per_group", "window")),
    Q("rt23", "retail_sales", "expert", "Which stores have above-average net_sales but below-average units?", expected_sql="WITH g AS (SELECT store d, SUM(net_sales) s, SUM(units) u FROM {t} GROUP BY 1) SELECT d, s, u FROM g WHERE s > (SELECT AVG(s) FROM g) AND u < (SELECT AVG(u) FROM g) ORDER BY 2 DESC", tags=("multi_condition",)),
    Q("rt24", "retail_sales", "expert", "Which categories with at least 400 transactions have the highest gross margin?", expected_sql="SELECT category AS d, ROUND(100.0*(SUM(net_sales)-SUM(cogs))/NULLIF(SUM(net_sales),0),2) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 400 ORDER BY 2 DESC", tags=("having", "ratio")),
    Q("rt25", "retail_sales", "expert", "What is each store_region's share of total net_sales?", expected_sql="SELECT store_region AS d, ROUND(100.0*SUM(net_sales)/(SELECT SUM(net_sales) FROM {t}),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("contribution",)),
    Q("rt26", "retail_sales", "expert", "Compare net_sales between loyalty members and non-members by channel", expected_sql="SELECT channel AS d, SUM(CASE WHEN loyalty_member='yes' THEN net_sales ELSE 0 END) AS member, SUM(CASE WHEN loyalty_member='no' THEN net_sales ELSE 0 END) AS non_member FROM {t} GROUP BY 1 ORDER BY 1", tags=("conditional_aggregation", "comparison")),
    Q("rt27", "retail_sales", "expert", "Compare total net_sales between 2023 and 2024 by category", expected_sql="SELECT category AS d, SUM(CASE WHEN strftime(CAST(txn_date AS DATE),'%Y')='2023' THEN net_sales ELSE 0 END) AS y2023, SUM(CASE WHEN strftime(CAST(txn_date AS DATE),'%Y')='2024' THEN net_sales ELSE 0 END) AS y2024 FROM {t} GROUP BY 1 ORDER BY 1", tags=("yoy",)),
    Q("rt28", "retail_sales", "medium", "Which stores sold the most?", kind="paraphrase", expected_sql="SELECT store AS d, SUM(net_sales) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("paraphrase",)),
    Q("rt29", "retail_sales", "simple", "What is the average customer age?", kind="abstain", tags=("abstention",)),
    Q("rt30", "retail_sales", "simple", "Which store has the best employee morale?", kind="abstain", tags=("abstention",)),
]

# ── employees (30) ───────────────────────────────────────────────────────────
EMPLOYEES = [
    Q("em01", "employees", "simple", "How many employees are there?", expected_sql="SELECT COUNT(*) AS v FROM {t}", tags=("count",)),
    Q("em02", "employees", "simple", "What is the average salary?", expected_sql="SELECT AVG(salary) AS v FROM {t}", tags=("aggregation",)),
    Q("em03", "employees", "simple", "What is the maximum salary?", expected_sql="SELECT MAX(salary) AS v FROM {t}", tags=("aggregation",)),
    Q("em04", "employees", "simple", "What is the total training_hours?", expected_sql="SELECT SUM(training_hours) AS v FROM {t}", tags=("aggregation",)),
    Q("em05", "employees", "simple", "How many distinct departments are there?", expected_sql="SELECT COUNT(DISTINCT department) AS v FROM {t}", tags=("distinct",)),
    Q("em06", "employees", "simple", "What is the average performance_score?", expected_sql="SELECT AVG(performance_score) AS v FROM {t}", tags=("aggregation",)),
    Q("em07", "employees", "medium", "What is the average salary by department?", expected_sql="SELECT department AS d, AVG(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("em08", "employees", "medium", "Which department has the highest average salary?", expected_sql="SELECT department AS d, AVG(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("ranking",)),
    Q("em09", "employees", "medium", "How many employees are in each job_level?", expected_sql="SELECT job_level AS d, COUNT(*) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("em10", "employees", "medium", "What is the average tenure_years by site?", expected_sql="SELECT site AS d, AVG(tenure_years) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("em11", "employees", "medium", "How many employees left the company?", expected_sql="SELECT COUNT(*) AS v FROM {t} WHERE attrition = 'yes'", tags=("filter",)),
    Q("em12", "employees", "medium", "What is the average salary for remote employees?", expected_sql="SELECT AVG(salary) AS v FROM {t} WHERE remote = 'yes'", tags=("filter",)),
    Q("em13", "employees", "medium", "What is the total salary by department?", expected_sql="SELECT department AS d, SUM(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("em14", "employees", "advanced", "What is the attrition rate by department?", expected_sql="SELECT department AS d, ROUND(100.0*SUM(CASE WHEN attrition='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio", "conditional_aggregation")),
    Q("em15", "employees", "advanced", "Which departments have above-average performance_score?", expected_sql="WITH g AS (SELECT department d, AVG(performance_score) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s > (SELECT AVG(s) FROM g) ORDER BY 2 DESC", tags=("above_average",)),
    Q("em16", "employees", "advanced", "Which sites have below-average salary?", expected_sql="WITH g AS (SELECT site d, AVG(salary) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s < (SELECT AVG(s) FROM g) ORDER BY 2 ASC", tags=("below_average",)),
    Q("em17", "employees", "advanced", "Which departments have at least 500 employees?", expected_sql="SELECT department AS d, COUNT(*) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 500 ORDER BY 2 DESC", tags=("having", "min_sample")),
    Q("em18", "employees", "advanced", "What are the top 5 sites by total salary?", expected_sql="SELECT site AS d, SUM(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("top_n",)),
    Q("em19", "employees", "advanced", "How many employees were hired each year?", expected_sql="SELECT CAST(strftime(CAST(hire_date AS DATE), '%Y') AS INTEGER) AS d, COUNT(*) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("em20", "employees", "advanced", "What percentage of total salary goes to the top 3 departments?", expected_sql="WITH g AS (SELECT department d, SUM(salary) s FROM {t} GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=3 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total",)),
    Q("em21", "employees", "advanced", "What is the average bonus_pct by job_level?", expected_sql="SELECT job_level AS d, AVG(bonus_pct) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("em22", "employees", "expert", "What are the top 3 job_levels by average salary within each department?", expected_sql="WITH g AS (SELECT department r, job_level c, AVG(salary) v FROM {t} GROUP BY 1,2), k AS (SELECT r,c,v, ROW_NUMBER() OVER (PARTITION BY r ORDER BY v DESC) rn FROM g) SELECT r,c,v FROM k WHERE rn<=3 ORDER BY r, v DESC", tags=("top_n_per_group", "window")),
    Q("em23", "employees", "expert", "Which departments have above-average salary but below-average performance_score?", expected_sql="WITH g AS (SELECT department d, AVG(salary) s, AVG(performance_score) p FROM {t} GROUP BY 1) SELECT d, s, p FROM g WHERE s > (SELECT AVG(s) FROM g) AND p < (SELECT AVG(p) FROM g) ORDER BY 2 DESC", tags=("multi_condition",)),
    Q("em24", "employees", "expert", "Which sites with at least 500 employees have the highest attrition rate?", expected_sql="SELECT site AS d, ROUND(100.0*SUM(CASE WHEN attrition='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 500 ORDER BY 2 DESC", tags=("having", "ratio")),
    Q("em25", "employees", "expert", "What is each department's share of total salary?", expected_sql="SELECT department AS d, ROUND(100.0*SUM(salary)/(SELECT SUM(salary) FROM {t}),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("contribution",)),
    Q("em26", "employees", "expert", "Compare average salary between remote and onsite employees by department", expected_sql="SELECT department AS d, AVG(CASE WHEN remote='yes' THEN salary END) AS remote_avg, AVG(CASE WHEN remote='no' THEN salary END) AS onsite_avg FROM {t} GROUP BY 1 ORDER BY 1", tags=("comparison", "conditional_aggregation")),
    Q("em27", "employees", "expert", "Which departments have the widest salary range?", expected_sql="SELECT department AS d, MAX(salary)-MIN(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("spread",)),
    Q("em28", "employees", "medium", "Which teams pay the most on average?", kind="paraphrase", expected_sql="SELECT department AS d, AVG(salary) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("paraphrase",)),
    Q("em29", "employees", "simple", "What is the average commute distance?", kind="abstain", tags=("abstention",)),
    Q("em30", "employees", "simple", "Which employee has the highest customer rating?", kind="abstain", tags=("abstention",)),
]

# ── products (30) ────────────────────────────────────────────────────────────
PRODUCTS = [
    Q("pr01", "products", "simple", "How many products are there?", expected_sql="SELECT COUNT(*) AS v FROM {t}", tags=("count",)),
    Q("pr02", "products", "simple", "What is the average list_price?", expected_sql="SELECT AVG(list_price) AS v FROM {t}", tags=("aggregation",)),
    Q("pr03", "products", "simple", "What is the total stock_on_hand?", expected_sql="SELECT SUM(stock_on_hand) AS v FROM {t}", tags=("aggregation",)),
    Q("pr04", "products", "simple", "What is the maximum gross_margin?", expected_sql="SELECT MAX(gross_margin) AS v FROM {t}", tags=("aggregation",)),
    Q("pr05", "products", "simple", "How many distinct brands are there?", expected_sql="SELECT COUNT(DISTINCT brand) AS v FROM {t}", tags=("distinct",)),
    Q("pr06", "products", "simple", "What is the average avg_rating?", expected_sql="SELECT AVG(avg_rating) AS v FROM {t}", tags=("aggregation",)),
    Q("pr07", "products", "medium", "What is the total units_sold_ytd by category?", expected_sql="SELECT category AS d, SUM(units_sold_ytd) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("pr08", "products", "medium", "Which brand has the highest total units_sold_ytd?", expected_sql="SELECT brand AS d, SUM(units_sold_ytd) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("ranking",)),
    Q("pr09", "products", "medium", "What are the top 5 vendors by total gross_margin?", expected_sql="SELECT vendor AS d, SUM(gross_margin) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", tags=("top_n",)),
    Q("pr10", "products", "medium", "What is the average list_price by category?", expected_sql="SELECT category AS d, AVG(list_price) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("pr11", "products", "medium", "How many products are discontinued?", expected_sql="SELECT COUNT(*) AS v FROM {t} WHERE discontinued = 'yes'", tags=("filter",)),
    Q("pr12", "products", "medium", "What is the average avg_rating by brand?", expected_sql="SELECT brand AS d, AVG(avg_rating) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("pr13", "products", "medium", "What is the total stock_on_hand for the Tools category?", expected_sql="SELECT SUM(stock_on_hand) AS v FROM {t} WHERE category = 'Tools'", tags=("filter",)),
    Q("pr14", "products", "advanced", "Which categories have above-average units_sold_ytd?", expected_sql="WITH g AS (SELECT category d, SUM(units_sold_ytd) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s > (SELECT AVG(s) FROM g) ORDER BY 2 DESC", tags=("above_average",)),
    Q("pr15", "products", "advanced", "Which brands have below-average avg_rating?", expected_sql="WITH g AS (SELECT brand d, AVG(avg_rating) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s < (SELECT AVG(s) FROM g) ORDER BY 2 ASC", tags=("below_average",)),
    Q("pr16", "products", "advanced", "What percentage of total units_sold_ytd comes from the top 5 brands?", expected_sql="WITH g AS (SELECT brand d, SUM(units_sold_ytd) s FROM {t} GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=5 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total",)),
    Q("pr17", "products", "advanced", "Which vendors have at least 100 products?", expected_sql="SELECT vendor AS d, COUNT(*) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 100 ORDER BY 2 DESC", tags=("having", "min_sample")),
    Q("pr18", "products", "advanced", "What is the margin percentage by category?", expected_sql="SELECT category AS d, ROUND(100.0*SUM(gross_margin)/NULLIF(SUM(list_price),0),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio",)),
    Q("pr19", "products", "advanced", "How many products were launched each year?", expected_sql="SELECT CAST(strftime(CAST(launch_date AS DATE), '%Y') AS INTEGER) AS d, COUNT(*) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("pr20", "products", "advanced", "What is the discontinued rate by category?", expected_sql="SELECT category AS d, ROUND(100.0*SUM(CASE WHEN discontinued='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio", "conditional_aggregation")),
    Q("pr21", "products", "advanced", "What are the top 10 skus by units_sold_ytd?", expected_sql="SELECT sku AS d, units_sold_ytd AS v FROM {t} ORDER BY 2 DESC LIMIT 10", tags=("top_n",)),
    Q("pr22", "products", "expert", "What are the top 3 brands by units_sold_ytd within each category?", expected_sql="WITH g AS (SELECT category r, brand c, SUM(units_sold_ytd) v FROM {t} GROUP BY 1,2), k AS (SELECT r,c,v, ROW_NUMBER() OVER (PARTITION BY r ORDER BY v DESC) rn FROM g) SELECT r,c,v FROM k WHERE rn<=3 ORDER BY r, v DESC", tags=("top_n_per_group", "window")),
    Q("pr23", "products", "expert", "Which categories have above-average list_price but below-average avg_rating?", expected_sql="WITH g AS (SELECT category d, AVG(list_price) p, AVG(avg_rating) r FROM {t} GROUP BY 1) SELECT d, p, r FROM g WHERE p > (SELECT AVG(p) FROM g) AND r < (SELECT AVG(r) FROM g) ORDER BY 2 DESC", tags=("multi_condition",)),
    Q("pr24", "products", "expert", "Which brands with at least 200 products have the highest margin percentage?", expected_sql="SELECT brand AS d, ROUND(100.0*SUM(gross_margin)/NULLIF(SUM(list_price),0),2) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 200 ORDER BY 2 DESC", tags=("having", "ratio")),
    Q("pr25", "products", "expert", "What is each category's share of total units_sold_ytd?", expected_sql="SELECT category AS d, ROUND(100.0*SUM(units_sold_ytd)/(SELECT SUM(units_sold_ytd) FROM {t}),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("contribution",)),
    Q("pr26", "products", "expert", "Compare average list_price between discontinued and active products by category", expected_sql="SELECT category AS d, AVG(CASE WHEN discontinued='yes' THEN list_price END) AS disc, AVG(CASE WHEN discontinued='no' THEN list_price END) AS active FROM {t} GROUP BY 1 ORDER BY 1", tags=("comparison",)),
    Q("pr27", "products", "expert", "Which vendors have the widest list_price range?", expected_sql="SELECT vendor AS d, MAX(list_price)-MIN(list_price) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("spread",)),
    Q("pr28", "products", "medium", "Which brands shifted the most units?", kind="paraphrase", expected_sql="SELECT brand AS d, SUM(units_sold_ytd) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("paraphrase",)),
    Q("pr29", "products", "simple", "What is the average shipping weight?", kind="abstain", tags=("abstention",)),
    Q("pr30", "products", "simple", "Which product has the highest warranty claims?", kind="abstain", tags=("abstention",)),
]

# ── subscriptions (30) ───────────────────────────────────────────────────────
SUBSCRIPTIONS = [
    Q("sb01", "subscriptions", "simple", "What is the total mrr?", expected_sql="SELECT SUM(mrr) AS v FROM {t}", tags=("aggregation",)),
    Q("sb02", "subscriptions", "simple", "How many subscription records are there?", expected_sql="SELECT COUNT(*) AS v FROM {t}", tags=("count",)),
    Q("sb03", "subscriptions", "simple", "What is the average seats?", expected_sql="SELECT AVG(seats) AS v FROM {t}", tags=("aggregation",)),
    Q("sb04", "subscriptions", "simple", "How many distinct accounts are there?", expected_sql="SELECT COUNT(DISTINCT account_id) AS v FROM {t}", tags=("distinct",)),
    Q("sb05", "subscriptions", "simple", "What is the average nps?", expected_sql="SELECT AVG(nps) AS v FROM {t}", tags=("aggregation",)),
    Q("sb06", "subscriptions", "simple", "What is the total support_tickets?", expected_sql="SELECT SUM(support_tickets) AS v FROM {t}", tags=("aggregation",)),
    Q("sb07", "subscriptions", "medium", "What is the total mrr by plan?", expected_sql="SELECT plan AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("sb08", "subscriptions", "medium", "Which industry has the highest total mrr?", expected_sql="SELECT industry AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 1", tags=("ranking",)),
    Q("sb09", "subscriptions", "medium", "What is the average usage_hours by plan?", expected_sql="SELECT plan AS d, AVG(usage_hours) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("sb10", "subscriptions", "medium", "How many accounts churned?", expected_sql="SELECT COUNT(*) AS v FROM {t} WHERE churned = 'yes'", tags=("filter",)),
    Q("sb11", "subscriptions", "medium", "What is the total mrr for the Enterprise plan?", expected_sql="SELECT SUM(mrr) AS v FROM {t} WHERE plan = 'Enterprise'", tags=("filter",)),
    Q("sb12", "subscriptions", "medium", "What are the top 3 industries by total mrr?", expected_sql="SELECT industry AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 3", tags=("top_n",)),
    Q("sb13", "subscriptions", "medium", "What is the average support_tickets by industry?", expected_sql="SELECT industry AS d, AVG(support_tickets) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("group_by",)),
    Q("sb14", "subscriptions", "advanced", "What is the monthly mrr trend?", expected_sql="SELECT strftime(CAST(month AS DATE), '%Y-%m') AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series", "mom")),
    Q("sb15", "subscriptions", "advanced", "What is the churn rate by plan?", expected_sql="SELECT plan AS d, ROUND(100.0*SUM(CASE WHEN churned='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio", "conditional_aggregation")),
    Q("sb16", "subscriptions", "advanced", "Which plans have above-average mrr?", expected_sql="WITH g AS (SELECT plan d, SUM(mrr) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s > (SELECT AVG(s) FROM g) ORDER BY 2 DESC", tags=("above_average",)),
    Q("sb17", "subscriptions", "advanced", "Which industries have below-average nps?", expected_sql="WITH g AS (SELECT industry d, AVG(nps) s FROM {t} GROUP BY 1) SELECT d, s AS v FROM g WHERE s < (SELECT AVG(s) FROM g) ORDER BY 2 ASC", tags=("below_average",)),
    Q("sb18", "subscriptions", "advanced", "Which industries have at least 600 records?", expected_sql="SELECT industry AS d, COUNT(*) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 600 ORDER BY 2 DESC", tags=("having", "min_sample")),
    Q("sb19", "subscriptions", "advanced", "What percentage of total mrr comes from the top 2 plans?", expected_sql="WITH g AS (SELECT plan d, SUM(mrr) s FROM {t} GROUP BY 1), r AS (SELECT s, ROW_NUMBER() OVER (ORDER BY s DESC) rn FROM g) SELECT ROUND(100.0*SUM(CASE WHEN rn<=2 THEN s ELSE 0 END)/NULLIF(SUM(s),0),2) AS v FROM r", tags=("percent_of_total",)),
    Q("sb20", "subscriptions", "advanced", "What is the average mrr per seat by plan?", expected_sql="SELECT plan AS d, ROUND(SUM(mrr)/NULLIF(SUM(seats),0),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("ratio",)),
    Q("sb21", "subscriptions", "advanced", "What is the total mrr by year?", expected_sql="SELECT CAST(strftime(CAST(month AS DATE), '%Y') AS INTEGER) AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 1", tags=("time_series",)),
    Q("sb22", "subscriptions", "expert", "What are the top 3 industries by mrr within each plan?", expected_sql="WITH g AS (SELECT plan r, industry c, SUM(mrr) v FROM {t} GROUP BY 1,2), k AS (SELECT r,c,v, ROW_NUMBER() OVER (PARTITION BY r ORDER BY v DESC) rn FROM g) SELECT r,c,v FROM k WHERE rn<=3 ORDER BY r, v DESC", tags=("top_n_per_group", "window")),
    Q("sb23", "subscriptions", "expert", "Which industries have above-average mrr but below-average nps?", expected_sql="WITH g AS (SELECT industry d, SUM(mrr) m, AVG(nps) n FROM {t} GROUP BY 1) SELECT d, m, n FROM g WHERE m > (SELECT AVG(m) FROM g) AND n < (SELECT AVG(n) FROM g) ORDER BY 2 DESC", tags=("multi_condition",)),
    Q("sb24", "subscriptions", "expert", "Which plans with at least 700 records have the highest churn rate?", expected_sql="SELECT plan AS d, ROUND(100.0*SUM(CASE WHEN churned='yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS v FROM {t} GROUP BY 1 HAVING COUNT(*) >= 700 ORDER BY 2 DESC", tags=("having", "ratio")),
    Q("sb25", "subscriptions", "expert", "What is each plan's share of total mrr?", expected_sql="SELECT plan AS d, ROUND(100.0*SUM(mrr)/(SELECT SUM(mrr) FROM {t}),2) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("contribution",)),
    Q("sb26", "subscriptions", "expert", "Compare mrr between churned and retained accounts by plan", expected_sql="SELECT plan AS d, SUM(CASE WHEN churned='yes' THEN mrr ELSE 0 END) AS churned_mrr, SUM(CASE WHEN churned='no' THEN mrr ELSE 0 END) AS retained_mrr FROM {t} GROUP BY 1 ORDER BY 1", tags=("comparison",)),
    Q("sb27", "subscriptions", "expert", "Compare total mrr between 2023 and 2024 by plan", expected_sql="SELECT plan AS d, SUM(CASE WHEN strftime(CAST(month AS DATE),'%Y')='2023' THEN mrr ELSE 0 END) AS y2023, SUM(CASE WHEN strftime(CAST(month AS DATE),'%Y')='2024' THEN mrr ELSE 0 END) AS y2024 FROM {t} GROUP BY 1 ORDER BY 1", tags=("yoy",)),
    Q("sb28", "subscriptions", "medium", "Which plans bring in the most recurring revenue?", kind="paraphrase", expected_sql="SELECT plan AS d, SUM(mrr) AS v FROM {t} GROUP BY 1 ORDER BY 2 DESC", tags=("paraphrase",)),
    Q("sb29", "subscriptions", "simple", "What is the average customer lifetime value?", kind="abstain", tags=("abstention",)),
    Q("sb30", "subscriptions", "simple", "Which sales rep closed the most accounts?", kind="abstain", tags=("abstention",)),
]

ALL_QUESTIONS: List[BenchQuestion] = MARKETPLACE + RETAIL + EMPLOYEES + PRODUCTS + SUBSCRIPTIONS


def by_difficulty() -> dict:
    counts: dict = {}
    for q in ALL_QUESTIONS:
        counts[q.difficulty] = counts.get(q.difficulty, 0) + 1
    return counts


def by_kind() -> dict:
    counts: dict = {}
    for q in ALL_QUESTIONS:
        counts[q.kind] = counts.get(q.kind, 0) + 1
    return counts


if __name__ == "__main__":
    print(f"total: {len(ALL_QUESTIONS)}")
    print("difficulty:", by_difficulty())
    print("kind:", by_kind())
    print("datasets:", {d: sum(1 for q in ALL_QUESTIONS if q.dataset == d) for d in DATASET_FILES})
