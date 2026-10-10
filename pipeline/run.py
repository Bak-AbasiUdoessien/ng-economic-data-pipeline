"""
run.py  -  Runs the whole pipeline: extract -> transform -> validate -> load -> export.

    python -m pipeline.run              # real World Bank data
    python -m pipeline.run --offline    # bundled sample responses (tests/fixtures) - no internet needed
"""

import argparse
import json
import logging
import os                                      # read environment variables
import sys

from . import config, extract, load, transform


def offline_raw():
    """Read the bundled sample responses instead of calling the API (the sample values are MADE UP)."""
    folder = config.ROOT / "tests" / "fixtures"
    return {code: json.loads((folder / f"{code}.json").read_text(encoding="utf-8")) for code in config.INDICATORS}


def main(argv=None):
    p = argparse.ArgumentParser(description="World Bank economic indicators ETL pipeline")
    p.add_argument("--offline", action="store_true", help="use bundled sample data instead of the API")
    p.add_argument("--no-export", action="store_true", help="skip writing data/exports/*.csv")
    args = p.parse_args(argv)                          # argv=None -> read the real command line

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    log = logging.getLogger("pipeline")
    url = config.DATABASE_URL
    if args.offline and "DATABASE_URL" not in os.environ:   # keep sample data out of the real warehouse
        url = f"sqlite:///{config.ROOT / 'data' / 'sample_warehouse.db'}"
    engine = load.get_engine(url)
    log.info("database: %s", engine.url.render_as_string(hide_password=True))   # never print passwords

    raw = offline_raw() if args.offline else extract.extract_all()
    df = transform.add_changes(transform.to_tidy(raw))
    problems = transform.validate(df)

    if problems:                                       # stop BEFORE loading if the data looks wrong
        for p_ in problems:
            log.error("quality check failed: %s", p_)
        load.log_run(engine, 0, "failed_checks", problems)
        return 1                                       # non-zero exit code -> GitHub Actions marks the run as failed

    rows = load.load(df, engine)
    load.log_run(engine, rows, "success", [])
    if not args.no_export and not args.offline:        # never publish sample data as if it were real
        log.info("exported %s", load.export_csv(df))
    print(load.warehouse_summary(engine).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())                                   # pass the return code to the operating system
