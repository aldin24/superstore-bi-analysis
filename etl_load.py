#!/usr/bin/env python3
"""
ETL: loads ./data/Sample - Superstore.csv into the Superstore star schema.

Run order: dims first (date, customer, product, geography, ship_mode), then fact.
Idempotent — safe to re-run at any time via ON CONFLICT upserts.
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "Sample - Superstore.csv")
BATCH_SIZE = 500


# ── connection ────────────────────────────────────────────────────────────────

def connect() -> psycopg2.extensions.connection:
    uri = os.environ.get("DATABASE_URI")
    if not uri:
        raise EnvironmentError("DATABASE_URI not set in .env")
    return psycopg2.connect(uri)


# ── CSV ───────────────────────────────────────────────────────────────────────

def read_csv() -> pd.DataFrame:
    df = pd.read_csv(
        CSV_PATH,
        encoding="latin-1",
        dtype={"Postal Code": str},   # preserve leading zeros
    )
    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%m/%d/%Y")
    df["Ship Date"]  = pd.to_datetime(df["Ship Date"],  format="%m/%d/%Y")
    return df


def date_to_key(ts: pd.Timestamp) -> int:
    """YYYYMMDD integer — Kimball date dim key."""
    return int(ts.strftime("%Y%m%d"))


# ── dim_date ──────────────────────────────────────────────────────────────────

def load_dim_date(conn, df: pd.DataFrame) -> None:
    # Must span ALL order dates AND ship dates — ship dates can exceed the last order date.
    all_dates = (
        pd.concat([df["Order Date"], df["Ship Date"]])
        .drop_duplicates()
        .sort_values()
    )

    rows = []
    for d in all_dates:
        rows.append((
            date_to_key(d),
            d.date(),
            d.isoweekday(),             # ISO 1=Mon … 7=Sun
            d.strftime("%A"),
            int(d.day),
            int(d.dayofyear),
            int(d.isocalendar()[1]),    # ISO week number
            int(d.month),
            d.strftime("%B"),
            int((d.month - 1) // 3 + 1),
            int(d.year),
            d.isoweekday() >= 6,
        ))

    sql = """
        INSERT INTO dim_date (
            date_key, full_date, day_of_week, day_name, day_of_month,
            day_of_year, week_of_year, month_num, month_name,
            quarter, year, is_weekend
        ) VALUES %s
        ON CONFLICT (date_key) DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f"  dim_date         {len(rows):>5} rows")


# ── dim_customer ──────────────────────────────────────────────────────────────

def load_dim_customer(conn, df: pd.DataFrame) -> None:
    data = (
        df[["Customer ID", "Customer Name", "Segment"]]
        .drop_duplicates("Customer ID")
        .itertuples(index=False, name=None)
    )
    rows = list(data)
    sql = """
        INSERT INTO dim_customer (customer_id, customer_name, segment)
        VALUES %s
        ON CONFLICT (customer_id) DO UPDATE SET
            customer_name = EXCLUDED.customer_name,
            segment       = EXCLUDED.segment
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f"  dim_customer     {len(rows):>5} rows")


# ── dim_product ───────────────────────────────────────────────────────────────

def load_dim_product(conn, df: pd.DataFrame) -> None:
    data = (
        df[["Product ID", "Product Name", "Category", "Sub-Category"]]
        .drop_duplicates(["Product ID", "Product Name"])
        .itertuples(index=False, name=None)
    )
    rows = list(data)
    sql = """
        INSERT INTO dim_product (product_id, product_name, category, sub_category)
        VALUES %s
        ON CONFLICT (product_id, product_name) DO UPDATE SET
            category     = EXCLUDED.category,
            sub_category = EXCLUDED.sub_category
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f"  dim_product      {len(rows):>5} rows")


# ── dim_geography ─────────────────────────────────────────────────────────────

def load_dim_geography(conn, df: pd.DataFrame) -> None:
    data = (
        df[["Postal Code", "City", "State", "Region", "Country"]]
        .drop_duplicates(["Postal Code", "City"])
        .itertuples(index=False, name=None)
    )
    rows = list(data)
    sql = """
        INSERT INTO dim_geography (postal_code, city, state, region, country)
        VALUES %s
        ON CONFLICT (postal_code, city) DO UPDATE SET
            state   = EXCLUDED.state,
            region  = EXCLUDED.region,
            country = EXCLUDED.country
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f"  dim_geography    {len(rows):>5} rows")


# ── dim_ship_mode ─────────────────────────────────────────────────────────────

def load_dim_ship_mode(conn, df: pd.DataFrame) -> None:
    modes = df["Ship Mode"].drop_duplicates().tolist()
    sql = """
        INSERT INTO dim_ship_mode (ship_mode)
        VALUES %s
        ON CONFLICT (ship_mode) DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, [(m,) for m in modes])
    conn.commit()
    print(f"  dim_ship_mode    {len(modes):>5} rows")


