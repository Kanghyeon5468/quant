"""Prepare real news/earnings evidence and run the configured model without mock fallbacks."""

import fcntl
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from quantcore.analysis.llm import Analyzer, digest, readiness, settings
from quantcore.analysis.usage import publish_usage
from quantcore.earnings.parsing import segments
from quantcore.information.store import now, publish, read_snapshot


def news_documents(directory):
    latest = read_snapshot(directory, "news")
    if not latest:
        return []
    articles = json.loads((latest[0] / "articles.json").read_text())
    selected = sorted(articles, key=lambda a: a["created_at"], reverse=True)[:20]
    needed = {(a["id"], a["updated_at"]): a for a in selected}
    result = []
    folder = latest[0]
    seen = set()
    alternatives = sorted((Path(directory) / "information/news").glob("*/manifest.json"), reverse=True)
    for _ in range(100):
        if folder.name in seen:
            raise ValueError("news parent snapshot cycle")
        seen.add(folder.name)
        manifest = json.loads((folder / "manifest.json").read_text())
        # Parent snapshots are hash verified before accessing their real original bodies.
        from hashlib import sha256

        for name, expected in manifest["hashes"].items():
            if Path(name).name != name or sha256((folder / name).read_bytes()).hexdigest() != expected:
                raise ValueError("news source hash mismatch")
        for name in manifest["hashes"]:
            if not name.startswith("raw_news_"):
                continue
            for row in json.loads((folder / name).read_text()).get("news", []):
                key = str(row["id"]), pd.Timestamp(row["updated_at"]).isoformat()
                article = needed.pop(key, None)
                if not article:
                    continue
                from quantcore.earnings.parsing import extract

                raw = (row.get("content") or row["headline"]).encode()
                text = extract(raw, "text/html") if len(raw) >= 200 else raw.decode()
                result.append(
                    {
                        "kind": "news",
                        "article_id": key[0],
                        "article_updated_at": key[1],
                        "symbols": article["symbols"],
                        "source_url": article["url"],
                        "source_sha256": digest(row),
                        "available_at": article["available_at"],
                        "segments": segments(text, "news"),
                        "content_scope": "body" if row.get("content") else "headline",
                    }
                )
        parent = manifest.get("previous_snapshot")
        if not needed:
            break
        if not parent:
            remaining = [p.parent for p in alternatives if p.parent.name not in seen]
            if not remaining:
                break
            folder = remaining[0]
            continue
        if Path(parent).name != parent:
            raise ValueError("invalid news parent path")
        folder = folder.parent / parent
    return result


def _run(root, config, ready):
    existing = read_snapshot(root / "datasets", "analysis")
    results = json.loads((existing[0] / "analyses.json").read_text()) if existing else []
    # Retain source-specific analyses; future models never overwrite earlier availability.
    known = {r["analysis_key"] for r in results}
    old_failures = existing[1].get("failures", []) if existing else []
    known |= {r["analysis_key"] for r in old_failures if r.get("analysis_key")}
    candidates = news_documents(root / "datasets")
    earnings = read_snapshot(root / "datasets", "earnings")
    if earnings:
        for document in json.loads((earnings[0] / "documents.json").read_text()):
            if document["kind"] in ("transcript", "earnings_release", "cfo_commentary"):
                candidates.append({**document, "symbols": [document["symbol"]]})
    pending = len(candidates)
    calls = 0
    failures = list(old_failures)
    if ready["status"] == "configured":
        analyzer = Analyzer(root, config)
        try:
            for document in sorted(
                candidates, key=lambda d: (d["kind"] == "transcript", d["available_at"]), reverse=True
            ):
                if calls >= 3:
                    break
                # Analyze bounded contiguous chunks; do not call a partial transcript a full analysis.
                chunks = []
                chunk = []
                length = 0
                for segment in document["segments"]:
                    if length + len(segment["text"]) > 35000 and chunk:
                        chunks.append(chunk)
                        chunk = []
                        length = 0
                    chunk.append(segment)
                    length += len(segment["text"])
                if chunk:
                    chunks.append(chunk)
                for number, chunk in enumerate(chunks):
                    key = digest(
                        {
                            "source": document["source_sha256"],
                            "prompt": "evidence-v1",
                            "model": config["model"],
                            "provider": config["provider"],
                            "chunk": number,
                            "segments_sha256": digest(chunk),
                        }
                    )
                    if key in known:
                        continue
                    if calls >= 3:
                        break
                    output = analyzer.analyze({**document, "segments": chunk})
                    calls += 1
                    if output["status"] == "ok":
                        results.append(
                            {
                                **output,
                                "analysis_key": key,
                                "kind": document["kind"],
                                "symbols": document["symbols"],
                                "source_url": document["source_url"],
                                "article_id": document.get("article_id"),
                                "article_updated_at": document.get("article_updated_at"),
                                "document_key": document.get("document_key"),
                                "chunk": number,
                                "segments_sha256": digest(chunk),
                                "total_chunks": len(chunks),
                                "fiscal_year": document.get("fiscal_year"),
                                "quarter": document.get("quarter"),
                            }
                        )
                        known.add(key)
                    elif output["status"] == "failed":
                        known.add(key)
                        failures.append(
                            {
                                "analysis_key": key,
                                "provider": config["provider"],
                                "model": config["model"],
                                "kind": document["kind"],
                                "source_url": document["source_url"],
                                **output,
                            }
                        )
        finally:
            analyzer.close()
    manifest = {
        "status": "partial" if failures else "complete" if ready["status"] == "configured" else "unavailable",
        "collected_at": now(),
        "readiness": ready,
        "candidate_documents": pending,
        "requests_this_refresh": calls,
        "analyses": len(results),
        "failures": failures,
        "previous_snapshot": existing[1]["snapshot_id"] if existing else None,
    }
    publish(root / "datasets", "analysis", {"analyses.json": results}, manifest)
    return {
        "status": manifest["status"],
        "analyses": len(results),
        "candidate_documents": pending,
        "requests": calls,
        "reason": ready.get("reason"),
        "failures": failures,
    }


def run(root):
    """A manual call and recurring collection must not publish competing analysis snapshots."""
    root = Path(root)
    directory = root / "artifacts/llm"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {
                "status": "pending",
                "reason": "analysis worker is already running",
                "requests": 0,
                "failures": [],
            }
        try:
            config = settings(root)
            ready = readiness(config)
            try:
                return _run(root, config, ready)
            finally:
                try:
                    publish_usage(root, ready, config["max_daily_calls"])
                except (OSError, ValueError, sqlite3.Error) as error:
                    logging.getLogger(__name__).warning("LLM usage publication failed: %s", type(error).__name__)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
