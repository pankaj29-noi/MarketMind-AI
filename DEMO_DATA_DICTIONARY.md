# DEMO_DATA_DICTIONARY — marketmind_demo_marketplace_4000.csv

**Dataset:** `data/marketmind_demo_marketplace_4000.csv`  
**Rows:** 4,000 (synthetic B2B marketplace orders)  
**Grain:** one row = one order line / order event  
**Purpose:** Universal analytics demo — questions execute through the real MarketMind pipeline (no hardcoded answers).

## Column dictionary

| Column | Type | Meaning | Example | Business interpretation |
|---|---|---|---|---|
| `order_id` | string | Unique order identifier | `ORD-00042` | Primary key for the order event |
| `order_date` | date (ISO) | Order placement date | `2024-06-15` | Time dimension for trends / YoY |
| `customer_id` | string | Buyer / customer key | `CUST-0012` | Customer entity id |
| `customer_name` | string | Buyer display name | `Alpha Corp 12` | Human-readable customer |
| `customer_region` | string | Customer territory | `West` | Geographic dimension (region/territory) |
| `customer_city` | string | Customer city | `Mumbai` | City within region |
| `supplier_id` | string | Vendor / supplier key | `SUP-007` | Supplier entity id |
| `supplier_name` | string | Supplier display name | `Apex Industries 7` | Human-readable supplier / vendor |
| `supplier_region` | string | Supplier home region | `West` | Supplier geography |
| `product_id` | string | Product SKU key | `PROD-0015` | Product entity id |
| `product_name` | string | Product display name | `Sensors Model 2` | Human-readable product |
| `product_category` | string | Top-level category | `Electronics` | Category dimension |
| `product_subcategory` | string | Sub-category | `Sensors` | Finer product taxonomy |
| `quantity` | integer | Units ordered | `12` | Quantity measure |
| `unit_price` | float | Price per unit before discount | `249.50` | Unit list price |
| `discount_percent` | float | Discount applied (%) | `10.0` | Discount rate on the line |
| `revenue` | float | Line revenue after discount | `2694.60` | `quantity × unit_price × (1 − discount_percent/100)`; cancelled lines may be zeroed/partial |
| `cost` | float | Cost of goods for the line | `1800.00` | Cost basis for margin |
| `profit` | float | Line profit | `894.60` | `revenue − cost` (cancelled lines use a loss/partial definition) |
| `order_status` | string | Order lifecycle state | `completed` | One of `completed`, `pending`, `cancelled` |
| `payment_method` | string | How the order was paid | `Net-30` | Payment dimension |
| `sales_channel` | string | Sales channel | `Online` | Channel dimension |
| `delivery_days` | integer / NULL | Days from order to delivery | `7` | Present mainly for `completed`; NULL for pending/cancelled |
| `rating` | float / NULL | Customer rating (1–5) | `4.3` | Order satisfaction; may be NULL |

## Semantic aliases (for NL understanding)

| User language | Maps to columns (when evidence supports) |
|---|---|
| revenue / sales / sales value / turnover / GMV | `revenue` |
| profit / earnings | `profit` |
| customers / buyers / clients | `customer_id` / `customer_name` |
| suppliers / vendors | `supplier_id` / `supplier_name` |
| orders / transactions | rows / `order_id` |
| region / territory | `customer_region` |
| category | `product_category` |
| average order value (AOV) | typically `AVG(revenue)` (often filtered to completed) |

## Baseline deterministic metrics (seed=42 generation)

See `data/marketmind_demo_marketplace_4000_stats.json`:

- Date range: 2023-01-01 → 2025-12-31  
- Unique customers: 300  
- Unique suppliers: 60  
- Unique products: 80  
- Regions: Central, East, North, South, West  
- Categories: Electronics, Industrial Equipment, Logistics Services, Packaging, Raw Materials  
- Status mix: completed / pending / cancelled (see stats JSON)

## Notes

- Synthetic only — no real PII.  
- Revenue formula holds for non-cancelled rows; cancelled rows intentionally vary to reflect real-world messy ERP exports.  
- Ground-truth SQL for benchmarks lives under `backend/benchmarks/` and is **never** injected into the production LLM path.
