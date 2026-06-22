# Superstore BI Agent

## Project
An agentic BI system:
natural-language questions → SQL → results from a PostgreSQL data warehouse,
visualized in Apache Superset. You (Claude Code) also build the warehouse and ETL.

## Stack
- Warehouse: PostgreSQL on Supabase, reached via the `postgres` MCP server
- Source data: ./Superstore.csv (Kaggle Superstore dataset)
- ETL: Python (pandas + psycopg2); config in .env (gitignored)
- BI: Apache Superset (dashboards built manually)
- Web enrichment (later phase): Brave Search MCP

## Database access
- Use the `postgres` MCP server for ALL schema inspection and SQL execution.
- Database is `postgres`; build the warehouse in the `public` schema.
- Never hardcode or print credentials — they live in .env and the MCP already has them.

## Conventions
- Star schema: `fact_` prefix for facts, `dim_` prefix for dimensions.
- Dimensions get surrogate integer PKs named `<thing>_key`; facts reference them as FKs.
- snake_case for all table and column names.
- ETL must be idempotent (ON CONFLICT), handle nulls/dedup, and load in batches.

## Working agreements
- Explain your plan before any schema or data change; use plan mode for destructive work.
- Show the DDL/SQL before running it; prefer small, reviewable steps.
- Don't invent column names — inspect the CSV or live schema first.

## Source data
- Superstore.csv is latin-1 / ISO-8859-1 encoded; Order Date and Ship Date are MM/DD/YYYY.
- dim_date must be generated to span ALL order AND ship dates (ship dates can fall after
  the last order date), or fact FKs to dim_date will fail.

## Schema
Fact — fact_order_lines
- Grain: one order line (one product on one order).
- Measures (additive → SUM): sales, quantity, discount, profit. Also days_to_ship.
- order_id is a degenerate dimension (groups line items into orders).
- source_row_id (UNIQUE) = CSV Row ID; the ETL idempotency anchor.
- FKs: order_date_key→dim_date, ship_date_key→dim_date (same table, role-playing),
  customer_key→dim_customer, product_key→dim_product,
  geography_key→dim_geography, ship_mode_key→dim_ship_mode.

Dimensions
- dim_date — date_key is YYYYMMDD integer; full_date, year, quarter, month_num/name,
  day_of_week (ISO: 1=Mon), is_weekend.
- dim_customer — customer_id (UNIQUE), customer_name, segment (Consumer|Corporate|Home Office).
- dim_product — natural key composite (product_id, product_name); category, sub_category.
- dim_geography — natural key composite (postal_code, city); state, region, country.
- dim_ship_mode — ship_mode (Standard Class|Second Class|First Class|Same Day).

## SQL generation rules (how to answer natural-language questions)

- Analytical questions are answered with SELECT only. Never INSERT/UPDATE/DELETE/DDL
  when answering a question.
- Query through the star schema: aggregate from fact_order_lines, join dimensions for
  labels. GROUP BY dimension attributes (category, region, segment...), not surrogate keys.
- If unsure of a column name, introspect the live schema via the postgres MCP — never guess.
- Respect these semantics:
  - discount is FRACTIONAL (0–0.8), not a percentage; ×100 only for display.
  - sales, quantity, profit are additive; profit can be negative.
  - "number of orders" = COUNT(DISTINCT order_id); "line items" = COUNT(*).
  - "placed/ordered" → join on order_date_key; "shipped" → ship_date_key.
    date_key is YYYYMMDD integer (filter years as date_key BETWEEN 20160101 AND 20161231).
- If a request is ambiguous (e.g. "top products" — by sales, quantity, or profit?),
  state the assumption you make, or ask.
- Always show the SQL you ran, then summarize the result in plain language; format
  currency and percentages for readability. Use LIMIT for exploratory queries.