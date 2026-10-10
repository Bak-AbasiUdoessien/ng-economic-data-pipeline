"""
make_fixtures.py  -  Builds tests/fixtures/*.json: SAMPLE responses in the exact World Bank
API format, with MADE-UP values. Used by the tests and by `python -m pipeline.run --offline`.
Run from the project folder:  python tests/make_fixtures.py
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "import pipeline" works
from pipeline import config                                        # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
START = {"FP.CPI.TOTL.ZG": 10, "NY.GDP.MKTP.KD.ZG": 4, "NY.GDP.PCAP.CD": 1500,
         "PA.NUS.FCRF": 100, "SL.UEM.TOTL.ZS": 8, "BX.TRF.PWKR.CD.DT": 2e9}   # invented starting levels


def main():
    rnd = random.Random(1)                                           # fixed seed -> identical files every time
    OUT.mkdir(exist_ok=True)
    for code in config.INDICATORS:
        rows = []
        for iso, name in config.COUNTRIES.items():
            level = START[code] * rnd.uniform(0.5, 1.5)
            for year in range(2024, 1999, -1):                       # the API lists newest first
                level *= rnd.uniform(0.95, 1.08)                     # wander a little each year
                missing = rnd.random() < 0.08                        # ~8% of years have no data, like the real API
                rows.append({"indicator": {"id": code, "value": config.INDICATORS[code][0]},
                             "country": {"id": iso[:2], "value": name},
                             "countryiso3code": iso, "date": str(year),
                             "value": None if missing else round(level, 3),
                             "unit": "", "obs_status": "", "decimal": 1})
        (OUT / f"{code}.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"wrote {len(config.INDICATORS)} SAMPLE fixture files to {OUT}")


if __name__ == "__main__":
    main()
