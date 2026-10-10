"""
Tests for the pipeline. Run from the project folder:  python -m pytest -v
No internet needed: the API is replaced by a fake session or the sample fixtures.
"""

import pandas as pd
import pytest                                            # pip install pytest

from pipeline import config, extract, load, run, transform


# ---------- helpers ----------------------------------------------------------

class FakeResponse:
    """Pretends to be a requests.Response."""
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status
    def json(self):
        return self.payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise extract.requests.HTTPError(str(self.status_code))


class FakeSession:
    """Returns the queued responses one by one and records which pages were requested."""
    def __init__(self, responses):
        self.responses, self.pages = list(responses), []
    def get(self, url, params, timeout):
        self.pages.append(params["page"])
        return self.responses.pop(0)                     # take the next queued response


def record(iso, year, value):
    """One raw record in World Bank format."""
    return {"countryiso3code": iso, "country": {"value": "x"}, "date": str(year), "value": value}


@pytest.fixture                                          # a fixture = setup shared by tests that ask for it by name
def sample_df():
    return transform.add_changes(transform.to_tidy(run.offline_raw()))


# ---------- extract ----------------------------------------------------------

def test_follows_every_page():
    session = FakeSession([
        FakeResponse([{"page": 1, "pages": 2}, [record("NGA", 2020, 1.0)]]),
        FakeResponse([{"page": 2, "pages": 2}, [record("NGA", 2021, 2.0)]]),
    ])
    rows = extract.fetch_indicator("FP.CPI.TOTL.ZG", ["NGA"], session=session)
    assert session.pages == [1, 2]                       # asked for page 1, then page 2
    assert len(rows) == 2


def test_retries_after_server_error(monkeypatch):
    monkeypatch.setattr(extract.time, "sleep", lambda s: None)   # don't really wait during tests
    session = FakeSession([FakeResponse({}, status=503),
                           FakeResponse([{"page": 1, "pages": 1}, [record("NGA", 2020, 1.0)]])])
    assert len(extract.fetch_indicator("FP.CPI.TOTL.ZG", ["NGA"], session=session)) == 1


def test_api_error_message_returns_no_rows():
    session = FakeSession([FakeResponse([{"message": [{"value": "Invalid value"}]}])])
    assert extract.fetch_indicator("BAD.CODE", ["NGA"], session=session) == []


# ---------- transform --------------------------------------------------------

def test_tidy_drops_nulls_and_unknown_countries():
    raw = {"FP.CPI.TOTL.ZG": [record("NGA", 2020, 13.2), record("NGA", 2021, None),
                              record("XXX", 2020, 5.0)]}
    df = transform.to_tidy(raw)
    assert list(df["year"]) == [2020]                    # null year and unknown country removed
    assert df.iloc[0]["country"] == "Nigeria"


def test_changes_are_per_country(sample_df):
    first_rows = sample_df.groupby(["country_code", "indicator_code"]).head(1)   # first year of every series
    assert first_rows["change"].isna().all()             # nothing to compare with -> NaN, never another country's value


def test_sample_data_passes_validation(sample_df):
    assert transform.validate(sample_df) == []


def test_validation_catches_bad_values(sample_df):
    bad = sample_df.copy()
    bad.loc[0, "value"] = -999                           # an impossible value
    bad = pd.concat([bad, bad.iloc[[1]]])                # and a duplicate row
    problems = transform.validate(bad)
    assert any("duplicate" in p for p in problems)
    assert any("outside" in p for p in problems)


# ---------- load -------------------------------------------------------------

def test_load_is_idempotent(sample_df, tmp_path):        # tmp_path = a temporary folder pytest provides
    engine = load.get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    load.load(sample_df, engine)
    load.load(sample_df, engine)                         # run twice...
    count = pd.read_sql("SELECT COUNT(*) AS n FROM fact_indicator", engine)["n"][0]
    assert count == len(sample_df)                       # ...still no duplicates


def test_run_offline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'e2e.db'}")
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{tmp_path / 'e2e.db'}")
    assert run.main(["--offline"]) == 0                  # exit code 0 = success
