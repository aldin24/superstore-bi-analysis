#!/usr/bin/env python3
"""
ETL: loads ./product_search.txt into dim_product_recommendations.

Each record in the JSON file maps to one row per recommendation entry.
Idempotent — safe to re-run via ON CONFLICT upsert on (product_key,
recommendation_type, source_url).
"""

import json
import os
import sys
from datetime import date

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

SOURCE_PATH = os.path.join(os.path.dirname(__file__), "product_search.txt")


# ── connection ────────────────────────────────────────────────────────────────

def connect() -> psycopg2.extensions.connection:
    uri = os.environ.get("DATABASE_URI")
    if not uri:
        raise EnvironmentError("DATABASE_URI not set in .env")
    return psycopg2.connect(uri)


# ── product_key resolution ────────────────────────────────────────────────────

def build_name_key_map(conn) -> dict:
    """Return {product_name: product_key} for the full dim_product table."""
    with conn.cursor() as cur:
        cur.execute("SELECT product_name, product_key FROM dim_product")
        return {name: key for name, key in cur.fetchall()}


# ── main load ─────────────────────────────────────────────────────────────────

def load(conn, products: list) -> int:
    today = date.today()
    name_key_map = build_name_key_map(conn)

    rows = []
    skipped = 0

    for product in products:
        product_key = product.get("product_key")

        # Fall back to name lookup if product_key is absent.
        if product_key is None:
            product_key = name_key_map.get(product.get("product_name"))
            if product_key is None:
                print(
                    f"  WARN: cannot resolve product_key for "
                    f"'{product.get('product_name')}' — skipping",
                    file=sys.stderr,
                )
                skipped += len(product.get("recommendations", []))
                continue

        for rec in product.get("recommendations", []):
            rec_type = rec.get("recommendation_type", "").strip()
            rec_text = rec.get("recommendation_text", "").strip()
            source   = rec.get("source_url", "").strip()

            if not (rec_type and rec_text and source):
                skipped += 1
                continue

            rows.append((product_key, today, rec_text, rec_type, source))

    if not rows:
        print("No rows to load.")
        return 0

    sql = """
        INSERT INTO dim_product_recommendations
            (product_key, recommendation_date, recommendation_text,
             recommendation_type, source_url)
        VALUES %s
        ON CONFLICT (product_key, recommendation_type, source_url) DO UPDATE SET
            recommendation_text = EXCLUDED.recommendation_text,
            recommendation_date = EXCLUDED.recommendation_date
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()

    if skipped:
        print(f"  Skipped (missing fields or unresolved key): {skipped}")
    return len(rows)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Reading {SOURCE_PATH} …")
    with open(SOURCE_PATH, encoding="utf-8") as fh:
        products = json.load(fh)
    print(f"  {len(products)} products, "
          f"{sum(len(p.get('recommendations', [])) for p in products)} recommendations")

    print("Connecting …")
    conn = connect()

    try:
        loaded = load(conn, products)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"  dim_product_recommendations  {loaded:>3} rows loaded (upserted)")
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
