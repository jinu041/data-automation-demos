"""Make the fictional sales data for the Power BI demo and print the numbers the dashboard must show.

The business (a small coffee roaster selling online, wholesale and to cafes) and every row are made up.

    python make_data.py          writes data/sales.csv and data/expected.json
"""
import csv, json, random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
random.seed(2025)

# product: (category, unit price, unit cost)
PRODUCTS = {
    "House Blend 1kg": ("Beans", 24.0, 13.5),
    "Single Origin 1kg": ("Beans", 34.0, 19.0),
    "Decaf 1kg": ("Beans", 27.0, 15.5),
    "Espresso Blend 1kg": ("Beans", 26.0, 14.0),
    "Pour-over Kit": ("Equipment", 45.0, 27.0),
    "Burr Grinder": ("Equipment", 119.0, 78.0),
    "Logo Mug": ("Merch", 14.0, 6.0),
    "Tote Bag": ("Merch", 18.0, 7.5),
}
REGIONS = {"North": 1.0, "South": 0.8, "East": 1.2, "West": 0.9}
CHANNELS = {"Online": 1.0, "Wholesale": 0.6, "Cafe": 0.5}
UNITS = {"Online": (1, 3), "Wholesale": (6, 30), "Cafe": (3, 12)}
SEASON = [0.8, 0.75, 0.9, 0.95, 1.0, 0.9, 0.85, 0.9, 1.0, 1.1, 1.3, 1.6]  # Jan..Dec


def rows():
    out, n = [], 10000
    day = date(2025, 1, 1)
    while day.year == 2025:
        for _ in range(max(0, round(random.gauss(5 * SEASON[day.month - 1], 1.5)))):
            n += 1
            region = random.choices(list(REGIONS), weights=REGIONS.values())[0]
            channel = random.choices(list(CHANNELS), weights=CHANNELS.values())[0]
            for product in random.sample(list(PRODUCTS), random.choice([1, 1, 2, 3])):
                category, price, cost = PRODUCTS[product]
                if channel == "Wholesale" and category == "Equipment":
                    continue  # wholesale buyers only take beans and merch
                units = random.randint(*UNITS[channel])
                if channel != "Online":
                    price = round(price * 0.85, 2)  # trade price
                out.append({
                    "OrderID": f"SO-{n}", "OrderDate": day.isoformat(), "Month": day.strftime("%Y-%m"),
                    "Region": region, "Channel": channel, "Category": category, "Product": product,
                    "Units": units, "UnitPrice": price, "UnitCost": cost,
                    "Revenue": round(units * price, 2), "Cost": round(units * cost, 2),
                })
        day += timedelta(days=1)
    return out


def expected(data):
    rev = sum(r["Revenue"] for r in data)
    cost = sum(r["Cost"] for r in data)
    orders = len({r["OrderID"] for r in data})
    by = lambda key: {k: round(v, 2) for k, v in sorted(_sum(data, key).items())}
    return {
        "rows": len(data), "revenue": round(rev, 2), "gross_margin_pct": round(100 * (rev - cost) / rev, 1),
        "orders": orders, "avg_order_value": round(rev / orders, 2),
        "revenue_by_month": by("Month"), "revenue_by_category": by("Category"),
        "revenue_by_channel": by("Channel"), "revenue_by_region": by("Region"),
    }


def _sum(data, key):
    acc = defaultdict(float)
    for r in data:
        acc[r[key]] += r["Revenue"]
    return acc


if __name__ == "__main__":
    data = rows()
    assert all(r["Revenue"] > 0 and r["Cost"] < r["Revenue"] for r in data)
    (HERE / "data").mkdir(exist_ok=True)
    with open(HERE / "data" / "sales.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)
    exp = expected(data)
    (HERE / "data" / "expected.json").write_text(json.dumps(exp, indent=2), encoding="utf-8")
    print(f"{exp['rows']:,} rows, {exp['orders']:,} orders, revenue ${exp['revenue']:,.2f}, "
          f"margin {exp['gross_margin_pct']}%, AOV ${exp['avg_order_value']:,.2f}")
