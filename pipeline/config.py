"""
config.py  -  Everything you might want to change, in one place.
"""

import os                                    # read environment variables
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the project folder
RAW_DIR = ROOT / "data" / "raw"                        # untouched API responses (git-ignored)
EXPORT_DIR = ROOT / "data" / "exports"                 # clean CSVs published for the dashboard

# Where to load the data. SQLite by default (a single file, no server needed).
# For PostgreSQL set an environment variable, e.g.
#   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/economy
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'warehouse.db'}")

API_BASE = "https://api.worldbank.org/v2"              # World Bank Open Data (free, no key)
START_YEAR, END_YEAR = 2000, 2025                      # range of years to request

# ISO3 code -> display name. Nigeria plus four large African economies to compare against.
COUNTRIES = {
    "NGA": "Nigeria",
    "GHA": "Ghana",
    "KEN": "Kenya",
    "ZAF": "South Africa",
    "EGY": "Egypt",
}

# World Bank code -> (short name, unit, sensible min, sensible max).
# The min/max are used by the data-quality checks to catch obviously broken values.
INDICATORS = {
    "FP.CPI.TOTL.ZG":   ("Inflation",              "% per year",       -50, 1000),
    "NY.GDP.MKTP.KD.ZG": ("GDP growth",            "% per year",       -60,   60),
    "NY.GDP.PCAP.CD":   ("GDP per person",         "current US$",        0, 200000),
    "PA.NUS.FCRF":      ("Official exchange rate", "local currency per US$", 0, 1e6),
    "SL.UEM.TOTL.ZS":   ("Unemployment",           "% of labour force",  0,  100),
    "BX.TRF.PWKR.CD.DT": ("Remittances received",  "current US$",        0, 1e12),
}
