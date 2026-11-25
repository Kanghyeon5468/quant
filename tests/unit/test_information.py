"""Controlled calculation/validation inputs only, never a source for actual-mode data."""

from pathlib import Path

import pandas as pd
import pytest

from quantcore.fundamentals.analysis import analyze
from quantcore.fundamentals.sec_facts import facts_for_tag, filing_time, standalone_quarters
from quantcore.information.institutions import compare_filings, parse_filing
from quantcore.information.news import normalize_article
from quantcore.information.service import InformationService
from quantcore.information.store import publish, read_snapshot


def fact(start, end, value):
    return {
        "start": start,
        "end": end,
        "value": value,
        "public_at": "2026-11-01T00:00:00+00:00",
        "available_at": "2026-11-25T00:00:00+00:00",
    }


def test_ytd_differences_conserve_flow_and_never_subtract_eps():
    rows = [
        fact("2026-01-01", "2026-03-31", 10),
        fact("2026-01-01", "2026-06-30", 25),
        fact("2026-01-01", "2026-09-30", 45),
        fact("2026-01-01", "2026-12-31", 70),
    ]
    quarters = standalone_quarters(rows)
    assert [r["value"] for _, r in sorted(quarters.items())] == [10, 15, 20, 25]
    assert sum(r["value"] for r in quarters.values()) == 70
    assert len(standalone_quarters(rows, additive=False)) == 1
    assert quarters["2026-12-31"]["start"] == "2026-10-01"


def test_no_difference_across_fiscal_starts_or_missing_quarters():
    rows = [fact("2025-12-01", "2026-03-31", 10), fact("2026-01-01", "2026-09-30", 40)]
    assert standalone_quarters(rows) == {}


def test_filing_date_fallback_is_conservative_new_york_day_end():
    stamp, basis = filing_time({"filed": "2026-11-16", "accn": "x"}, {})
    assert stamp == pd.Timestamp("2026-11-17T05:00:00Z")
    assert "date-only" in basis
    stamp, _ = filing_time({"filed": "2026-11-16", "accn": "x"}, {"x": "2026-11-16T20:00:00Z"})
    assert stamp == pd.Timestamp("2026-11-16T20:00:00Z")


def test_companyfact_not_available_before_collection():
    row = {
        "form": "10-Q",
        "filed": "2026-11-01",
        "accn": "x",
        "val": 100,
        "start": "2026-07-01",
        "end": "2026-09-30",
    }
    payload = {"facts": {"us-gaap": {"Revenue": {"units": {"USD": [row]}}}}}
    assert (
        facts_for_tag(
            payload, "us-gaap", "Revenue", "USD", {}, "2026-11-25T00:00Z", pd.Timestamp("2026-11-24T23:59Z")
        )
        == []
    )


def test_nulls_are_not_zero_or_type_errors():
    result = analyze(
        [
            {
                "period_end": "2026-09-30",
                "published_at": "2026-11-01",
                "available_at": "2026-11-25",
                "source": "controlled unit input",
                "mode": "unit",
                "shares": None,
                "net_income": None,
                "debt": None,
                "tax_rate": None,
            }
        ]
    )
    assert all(m["value"] is None for m in result["metrics"])


def xmls(value="100", total="100", amendment="false"):
    cover = f"<r><reportCalendarOrQuarter>09-30-2026</reportCalendarOrQuarter><tableEntryTotal>1</tableEntryTotal><tableValueTotal>{total}</tableValueTotal><isAmendment>{amendment}</isAmendment></r>".encode()
    table = f"<informationTable><infoTable><nameOfIssuer>Unit input</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>UNIT</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable></informationTable>".encode()
    return cover, table


def filing():
    return {
        "reportDate": "2026-09-30",
        "filingDate": "2026-11-16",
        "acceptanceDateTime": "2026-11-16T21:00Z",
        "accessionNumber": "unit",
        "url": "https://www.sec.gov/",
    }


def test_13f_counts_totals_units_and_unknown_cusip():
    row = parse_filing(*xmls(), filing(), "Unit manager", "2026-11-25T00:00Z", {})
    assert row["reported_total_usd"] == "100" and row["rows"][0]["ticker"] is None
    assert row["original_value_multiplier"] == 1
    old = {**filing(), "filingDate": "2022-11-16"}
    assert parse_filing(*xmls(), old, "Unit", "2026-11-25T00:00Z", {})["reported_total_usd"] == "100000"


