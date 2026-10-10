# African Economic Indicators: ETL Pipeline

[![tests](https://github.com/Bak-AbasiUdoessien/ng-economic-data-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/Bak-AbasiUdoessien/ng-economic-data-pipeline/actions/workflows/tests.yml)
[![pipeline](https://github.com/Bak-AbasiUdoessien/ng-economic-data-pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Bak-AbasiUdoessien/ng-economic-data-pipeline/actions/workflows/pipeline.yml)

An automated data pipeline that runs **every Monday on GitHub Actions**. It downloads economic indicators for **Nigeria, Ghana, Kenya, South Africa and Egypt** from the World Bank API, cleans them with **pandas**, runs **data-quality checks**, loads them into a **SQL warehouse** (SQLite or PostgreSQL), and publishes clean CSVs. The [ng-economy-dashboard](https://github.com/Bak-AbasiUdoessien/ng-economy-dashboard) reads those CSVs.

```
World Bank API ──extract──► raw JSON ──transform──► tidy pandas table ──validate──► load ──► SQL warehouse
   (paged, retried)          (kept)     (types, dedupe,      (ranges, dupes,     (one          + data/exports/*.csv
                                         yearly changes)      missing countries)  transaction)
```

**Indicators:** inflation, GDP growth, GDP per person, the official exchange rate, unemployment and remittances.

## Run it
```bash
python -m venv .venv && .venv\Scripts\activate        # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt

python -m pipeline.run              # real data from the World Bank -> data/warehouse.db + data/exports/
python -m pipeline.run --offline    # bundled SAMPLE responses, no internet, separate sample database
python -m pytest -v                 # 9 tests
```

### With PostgreSQL (Docker)
```bash
docker compose up --build           # starts Postgres and runs the pipeline against it
```
Or point the pipeline at any Postgres database with `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`.

## Engineering decisions
| Decision | Why |
|---|---|
| **Retry with exponential backoff** (1s, 2s, 4s…) on 429/5xx | Public APIs fail now and then, and one network hiccup shouldn't kill the weekly run |
| **Follow every page** of results | The API pages its responses, and taking only page 1 would silently lose data |
| **Keep the raw responses** in `data/raw/<date>/` | You can re-run transforms without re-downloading, and audit exactly what the API sent |
| **Validate before loading** | Bad data never reaches the warehouse or the dashboard. Failed runs are logged in `pipeline_runs` |
| **One transaction per load** | Either everything is written or nothing is, so a crash can't leave a half-loaded warehouse |
| **Idempotent loads** (safe to re-run) | Re-running never creates duplicates. Tested, including twice against real Postgres in CI |
| **A star schema** (`dim_country`, `dim_indicator`, `fact_indicator`) | The standard data-warehouse layout that BI tools expect |
| **SQLAlchemy** | The same code runs on SQLite (local) and PostgreSQL (production) |
| **Sample data never exported** | `--offline` writes to a separate database and never touches `data/exports` |

## CI/CD
- **tests.yml** (every push) runs the unit tests, runs the full pipeline **twice against a real PostgreSQL 16 service**, and builds the **Docker** image.
- **pipeline.yml** (Mondays, plus a manual "Run workflow" button) runs the real pipeline and commits the updated `data/exports/*.csv`.

## Query the warehouse
```sql
-- Nigeria's inflation, latest 5 years
SELECT f.year, ROUND(f.value, 1) AS inflation_pct
FROM fact_indicator f
WHERE f.country_code = 'NGA' AND f.indicator_code = 'FP.CPI.TOTL.ZG'
ORDER BY f.year DESC LIMIT 5;
```

Data source: World Bank Open Data (World Development Indicators), licensed CC BY 4.0. The values in `tests/fixtures/` are **made up**, for tests only.
