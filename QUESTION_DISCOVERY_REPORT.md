# Question Discovery Benchmark

Dataset-aware question discovery across 8 datasets. Every displayed question is
schema-checked, SQL-validated and proven by read-only DuckDB execution before display.

## Totals

- Advanced questions validated (benchmark bank): **76**
- Expert questions validated (benchmark bank): **43**
- Advanced questions shown in UI: **31**
- Expert questions shown in UI: **17**
- Schema-valid displayed questions: **100.0%**
- Advanced/expert pattern execution success: **100.0%**
- Discovery latency (cold) p50 / max: **31.78 ms / 47.54 ms**

## Per dataset

| Dataset | Rows | Cols | Band | Quick | Analytics | Advanced | Expert | Schema valid | Cold ms | Warm ms |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_sales | 900 | 9 | rich | 3 | 3 | 5 | 3 | 100.0% | 47.54 | 6.12 |
| B_employees | 400 | 7 | moderate | 3 | 3 | 4 | 2 | 100.0% | 26.3 | 4.35 |
| C_products | 500 | 8 | moderate | 4 | 2 | 4 | 2 | 100.0% | 39.76 | 5.22 |
| D_customers | 600 | 8 | rich | 3 | 3 | 5 | 3 | 100.0% | 37.89 | 5.24 |
| E_financial | 700 | 8 | rich | 3 | 3 | 5 | 3 | 100.0% | 37.26 | 5.53 |
| F_timeseries | 730 | 5 | moderate | 3 | 3 | 4 | 2 | 100.0% | 18.27 | 3.44 |
| G_small | 4 | 2 | minimal | 3 | 2 | 0 | 0 | 100.0% | 5.7 | 1.39 |
| H_messy | 120 | 5 | moderate | 3 | 3 | 4 | 2 | 100.0% | 17.83 | 3.56 |

## Advanced question bank (validated)

- `A_sales` — Which region values have total revenue above the overall average?
- `A_sales` — Which region values have total profit above the overall average?
- `A_sales` — Which category values have total revenue above the overall average?
- `A_sales` — Which category values have total profit above the overall average?
- `A_sales` — What percentage of total revenue comes from the top 10 region values?
- `A_sales` — What percentage of total revenue comes from the top 10 category values?
- `A_sales` — Among region values with at least 5 records, which are the top 10 by total revenue?
- `A_sales` — Among category values with at least 5 records, which are the top 10 by total revenue?
- `A_sales` — Which category values have total revenue above their own region average?
- `A_sales` — How did total revenue change year over year?
- `A_sales` — How does total revenue split across region, and what share does each represent?
- `B_employees` — Which department values have total salary above the overall average?
- `B_employees` — Which location values have total salary above the overall average?
- `B_employees` — What percentage of total salary comes from the top 10 department values?
- `B_employees` — What percentage of total salary comes from the top 10 location values?
- `B_employees` — Among department values with at least 5 records, which are the top 10 by total salary?
- `B_employees` — Among location values with at least 5 records, which are the top 10 by total salary?
- `B_employees` — Which location values have total salary above their own department average?
- `B_employees` — How did total salary change year over year?
- `B_employees` — How does total salary split across department, and what share does each represent?
- `C_products` — Which category values have total units sold above the overall average?
- `C_products` — Which category values have total stock above the overall average?
- `C_products` — Which brand values have total units sold above the overall average?
- `C_products` — Which brand values have total stock above the overall average?
- `C_products` — What percentage of total units sold comes from the top 10 category values?
- `C_products` — What percentage of total units sold comes from the top 10 brand values?
- `C_products` — Among category values with at least 5 records, which are the top 10 by total units sold?
- `C_products` — Among brand values with at least 5 records, which are the top 10 by total units sold?
- `C_products` — Which category values have above-average units sold but below-average stock?
- `C_products` — Which brand values have above-average units sold but below-average stock?
- `C_products` — Which brand values have total units sold above their own category average?
- `C_products` — How does total units sold split across category, and what share does each represent?
- `D_customers` — Which country values have total total spend above the overall average?
- `D_customers` — Which country values have total orders above the overall average?
- `D_customers` — Which segment values have total total spend above the overall average?
- `D_customers` — Which segment values have total orders above the overall average?
- `D_customers` — What percentage of total total spend comes from the top 10 country values?
- `D_customers` — What percentage of total total spend comes from the top 10 segment values?
- `D_customers` — Among country values with at least 5 records, which are the top 10 by total total spend?
- `D_customers` — Among segment values with at least 5 records, which are the top 10 by total total spend?

