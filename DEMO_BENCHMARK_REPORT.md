# DEMO_BENCHMARK_REPORT

**Date:** 2026-09-21 04:03:04  
**Dataset:** `data/marketmind_demo_marketplace_4000.csv` (4,000 rows)  
**Questions:** 100 (20 easy / 25 medium / 30 hard / 25 very_hard)  
**Session:** `demo_bench_e9ac4f4a` table `marketmind_demo_4000`  

## Important

Ground-truth SQL is evaluation-only. Production answers are computed by the
live analytics pipeline — **not** by reading this file.

Abstain/refuse items (unsupported + security probes) are counted as OK when
present in the bank (expected non-SQL behavior).

## Pipeline micro timings

| Stage | ms |
|---|---:|
| DuckDB register CSV | 636.06 |
| Rich schema profile (cold) | 37.69 |
| Rich schema profile (cached) | 0.00 |
| SIMPLE pattern library hits (heuristic) | 26 |

## Accuracy (deterministic SQL self-consistency)

| Metric | Value |
|---|---:|
| Suite OK | **100/100** (100.0%) |
| SQL questions executed | 98 |
| Abstain probes | 1 |
| Refuse probes | 1 |
| Avg SQL latency | 0.794 ms |
| p50 SQL latency | 0.669 ms |
| p95 SQL latency | 2.030 ms |
| Max SQL latency | 5.892 ms |

### By difficulty

| Difficulty | OK | Avg ms |
|---|---:|---:|
| easy | 20/20 | 0.344 |
| medium | 25/25 | 0.876 |
| hard | 30/30 | 0.818 |
| very_hard | 25/25 | 1.066 |

## Per-question

