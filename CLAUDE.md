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

## Schema
_To be filled in after we design the star schema._

## SQL generation rules
_The NL→SQL system prompt — added once the schema exists._