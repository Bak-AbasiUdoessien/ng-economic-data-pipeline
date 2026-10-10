"""
transform.py  -  T of ETL: turn raw API records into one clean, tidy pandas table,
then check its quality before anything is loaded.

"Tidy" = one row per observation: (country, indicator, year) -> value.
"""

import logging

import pandas as pd                               # the standard data-analysis library (pip install pandas)

from . import config

log = logging.getLogger(__name__)

COLUMNS = ["country_code", "country", "indicator_code", "indicator", "unit", "year", "value"]


def to_tidy(raw):
    """Flatten {indicator: [records]} into a tidy DataFrame with the right data types."""
    rows = []
    for code, records in raw.items():
        name, unit, _lo, _hi = config.INDICATORS[code]          # look up the friendly name and unit
        for r in records:
            rows.append({
                "country_code": r.get("countryiso3code") or "",  # 'or ""' turns None into an empty string
                "country": (r.get("country") or {}).get("value", ""),   # nested JSON: {"id":..., "value": "Nigeria"}
                "indicator_code": code,
                "indicator": name,
                "unit": unit,
                "year": r.get("date"),
                "value": r.get("value"),
            })
    df = pd.DataFrame(rows, columns=COLUMNS)                    # columns= keeps the order even if rows is empty

    before = len(df)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")     # text -> number; anything odd becomes NaN
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["year", "value"])                    # the API sends null for years with no data
    df = df[df["country_code"].isin(config.COUNTRIES)]          # keep only the countries we asked for
    df["year"] = df["year"].astype(int)
    df["country"] = df["country_code"].map(config.COUNTRIES)    # use our own consistent country names
    df = (df.drop_duplicates(subset=["country_code", "indicator_code", "year"], keep="last")   # one value per key
            .sort_values(["indicator_code", "country_code", "year"])
            .reset_index(drop=True))                            # renumber rows 0, 1, 2...
    log.info("transform: %d raw rows -> %d clean rows", before, len(df))
    return df


def add_changes(df):
    """Add the change since the previous available year for each country + indicator."""
    df = df.sort_values(["country_code", "indicator_code", "year"]).copy()   # .copy() avoids pandas warnings
    grouped = df.groupby(["country_code", "indicator_code"])["value"]        # one group per line on a chart
    df["change"] = grouped.diff()                                            # value minus previous value
    df["pct_change"] = (grouped.pct_change(fill_method=None) * 100).round(2) # % change from previous value
    return df.reset_index(drop=True)


def validate(df):
    """
    Data-quality checks. Returns a list of problems (empty list = all good).
    Running checks BEFORE loading means bad data never reaches the dashboard.
    """
    problems = []
    if df.empty:
        problems.append("no rows at all - did the API change or fail?")
        return problems
    keys = ["country_code", "indicator_code", "year"]
    dupes = int(df.duplicated(subset=keys).sum())                # .sum() counts the True values
    if dupes:
        problems.append(f"{dupes} duplicate (country, indicator, year) rows")
    bad_years = df[(df["year"] < 1960) | (df["year"] > 2100)]   # | means OR for pandas columns
    if len(bad_years):
        problems.append(f"{len(bad_years)} rows with impossible years")
    for code, (name, _unit, lo, hi) in config.INDICATORS.items():
        sub = df[df["indicator_code"] == code]
        out = sub[(sub["value"] < lo) | (sub["value"] > hi)]
        if len(out):
            problems.append(f"{name}: {len(out)} values outside [{lo}, {hi}], e.g. "
                            f"{out.iloc[0]['country_code']} {out.iloc[0]['year']} = {out.iloc[0]['value']}")
    missing = set(config.COUNTRIES) - set(df["country_code"])   # set difference = countries with no data at all
    if missing:
        problems.append(f"no data for: {sorted(missing)}")
    return problems
