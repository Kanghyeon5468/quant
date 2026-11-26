"""Official Q4 IR feeds and linked public documents only; bounded, robots-aware, no audio."""

import hashlib
import json
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from quantcore.earnings.parsing import extract, segments
from quantcore.information.store import now, publish, read_snapshot

ADAPTERS = {
    "NVDA": {
        "host": "investor.nvidia.com",
        "page": "https://investor.nvidia.com/financial-info/financial-reports/",
        "allowed": {
            "investor.nvidia.com": ("/files/", "/financial-info/", "/feed/"),
            "nvidianews.nvidia.com": ("/news/",),
            "s201.q4cdn.com": ("/141608511/files/",),
        },
    },
    "AAPL": {
        "host": "investor.apple.com",
        "page": "https://investor.apple.com/investor-relations/default.aspx",
        "allowed": {
            "investor.apple.com": ("/feed/", "/investor-relations/"),
            "www.apple.com": ("/newsroom/",),
            "s2.q4cdn.com": ("/470004039/files/",),
        },
    },
}
CATEGORIES = {
    "transcript": "transcript",
    "cfo": "cfo_commentary",
    "news": "earnings_release",
    "statement": "financial_statements",
}


class OfficialIR:
    def __init__(self, adapter, transport=None):
        self.adapter = adapter
        self.robots = {}
        self.next_request = 0.0
        self.client = httpx.Client(
            timeout=25,
            headers={"User-Agent": "QuantCore-Research/1.0"},
            transport=transport,
            follow_redirects=False,
        )

    def close(self):
        self.client.close()

    def get(self, url, params=None):
        p = urlsplit(url)
        if (
            p.scheme != "https"
            or p.username
            or p.password
            or p.port
            or p.fragment
            or ".." in p.path
            or p.hostname not in self.adapter["allowed"]
            or not p.path.startswith(self.adapter["allowed"][p.hostname])
        ):
            raise ValueError("URL is outside verified official IR source paths")
        if p.hostname not in self.robots:
            response = self.client.get(f"https://{p.hostname}/robots.txt")
            if response.status_code not in (200, 404):
                raise RuntimeError(f"IR robots unavailable HTTP {response.status_code}; stopped")
            parser = RobotFileParser()
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            self.robots[p.hostname] = parser
        if not self.robots[p.hostname].can_fetch("QuantCore-Research", url):
            raise RuntimeError("IR robots excludes this document")
        time.sleep(max(0, self.next_request - time.monotonic()))
        self.next_request = time.monotonic() + 0.6
        with self.client.stream("GET", url, params=params) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Official IR HTTP {response.status_code}; no bypass")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 15 * 1024 * 1024:
                    raise ValueError("IR document exceeds 15 MB limit")
            return bytes(data), response.headers.get("content-type", "")


