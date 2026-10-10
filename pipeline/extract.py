"""
extract.py  -  E of ETL: download raw data from the World Bank API.

Handles the things real APIs do to you:
  * results split across several pages      -> follow every page
  * temporary network errors / rate limits  -> retry with a growing wait (backoff)
  * keeps an untouched copy of every response -> you can re-run transforms without re-downloading
"""

import json
import logging
import time
from datetime import date

import requests                                   # the standard library for HTTP in Python (pip install requests)

from . import config                              # "." = import from this same package

log = logging.getLogger(__name__)                 # a logger named after this module


def get_json(url, params, retries=4, session=None):
    """GET a URL and return parsed JSON, retrying on failure with exponential backoff (1s, 2s, 4s...)."""
    http = session or requests                    # tests pass in a fake session; normally use requests itself
    for attempt in range(retries):
        try:
            resp = http.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:   # rate-limited or server problem -> worth retrying
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()                   # any other 4xx error -> stop now (retrying won't help)
            return resp.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as err:
            if attempt == retries - 1:                # that was the last try -> give up and let the caller know
                raise
            wait = 2 ** attempt                       # 1, 2, 4, 8 seconds
            log.warning("attempt %d failed (%s); retrying in %ds", attempt + 1, err, wait)
            time.sleep(wait)


def fetch_indicator(indicator, countries, session=None):
    """
    Download one indicator for several countries (one request per page, all pages).
    Returns the list of raw records exactly as the API sent them.
    """
    url = f"{config.API_BASE}/country/{';'.join(countries)}/indicator/{indicator}"   # ';' asks for many countries at once
    params = {"format": "json", "per_page": 1000, "date": f"{config.START_YEAR}:{config.END_YEAR}", "page": 1}
    records = []
    while True:
        payload = get_json(url, params, session=session)
        # The API returns [metadata, rows]. An error comes back as [{"message": [...]}] with no rows.
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            msg = payload[0].get("message") if isinstance(payload, list) and payload else payload
            log.warning("no data for %s: %s", indicator, msg)
            break
        meta, rows = payload
        records.extend(rows)                          # add this page's rows to the full list
        if meta["page"] >= meta["pages"]:             # last page reached
            break
        params["page"] += 1                           # otherwise ask for the next page
    log.info("%s: %d raw records", indicator, len(records))
    return records


def extract_all(session=None, save_raw=True):
    """Download every configured indicator. Returns {indicator_code: [records]}."""
    raw = {}
    for code in config.INDICATORS:
        raw[code] = fetch_indicator(code, list(config.COUNTRIES), session=session)
    if save_raw:                                      # keep a dated copy of exactly what the API returned
        folder = config.RAW_DIR / date.today().isoformat()
        folder.mkdir(parents=True, exist_ok=True)     # parents=True also creates data/raw if needed
        for code, records in raw.items():
            (folder / f"{code}.json").write_text(json.dumps(records), encoding="utf-8")
    return raw
