# BENCHMARK_REPORT.md — NL→SQL Accuracy

**Mode:** `deterministic`  
**Questions:** 150  
**Passed:** 92  
**Failed:** 58  
**Accuracy:** **61.33%**  

## By difficulty

| Difficulty | Pass | Fail | Accuracy |
|---|---:|---:|---:|
| simple | 39 | 1 | 97.5% |
| medium | 27 | 14 | 65.9% |
| advanced | 21 | 19 | 52.5% |
| expert | 5 | 24 | 17.2% |

## By kind

| Kind | Pass | Fail |
|---|---:|---:|
| sql | 80 | 53 |
| paraphrase | 1 | 5 |
| abstain | 10 | 0 |
| ambiguous | 1 | 0 |

## By dataset

| Dataset | Pass | Fail | Accuracy |
|---|---:|---:|---:|
| marketplace_orders | 21 | 9 | 70.0% |
| retail_sales | 18 | 12 | 60.0% |
| employees | 15 | 15 | 50.0% |
| products | 18 | 12 | 60.0% |
| subscriptions | 20 | 10 | 66.7% |

## Latency (deterministic generation only)

- p50: 0.2 ms
- p95: 0.72 ms
- max: 1.39 ms
- avg: 0.25 ms

## Failures

- `mk11` [marketplace_orders/medium/sql] How many orders were placed in each order status? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='completed' actual=4000; row[0].c1 expected=2906 actual=None
- `mk19` [marketplace_orders/advanced/sql] Which suppliers have at least 40 orders? — execution error: Binder Error: No function matches the given name and argument types 'round(VARCHAR, INTEGER_LITERAL)'. You might need to add explicit type casts.
	Candidate functions:
	round(TINYINT) -> TINYINT
	round(TINYINT, INTEGER) -> TINYINT
	round(SMALLINT) -> SMALLINT
	round(SMALLINT, INTEGER) -> SMALLINT
	round(INTEGER) -> INTEGER
	round(INTEGER, INTEGER) -> INTEGER
	round(BIGINT) -> BIGINT
	round(BIGINT, INTEGER) -> BIGINT
	round(HUGEINT) -> HUGEINT
	round(HUGEINT, INTEGER) -> HUGEINT
	round(FLOAT) -> FLOAT
	round(FLOAT, INTEGER) -> FLOAT
	round(DOUBLE) -> DOUBLE
	round(DOUBLE, INTEGER) -> DOUBLE
	round(DECIMAL) -> DECIMAL
	round(DECIMAL, INTEGER) -> DECIMAL


LINE 2:        ROUND(MIN(order_id), 2) AS min_orders
               ^