def collect(root):
    from pathlib import Path

    root = Path(root)
    previous = read_snapshot(root / "datasets", "earnings")
    old = json.loads((previous[0] / "documents.json").read_text()) if previous else []
    old_by_key = {d["document_key"]: d for d in old}
    documents, raw_files, failures, coverage = [], {}, [], {}
    for symbol, adapter in ADAPTERS.items():
        client = OfficialIR(adapter)
        try:
            url = f"https://{adapter['host']}/feed/FinancialReport.svc/GetFinancialReportList"
            raw, _ = client.get(
                url,
                {
                    "LanguageId": 1,
                    "reportTypes": "First Quarter|Second Quarter|Third Quarter|Fourth Quarter",
                    "year": -1,
                    "pageSize": 8,
                    "pageNumber": 0,
                },
            )
            raw_files[f"{symbol}_feed.json"] = raw
            reports = json.loads(raw)["GetFinancialReportListResult"][:2]
            kinds = []
            listed_transcripts = sum(
                d["DocumentCategory"].lower() == "transcript" for r in reports for d in r["Documents"]
            )
            for report in reports:
                for item in report["Documents"]:
                    kind = CATEGORIES.get(item["DocumentCategory"].lower())
                    if not kind:
                        continue  # Never download third-party webcast/audio or assume transcription rights.
                    source = urljoin(adapter["page"], item["DocumentPath"])
                    key = f"{symbol}:{item['DocumentId']}:{item.get('RevisionNumber')}"
                    cached = old_by_key.get(key)
                    if cached:
                        if cached.get("parser_version") != "speaker-v2":
                            cached = {
                                **cached,
                                "segments": segments((previous[0] / cached["text_file"]).read_text(), kind),
                                "parsed_at": now(),
                                "available_at": now(),
                                "parser_version": "speaker-v2",
                            }
                        documents.append(cached)
                        for name in (cached["raw_file"], cached["text_file"]):
                            raw_files[name] = (previous[0] / name).read_bytes()
                        kinds.append(kind)
                        continue
                    try:
                        payload, ctype = client.get(source)
                        observed = now()
                        text = extract(payload, ctype)
                        raw_sha = hashlib.sha256(payload).hexdigest()
                        name = raw_sha[:24]
                        raw_file = name + (".pdf" if payload.startswith(b"%PDF") else ".html")
                        text_file = name + ".txt"
                        raw_files[raw_file] = payload
                        raw_files[text_file] = text.encode()
                        parsed_at = now()
                        documents.append(
                            {
                                "document_key": key,
                                "symbol": symbol,
                                "company": "NVIDIA" if symbol == "NVDA" else "Apple",
                                "kind": kind,
                                "fiscal_year": report["ReportYear"],
                                "quarter": report["ReportSubType"],
                                "ir_report_date": report.get("ReportDate"),
                                "scheduled_at": None,
                                "actual_started_at": None,
                                "actual_ended_at": None,
                                "public_at": None,
                                "public_time_basis": "not verified; availability starts at collection and parsing",
                                "collected_at": observed,
                                "parsed_at": parsed_at,
                                "available_at": parsed_at,
                                "source_url": source,
                                "listing_url": adapter["page"],
                                "source_sha256": raw_sha,
                                "raw_file": raw_file,
                                "text_file": text_file,
                                "segments": segments(text, kind),
                                "characters": len(text),
                                "quality": "text_extracted",
                                "rights_status": "official public IR document; private research only; no raw redistribution",
                                "audio_downloaded": False,
                                "analysis_status": "pending_model_configuration",
                                "parser_version": "speaker-v2",
                            }
                        )
                        kinds.append(kind)
                    except (RuntimeError, ValueError, httpx.HTTPError) as error:
                        failures.append(
                            {"symbol": symbol, "kind": kind, "source_url": source, "reason": str(error)[:150]}
                        )
            coverage[symbol] = {
                "documents": len(kinds),
                "transcripts": kinds.count("transcript"),
                "listed_transcripts": listed_transcripts,
                "transcript_status": "available"
                if "transcript" in kinds
                else "access_blocked"
                if listed_transcripts
                else "unavailable",
                "reason": None
                if "transcript" in kinds
                else "Listed official transcript could not be collected under verified access/robots rules"
                if listed_transcripts
                else "No official transcript provided in the verified latest IR reports; webcast not downloaded",
            }
        except (RuntimeError, ValueError, KeyError, httpx.HTTPError) as error:
            failures.append({"symbol": symbol, "reason": str(error)[:150]})
        finally:
            client.close()
    if not documents:
        raise RuntimeError("No official earnings document collected: " + json.dumps(failures))
    from quantcore.earnings.comparison import compare

    raw_files["comparisons.json"] = compare(documents)
    raw_files["documents.json"] = documents
    _, manifest = publish(
        root / "datasets",
        "earnings",
        raw_files,
        {
            "status": "partial" if failures else "complete",
            "collected_at": now(),
            "coverage": coverage,
            "failures": failures,
            "source": "official issuer IR public financial-report feeds",
            "previous_snapshot": previous[1]["snapshot_id"] if previous else None,
            "documents": len(documents),
        },
    )
    return {
        "documents": len(documents),
        "coverage": coverage,
        "failures": failures,
        "snapshot_id": manifest["snapshot_id"],
    }
