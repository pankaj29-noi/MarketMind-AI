# BENCHMARK_REPORT.md — NL→SQL Accuracy

**Mode:** `deterministic`  
**Questions:** 150  
**Passed:** 44  
**Failed:** 106  
**Accuracy:** **29.33%**  

## By difficulty

| Difficulty | Pass | Fail | Accuracy |
|---|---:|---:|---:|
| simple | 35 | 5 | 87.5% |
| medium | 2 | 39 | 4.9% |
| advanced | 7 | 33 | 17.5% |
| expert | 0 | 29 | 0.0% |

## By kind

| Kind | Pass | Fail |
|---|---:|---:|
| sql | 33 | 100 |
| paraphrase | 0 | 6 |
| abstain | 10 | 0 |
| ambiguous | 1 | 0 |

## By dataset

| Dataset | Pass | Fail | Accuracy |
|---|---:|---:|---:|
| marketplace_orders | 10 | 20 | 33.3% |
| retail_sales | 9 | 21 | 30.0% |
| employees | 8 | 22 | 26.7% |
| products | 9 | 21 | 30.0% |
| subscriptions | 8 | 22 | 26.7% |

## Latency (deterministic generation only)

- p50: 0.06 ms
- p95: 0.28 ms
- max: 2.1 ms
- avg: 0.12 ms

## Failures

