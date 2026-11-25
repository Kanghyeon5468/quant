"""13F XML normalization with explicit filing units, amendment and stale-report status."""

from collections import defaultdict
from decimal import Decimal
from xml.etree import ElementTree as ET

import pandas as pd


def xml(raw):
    if len(raw) > 30 * 1024 * 1024 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("unsafe or oversized filing XML")
    return ET.fromstring(raw)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def value(node, name, default=None):
    return next((n.text.strip() for n in node.iter() if local(n.tag) == name and n.text), default)


def parse_filing(cover_raw, holdings_raw, filing, manager, collected_at, mapping):
    cover, table = xml(cover_raw), xml(holdings_raw)
    if pd.Timestamp(value(cover, "reportCalendarOrQuarter")).date().isoformat() != filing["reportDate"]:
        raise ValueError("13F cover/submissions period mismatch")
    scale = 1 if filing["filingDate"] >= "2023-01-03" else 1000
    rows = []
    for node in table.iter():
        if local(node.tag) != "infoTable":
            continue
        cusip = value(node, "cusip")
        amount, shares = Decimal(value(node, "value")), Decimal(value(node, "sshPrnamt"))
        if not amount.is_finite() or not shares.is_finite() or amount < 0 or shares < 0:
            raise ValueError("invalid 13F value/quantity")
        rows.append(
            {
                "cusip": cusip,
                "ticker": mapping.get(cusip),
                "issuer": value(node, "nameOfIssuer"),
                "class": value(node, "titleOfClass"),
                "put_call": value(node, "putCall"),
                "share_type": value(node, "sshPrnamtType"),
                "discretion": value(node, "investmentDiscretion"),
                "reported_value_usd": str(amount * scale),
                "shares": str(shares),
            }
        )
    expected_n, expected_v = value(cover, "tableEntryTotal"), value(cover, "tableValueTotal")
    if expected_n is None or int(expected_n) != len(rows) or expected_v is None:
        raise ValueError("13F table count could not be reconciled")
    if sum((Decimal(r["reported_value_usd"]) for r in rows), Decimal(0)) != Decimal(expected_v) * scale:
        raise ValueError("13F cover/table total mismatch")
    amendment = (
        value(cover, "amendmentType") if value(cover, "isAmendment", "false").lower() == "true" else None
    )
    public = pd.Timestamp(filing["acceptanceDateTime"])
    if public.tzinfo is None:
        raise ValueError("13F acceptance timestamp needs timezone")
    available = max(public, pd.Timestamp(collected_at))
    return {
        "manager": manager,
        "report_date": filing["reportDate"],
        "filed_date": filing["filingDate"],
        "accession": filing["accessionNumber"],
        "public_at": public.isoformat(),
        "collected_at": collected_at,
        "available_at": available.isoformat(),
        "amendment": amendment,
        "rows": rows,
        "value_unit": "USD",
        "original_value_multiplier": scale,
        "reported_total_usd": str(Decimal(expected_v) * scale),
        "entry_count": len(rows),
        "source_url": filing["url"],
        "reconciliation": "cover value and entry count verified",
    }


def compare_filings(filings, split_events, as_of):
    by_period = defaultdict(list)
    for filing in filings:
        by_period[filing["report_date"]].append(filing)
    effective = []
    for period, group in sorted(by_period.items()):
        active = None
        for filing in sorted(group, key=lambda f: (f["public_at"], f["accession"])):
            amendment = filing["amendment"]
            if amendment is None or amendment == "RESTATEMENT":
                active = {**filing, "rows": list(filing["rows"])}
            elif amendment == "NEW HOLDINGS" and active:
                active = {**filing, "rows": active["rows"] + filing["rows"]}
            else:
                raise ValueError("13F amendment needs a verified base/restatement; no inferred holdings")
        if active:
            effective.append(active)
    if not effective:
        return {"status": "unavailable", "reason": "No verified 13F filing"}
    current, prior = effective[-1], effective[-2] if len(effective) > 1 else None

    def aggregate(rows):
        output = {}
        for row in rows:
            key = row["cusip"], row["class"], row["share_type"], row["put_call"]
            result = output.setdefault(key, {**row, "shares": Decimal(0), "reported_value_usd": Decimal(0)})
            result["shares"] += Decimal(row["shares"])
            result["reported_value_usd"] += Decimal(row["reported_value_usd"])
        return output

    current_rows = aggregate(current["rows"])
    previous_rows = aggregate(prior["rows"]) if prior else {}
    holdings = []
    for key in current_rows.keys() | previous_rows.keys():
        row, old = current_rows.get(key), previous_rows.get(key)
        entry = dict(row or old)
        q = row["shares"] if row else Decimal(0)
        old_q = old["shares"] if old else Decimal(0)
        adjusted = old_q
        if prior and entry.get("ticker") and entry["share_type"] == "SH" and not entry["put_call"]:
            for event in split_events:
                if (
                    event["type"] == "split"
                    and event["symbol"] == entry["ticker"]
                    and prior["report_date"] < event["effective_date"] <= current["report_date"]
                ):
                    adjusted *= Decimal(event["ratio"])
        delta = q - adjusted if prior else None
        entry.update(
            shares=str(q),
            reported_value_usd=str(row["reported_value_usd"]) if row else "0",
            prior_shares=str(old_q) if prior else None,
            split_adjusted_prior_shares=str(adjusted) if prior else None,
            share_change=str(delta) if delta is not None else None,
            change_fraction=float(delta / adjusted) if adjusted and delta is not None else None,
            change="unavailable"
            if prior is None
            else (
                "new"
                if not adjusted and q
                else "exited"
                if not q
                else "increased"
                if delta > 0
                else "decreased"
                if delta < 0
                else "unchanged"
            ),
        )
        holdings.append(entry)
    age = (pd.Timestamp(as_of).date() - pd.Timestamp(current["report_date"]).date()).days
    return {
        "status": "stale" if age > 150 else "ok",
        "manager": current["manager"],
        "report_date": current["report_date"],
        "prior_report_date": prior["report_date"] if prior else None,
        "report_age_days": age,
        "available_at": max(f["available_at"] for f in effective[-2:]),
        "reported_total_usd": current["reported_total_usd"],
        "entry_count": current["entry_count"],
        "source_url": current["source_url"],
        "holdings": sorted(holdings, key=lambda r: Decimal(r["reported_value_usd"]), reverse=True),
        "filings": [{k: v for k, v in f.items() if k != "rows"} for f in filings],
        "limitations": [
            "13F is delayed reported long holdings, not current account holdings or complete NAV",
            "unmapped CUSIPs remain unmapped; options/principal are separate from common shares",
            "share changes are not transaction dates or execution prices",
        ],
    }
