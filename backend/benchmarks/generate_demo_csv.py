#!/usr/bin/env python3
"""Regenerate data/marketmind_demo_marketplace_4000.csv (deterministic seed=42)."""
from __future__ import annotations

import json
import random
import csv
from datetime import date, timedelta
from pathlib import Path

SEED = 42
N_ROWS = 4000


def generate(out: Path) -> dict:
    random.seed(SEED)
    regions = ["North", "South", "East", "West", "Central"]
    cities = {
        "North": ["Delhi", "Chandigarh", "Jaipur", "Lucknow"],
        "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi"],
        "East": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati"],
        "West": ["Mumbai", "Pune", "Ahmedabad", "Surat"],
        "Central": ["Indore", "Bhopal", "Nagpur", "Raipur"],
    }
    categories = {
        "Industrial Equipment": ["Pump Systems", "Conveyors", "Compressors", "CNC Parts"],
        "Electronics": ["Sensors", "Controllers", "Cables", "Power Supplies"],
        "Raw Materials": ["Steel", "Polymers", "Chemicals", "Alloys"],
        "Packaging": ["Corrugated", "Films", "Labels", "Pallets"],
        "Logistics Services": ["Freight", "Warehousing", "Last Mile", "Cold Chain"],
    }
    statuses = [
        "completed",
        "completed",
        "completed",
        "completed",
        "pending",
        "cancelled",
        "completed",
    ]
    channels = ["Online", "Direct Sales", "Partner", "Marketplace"]
    payments = ["Credit Card", "Wire Transfer", "Net-30", "UPI", "Letter of Credit"]

    suppliers = []
    for i in range(1, 61):
        reg = regions[i % len(regions)]
        suppliers.append(
            {
                "supplier_id": f"SUP-{i:03d}",
                "supplier_name": (
                    f"{random.choice(['Apex','Nova','Prime','Zenith','Orbit','Summit'])} "
                    f"{random.choice(['Industries','Supplies','Trading','Manufacturing','Solutions'])} {i}"
                ),
                "supplier_region": reg,
            }
        )

    customers = []
    for i in range(1, 301):
        reg = regions[i % len(regions)]
        customers.append(
            {
                "customer_id": f"CUST-{i:04d}",
                "customer_name": (
                    f"{random.choice(['Alpha','Beta','Gamma','Delta','Echo','Foxtrot'])} "
                    f"{random.choice(['Corp','Ltd','Pvt Ltd','Enterprises','Group'])} {i}"
                ),
                "customer_region": reg,
                "customer_city": random.choice(cities[reg]),
            }
        )

    products = []
    pid = 1
    for cat, subs in categories.items():
        for sub in subs:
            for k in range(4):
                products.append(
                    {
                        "product_id": f"PROD-{pid:04d}",
                        "product_name": f"{sub} Model {k+1}",
                        "product_category": cat,
                        "product_subcategory": sub,
                        "base_price": round(random.uniform(50, 5000), 2),
                        "base_cost_ratio": random.uniform(0.55, 0.85),
                    }
                )
                pid += 1

    start = date(2023, 1, 1)
    span = (date(2025, 12, 31) - start).days
    cols = [
        "order_id",
        "order_date",
        "customer_id",
        "customer_name",
        "customer_region",
        "customer_city",
        "supplier_id",
        "supplier_name",
        "supplier_region",
        "product_id",
        "product_name",
        "product_category",
        "product_subcategory",
        "quantity",
        "unit_price",
        "discount_percent",
        "revenue",
        "cost",
        "profit",
        "order_status",
        "payment_method",
        "sales_channel",
        "delivery_days",
        "rating",
    ]
    rows = []
    for i in range(1, N_ROWS + 1):
        cust = random.choice(customers)
        if random.random() < 0.6:
            local = [s for s in suppliers if s["supplier_region"] == cust["customer_region"]]
            supp = random.choice(local or suppliers)
        else:
            supp = random.choice(suppliers)
        prod = random.choice(products)
        status = random.choice(statuses)
        qty = min(250, max(1, int(random.lognormvariate(1.2, 0.9))))
        unit_price = round(prod["base_price"] * random.uniform(0.9, 1.15), 2)
        discount = (
            round(random.choice([0, 0, 0, 5, 5, 10, 12, 15, 20]) + random.uniform(0, 2), 2)
            if random.random() < 0.45
            else 0.0
        )
        discount = min(discount, 30.0)
        revenue = round(qty * unit_price * (1 - discount / 100.0), 2)
        cost_unit = unit_price * prod["base_cost_ratio"] * random.uniform(0.95, 1.05)
        cost = round(qty * cost_unit, 2)
        if status == "cancelled":
            revenue = 0.0 if random.random() < 0.7 else round(revenue * 0.1, 2)
            profit = round(revenue - cost * 0.2, 2)
            delivery_days = ""
            rating = ""
        elif status == "pending":
            profit = round(revenue - cost, 2)
            delivery_days = ""
            rating = ""
        else:
            profit = round(revenue - cost, 2)
            delivery_days = min(45, max(1, int(random.gauss(7, 3))))
            rating = round(min(5.0, max(1.0, random.gauss(4.1, 0.7))), 1)
            if random.random() < 0.08:
                rating = ""
        d = start + timedelta(days=random.randint(0, span))
        rows.append(
            {
                "order_id": f"ORD-{i:05d}",
                "order_date": d.isoformat(),
                **cust,
                **{k: supp[k] for k in ("supplier_id", "supplier_name", "supplier_region")},
                "product_id": prod["product_id"],
                "product_name": prod["product_name"],
                "product_category": prod["product_category"],
                "product_subcategory": prod["product_subcategory"],
                "quantity": qty,
                "unit_price": unit_price,
                "discount_percent": discount,
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "order_status": status,
                "payment_method": random.choice(payments),
                "sales_channel": random.choice(channels),
                "delivery_days": delivery_days,
                "rating": rating,
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    import duckdb

    con = duckdb.connect()
    con.execute(f"CREATE TABLE orders AS SELECT * FROM read_csv_auto('{out}')")
    stats = {
        "path": str(out),
        "rows": con.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "columns": cols,
        "date_min": str(con.execute("SELECT MIN(order_date) FROM orders").fetchone()[0]),
        "date_max": str(con.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]),
        "unique_customers": con.execute(
            "SELECT COUNT(DISTINCT customer_id) FROM orders"
        ).fetchone()[0],
        "unique_suppliers": con.execute(
            "SELECT COUNT(DISTINCT supplier_id) FROM orders"
        ).fetchone()[0],
        "unique_products": con.execute(
            "SELECT COUNT(DISTINCT product_id) FROM orders"
        ).fetchone()[0],
        "regions": [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT customer_region FROM orders ORDER BY 1"
            ).fetchall()
        ],
        "categories": [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT product_category FROM orders ORDER BY 1"
            ).fetchall()
        ],
        "order_statuses": dict(
            con.execute(
                "SELECT order_status, COUNT(*) FROM orders GROUP BY 1 ORDER BY 1"
            ).fetchall()
        ),
        "seed": SEED,
    }
    stats_path = out.with_name(out.stem + "_stats.json")
    stats_path.write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    target = root / "data" / "marketmind_demo_marketplace_4000.csv"
    print(json.dumps(generate(target), indent=2))