@pytest.mark.parametrize("cover,table", [xmls(total="101"), (b"<!DOCTYPE r><r/>", b"<r/>")])
def test_13f_rejects_bad_totals_or_unsafe_xml(cover, table):
    with pytest.raises(ValueError):
        parse_filing(cover, table, filing(), "Unit", "2026-11-25T00:00Z", {})


def test_13f_new_holdings_requires_base():
    row = parse_filing(*xmls(), filing(), "Unit", "2026-11-25T00:00Z", {})
    with pytest.raises(ValueError):
        compare_filings([{**row, "amendment": "NEW HOLDINGS"}], [], "2026-11-25T00:00Z")


def test_13f_split_adjusted_change_not_false_purchase():
    row = parse_filing(*xmls(), filing(), "Unit", "2026-11-25T00:00Z", {"UNIT": "UNIT"})
    prior = {**row, "report_date": "2026-06-30", "rows": [{**row["rows"][0], "shares": "1"}]}
    result = compare_filings(
        [prior, row],
        [{"type": "split", "symbol": "UNIT", "effective_date": "2026-08-01", "ratio": "10"}],
        "2026-11-25T00:00Z",
    )
    assert result["holdings"][0]["change"] == "unchanged"


def test_news_no_generated_sentiment_and_updated_availability():
    row = {
        "id": 1,
        "created_at": "2026-11-01T00:00Z",
        "updated_at": "2026-11-24T00:00Z",
        "headline": "Unit earnings revenue $10 million, outlook 3%",
        "url": "https://example.com",
        "symbols": [],
        "content": "",
    }
    news = normalize_article(row, "2026-11-25T01:00Z", "2026-11-25T01:01Z")
    assert news["sentiment"] is None and news["llm_status"] == "unavailable"
    assert news["quality"] == "metadata_only" and news["topics"] == ["earnings", "guidance"]
    assert news["numeric_mentions"] == ["$10 million", "3%"]
    assert pd.Timestamp(news["available_at"]) == pd.Timestamp("2026-11-25T01:01Z")
    assert "summary" not in news


def test_snapshot_hashes_and_unavailable_sources(tmp_path):
    assert InformationService(tmp_path).financials("AAPL")["metrics"] == []
    assert InformationService(tmp_path).report()["earnings_calls"]["status"] == "unavailable"
    folder, _ = publish(
        tmp_path, "news", {"articles.json": []}, {"status": "complete", "collected_at": "2026-11-25T00:00Z"}
    )
    assert read_snapshot(tmp_path, "news")[0] == folder
    (folder / "articles.json").write_text("[1]")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_snapshot(tmp_path, "news")


def test_before_real_observation_and_current_real_coverage():
    directory = Path(__file__).resolve().parents[2] / "datasets"
    if not (directory / "information/financials/latest.json").exists():
        pytest.skip("private actual cache absent")
    service = InformationService(directory)
    for symbol in ("AAPL", "MSFT", "NVDA", "TSLA"):
        assert service.financials(symbol, "2026-11-24T23:59:59Z")["metrics"] == []
        actual = service.financials(symbol)
        assert actual["financial_source"] == "SEC CompanyFacts" and actual["period_end"].startswith("2026-")
        assert sum(m["value"] is not None for m in actual["metrics"]) >= 12
        assert actual["statement"]["debt"] is None
    old = service.report(as_of="2026-11-24T23:59:59Z")
    assert old["news"]["articles"] == [] and old["institutions"]["managers"] == []


@pytest.mark.parametrize(
    "url",
    [
        "http://data.sec.gov/submissions/CIK0000320193.json",
        "https://evil.example/submissions/CIK0000320193.json",
        "https://data.sec.gov/submissions/CIK0000320193.json?x=1",
        "https://www.sec.gov/Archives/edgar/data/123/000000000000000000/../secret",
    ],
)
def test_sec_endpoint_scope(tmp_path, url):
    import httpx

    from quantcore.data.providers.sec import SECData

    (tmp_path / ".env").write_text('SEC_USER_AGENT="QuantCore unit unit@example.com"')
    client = SECData(tmp_path, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    try:
        with pytest.raises(ValueError):
            client.get(url)
        assert client.get("https://data.sec.gov/submissions/CIK0000320193.json") == b"{}"
    finally:
        client.close()