- `mk05` [marketplace_orders/simple/sql] How many distinct suppliers are there? — scalar mismatch expected=60 actual=4000
- `mk06` [marketplace_orders/medium/sql] What is the total revenue by customer region? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='South' actual=46002445.42; row[0].c1 expected=9721375.45 actual=None
- `mk07` [marketplace_orders/medium/sql] Which customer region has the highest total revenue? — scalar mismatch expected=9721375.45 actual=46002445.420000024
- `mk09` [marketplace_orders/medium/sql] What is the average profit by product category? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Electronics' actual=2931.85741; row[0].c1 expected=3361.543835 actual=None
- `mk10` [marketplace_orders/medium/sql] What is the total revenue by sales channel? — row_count expected=4 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Marketplace' actual=46002445.42; row[0].c1 expected=12523070.83 actual=None
- `mk11` [marketplace_orders/medium/sql] How many orders were placed in each order status? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='completed' actual=4000; row[0].c1 expected=2906 actual=None
- `mk12` [marketplace_orders/medium/sql] What is the total revenue for the North customer region? — scalar mismatch expected=9451730.169999998 actual=46002445.420000024
- `mk15` [marketplace_orders/advanced/sql] Which customer regions have above-average revenue? — row_count expected=4 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='South' actual=11500.611355; row[0].c1 expected=9721375.45 actual=None
- `mk16` [marketplace_orders/advanced/sql] Which product categories have below-average profit? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Packaging' actual=2931.85741; row[0].c1 expected=2079974.64 actual=None
- `mk17` [marketplace_orders/advanced/sql] What is the monthly revenue trend? — row_count expected=36 actual=20
- `mk18` [marketplace_orders/advanced/sql] What is the total revenue by year? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2023 actual=46002445.42; row[0].c1 expected=16779397.46 actual=None
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
- `mk22` [marketplace_orders/expert/sql] Which customer regions have above-average revenue but below-average profit? — scalar mismatch expected=2320290.999999999 actual=11500.611355000006
- `mk23` [marketplace_orders/expert/sql] Which suppliers with at least 30 orders have the highest profit margin? — row_count expected=10 actual=20; row[0].c0 expected='Zenith Industries 26' actual='Apex Manufacturing 20'; row[0].c1 expected=31.19 actual=-37014.52
- `mk24` [marketplace_orders/expert/sql] What is each customer region's share of total revenue? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='South' actual=46002445.42; row[0].c1 expected=21.13 actual=None
- `mk25` [marketplace_orders/expert/sql] Compare total revenue between 2023 and 2024 by customer region — row_count expected=5 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Central' actual=46002445.42; row[0].c1 expected=3337084.2 actual=None; row[0].c2 expected=2799410.66 actual=None
- `mk26` [marketplace_orders/medium/paraphrase] Which vendors generated the most sales? — row_count expected=5 actual=20; row[0].c0 expected='Orbit Trading 27' actual='Warehousing Model 2'; row[0].c1 expected=1165578.68 actual=1415426.31
- `mk27` [marketplace_orders/medium/paraphrase] Who are the biggest sellers by revenue? — row[0].c0 expected='Orbit Trading 27' actual='Industrial Equipment'; row[0].c1 expected=1165578.68 actual=10062275.36
- `rt04` [retail_sales/simple/sql] How many distinct stores are there? — scalar mismatch expected=18 actual=3600
- `rt07` [retail_sales/medium/sql] What is the total net_sales by category? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Beauty' actual=13644362.35; row[0].c1 expected=2431114.65 actual=None
- `rt08` [retail_sales/medium/sql] Which store_region has the highest total net_sales? — scalar mismatch expected=4007717.8600000013 actual=13644362.349999988
- `rt10` [retail_sales/medium/sql] What is the total net_sales by channel? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Curbside' actual=13644362.35; row[0].c1 expected=4654735.07 actual=None
- `rt11` [retail_sales/medium/sql] What is the total net_sales for the Online channel? — scalar mismatch expected=4438451.529999992 actual=13644362.349999988
- `rt12` [retail_sales/medium/sql] How many transactions were returned? — scalar mismatch expected=259 actual=3600
- `rt13` [retail_sales/medium/sql] What is the average net_sales for loyalty members? — scalar mismatch expected=3682.1032521847687 actual=3790.1006527777745
- `rt15` [retail_sales/advanced/sql] Which categories have above-average net_sales? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Beauty' actual=3790.100653; row[0].c1 expected=2431114.65 actual=None
- `rt16` [retail_sales/advanced/sql] What is the monthly net_sales trend? — row_count expected=24 actual=20
- `rt17` [retail_sales/advanced/sql] What is the return rate by category? — row[0].c0 expected='Electronics' actual='Beauty'; row[0].c1 expected=8.35 actual=2431114.65
- `rt18` [retail_sales/advanced/sql] Which stores have at least 200 transactions? — no SQL generated (unsupported_domain)
- `rt19` [retail_sales/advanced/sql] What is the gross margin by category? — row[0].c1 expected=39.43 actual=2431114.65
- `rt20` [retail_sales/advanced/sql] What is the total net_sales by year? — row_count expected=2 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2023 actual=13644362.35; row[0].c1 expected=6929452.83 actual=None
- `rt21` [retail_sales/advanced/sql] Which channels have below-average units? — scalar mismatch expected=24394 actual=20.691388888888888
- `rt22` [retail_sales/expert/sql] What are the top 3 categories by net_sales within each store_region? — row_count expected=12 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='East' actual='Store 08'; row[0].c1 expected='Beauty' actual=862455.31; row[0].c2 expected=770962.35 actual=None
- `rt23` [retail_sales/expert/sql] Which stores have above-average net_sales but below-average units? — row_count expected=2 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Store 05' actual=3790.100653; row[0].c1 expected=781267.92 actual=None; row[0].c2 expected=4072 actual=None
- `rt24` [retail_sales/expert/sql] Which categories with at least 400 transactions have the highest gross margin? — row[0].c0 expected='Beauty' actual='Apparel'; row[0].c1 expected=39.43 actual=3.77
- `rt25` [retail_sales/expert/sql] What is each store_region's share of total net_sales? — row_count expected=4 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='East' actual=13644362.35; row[0].c1 expected=29.37 actual=None
- `rt26` [retail_sales/expert/sql] Compare net_sales between loyalty members and non-members by channel — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=1991320.7 actual=4654735.07; row[0].c2 expected=2663414.37 actual=None
- `rt27` [retail_sales/expert/sql] Compare total net_sales between 2023 and 2024 by category — row_count expected=6 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Apparel' actual=13644362.35; row[0].c1 expected=1073071.25 actual=None; row[0].c2 expected=1297661.86 actual=None
- `rt28` [retail_sales/medium/paraphrase] Which stores sold the most? — no SQL generated (unsupported_domain)
- `em05` [employees/simple/sql] How many distinct departments are there? — scalar mismatch expected=6 actual=3200
- `em07` [employees/medium/sql] What is the average salary by department? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Support' actual=124040.625625; row[0].c1 expected=127851.766957 actual=None
- `em08` [employees/medium/sql] Which department has the highest average salary? — scalar mismatch expected=127851.76695652174 actual=124040.625625
- `em09` [employees/medium/sql] How many employees are in each job_level? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Senior' actual=3200; row[0].c1 expected=652 actual=None
- `em10` [employees/medium/sql] What is the average tenure_years by site? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Toronto' actual=5.575531; row[0].c1 expected=5.775318 actual=None
- `em11` [employees/medium/sql] How many employees left the company? — scalar mismatch expected=611 actual=3200
- `em12` [employees/medium/sql] What is the average salary for remote employees? — scalar mismatch expected=124280.15138772078 actual=124040.625625
- `em13` [employees/medium/sql] What is the total salary by department? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Support' actual=396930002.0; row[0].c1 expected=73514766.0 actual=None
- `em14` [employees/advanced/sql] What is the attrition rate by department? — no SQL generated (unsupported_schema)
- `em15` [employees/advanced/sql] Which departments have above-average performance_score? — row_count expected=4 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Finance' actual=3.018675; row[0].c1 expected=3.068712 actual=None
- `em16` [employees/advanced/sql] Which sites have below-average salary? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Austin' actual=124040.625625; row[0].c1 expected=120230.534375 actual=None
- `em17` [employees/advanced/sql] Which departments have at least 500 employees? — no SQL generated (unsupported_domain)
- `em18` [employees/advanced/sql] What are the top 5 sites by total salary? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Pune' actual=396930002.0; row[0].c1 expected=86351733.0 actual=None
- `em19` [employees/advanced/sql] How many employees were hired each year? — row_count expected=10 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2015 actual=3200; row[0].c1 expected=300 actual=None
- `em21` [employees/advanced/sql] What is the average bonus_pct by job_level? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Principal' actual=10.918847; row[0].c1 expected=11.260503 actual=None
- `em22` [employees/expert/sql] What are the top 3 job_levels by average salary within each department? — row_count expected=18 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Engineering' actual=124040.625625; row[0].c1 expected='Principal' actual=None; row[0].c2 expected=191224.651376 actual=None
- `em23` [employees/expert/sql] Which departments have above-average salary but below-average performance_score? — scalar mismatch expected=2.941947826086956 actual=124040.625625
- `em24` [employees/expert/sql] Which sites with at least 500 employees have the highest attrition rate? — row_count expected=5 actual=20; columns expected=['c0', 'c1'] actual=['c0', 'c1', 'c10', 'c11', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9']; row[0].c0 expected='Bengaluru' actual='E22141'; row[0].c1 expected=21.41 actual='2024-05-09'
- `em25` [employees/expert/sql] What is each department's share of total salary? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Support' actual=396930002.0; row[0].c1 expected=18.52 actual=None
- `em26` [employees/expert/sql] Compare average salary between remote and onsite employees by department — row_count expected=6 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Engineering' actual=124040.625625; row[0].c1 expected=118889.78 actual=None; row[0].c2 expected=125571.047478 actual=None
- `em27` [employees/expert/sql] Which departments have the widest salary range? — no SQL generated (unsupported_schema)
- `em28` [employees/medium/paraphrase] Which teams pay the most on average? — no SQL generated (unsupported_domain)
- `pr05` [products/simple/sql] How many distinct brands are there? — scalar mismatch expected=12 actual=3000
- `pr07` [products/medium/sql] What is the total units_sold_ytd by category? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Tools' actual=7812031; row[0].c1 expected=1360246 actual=None
- `pr08` [products/medium/sql] Which brand has the highest total units_sold_ytd? — scalar mismatch expected=723553 actual=7812031
- `pr09` [products/medium/sql] What are the top 5 vendors by total gross_margin? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Vendor 23' actual=502185.28; row[0].c1 expected=27104.62 actual=None
- `pr10` [products/medium/sql] What is the average list_price by category? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Measuring' actual=366.98183; row[0].c1 expected=382.09128 actual=None
- `pr11` [products/medium/sql] How many products are discontinued? — scalar mismatch expected=363 actual=3000
- `pr12` [products/medium/sql] What is the average avg_rating by brand? — row_count expected=12 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Brand A' actual=3.490327; row[0].c1 expected=3.642109 actual=None
- `pr13` [products/medium/sql] What is the total stock_on_hand for the Tools category? — scalar mismatch expected=456113 actual=2717392
- `pr14` [products/advanced/sql] Which categories have above-average units_sold_ytd? — row_count expected=2 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Tools' actual=2604.010333; row[0].c1 expected=1360246 actual=None
- `pr15` [products/advanced/sql] Which brands have below-average avg_rating? — row_count expected=7 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Brand C' actual=3.490327; row[0].c1 expected=3.409247 actual=None
- `pr17` [products/advanced/sql] Which vendors have at least 100 products? — row_count expected=25 actual=50; row[0].c0 expected='Vendor 23' actual='SKU50148'; row[0].c1 expected=152 actual=0.38
- `pr18` [products/advanced/sql] What is the margin percentage by category? — row[0].c1 expected=47.36 actual=90481.92
- `pr19` [products/advanced/sql] How many products were launched each year? — row_count expected=7 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2019 actual=3000; row[0].c1 expected=488 actual=None
- `pr20` [products/advanced/sql] What is the discontinued rate by category? — row[0].c1 expected=14.0 actual=90481.92
- `pr22` [products/expert/sql] What are the top 3 brands by units_sold_ytd within each category? — row_count expected=18 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c0 expected='Adhesives' actual='Brand J'; row[0].c1 expected='Brand A' actual=723553; row[0].c2 expected=127139 actual=None
- `pr23` [products/expert/sql] Which categories have above-average list_price but below-average avg_rating? — row_count expected=2 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Measuring' actual=366.98183; row[0].c1 expected=382.09128 actual=None; row[0].c2 expected=3.47112 actual=None
- `pr24` [products/expert/sql] Which brands with at least 200 products have the highest margin percentage? — row_count expected=12 actual=50; row[0].c0 expected='Brand H' actual='SKU50148'; row[0].c1 expected=47.4 actual=0.38
- `pr25` [products/expert/sql] What is each category's share of total units_sold_ytd? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Tools' actual=7812031; row[0].c1 expected=17.41 actual=None
- `pr26` [products/expert/sql] Compare average list_price between discontinued and active products by category — row_count expected=6 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Adhesives' actual=366.98183; row[0].c1 expected=366.6225 actual=None; row[0].c2 expected=345.305495 actual=None
- `pr27` [products/expert/sql] Which vendors have the widest list_price range? — no SQL generated (unsupported_schema)
- `pr28` [products/medium/paraphrase] Which brands shifted the most units? — no SQL generated (unsupported_domain)
- `sb04` [subscriptions/simple/sql] How many distinct accounts are there? — scalar mismatch expected=1400 actual=4000
- `sb07` [subscriptions/medium/sql] What is the total mrr by plan? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Enterprise' actual=40765977.3; row[0].c1 expected=29834552.54 actual=None
- `sb08` [subscriptions/medium/sql] Which industry has the highest total mrr? — scalar mismatch expected=7257266.989999998 actual=40765977.29999991
- `sb09` [subscriptions/medium/sql] What is the average usage_hours by plan? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Starter' actual=447.285825; row[0].c1 expected=452.204125 actual=None
- `sb10` [subscriptions/medium/sql] How many accounts churned? — scalar mismatch expected=341 actual=4000
- `sb11` [subscriptions/medium/sql] What is the total mrr for the Enterprise plan? — scalar mismatch expected=29834552.539999973 actual=40765977.29999991
- `sb12` [subscriptions/medium/sql] What are the top 3 industries by total mrr? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Logistics' actual=40765977.3; row[0].c1 expected=7257266.99 actual=None
- `sb13` [subscriptions/medium/sql] What is the average support_tickets by industry? — row_count expected=6 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Retail' actual=12.42175; row[0].c1 expected=12.70743 actual=None
- `sb14` [subscriptions/advanced/sql] What is the monthly mrr trend? — no SQL generated (unsupported_schema)
- `sb15` [subscriptions/advanced/sql] What is the churn rate by plan? — no SQL generated (unsupported_schema)
- `sb16` [subscriptions/advanced/sql] Which plans have above-average mrr? — scalar mismatch expected=29834552.539999973 actual=10191.494324999976
- `sb17` [subscriptions/advanced/sql] Which industries have below-average nps? — row_count expected=4 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Fintech' actual=-1.11625; row[0].c1 expected=-4.080916 actual=None
- `sb18` [subscriptions/advanced/sql] Which industries have at least 600 records? — no SQL generated (unsupported_domain)
- `sb20` [subscriptions/advanced/sql] What is the average mrr per seat by plan? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Enterprise' actual=10191.494325; row[0].c1 expected=1193.19 actual=None
- `sb21` [subscriptions/advanced/sql] What is the total mrr by year? — row_count expected=3 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected=2023 actual=40765977.3; row[0].c1 expected=17817871.1 actual=None
- `sb22` [subscriptions/expert/sql] What are the top 3 industries by mrr within each plan? — row_count expected=15 actual=3; columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected='Education' actual=29834552.54; row[0].c2 expected=5203699.77 actual=None
- `sb23` [subscriptions/expert/sql] Which industries have above-average mrr but below-average nps? — row_count expected=2 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Logistics' actual=10191.494325; row[0].c1 expected=7257266.99 actual=None; row[0].c2 expected=-1.743338 actual=None
- `sb24` [subscriptions/expert/sql] Which plans with at least 700 records have the highest churn rate? — no SQL generated (unsupported_domain)
- `sb25` [subscriptions/expert/sql] What is each plan's share of total mrr? — row_count expected=5 actual=1; columns expected=['c0', 'c1'] actual=['c0']; row[0].c0 expected='Enterprise' actual=40765977.3; row[0].c1 expected=73.18 actual=None
- `sb26` [subscriptions/expert/sql] Compare mrr between churned and retained accounts by plan — columns expected=['c0', 'c1', 'c2'] actual=['c0', 'c1']; row[0].c1 expected=2400634.41 actual=29834552.54; row[0].c2 expected=27433918.13 actual=None
- `sb27` [subscriptions/expert/sql] Compare total mrr between 2023 and 2024 by plan — row_count expected=5 actual=1; columns expected=['c0', 'c1', 'c2'] actual=['c0']; row[0].c0 expected='Enterprise' actual=40765977.3; row[0].c1 expected=12979868.23 actual=None; row[0].c2 expected=11906207.19 actual=None
- `sb28` [subscriptions/medium/paraphrase] Which plans bring in the most recurring revenue? — no SQL generated (unsupported_schema)

## Notes

- Ground truth SQL is independent of the pipeline and runs in DuckDB.
- `deterministic` mode measures the pattern library + analytics fallback.
- It does **not** claim full LLM-path accuracy; that requires `--mode pipeline`
  with a live provider.
- Abstention and ambiguity are scored as correct when the system declines
  rather than inventing an answer.