## Expert question bank (validated)

- `A_sales` — Which region values increased revenue year over year while profit declined?
- `A_sales` — In the latest year, which are the top 10 region values by revenue, and what share of that year's total do they represent?
- `A_sales` — What are the top 3 category values by revenue within each region, excluding those with fewer than 5 records?
- `A_sales` — For each region, which category has the highest revenue, and what percentage of that region's total does it represent?
- `A_sales` — Which region values together account for the first 80% of cumulative revenue?
- `A_sales` — Which category values together account for the first 80% of cumulative revenue?
- `B_employees` — In the latest year, which are the top 10 department values by salary, and what share of that year's total do they represent?
- `B_employees` — What are the top 3 location values by salary within each department, excluding those with fewer than 5 records?
- `B_employees` — For each department, which location has the highest salary, and what percentage of that department's total does it represent?
- `B_employees` — Which department values together account for the first 80% of cumulative salary?
- `B_employees` — Which location values together account for the first 80% of cumulative salary?
- `C_products` — What are the top 3 brand values by units sold within each category, excluding those with fewer than 5 records?
- `C_products` — For each category, which brand has the highest units sold, and what percentage of that category's total does it represent?
- `C_products` — Which category values together account for the first 80% of cumulative units sold?
- `C_products` — Which brand values together account for the first 80% of cumulative units sold?
- `C_products` — Which brand values rank in the top 20% of units sold within their category but have below-category-average stock?
- `C_products` — Among category values with at least 5 records, which have above-average units sold and below-average stock, ranked by total units sold?
- `C_products` — Among brand values with at least 5 records, which have above-average units sold and below-average stock, ranked by total units sold?
- `D_customers` — Which country values increased total spend year over year while orders declined?
- `D_customers` — In the latest year, which are the top 10 country values by total spend, and what share of that year's total do they represent?
- `D_customers` — What are the top 3 segment values by total spend within each country, excluding those with fewer than 5 records?
- `D_customers` — For each country, which segment has the highest total spend, and what percentage of that country's total does it represent?
- `D_customers` — Which country values together account for the first 80% of cumulative total spend?
- `D_customers` — Which segment values together account for the first 80% of cumulative total spend?
- `D_customers` — Which segment values rank in the top 20% of total spend within their country but have below-country-average orders?
- `D_customers` — Among country values with at least 5 records, which have above-average total spend and below-average orders, ranked by total total spend?
- `D_customers` — Among segment values with at least 5 records, which have above-average total spend and below-average orders, ranked by total total spend?
- `E_financial` — Which business unit values increased revenue year over year while profit declined?
- `E_financial` — In the latest year, which are the top 10 business unit values by revenue, and what share of that year's total do they represent?
- `E_financial` — What are the top 3 cost center values by revenue within each business unit, excluding those with fewer than 5 records?
- `E_financial` — For each business unit, which cost center has the highest revenue, and what percentage of that business unit's total does it represent?
- `E_financial` — Which business unit values together account for the first 80% of cumulative revenue?
- `E_financial` — Which cost center values together account for the first 80% of cumulative revenue?
- `E_financial` — Which cost center values rank in the top 20% of revenue within their business unit but have below-business unit-average profit?
- `E_financial` — Among cost center values with at least 5 records, which have above-average revenue and below-average profit, ranked by total revenue?
- `F_timeseries` — In the latest year, which are the top 10 site values by output units, and what share of that year's total do they represent?
- `F_timeseries` — Which site values together account for the first 80% of cumulative output units?
- `G_small` — Which name values together account for the first 80% of cumulative age?
- `H_messy` — In the latest year, which are the top 10 Region values by rev, and what share of that year's total do they represent?
- `H_messy` — What are the top 3 Prod Name values by rev within each Region, excluding those with fewer than 5 records?

## Execution failures

- None
