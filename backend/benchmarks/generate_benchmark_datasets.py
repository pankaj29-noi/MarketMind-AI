"""Generate the benchmark dataset family.

Four schemas beyond the marketplace demo, each 3,000-4,000 rows, so accuracy cannot
be achieved by overfitting one column layout. Seeded, so ground truth is stable.

Usage: python -m backend.benchmarks.generate_benchmark_datasets
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List

OUT_DIR = Path("data/benchmark")
SEED = 20260921


def _dates(n: int, rng: random.Random, start: date, span_days: int) -> List[str]:
    return [(start + timedelta(days=rng.randrange(span_days))).isoformat() for _ in range(n)]


def retail_sales(rng: random.Random, rows: int = 3600) -> List[Dict]:
    """Retail transactions. Concepts: store, category, units, net_sales, returns."""
    stores = [f"Store {i:02d}" for i in range(1, 19)]
    regions = ["East", "West", "North", "South"]
    store_region = {s: regions[i % len(regions)] for i, s in enumerate(stores)}
    categories = ["Grocery", "Apparel", "Electronics", "Home", "Beauty", "Toys"]
    channels = ["In-Store", "Online", "Curbside"]
    out = []
    for i, day in enumerate(_dates(rows, rng, date(2023, 1, 1), 730)):
        store = rng.choice(stores)
        category = rng.choice(categories)
        units = rng.randint(1, 40)
        unit_cost = round(rng.uniform(3, 220), 2)
        markup = rng.uniform(1.15, 2.1)
        net_sales = round(units * unit_cost * markup, 2)
        returned = rng.random() < 0.07
        out.append(
            {
                "txn_id": f"T{100000 + i}",
                "txn_date": day,
                "store": store,
                "store_region": store_region[store],
                "category": category,
                "channel": rng.choice(channels),
                "units": units,
                "unit_cost": unit_cost,
                "net_sales": net_sales,
                "cogs": round(units * unit_cost, 2),
                "returned": "yes" if returned else "no",
                "loyalty_member": "yes" if rng.random() < 0.45 else "no",
            }
        )
    return out


def employees(rng: random.Random, rows: int = 3200) -> List[Dict]:
    """HR records. Concepts: department, salary, tenure, performance, attrition."""
    departments = ["Engineering", "Sales", "Support", "Finance", "Marketing", "Operations"]
    levels = ["Junior", "Mid", "Senior", "Lead", "Principal"]
    level_base = {"Junior": 55000, "Mid": 82000, "Senior": 118000, "Lead": 148000, "Principal": 186000}
    sites = ["Bengaluru", "Pune", "Berlin", "Austin", "Toronto"]
    out = []
    for i, hire in enumerate(_dates(rows, rng, date(2015, 1, 1), 3650)):
        level = rng.choice(levels)
        dept = rng.choice(departments)
        out.append(
            {
                "employee_id": f"E{20000 + i}",
                "hire_date": hire,
                "department": dept,
                "job_level": level,
                "site": rng.choice(sites),
                "salary": round(level_base[level] * rng.uniform(0.85, 1.25), 0),
                "bonus_pct": round(rng.uniform(0, 22), 2),
                "performance_score": round(rng.uniform(1.0, 5.0), 2),
                "tenure_years": round(rng.uniform(0.2, 11.0), 1),
                "training_hours": rng.randint(0, 120),
                "attrition": "yes" if rng.random() < 0.18 else "no",
                "remote": "yes" if rng.random() < 0.38 else "no",
            }
        )
    return out


def products(rng: random.Random, rows: int = 3000) -> List[Dict]:
    """Product catalogue. Concepts: brand, price, margin, stock, rating, returns."""
    brands = [f"Brand {chr(65 + i)}" for i in range(12)]
    categories = ["Tools", "Lighting", "Fasteners", "Safety", "Adhesives", "Measuring"]
    suppliers = [f"Vendor {i:02d}" for i in range(1, 26)]
    out = []
    for i, launch in enumerate(_dates(rows, rng, date(2019, 1, 1), 2200)):
        cost = round(rng.uniform(2, 400), 2)
        price = round(cost * rng.uniform(1.1, 2.6), 2)
        out.append(
            {
                "sku": f"SKU{50000 + i}",
                "launch_date": launch,
                "brand": rng.choice(brands),
                "category": categories[i % len(categories)],
                "vendor": rng.choice(suppliers),
                "list_price": price,
                "unit_cost": cost,
                "gross_margin": round(price - cost, 2),
                "stock_on_hand": rng.randint(0, 1800),
                "units_sold_ytd": rng.randint(0, 5200),
                "avg_rating": round(rng.uniform(2.0, 5.0), 2),
                "review_count": rng.randint(0, 900),
                "discontinued": "yes" if rng.random() < 0.12 else "no",
            }
        )
    return out


def subscriptions(rng: random.Random, rows: int = 4000) -> List[Dict]:
    """Monthly subscription time series. Concepts: MRR, plan, churn, cohort."""
    plans = ["Free", "Starter", "Growth", "Scale", "Enterprise"]
    plan_mrr = {"Free": 0, "Starter": 29, "Growth": 99, "Scale": 349, "Enterprise": 1200}
    industries = ["Retail", "Fintech", "Health", "Logistics", "Education", "Media"]
    out = []
    for i in range(rows):
        month = date(2023, 1, 1) + timedelta(days=30 * rng.randrange(30))
        plan = rng.choice(plans)
        seats = rng.randint(1, 60)
        mrr = round(plan_mrr[plan] * seats * rng.uniform(0.9, 1.1), 2)
        out.append(
            {
                "account_id": f"A{9000 + (i % 1400)}",
                "month": month.replace(day=1).isoformat(),
                "plan": plan,
                "industry": rng.choice(industries),
                "seats": seats,
                "mrr": mrr,
                "support_tickets": rng.randint(0, 25),
                "nps": rng.randint(-100, 100),
                "usage_hours": round(rng.uniform(0, 900), 1),
                "churned": "yes" if rng.random() < 0.09 else "no",
            }
        )
    return out


GENERATORS: Dict[str, Callable[[random.Random], List[Dict]]] = {
    "retail_sales": retail_sales,
    "employees": employees,
    "products": products,
    "subscriptions": subscriptions,
}


def generate_all(out_dir: Path = OUT_DIR) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for name, fn in GENERATORS.items():
        rng = random.Random(f"{SEED}:{name}")
        rows = fn(rng)
        path = out_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        written[name] = path
        print(f"{name}: {len(rows)} rows x {len(rows[0])} cols -> {path}")
    return written


if __name__ == "__main__":
    generate_all()