# ── fact_order_lines ──────────────────────────────────────────────────────────

def load_fact(conn, df: pd.DataFrame) -> None:
    # Read surrogate key maps from each dim (all small enough to fit in memory).
    with conn.cursor() as cur:
        cur.execute("SELECT customer_id, customer_key FROM dim_customer")
        cust_df = pd.DataFrame(cur.fetchall(), columns=["Customer ID", "customer_key"])

        cur.execute("SELECT product_id, product_name, product_key FROM dim_product")
        prod_df = pd.DataFrame(cur.fetchall(), columns=["Product ID", "Product Name", "product_key"])

        cur.execute("SELECT postal_code, city, geography_key FROM dim_geography")
        geo_df = pd.DataFrame(cur.fetchall(), columns=["Postal Code", "City", "geography_key"])

        cur.execute("SELECT ship_mode, ship_mode_key FROM dim_ship_mode")
        ship_df = pd.DataFrame(cur.fetchall(), columns=["Ship Mode", "ship_mode_key"])

    # Compute derived columns, then merge in all surrogate keys.
    fact = df.copy()
    fact["order_date_key"] = fact["Order Date"].apply(date_to_key)
    fact["ship_date_key"]  = fact["Ship Date"].apply(date_to_key)
    fact["days_to_ship"]   = (fact["Ship Date"] - fact["Order Date"]).dt.days.astype(int)

    fact = fact.merge(cust_df, on="Customer ID",              how="left")
    fact = fact.merge(prod_df, on=["Product ID", "Product Name"], how="left")
    fact = fact.merge(geo_df,  on=["Postal Code", "City"],    how="left")
    fact = fact.merge(ship_df, on="Ship Mode",                how="left")

    # Guard: any unresolved FK means a dim wasn't loaded.
    fk_cols = ["customer_key", "product_key", "geography_key", "ship_mode_key"]
    for col in fk_cols:
        missing = int(fact[col].isna().sum())
        if missing:
            raise ValueError(
                f"{missing} rows have no {col} — ensure all dims loaded first"
            )

    # Cast to correct Python types so psycopg2 sends the right SQL types.
    fact["Row ID"]        = fact["Row ID"].astype(int)
    fact["order_date_key"]= fact["order_date_key"].astype(int)
    fact["ship_date_key"] = fact["ship_date_key"].astype(int)
    fact["customer_key"]  = fact["customer_key"].astype(int)
    fact["product_key"]   = fact["product_key"].astype(int)
    fact["geography_key"] = fact["geography_key"].astype(int)
    fact["ship_mode_key"] = fact["ship_mode_key"].astype(int)
    fact["Quantity"]      = fact["Quantity"].astype(int)

    cols = [
        "Row ID", "Order ID",
        "order_date_key", "ship_date_key",
        "customer_key", "product_key", "geography_key", "ship_mode_key",
        "Sales", "Quantity", "Discount", "Profit", "days_to_ship",
    ]
    all_rows = [tuple(r) for r in fact[cols].itertuples(index=False, name=None)]

    sql = """
        INSERT INTO fact_order_lines (
            source_row_id, order_id,
            order_date_key, ship_date_key,
            customer_key, product_key, geography_key, ship_mode_key,
            sales, quantity, discount, profit, days_to_ship
        ) VALUES %s
        ON CONFLICT (source_row_id) DO UPDATE SET
            order_id       = EXCLUDED.order_id,
            order_date_key = EXCLUDED.order_date_key,
            ship_date_key  = EXCLUDED.ship_date_key,
            customer_key   = EXCLUDED.customer_key,
            product_key    = EXCLUDED.product_key,
            geography_key  = EXCLUDED.geography_key,
            ship_mode_key  = EXCLUDED.ship_mode_key,
            sales          = EXCLUDED.sales,
            quantity       = EXCLUDED.quantity,
            discount       = EXCLUDED.discount,
            profit         = EXCLUDED.profit,
            days_to_ship   = EXCLUDED.days_to_ship
    """

    total = len(all_rows)
    with conn.cursor() as cur:
        for i in range(0, total, BATCH_SIZE):
            batch = all_rows[i : i + BATCH_SIZE]
            execute_values(cur, sql, batch)
            conn.commit()
            loaded = min(i + BATCH_SIZE, total)
            print(f"  fact_order_lines {loaded:>5}/{total} rows", end="\r")
    print(f"  fact_order_lines {total:>5}/{total} rows")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Reading CSV …")
    df = read_csv()
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    print("Connecting …")
    conn = connect()

    try:
        print("Loading dimensions …")
        load_dim_date(conn, df)
        load_dim_customer(conn, df)
        load_dim_product(conn, df)
        load_dim_geography(conn, df)
        load_dim_ship_mode(conn, df)

        print("Loading fact …")
        load_fact(conn, df)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
