"""
load.py  -  L of ETL: write the clean table into a database (a small "star schema")
and export CSVs for the dashboard.

Works with SQLite (default) or PostgreSQL - SQLAlchemy hides the differences.

Tables:
  dim_country    one row per country           (a "dimension": descriptive info)
  dim_indicator  one row per indicator
  fact_indicator one row per country/indicator/year value   (the "facts": the numbers)
  pipeline_runs  a log of every run - when, how many rows, and whether it passed checks
"""

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text      # pip install sqlalchemy

from . import config

log = logging.getLogger(__name__)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS dim_country (
           country_code VARCHAR(3) PRIMARY KEY,
           country      VARCHAR(100) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS dim_indicator (
           indicator_code VARCHAR(40) PRIMARY KEY,
           indicator      VARCHAR(100) NOT NULL,
           unit           VARCHAR(60)  NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS fact_indicator (
           country_code   VARCHAR(3)  NOT NULL REFERENCES dim_country(country_code),
           indicator_code VARCHAR(40) NOT NULL REFERENCES dim_indicator(indicator_code),
           year           INTEGER     NOT NULL,
           value          DOUBLE PRECISION NOT NULL,
           PRIMARY KEY (country_code, indicator_code, year))""",
    """CREATE TABLE IF NOT EXISTS pipeline_runs (
           run_at     VARCHAR(40) NOT NULL,
           rows_loaded INTEGER    NOT NULL,
           status     VARCHAR(20) NOT NULL,
           problems   TEXT)""",
]


def get_engine(url=None):
    """Create a database connection pool. Pass url in tests; otherwise use config."""
    return create_engine(url or config.DATABASE_URL)


def load(df, engine):
    """
    Replace the warehouse contents with this run's data, inside ONE transaction:
    either everything is written, or (if anything fails) nothing changes.
    That makes the pipeline safe to re-run - no duplicates, no half-finished loads.
    """
    with engine.begin() as conn:                       # begin() = start a transaction; commits at the end of the block
        for ddl in SCHEMA:
            conn.execute(text(ddl))                    # text() marks a raw SQL string
        conn.execute(text("DELETE FROM fact_indicator"))     # children first (foreign keys)
        conn.execute(text("DELETE FROM dim_country"))
        conn.execute(text("DELETE FROM dim_indicator"))
        countries = df[["country_code", "country"]].drop_duplicates()
        indicators = df[["indicator_code", "indicator", "unit"]].drop_duplicates()
        facts = df[["country_code", "indicator_code", "year", "value"]]
        # to_sql with if_exists="append" inserts into the tables we created above (keeping our keys/types).
        countries.to_sql("dim_country", conn, if_exists="append", index=False)
        indicators.to_sql("dim_indicator", conn, if_exists="append", index=False)
        facts.to_sql("fact_indicator", conn, if_exists="append", index=False, chunksize=1000)
    log.info("loaded %d facts, %d countries, %d indicators", len(facts), len(countries), len(indicators))
    return len(facts)


def log_run(engine, rows, status, problems):
    """Record this run in pipeline_runs (also done when the run fails its checks)."""
    with engine.begin() as conn:
        conn.execute(text(SCHEMA[3]))                  # make sure the log table exists
        conn.execute(text("INSERT INTO pipeline_runs VALUES (:run_at, :rows, :status, :problems)"),
                     {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "rows": rows, "status": status, "problems": "; ".join(problems) or None})


def export_csv(df):
    """Write the tidy table (with changes) to data/exports/ for the dashboard and for anyone to download."""
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.EXPORT_DIR / "indicators.csv"
    df.to_csv(path, index=False)                       # index=False: don't write pandas' row numbers
    latest = (df.sort_values("year").groupby(["country_code", "indicator_code"]).tail(1))   # last year per series
    latest.to_csv(config.EXPORT_DIR / "latest.csv", index=False)
    return path


def warehouse_summary(engine):
    """A small SQL query against the warehouse, to prove the load worked."""
    sql = text("""
        SELECT i.indicator, COUNT(*) AS n_values, MIN(f.year) AS first_year, MAX(f.year) AS last_year
        FROM fact_indicator f JOIN dim_indicator i ON i.indicator_code = f.indicator_code
        GROUP BY i.indicator ORDER BY i.indicator""")
    return pd.read_sql(sql, engine)                    # run SQL and get a DataFrame back
