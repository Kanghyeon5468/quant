"""Observed public macro snapshots from FRED and the BLS release calendar."""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from quantcore.information.store import now, publish, read_snapshot

FRED = "https://fred.stlouisfed.org"
BLS_CALENDAR = "https://www.bls.gov/schedule/news_release/bls.ics"
FED_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
SERIES = {
    "GDPC1": ("미국 실질 GDP", "billions of chained 2017 USD", "quarterly"),
    "CPIAUCSL": ("미국 CPI", "index 1982–84=100", "monthly"),
    "PCEPILFE": ("미국 근원 PCE 물가지수", "index 2017=100", "monthly"),
    "UNRATE": ("미국 실업률", "percent", "monthly"),
    "PAYEMS": ("미국 비농업 고용", "thousands of persons", "monthly"),
    "FEDFUNDS": ("미국 유효 연방기금금리", "percent", "monthly"),
    "DGS2": ("미 국채 2년물", "percent", "daily"),
    "DGS10": ("미 국채 10년물", "percent", "daily"),
    "DEXKOUS": ("원/달러 기준 환율", "KRW per USD", "daily"),
    "DCOILWTICO": ("WTI 현물 원유", "USD per barrel", "daily"),
}


def parse_series(raw, series, collected_at):
    rows = csv.DictReader(io.StringIO(raw))
    if not rows.fieldnames or series not in rows.fieldnames:
        raise ValueError("unexpected FRED CSV")
    observations = {}
    for row in rows:
        period = date.fromisoformat(row.get("observation_date") or row["DATE"])
        raw_value = row[series]
        if raw_value in ("", ".", None) or period > datetime.fromisoformat(collected_at).date():
            continue
        value = Decimal(raw_value)
        if not value.is_finite() or (series == "DEXKOUS" and value <= 0):
            raise ValueError("invalid FRED observation")
        key = period.isoformat()
        if key in observations and observations[key] != str(value):
            raise ValueError("conflicting FRED observation")
        observations[key] = str(value)
    if not observations:
        raise ValueError("no public macro observations")
    label, unit, frequency = SERIES[series]
    return {"id": series, "label": label, "unit": unit, "frequency": frequency,
            "source": "FRED", "url": f"{FRED}/series/{series}", "available_at": collected_at,
            "basis": "current revised series; historical publication vintages unavailable",
            "observations": [{"period": key, "value": observations[key]} for key in sorted(observations)]}


def parse_calendar(raw):
    events, event = [], {}
    if "BEGIN:VCALENDAR" not in raw:
        raise ValueError("unexpected BLS calendar")
    raw = raw.replace("\r\n", "\n").replace("\n ", "").replace("\n\t", "")
    for line in raw.splitlines():
        if line == "BEGIN:VEVENT":
            event = {}
        elif line == "END:VEVENT":
            stamp = event.get("DTSTART", "")
            if len(stamp) >= 15 and event.get("SUMMARY"):
                local = datetime.strptime(stamp.rstrip("Z"), "%Y%m%dT%H%M%S")
                zone = timezone.utc if stamp.endswith("Z") else ZoneInfo("America/New_York")
                events.append({"title": event["SUMMARY"].replace("\\,", ","),
                               "scheduled_at": local.replace(tzinfo=zone).astimezone(timezone.utc).isoformat()})
        else:
            key, _, value = line.partition(":")
            event[key.split(";")[0]] = value
    if not events:
        raise ValueError("no dated BLS calendar events")
    return sorted(events, key=lambda row: row["scheduled_at"])


def parse_fomc(raw):
    heading = r"<h4>\s*(?:<a[^>]*>\s*)?(20\d{2}) FOMC Meetings"
    sections = re.split(heading, raw, flags=re.I)
    pattern = r'fomc-meeting__month[^>]*>\s*(?:<strong>)?([A-Za-z]+)(?:</strong>)?.*?fomc-meeting__date[^>]*>\s*(\d{1,2})-(\d{1,2})'
    events = []
    current_year = datetime.now(timezone.utc).year
    for i in range(1, len(sections), 2):
        year = int(sections[i])
        if year not in (current_year, current_year+1):
            continue
        for month, start, end in re.findall(pattern, sections[i+1], re.S):
            if int(start) > int(end):
                continue
            day = datetime.strptime(f"{year} {month} {end}", "%Y %B %d").date()
            events.append({"title": "FOMC meeting (last day)", "scheduled_date": day.isoformat(), "timezone": "America/New_York"})
    if not events:
        raise ValueError("no FOMC meeting dates")
    return sorted(events, key=lambda row: row["scheduled_date"])


def collect(directory, transport=None):
    previous = read_snapshot(directory, "macro")
    report = json.loads((previous[0] / "report.json").read_text()) if previous else {"series": {}, "calendar": {}}
    failures = {}
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=365 * 5)).isoformat()
    with httpx.Client(timeout=12, follow_redirects=False, transport=transport) as client:
        for series in SERIES:
            try:
                response = client.get(f"{FRED}/graph/fredgraph.csv", params={"id": series, "cosd": cutoff})
                response.raise_for_status()
                report["series"][series] = parse_series(response.text, series, now())
            except (httpx.HTTPError, ValueError, KeyError, InvalidOperation) as error:
                failures[series] = type(error).__name__
        try:
            response = client.get(BLS_CALENDAR)
            response.raise_for_status()
            report["calendar"]["bls"] = {"events": parse_calendar(response.text), "url": BLS_CALENDAR,
                                  "available_at": now(), "source": "U.S. Bureau of Labor Statistics"}
        except (httpx.HTTPError, ValueError) as error:
            failures["bls_calendar"] = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
        try:
            response = client.get(FED_CALENDAR)
            response.raise_for_status()
            report["calendar"]["fomc"] = {"events": parse_fomc(response.text), "url": FED_CALENDAR,
                                           "available_at": now(), "source": "Federal Reserve"}
        except (httpx.HTTPError, ValueError) as error:
            failures["fomc_calendar"] = type(error).__name__
    report.update(status="partial" if failures else "ok", failures=failures, checked_at=now())
    publish(directory, "macro", {"report.json": report}, {"collected_at": report["checked_at"], "status": report["status"]})
    return report


def report(directory):
    snapshot = read_snapshot(directory, "macro")
    if not snapshot:
        return {"status": "unavailable", "series": {}, "calendar": {}, "reason": "공개 거시 데이터 수집본이 없습니다."}
    data = json.loads((Path(snapshot[0]) / "report.json").read_text())
    two, ten = (data["series"].get(name, {}).get("observations", []) for name in ("DGS2", "DGS10"))
    shorter = {row["period"]: row["value"] for row in two}
    data["curve"] = [
        {"period": row["period"], "spread_pp": str(Decimal(row["value"]) - Decimal(shorter[row["period"]]))}
        for row in ten if row["period"] in shorter
    ]
    return data


def usd_to_krw(source, amount):
    fx = source["series"].get("DEXKOUS")
    if not fx or "DEXKOUS" in source.get("failures", {}):
        raise ValueError("USD/KRW reference rate unavailable")
    row = fx["observations"][-1]
    if (datetime.now(timezone.utc).date() - date.fromisoformat(row["period"])).days > 14:
        raise ValueError("USD/KRW reference rate is stale")
    return {"usd": str(amount), "krw": str((amount * Decimal(row["value"])).quantize(Decimal("1"))),
            "rate": row["value"], "period": row["period"], "available_at": fx["available_at"], "url": fx["url"]}
