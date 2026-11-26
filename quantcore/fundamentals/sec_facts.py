"""Real SEC CompanyFacts normalization: revision-aware quarters, YTD differences and TTM.
No absent financial field is filled with zero. EPS/weighted share YTD values are
not subtracted as if they were additive cash flows.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantcore.fundamentals.analysis import analyze

FLOW_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
        "PaymentsToAcquireProductiveAssets",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "DepreciationAmortizationAndAccretionNet",
    ],
    "interest_expense": ["InterestExpenseNonOperating", "InterestAndDebtExpense", "InterestExpense"],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
}
STOCK_TAGS = {
    "assets": ["Assets"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "liabilities": ["Liabilities"],
    "long_term_debt_current": ["LongTermDebtCurrent"],
    "long_term_debt_noncurrent": ["LongTermDebtNoncurrent"],
    "shares": ["CommonStockSharesOutstanding"],
}


ADVANCED_FLOWS = {
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "common_stock_issuance": ["ProceedsFromIssuanceOfCommonStock"],
}
ADVANCED_STOCKS = {
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent"],
    "payables": ["AccountsPayableCurrent"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
}


def aware(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("financial cutoff requires timezone")
    return stamp.tz_convert("UTC")


def filing_time(row, acceptance):
    if row.get("accn") in acceptance:
        return aware(acceptance[row["accn"]]), "SEC acceptanceDateTime"
    # CompanyFacts often provides only a date. Conservatively wait until the end of that NY filing day.
    day = pd.Timestamp(row["filed"]).tz_localize("America/New_York") + pd.Timedelta(days=1)
    return day.tz_convert("UTC"), "date-only: end of filing day in New York"


def facts_for_tag(payload, taxonomy, tag, unit, acceptance, collected_at, cutoff):
    rows = payload.get("facts", {}).get(taxonomy, {}).get(tag, {}).get("units", {}).get(unit, [])
    chosen = {}
    for original in rows:
        if original.get("form") not in ("10-K", "10-Q", "10-K/A", "10-Q/A") or not original.get("filed"):
            continue
        public, basis = filing_time(original, acceptance)
        available = max(public, aware(collected_at))
        if available > cutoff or pd.Timestamp(original["end"]).date() > cutoff.date():
            continue
        value = float(original["val"])
        if not np.isfinite(value):
            continue
        key = (original.get("start"), original["end"])
        row = {
            **original,
            "value": value,
            "tag": tag,
            "taxonomy": taxonomy,
            "unit": unit,
            "public_at": public.isoformat(),
            "available_at": available.isoformat(),
            "public_time_basis": basis,
        }
        previous = chosen.get(key)
        if previous is None or (row["public_at"], row["accn"]) > (previous["public_at"], previous["accn"]):
            chosen[key] = row
    return list(chosen.values())


def field_facts(payload, aliases, unit, acceptance, collected_at, cutoff, taxonomy="us-gaap"):
    result = {}
    for tag in aliases:
        for row in facts_for_tag(payload, taxonomy, tag, unit, acceptance, collected_at, cutoff):
            result.setdefault((row.get("start"), row["end"]), row)
    return list(result.values())


def standalone_quarters(rows, additive=True):
    rows = [r for r in rows if r.get("start")]
    direct = {}
    for row in rows:
        days = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).days + 1
        if 75 <= days <= 105:
            direct[(row["start"], row["end"])] = {
                **row,
                "derivation": "reported standalone quarter",
                "components": [row],
            }
    if additive:
        for row in rows:
            duration = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).days + 1
            if not 150 <= duration <= 380:
                continue
            prior = [
                p
                for p in rows
                if p["start"] == row["start"]
                and p["end"] < row["end"]
                and 75 <= (pd.Timestamp(row["end"]) - pd.Timestamp(p["end"])).days <= 105
            ]
            if not prior:
                continue
            previous = max(prior, key=lambda p: p["end"])
            start = (pd.Timestamp(previous["end"]) + pd.Timedelta(days=1)).date().isoformat()
            direct.setdefault(
                (start, row["end"]),
                {
                    **row,
                    "start": start,
                    "value": row["value"] - previous["value"],
                    "available_at": max(row["available_at"], previous["available_at"]),
                    "public_at": max(row["public_at"], previous["public_at"]),
                    "derivation": "current YTD minus preceding YTD with identical fiscal start",
                    "components": [row, previous],
                },
            )
    # Multiple tag periods with the same end must not count as two quarters.
    by_end = {}
    for row in direct.values():
        previous = by_end.get(row["end"])
        if previous is None or (row["derivation"].startswith("reported"), row["public_at"]) > (
            previous["derivation"].startswith("reported"),
            previous["public_at"],
        ):
            by_end[row["end"]] = row
    return by_end


def normalize(payload, collected_at, acceptance=None, cutoff=None, *, advanced=False):
    cutoff = aware(cutoff or pd.Timestamp.now(tz="UTC"))
    acceptance = acceptance or {}
    flow_tags = {**FLOW_TAGS, **ADVANCED_FLOWS} if advanced else FLOW_TAGS
    stock_tags = {**STOCK_TAGS, **ADVANCED_STOCKS} if advanced else STOCK_TAGS
    flows = {
        key: standalone_quarters(field_facts(payload, tags, "USD", acceptance, collected_at, cutoff))
        for key, tags in flow_tags.items()
    }
    eps = standalone_quarters(
        field_facts(payload, ["EarningsPerShareDiluted"], "USD/shares", acceptance, collected_at, cutoff),
        additive=False,
    )
    stocks = {
        key: field_facts(
            payload, tags, "shares" if key == "shares" else "USD", acceptance, collected_at, cutoff
        )
        for key, tags in stock_tags.items()
    }
    dei = field_facts(
        payload,
        ["EntityCommonStockSharesOutstanding"],
        "shares",
        acceptance,
        collected_at,
        cutoff,
        taxonomy="dei",
    )
    ends = sorted(flows["revenue"])
    records = []
    for end in ends:
        revenue_quarters = [flows["revenue"][e] for e in ends if e <= end][-4:]
        if len(revenue_quarters) != 4:
            continue
        if any(
            pd.Timestamp(b["start"]) != pd.Timestamp(a["end"]) + pd.Timedelta(days=1)
            for a, b in zip(revenue_quarters, revenue_quarters[1:])
        ):
            continue
        if not 330 <= (pd.Timestamp(end) - pd.Timestamp(revenue_quarters[0]["start"])).days + 1 <= 380:
            continue
        expected = [(r["start"], r["end"]) for r in revenue_quarters]
        record = {
            "period_end": end,
            "period_start": revenue_quarters[0]["start"],
            "currency": "USD",
            "mode": "historical",
            "source": "SEC CompanyFacts",
            "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(payload['cik']):010d}.json",
            "industry": "nonfinancial",
            "evidence": {},
            "missing_fields": [],
        }
        for key, by_end in flows.items():
            matching = [by_end.get(e) for _, e in expected]
            if all(
                r is not None and (r["start"], r["end"]) == period for r, period in zip(matching, expected)
            ):
                record[key] = sum(r["value"] for r in matching)
                record["evidence"][key] = matching
            else:
                record[key] = None
                record["missing_fields"].append(key)
        eps_quarters = [eps.get(e) for _, e in expected]
        record["reported_eps"] = (
            sum(r["value"] for r in eps_quarters)
            if all(r and (r["start"], r["end"]) == p for r, p in zip(eps_quarters, expected))
            else None
        )
        for key, rows in stocks.items():
            matching = [r for r in rows if r["end"] == end and not r.get("start")]
            row = max(matching, key=lambda r: r["public_at"]) if matching else None
            record[key] = row["value"] if row else None
            if row:
                record["evidence"][key] = [row]
        record["debt"] = None  # Long-term debt is not silently relabeled as total interest-bearing debt.
        if (
            record.get("long_term_debt_current") is not None
            and record.get("long_term_debt_noncurrent") is not None
        ):
            record["long_term_debt_total"] = (
                record["long_term_debt_current"] + record["long_term_debt_noncurrent"]
            )
        tax, pretax = record.get("income_tax"), record.get("pretax_income")
        record["tax_rate"] = tax / pretax if tax is not None and pretax and 0 <= tax / pretax <= 1 else None
        evidence = [p for rows in record["evidence"].values() for r in rows for p in r.get("components", [r])]
        record["published_at"] = max((r["public_at"] for r in evidence), default=collected_at)
        record["available_at"] = max((r["available_at"] for r in evidence), default=collected_at)
        records.append(record)
    point_shares = sorted(
        [r for r in dei + stocks["shares"] if not r.get("start")], key=lambda r: (r["end"], r["public_at"])
    )
    return {
        "records": records,
        "point_shares": point_shares,
        "cutoff": cutoff.isoformat(),
        "status": "ok" if records else "unavailable",
        "source_entity": payload.get("entityName"),
        "limitations": [
            "additive USD flows may use same-fiscal-start YTD differences; EPS YTD is not subtracted",
            "facts are usable only after both recorded collection time and publication time",
            "missing tags/periods remain null; debt is not inferred from absent short-term borrowing",
        ],
    }


def analyze_real(normalized):
    records = normalized["records"]
    if not records:
        return {"status": "missing", "metrics": [], "reason": "사용 가능한 연속 4분기 재무자료가 없습니다."}
    current = records[-1]
    previous = [
        r
        for r in records[:-1]
        if 330 <= (pd.Timestamp(current["period_end"]) - pd.Timestamp(r["period_end"])).days <= 400
    ]
    prior = (
        min(
            previous,
            key=lambda r: abs(
                (pd.Timestamp(current["period_end"]) - pd.Timestamp(r["period_end"])).days - 365
            ),
        )
        if previous
        else None
    )
    # Reuse the established financial-ratio engine with a comparable prior-year TTM period.
    result = analyze(([prior] if prior else []) + [current])
    for metric in result["metrics"]:
        if metric["name"] == "eps_growth":
            now, before = current.get("reported_eps"), (prior or {}).get("reported_eps")
            metric["value"] = (
                (now - before) / before if now is not None and before is not None and before > 0 else None
            )
            metric["status"] = "ok" if metric["value"] is not None else "not_applicable"
            metric["formula"] = "year-over-year growth of summed directly reported quarterly diluted EPS"
    result.update(
        status="partial" if any(m["value"] is None for m in result["metrics"]) else "ok",
        limitations=normalized["limitations"],
        period_basis="TTM flows; year-over-year comparable TTM; point balance sheet",
        period_start=current["period_start"],
        period_end=current["period_end"],
        evidence=current["evidence"],
        missing_fields=current["missing_fields"],
    )
    return result


def load_financial_snapshot(data_directory):
    directory = Path(data_directory) / "information/financials"
    pointer = directory / "latest.json"
    if not pointer.exists():
        return None
    folder = directory / Path(json.loads(pointer.read_text())["snapshot_directory"]).name
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, expected in manifest["hashes"].items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError("financial snapshot hash mismatch")
    return folder, manifest