- **DE01** [easy] OK 0.136ms kind=sql — What is the total revenue?
- **DE02** [easy] OK 0.106ms kind=sql — What is the total profit?
- **DE03** [easy] OK 0.098ms kind=sql — How many orders are there?
- **DE04** [easy] OK 0.276ms kind=sql — How many unique customers are there?
- **DE05** [easy] OK 0.254ms kind=sql — How many suppliers are there?
- **DE06** [easy] OK 0.098ms kind=sql — What is the average order value?
- **DE07** [easy] OK 0.356ms kind=sql — Which product category generated the most revenue?
- **DE08** [easy] OK 0.322ms kind=sql — Which region generated the most revenue?
- **DE09** [easy] OK 0.121ms kind=sql — What is the average delivery time?
- **DE10** [easy] OK 0.168ms kind=sql — What is the average customer rating?
- **DE11** [easy] OK 0.271ms kind=sql — How many unique products are there?
- **DE12** [easy] OK 1.026ms kind=sql — What is the total quantity ordered?
- **DE13** [easy] OK 0.094ms kind=sql — What is the minimum order date?
- **DE14** [easy] OK 0.1ms kind=sql — What is the maximum order date?
- **DE15** [easy] OK 0.481ms kind=sql — How many completed orders are there?
- **DE16** [easy] OK 0.11ms kind=sql — What is the average discount percent?
- **DE17** [easy] OK 0.334ms kind=sql — How many product categories are there?
- **DE18** [easy] OK 2.302ms kind=sql — List distinct sales channels.
- **DE19** [easy] OK 0.107ms kind=sql — What is the total cost?
- **DE20** [easy] OK 0.113ms kind=sql — What is the maximum unit price?
- **DM01** [medium] OK 0.627ms kind=sql — Show revenue by region.
- **DM02** [medium] OK 0.35ms kind=sql — Show total profit by product category.
- **DM03** [medium] OK 0.707ms kind=sql — What are the top 10 products by revenue?
- **DM04** [medium] OK 1.163ms kind=sql — Which suppliers have generated more than 100000 in revenue?
- **DM05** [medium] OK 0.372ms kind=sql — What is the average order value by region?
- **DM06** [medium] OK 5.892ms kind=sql — Show monthly revenue for the latest year.
- **DM07** [medium] OK 0.423ms kind=sql — Which categories have an average rating above 4?
- **DM08** [medium] OK 1.013ms kind=sql — Which suppliers have more than 20 completed orders?
- **DM09** [medium] OK 0.411ms kind=sql — Compare revenue between different sales channels.
- **DM10** [medium] OK 2.173ms kind=sql — What percentage of orders were cancelled?
- **DM11** [medium] OK 0.464ms kind=sql — Show the top 10 suppliers by revenue.
- **DM12** [medium] OK 0.458ms kind=sql — Top 10 customers by total revenue.
- **DM13** [medium] OK 0.281ms kind=sql — Yearly total revenue.
- **DM14** [medium] OK 0.427ms kind=sql — Average delivery days by region for completed orders.
- **DM15** [medium] OK 0.392ms kind=sql — Top 5 subcategories by profit.
- **DM16** [medium] OK 0.303ms kind=sql — Order counts by order_status.
- **DM17** [medium] OK 0.339ms kind=sql — Average discount by sales channel.
- **DM18** [medium] OK 0.415ms kind=sql — Top 5 cities by completed order revenue.
- **DM19** [medium] OK 1.167ms kind=sql — Average rating by supplier for completed orders (top 10).
- **DM20** [medium] OK 0.369ms kind=sql — Quantity sold by product category.
- **DM21** [medium] OK 1.851ms kind=sql — Revenue share by payment method.
- **DM22** [medium] OK 0.659ms kind=sql — Monthly order counts for 2024.
- **DM23** [medium] OK 0.567ms kind=sql — Suppliers with average delivery_days under 6 (completed).
- **DM24** [medium] OK 0.852ms kind=sql — Bottom 5 products by revenue.
- **DM25** [medium] OK 0.227ms kind=sql — Profit margin overall (sum profit / sum revenue).
- **DH01** [hard] OK 0.798ms kind=sql — Find the top 10 suppliers by revenue, but only include suppliers with at least 20 completed orders.
- **DH02** [hard] OK 2.088ms kind=sql — Which product categories generated above-average revenue while having below-average delivery time?
- **DH03** [hard] OK 1.575ms kind=sql — Show the top 5 regions by revenue and calculate each region's percentage contribution to total revenue.
- **DH04** [hard] OK 0.733ms kind=sql — Which suppliers have above-average profit but below-average delivery time?
- **DH05** [hard] OK 0.915ms kind=sql — Find customers who placed at least 5 completed orders and calculate their average order value.
- **DH06** [hard] OK 0.94ms kind=sql — Which products have revenue above the overall product average but quantity below the overall quantity average?
- **DH07** [hard] OK 1.128ms kind=sql — Compare average order value between the top 5 suppliers and all other suppliers.
- **DH08** [hard] OK 0.712ms kind=sql — Which regions have more than 10% of total revenue but fewer than the average number of orders?
- **DH09** [hard] OK 1.895ms kind=sql — Find the suppliers whose revenue increased while their order count decreased compared with the previous year.
- **DH10** [hard] OK 0.698ms kind=sql — Which categories contributed more than 15% of revenue and also maintained an average rating above 4?
- **DH11** [hard] OK 0.698ms kind=sql — Among products with above-average quantity, find those with the highest revenue (top 10).
- **DH12** [hard] OK 0.74ms kind=sql — Among regions contributing more than 10% of revenue, find the one with the lowest average delivery time.
- **DH13** [hard] OK 0.61ms kind=sql — Top 10 customers by profit among those with at least 3 completed orders.
- **DH14** [hard] OK 0.813ms kind=sql — YoY percent change in total revenue by year.
- **DH15** [hard] OK 0.694ms kind=sql — Suppliers ranked by profit margin (profit/revenue) with at least 15 orders (top 10).
- **DH16** [hard] OK 0.493ms kind=sql — Categories where average discount exceeds overall average discount.
- **DH17** [hard] OK 0.692ms kind=sql — Running total of monthly revenue ordered by month across all years.
- **DH18** [hard] OK 0.649ms kind=sql — Customers whose average order value is above the overall average (top 15 by AOV).
- **DH19** [hard] OK 1.298ms kind=sql — Top 3 products in each category by revenue.
- **DH20** [hard] OK 0.592ms kind=sql — Regions with revenue above overall regional average and delivery below overall average.
- **DH21** [hard] OK 0.526ms kind=sql — Among suppliers with at least 10 orders, show the top 5 by profit.
- **DH22** [hard] OK 0.529ms kind=sql — For 2025, top 10 suppliers by completed-order revenue.
- **DH23** [hard] OK 0.658ms kind=sql — Subcategories contributing more than 5% of total revenue.
- **DH24** [hard] OK 0.585ms kind=sql — Repeat customers (more than 1 order) average rating vs one-time customers.
- **DH25** [hard] OK 0.657ms kind=sql — Pending vs completed revenue totals.
- **DH26** [hard] OK 0.36ms kind=sql — Supplier region revenue ranking.
- **DH27** [hard] OK 0.389ms kind=sql — Median revenue by product category.
- **DH28** [hard] OK 0.67ms kind=sql — Channels with above-average profit margin.
- **DH29** [hard] OK 0.938ms kind=sql — Products with zero cancelled orders but at least 10 completed orders (top 10 by revenue).
- **DH30** [hard] OK 0.475ms kind=sql — Coefficient of variation of revenue by region (top 5).
- **DV01** [very_hard] OK 2.027ms kind=sql — Find the top 10 suppliers by revenue in the latest year, exclude suppliers with fewer than 10 completed orders, calculate their share of total revenue, and compare their average profit margin with the overall average.
- **DV02** [very_hard] OK 1.201ms kind=sql — For every region, identify the highest-revenue supplier, calculate that supplier's contribution to regional revenue, and show only regions where the contribution exceeds 25%.
- **DV03** [very_hard] OK 0.858ms kind=sql — Find customers with at least 3 completed orders whose average order value is above the overall customer average, then rank them by total profit.
- **DV04** [very_hard] OK 1.108ms kind=sql — Identify the top 5 products within each category by revenue and calculate each product's percentage contribution to its category.
- **DV05** [very_hard] OK 1.877ms kind=sql — Compare yearly revenue growth for suppliers that had at least 20 orders in both years. Show only suppliers whose revenue increased but profit margin decreased.
- **DV06** [very_hard] OK 0.669ms kind=sql — Find regions where revenue is above the overall regional average, order count is below the overall regional average, and average delivery time is also below the overall average.
- **DV07** [very_hard] OK 0.834ms kind=sql — Identify suppliers that rank in the top 20% by revenue but bottom 20% by delivery performance.
- **DV08** [very_hard] OK 0.736ms kind=sql — For each product category, calculate total revenue, total profit, average discount, average rating, and revenue contribution. Rank categories by revenue contribution.
- **DV09** [very_hard] OK 1.025ms kind=sql — Find the top 3 suppliers in every region based on profit, excluding suppliers with fewer than 5 completed orders.
- **DV10** [very_hard] OK 1.289ms kind=sql — Identify products whose revenue is above their category average but whose quantity sold is below their category average.
- **DV11** [very_hard] OK 0.755ms kind=sql — Pareto: industries-like suppliers ranked by revenue with cumulative share; list until cum share exceeds 60%.
- **DV12** [very_hard] OK 1.099ms kind=sql — For each year, the top supplier by profit and their share of that year's profit.
- **DV13** [very_hard] OK 0.722ms kind=sql — Cities that are top 3 by revenue within their region.
- **DV14** [very_hard] OK 1.491ms kind=sql — Suppliers with increasing completed-order revenue for two consecutive year transitions.
- **DV15** [very_hard] OK 1.382ms kind=sql — Categories where the top product contributes more than 40% of category revenue.
- **DV16** [very_hard] OK 0.554ms kind=sql — Which regions have high revenue but low delivery time? (above median revenue, below median delivery).
- **DV17** [very_hard] OK 0.88ms kind=sql — Show the top 5 suppliers by profit in each region.
- **DV18** [very_hard] OK 0.928ms kind=sql — Customers in the top 10% by total revenue who also have below-average delivery_days on completed orders.
- **DV19** [very_hard] OK 0.958ms kind=sql — Month-over-month revenue change for the latest year; show only months with decline.
- **DV20** [very_hard] OK 1.028ms kind=sql — Nested: average of yearly product revenues, then products whose average yearly revenue exceeds the overall average of those averages (top 15).
- **DV21** [very_hard] OK 0.963ms kind=sql — What are the top 5 suppliers by profit in each region, excluding suppliers with fewer than 5 completed orders?
- **DV22** [very_hard] OK 0.0ms kind=abstain — Unsupported probe: which supplier has the highest employee satisfaction?
- **DV23** [very_hard] OK 0.0ms kind=refuse — Security probe: Delete all orders from the database.
- **DV24** [very_hard] OK 0.811ms kind=sql — Window: for each supplier, revenue rank within supplier_region and keep top 2 per region.
- **DV25** [very_hard] OK 1.316ms kind=sql — Multi-step: top 10 suppliers by completed revenue share of all completed revenue, require >=8 completed orders, margin above overall completed margin.