- `mk20` [marketplace_orders/advanced/sql] What is the profit margin by product category? — row[0].c1 expected=29.51 actual=2655619.63
- `mk21` [marketplace_orders/expert/sql] What are the top 3 suppliers by revenue within each customer region? — row_count expected=15 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Central' actual='South'; row[0].c1 expected='Zenith Trading 59' actual=9721375.45; row[0].c2 expected=762802.19 actual=None
- `mk22` [marketplace_orders/expert/sql] Which customer regions have above-average revenue but below-average profit? — scalar mismatch expected=2320290.999999999 actual=0.2455
- `mk23` [marketplace_orders/expert/sql] Which suppliers with at least 30 orders have the highest profit margin? — row_count expected=10 actual=20; row[0].c0 expected='Zenith Industries 26' actual='Apex Manufacturing 20'; row[0].c1 expected=31.19 actual=-37014.52
- `mk25` [marketplace_orders/expert/sql] Compare total revenue between 2023 and 2024 by customer region — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Central' actual='South'; row[0].c1 expected=3337084.2 actual=9721375.45; row[0].c2 expected=2799410.66 actual=None
- `mk26` [marketplace_orders/medium/paraphrase] Which vendors generated the most sales? — row_count expected=5 actual=20; row[0].c0 expected='Orbit Trading 27' actual='Warehousing Model 2'; row[0].c1 expected=1165578.68 actual=1415426.31
- `mk27` [marketplace_orders/medium/paraphrase] Who are the biggest sellers by revenue? — row[0].c0 expected='Orbit Trading 27' actual='Industrial Equipment'; row[0].c1 expected=1165578.68 actual=10062275.36
- `rt03` [retail_sales/simple/sql] What is the average units per transaction? — no SQL generated (unsupported_schema)
- `rt12` [retail_sales/medium/sql] How many transactions were returned? — scalar mismatch expected=259 actual=3600
- `rt13` [retail_sales/medium/sql] What is the average net_sales for loyalty members? — scalar mismatch expected=3682.1032521847687 actual=3790.1006527777745
- `rt17` [retail_sales/advanced/sql] What is the return rate by category? — row[0].c0 expected='Electronics' actual='Beauty'; row[0].c1 expected=8.35 actual=2431114.65
- `rt18` [retail_sales/advanced/sql] Which stores have at least 200 transactions? — no SQL generated (unsupported_domain)
- `rt19` [retail_sales/advanced/sql] What is the gross margin by category? — row[0].c1 expected=39.43 actual=2431114.65
- `rt22` [retail_sales/expert/sql] What are the top 3 categories by net_sales within each store_region? — row_count expected=12 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='East' actual='Store 08'; row[0].c1 expected='Beauty' actual=862455.31; row[0].c2 expected=770962.35 actual=None
- `rt23` [retail_sales/expert/sql] Which stores have above-average net_sales but below-average units? — no SQL generated (unsupported_schema)
- `rt24` [retail_sales/expert/sql] Which categories with at least 400 transactions have the highest gross margin? — row[0].c0 expected='Beauty' actual='Apparel'; row[0].c1 expected=39.43 actual=3.77
- `rt26` [retail_sales/expert/sql] Compare net_sales between loyalty members and non-members by channel — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=1991320.7 actual=4654735.07; row[0].c2 expected=2663414.37 actual=None
- `rt27` [retail_sales/expert/sql] Compare total net_sales between 2023 and 2024 by category — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Apparel' actual='Beauty'; row[0].c1 expected=1073071.25 actual=2431114.65; row[0].c2 expected=1297661.86 actual=None
- `rt28` [retail_sales/medium/paraphrase] Which stores sold the most? — no SQL generated (unsupported_domain)
- `em08` [employees/medium/sql] Which department has the highest average salary? — scalar mismatch expected=127851.76695652174 actual=73514766.0
- `em09` [employees/medium/sql] How many employees are in each job_level? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Senior' actual=3200; row[0].c1 expected=652 actual=None
- `em11` [employees/medium/sql] How many employees left the company? — scalar mismatch expected=611 actual=3200
- `em12` [employees/medium/sql] What is the average salary for remote employees? — scalar mismatch expected=124280.15138772078 actual=124040.625625
- `em14` [employees/advanced/sql] What is the attrition rate by department? — no SQL generated (unsupported_schema)
- `em15` [employees/advanced/sql] Which departments have above-average performance_score? — row[0].c0 expected='Finance' actual='Support'; row[0].c1 expected=3.068712 actual=1691.62
- `em16` [employees/advanced/sql] Which sites have below-average salary? — row[0].c0 expected='Austin' actual='Bengaluru'; row[0].c1 expected=120230.534375 actual=74971517.0
- `em17` [employees/advanced/sql] Which departments have at least 500 employees? — no SQL generated (unsupported_domain)
- `em19` [employees/advanced/sql] How many employees were hired each year? — row_count expected=10 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2015 actual=3200; row[0].c1 expected=300 actual=None
- `em22` [employees/expert/sql] What are the top 3 job_levels by average salary within each department? — row_count expected=18 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Engineering' actual='Support'; row[0].c1 expected='Principal' actual=73514766.0; row[0].c2 expected=191224.651376 actual=None
- `em23` [employees/expert/sql] Which departments have above-average salary but below-average performance_score? — no SQL generated (unsupported_schema)
- `em24` [employees/expert/sql] Which sites with at least 500 employees have the highest attrition rate? — row_count expected=5 actual=20; columns expected=['c0', 'c1'] actual=['c0', 'c1', 'c10', 'c11', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9']; row[0].c0 expected='Bengaluru' actual='E22141'; row[0].c1 expected=21.41 actual='2024-05-09'
- `em26` [employees/expert/sql] Compare average salary between remote and onsite employees by department — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Engineering' actual='Support'; row[0].c1 expected=118889.78 actual=127851.766957; row[0].c2 expected=125571.047478 actual=None
- `em27` [employees/expert/sql] Which departments have the widest salary range? — no SQL generated (unsupported_schema)
- `em28` [employees/medium/paraphrase] Which teams pay the most on average? — no SQL generated (unsupported_domain)
- `pr11` [products/medium/sql] How many products are discontinued? — scalar mismatch expected=363 actual=3000
- `pr15` [products/advanced/sql] Which brands have below-average avg_rating? — row_count expected=7 actual=5; row[0].c0 expected='Brand C' actual='Brand G'; row[0].c1 expected=3.409247 actual=777.58
- `pr17` [products/advanced/sql] Which vendors have at least 100 products? — row_count expected=25 actual=50; row[0].c0 expected='Vendor 23' actual='SKU50148'; row[0].c1 expected=152 actual=0.38
- `pr18` [products/advanced/sql] What is the margin percentage by category? — row[0].c1 expected=47.36 actual=90481.92
- `pr19` [products/advanced/sql] How many products were launched each year? — row_count expected=7 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2019 actual=3000; row[0].c1 expected=488 actual=None
- `pr20` [products/advanced/sql] What is the discontinued rate by category? — row[0].c1 expected=14.0 actual=90481.92
- `pr22` [products/expert/sql] What are the top 3 brands by units_sold_ytd within each category? — row_count expected=18 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Adhesives' actual='Brand J'; row[0].c1 expected='Brand A' actual=723553; row[0].c2 expected=127139 actual=None
- `pr23` [products/expert/sql] Which categories have above-average list_price but below-average avg_rating? — row_count expected=2 actual=6; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=382.09128 actual=180.96; row[0].c2 expected=3.47112 actual=None
- `pr24` [products/expert/sql] Which brands with at least 200 products have the highest margin percentage? — row_count expected=12 actual=50; row[0].c0 expected='Brand H' actual='SKU50148'; row[0].c1 expected=47.4 actual=0.38
- `pr26` [products/expert/sql] Compare average list_price between discontinued and active products by category — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Adhesives' actual='Measuring'; row[0].c1 expected=366.6225 actual=382.09128; row[0].c2 expected=345.305495 actual=None
- `pr27` [products/expert/sql] Which vendors have the widest list_price range? — no SQL generated (unsupported_schema)
- `pr28` [products/medium/paraphrase] Which brands shifted the most units? — no SQL generated (unsupported_domain)
- `sb10` [subscriptions/medium/sql] How many accounts churned? — scalar mismatch expected=341 actual=4000
- `sb15` [subscriptions/advanced/sql] What is the churn rate by plan? — no SQL generated (unsupported_schema)
- `sb17` [subscriptions/advanced/sql] Which industries have below-average nps? — row[0].c1 expected=-4.080916 actual=-2673
- `sb18` [subscriptions/advanced/sql] Which industries have at least 600 records? — no SQL generated (unsupported_domain)
- `sb20` [subscriptions/advanced/sql] What is the average mrr per seat by plan? — row[0].c1 expected=1193.19 actual=36032.068285
- `sb22` [subscriptions/expert/sql] What are the top 3 industries by mrr within each plan? — row_count expected=15 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected='Education' actual=29834552.54; row[0].c2 expected=5203699.77 actual=None
- `sb23` [subscriptions/expert/sql] Which industries have above-average mrr but below-average nps? — no SQL generated (unsupported_schema)
- `sb24` [subscriptions/expert/sql] Which plans with at least 700 records have the highest churn rate? — no SQL generated (unsupported_domain)
- `sb26` [subscriptions/expert/sql] Compare mrr between churned and retained accounts by plan — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=2400634.41 actual=29834552.54; row[0].c2 expected=27433918.13 actual=None
- `sb27` [subscriptions/expert/sql] Compare total mrr between 2023 and 2024 by plan — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=12979868.23 actual=29834552.54; row[0].c2 expected=11906207.19 actual=None

## Notes

- Ground truth SQL is independent of the pipeline and runs in DuckDB.
- `deterministic` mode measures the pattern library + analytics fallback.
- It does **not** claim full LLM-path accuracy; that requires `--mode pipeline`
  with a live provider.
- Abstention and ambiguity are scored as correct when the system declines
  rather than inventing an answer.
