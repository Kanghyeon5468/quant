"""Bounded refreshes using only existing SEC and Alpaca read connections."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from quantcore.core.files import atomic_json
from quantcore.data.providers.alpaca import SYMBOLS, AlpacaData
from quantcore.data.providers.sec import SECData
from quantcore.data.reference.securities import load_reference
from quantcore.fundamentals.sec_facts import analyze_real, normalize
from quantcore.information.institutions import compare_filings, parse_filing
from quantcore.information.news import normalize_article
from quantcore.information.store import now, publish, read_snapshot

COMPANIES = {"AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "TSLA": 1318605}
MANAGERS = {1067983: "Berkshire Hathaway", 102909: "Vanguard Group"}


def cached_probe(root):
    directory = Path(root) / "datasets/information"
    pointer = directory / "latest.json"
    if not pointer.exists():
        return None
    folder = directory / Path(json.loads(pointer.read_text())["snapshot_directory"]).name
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, digest in manifest["hashes"].items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("probe hash mismatch")
    return folder, manifest


def financials(root, sec, reuse_probe=False):
    root = Path(root)
    probe = cached_probe(root) if reuse_probe else None
    ref = load_reference(root)
    documents, coverage = {}, {}
    collected = now()
    for symbol, cik in COMPANIES.items():
        name = f"companyfacts_{symbol}.json"
        raw = (
            (probe[0] / name).read_bytes()
            if probe
            else sec.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        )
        submissions = (
            sec.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            if not probe
            else (Path(ref["directory"]) / f"sec_{symbol}.json").read_bytes()
        )
        payload = json.loads(raw)
        if int(payload["cik"]) != cik:
            raise ValueError("SEC CompanyFacts identity mismatch")
        recent = json.loads(submissions)["filings"]["recent"]
        acceptance = dict(zip(recent["accessionNumber"], recent["acceptanceDateTime"]))
        observed = probe[1]["collected_at"] if probe else now()
        normalized = normalize(payload, observed, acceptance)
        normalized.update(symbol=symbol, collected_at=observed, analyzed_at=now())
        report = analyze_real(normalized)
        documents.update(
            {name: raw, f"submissions_{symbol}.json": submissions, f"normalized_{symbol}.json": normalized}
        )
        coverage[symbol] = {
            "status": report["status"],
            "period_end": report.get("period_end"),
            "metrics_available": sum(m["value"] is not None for m in report["metrics"]),
            "metrics_total": len(report["metrics"]),
        }
    publish(
        root / "datasets",
        "financials",
        documents,
        {
            "status": "complete",
            "collected_at": collected,
            "completed_at": now(),
            "source": "SEC CompanyFacts + submissions",
            "coverage": coverage,
        },
    )
    return coverage


def filings_from_submissions(data):
    recent = data["filings"]["recent"]
    rows = [dict(zip(recent, values)) for values in zip(*recent.values())]
    rows = [r for r in rows if r["form"] in ("13F-HR", "13F-HR/A") and r.get("reportDate")]
    periods = sorted({r["reportDate"] for r in rows}, reverse=True)[:2]
    return [r for r in rows if r["reportDate"] in periods]


def institutions(root, sec):
    root = Path(root)
    reference = load_reference(root)
    mapping = {}
    for event in reference["actions"] if reference else []:
        raw = event["raw"]
        cusip = raw.get("cusip") or raw.get("new_cusip")
        if cusip and event["symbol"] in SYMBOLS:
            mapping[cusip] = event["symbol"]
    documents, managers, failures = {}, [], []
    for cik, label in MANAGERS.items():
        try:
            raw = sec.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            data = json.loads(raw)
            if int(data["cik"]) != cik:
                raise ValueError("13F manager identity mismatch")
            documents[f"manager_{cik}.json"] = raw
            filings = []
            for filing in filings_from_submissions(data):
                accn = filing["accessionNumber"].replace("-", "")
                base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/"
                index = sec.get(base + "index.json")
                documents[f"{accn}_index.json"] = index
                names = [
                    r["name"]
                    for r in json.loads(index)["directory"]["item"]
                    if r["name"].endswith(".xml") and "/" not in r["name"]
                ]
                primary = Path(filing["primaryDocument"]).name
                if primary not in names:
                    raise ValueError("13F cover not in official archive index")
                cover = sec.get(base + primary)
                tables = [n for n in names if n != primary]
                if len(tables) != 1:
                    raise ValueError("13F information table is ambiguous or unavailable")
                table = sec.get(base + tables[0])
                documents[f"{accn}_cover.xml"] = cover
                documents[f"{accn}_table.xml"] = table
                observed = now()
                item = parse_filing(
                    cover,
                    table,
                    {**filing, "url": base + accn[:10] + "-" + accn[10:12] + "-" + accn[12:] + "-index.html"},
                    data["name"],
                    observed,
                    mapping,
                )
                filings.append(item)
            managers.append(compare_filings(filings, reference["actions"] if reference else [], now()))
        except (RuntimeError, ValueError, KeyError) as error:
            failures.append({"manager": label, "status": "unavailable", "reason": str(error)[:180]})
    if not managers:
        raise RuntimeError("No actual 13F filings could be verified: " + json.dumps(failures))
    report = {
        "status": "partial" if failures or any(m["status"] != "ok" for m in managers) else "ok",
        "collected_at": now(),
        "managers": managers,
        "unavailable": failures,
        "excluded": [
            {
                "manager": "BlackRock Finance, Inc. CIK1364742",
                "reason": "cached entity latest 2024 report; current parent identity not verified",
            }
        ],
    }
    documents["report.json"] = report
    publish(
        root / "datasets",
        "institutions",
        documents,
        {
            "status": report["status"],
            "collected_at": now(),
            "source": "SEC EDGAR 13F-HR official XML",
            "managers": len(managers),
        },
    )
    return {
        "managers": len(managers),
        "filings": sum(len(m["filings"]) for m in managers),
        "failures": failures,
    }


def news(root, env_file):
    root = Path(root)
    old = read_snapshot(root / "datasets", "news")
    previous = json.loads((old[0] / "articles.json").read_text()) if old else []
    # Fixed bounded window, overlap on incremental fetch; no fabricated old-news history.
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    if old:
        start = max(start, pd.Timestamp(old[1]["collected_at"]) - pd.Timedelta(hours=2))
    client = AlpacaData(env_file)
    docs, incoming, truncated = {}, [], False
    try:
        pages = client.pages(
            "/v1beta1/news",
            {
                "symbols": ",".join(SYMBOLS),
                "start": start.isoformat(),
                "end": pd.Timestamp.now(tz="UTC").isoformat(),
                "limit": 50,
                "sort": "desc",
                "include_content": "true",
            },
        )
        for i, page in enumerate(pages):
            docs[f"raw_news_{i:03d}.json"] = page
            observed = now()
            for row in page.get("news", []):
                if urlsplit(row["url"]).scheme not in ("https", "http"):
                    raise ValueError("invalid news source URL")
                incoming.append(normalize_article(row, observed, now()))
            if i >= 9:
                truncated = bool(page.get("next_page_token"))
                break
    finally:
        client.close()
    # Preserve first observed availability for identical article versions across refreshes.
    versions = {(a["id"], a["updated_at"], a["content_sha256"]): a for a in previous}
    for article in incoming:
        versions.setdefault((article["id"], article["updated_at"], article["content_sha256"]), article)
    articles = sorted(versions.values(), key=lambda a: (a["created_at"], a["updated_at"]), reverse=True)[
        :5000
    ]
    docs["articles.json"] = articles
    collected = now()
    publish(
        root / "datasets",
        "news",
        docs,
        {
            "status": "truncated" if truncated else "complete",
            "collected_at": collected,
            "source": "Alpaca News API",
            "previous_snapshot": old[1]["snapshot_id"] if old else None,
            "previous_manifest_sha256": hashlib.sha256((old[0] / "manifest.json").read_bytes()).hexdigest()
            if old
            else None,
            "article_versions": len(articles),
            "fetched": len(incoming),
            "truncated": truncated,
            "llm_status": "unavailable",
            "earnings_transcripts": "unavailable",
            "window_start": start.isoformat(),
        },
    )
    return {"articles": len(articles), "fetched": len(incoming), "truncated": truncated}


def refresh(root, env_file=None, force=False, reuse_probe=False):
    """Independent TTLs/backoff. Failures preserve the last successful immutable snapshot."""
    from quantcore.paper.journal import Journal

    root = Path(root)
    lock = Journal(root / "artifacts/information_worker")
    results = {}
    try:
        with lock.lock():
            state_path = root / "artifacts/information_worker/state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            jobs = [("financials", 24 * 60), ("institutions", 24 * 60), ("news", 15)]
            configured = root / "configs/information.json"
            if configured.exists() and json.loads(configured.read_text()).get("earnings_calls"):
                jobs += [("earnings", 24 * 60), ("llm_analysis", 15)]
            if configured.exists() and json.loads(configured.read_text()).get("macro_public"):
                jobs.append(("macro", 6 * 60))
            if configured.exists() and json.loads(configured.read_text()).get("crypto_public"):
                jobs.append(("crypto", 6 * 60))
            for kind, ttl in jobs:
                last = state.get(kind, {})
                if (
                    not force
                    and last.get("next_attempt_at")
                    and pd.Timestamp(last["next_attempt_at"]) > pd.Timestamp.now(tz="UTC")
                ):
                    results[kind] = last
                    continue
                try:
                    if kind == "earnings":
                        from quantcore.earnings.collector import collect

                        result = collect(root)
                    elif kind == "llm_analysis":
                        from quantcore.analysis.worker import run

                        result = run(root)
                    elif kind == "macro":
                        from quantcore.macro.public import collect

                        result = collect(root / "datasets")
                        result = {k: result[k] for k in ("status", "checked_at", "failures")}
                    elif kind == "crypto":
                        from quantcore.data.providers.coinbase_public import collect

                        result = {"status": "ok", **collect(root / "datasets")}
                    elif kind == "news":
                        result = news(root, env_file)
                    else:
                        sec = SECData(root)
                        try:
                            result = (
                                financials(root, sec, reuse_probe)
                                if kind == "financials"
                                else institutions(root, sec)
                            )
                        finally:
                            sec.close()
                    results[kind] = {
                        "status": "partial"
                        if result.get("failures")
                        else result["status"]
                        if result.get("status") in ("unavailable", "pending")
                        else "ok",
                        "completed_at": now(),
                        "result": result,
                        "next_attempt_at": (
                            pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=ttl)
                        ).isoformat(),
                    }
                except Exception as error:
                    failures = last.get("failures", 0) + 1
                    results[kind] = {
                        "status": "failed",
                        "failures": failures,
                        "checked_at": now(),
                        "reason": str(error)[:240],
                        "next_attempt_at": (
                            pd.Timestamp.now(tz="UTC")
                            + pd.Timedelta(minutes=min(24 * 60, 15 * 3 ** min(failures - 1, 4)))
                        ).isoformat(),
                    }
                state[kind] = results[kind]
                atomic_json(state_path, state)
                atomic_json(root / "datasets/information/worker_status.json", state)
    finally:
        lock.close()
    return results
