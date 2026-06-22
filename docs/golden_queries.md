# Golden Queries — Superstore BI Evaluation Suite

Canonical NL→SQL pairs used to verify the star schema and the NL→SQL agent.
Each entry records: the business question, the exact SQL run, the result, and a PASS/FAIL verdict.

> **Conventions (from CLAUDE.md)**
> - `discount` is fractional (0–0.8); multiply × 100 for display.
> - "number of orders" = `COUNT(DISTINCT order_id)`; "line items" = `COUNT(*)`.
> - "placed/ordered" → filter on `order_date_key`; "shipped" → `ship_date_key`.
> - `date_key` is a YYYYMMDD integer (e.g. `BETWEEN 20160101 AND 20161231`).

---

## Q1 — Total revenue

**Question:** What is our total revenue?

```sql
SELECT SUM(sales) AS total_revenue
FROM fact_order_lines;
```

**Result:**

| total_revenue |
|---:|
| $2,297,200.86 |

**Verdict:** ✅ PASS — cross-checked: regional totals ($725,458 + $678,781 + $501,240 + $391,722) and yearly totals (2014–2017) both sum to the same figure.

---

## Q2 — Average discount % by category

**Question:** What is the average discount percentage per product category?

```sql
SELECT
    p.category,
    ROUND(AVG(f.discount) * 100, 2) AS avg_discount_pct
FROM fact_order_lines f
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY p.category
ORDER BY avg_discount_pct DESC;
```

**Result:**

| category | avg_discount_pct |
|---|---:|
| Furniture | 17.39% |
| Office Supplies | 15.73% |
| Technology | 13.23% |

**Verdict:** ✅ PASS — discount correctly multiplied × 100 for display; Furniture's high discount rate aligns with its two loss-making sub-categories (Tables, Bookcases).

---

## Q3 — Sales and profit by region

**Question:** How do sales and profit break down by region?

```sql
SELECT
    g.region,
    SUM(f.sales)  AS total_sales,
    SUM(f.profit) AS total_profit,
    ROUND(SUM(f.profit) / SUM(f.sales) * 100, 2) AS profit_margin_pct
FROM fact_order_lines f
JOIN dim_geography g ON f.geography_key = g.geography_key
GROUP BY g.region
ORDER BY total_sales DESC;
```

**Result:**

| region | total_sales | total_profit | profit_margin_pct |
|---|---:|---:|---:|
| West | $725,457.82 | $108,418.45 | 14.94% |
| East | $678,781.24 | $91,522.78 | 13.48% |
| Central | $501,239.89 | $39,706.36 | 7.92% |
| South | $391,721.91 | $46,749.43 | 11.93% |

**Verdict:** ✅ PASS — four regions present; totals sum to $2,297,200.86 (matches Q1). Central is notably the worst-margin region despite being 3rd in revenue.

---

## Q4 — Sales by year (order date)

**Question:** How have annual sales trended year over year?

```sql
SELECT
    d.year,
    SUM(f.sales)               AS total_sales,
    COUNT(DISTINCT f.order_id) AS orders
FROM fact_order_lines f
JOIN dim_date d ON f.order_date_key = d.date_key
GROUP BY d.year
ORDER BY d.year;
```

**Result:**

| year | total_sales | orders |
|---:|---:|---:|
| 2014 | $484,247.50 | 969 |
| 2015 | $470,532.51 | 1,038 |
| 2016 | $609,205.60 | 1,315 |
| 2017 | $733,215.26 | 1,687 |

**Verdict:** ✅ PASS — data spans 4 years; yearly totals sum to $2,297,200.86 (matches Q1). Sales dipped slightly in 2015 before recovering strongly; consistent order volume growth each year.

---

## Q5 — Top 5 products by sales

**Question:** What are the top 5 selling products?

```sql
SELECT
    p.product_name,
    p.category,
    p.sub_category,
    SUM(f.sales)    AS total_sales,
    SUM(f.quantity) AS total_units,
    SUM(f.profit)   AS total_profit
FROM fact_order_lines f
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY p.product_name, p.category, p.sub_category
ORDER BY total_sales DESC
LIMIT 5;
```

**Result:**

| product_name | category | total_sales | total_units | total_profit |
|---|---|---:|---:|---:|
| Canon imageCLASS 2200 Advanced Copier | Technology / Copiers | $61,599.82 | 20 | $25,199.93 |
| Fellowes PB500 Electric Punch Binding Machine | Office Supplies / Binders | $27,453.38 | 31 | $7,753.04 |
| Cisco TelePresence System EX90 | Technology / Machines | $22,638.48 | 6 | **–$1,811.08** |
| HON 5400 Series Task Chairs for Big and Tall | Furniture / Chairs | $21,870.58 | 39 | $0.00 |
| GBC DocuBind TL300 Electric Binding System | Office Supplies / Binders | $19,823.48 | 37 | $2,233.51 |

**Verdict:** ✅ PASS — Canon copier is the clear #1 by revenue at $61.6K. Note: Cisco TelePresence (#3) is sold at a loss; HON chairs (#4) show zero profit — both margin anomalies worth investigating.

---

## Q6 — Total order count

**Question:** How many orders did we have?

```sql
SELECT COUNT(DISTINCT order_id) AS total_orders
FROM fact_order_lines;
```

**Result:**

| total_orders |
|---:|
| 5,009 |

**Verdict:** ✅ PASS — 5,009 distinct orders across 9,994 line items (≈ 2 items/order on average). Uses `COUNT(DISTINCT order_id)` per convention, not `COUNT(*)`.

---

## Q7 — Sub-categories with negative total profit

**Question:** Which sub-categories had negative total profit?

```sql
SELECT
    p.category,
    p.sub_category,
    SUM(f.profit)   AS total_profit,
    SUM(f.sales)    AS total_sales,
    COUNT(DISTINCT f.order_id) AS orders
FROM fact_order_lines f
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY p.category, p.sub_category
HAVING SUM(f.profit) < 0
ORDER BY total_profit ASC;
```

**Result:**

| sub_category | category | total_profit | total_sales | margin |
|---|---|---:|---:|---:|
| Tables | Furniture | –$17,725.48 | $206,965.53 | –8.6% |
| Bookcases | Furniture | –$3,472.56 | $114,879.00 | –3.0% |
| Supplies | Office Supplies | –$1,189.10 | $46,673.54 | –2.5% |

**Verdict:** ✅ PASS — 3 sub-categories in the red. Furniture accounts for 2 of them; Tables is severely loss-making despite $207K in revenue. Aligns with Q2's finding that Furniture carries the highest average discount (17.4%).

---

## Q8 — Orders placed in 2016 vs shipped in 2016

**Question:** Compare sales for orders placed in 2016 versus orders shipped in 2016.

```sql
SELECT
    'Placed in 2016'            AS basis,
    COUNT(DISTINCT f.order_id)  AS orders,
    SUM(f.quantity)             AS units,
    SUM(f.sales)                AS total_sales,
    SUM(f.profit)               AS total_profit
FROM fact_order_lines f
WHERE f.order_date_key BETWEEN 20160101 AND 20161231

UNION ALL

SELECT
    'Shipped in 2016',
    COUNT(DISTINCT f.order_id),
    SUM(f.quantity),
    SUM(f.sales),
    SUM(f.profit)
FROM fact_order_lines f
WHERE f.ship_date_key BETWEEN 20160101 AND 20161231;
```

**Result:**

| basis | orders | units | total_sales | total_profit |
|---|---:|---:|---:|---:|
| Placed in 2016 | 1,315 | 9,837 | $609,205.60 | $81,795.17 |
| Shipped in 2016 | 1,305 | 9,823 | $611,325.75 | $82,941.10 |

**Verdict:** ✅ PASS — correctly uses `order_date_key` vs `ship_date_key` for each filter. The ~$2K gap reflects pipeline boundary effects: late-2016 orders shipped in 2017 are excluded from "shipped", while late-2015 orders shipped in early 2016 are included. Placed figure matches Q4's 2016 total exactly ($609,205.60).
