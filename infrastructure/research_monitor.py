"""Persist timestamped QuantCore monitoring samples independently of the API."""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def sample(url, token):
    headers = {"Authorization": "Bearer "+token} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            report = json.loads(response.read(1_000_000))
    except HTTPError as error:
        return {"status": "unavailable", "http_status": error.code}
    except (URLError, TimeoutError, ValueError):
        return {"status": "unavailable", "reason": "monitoring query failed"}
    return {"status": "ok", **{key: report[key] for key in (
        "latency_ms", "errors", "event_queue_depth", "incremental_portfolio_covariance",
        "dataset_version", "mode",
    ) if key in report}}


def cycle(db, url, token):
    point = datetime.now(timezone.utc)
    report = sample(url, token)
    with db:
        db.execute("INSERT INTO samples VALUES (?, ?)", (point.isoformat(), json.dumps(report)))
        db.execute("DELETE FROM samples WHERE at < ?", ((point-timedelta(days=30)).isoformat(),))
    print(json.dumps({"at": point.isoformat(), "status": report["status"]}), flush=True)


if __name__ == "__main__":
    elapsed = 60
    upstream = os.getenv("QUANTCORE_MONITOR_URL", "http://api:8000/api/monitoring")
    token = os.getenv("QUANTCORE_MONITOR_TOKEN") or os.getenv("QUANTCORE_API_TOKEN", "")
    with sqlite3.connect("/state/monitoring.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS samples (at TEXT PRIMARY KEY, report TEXT NOT NULL)")
        while True:
            started = time.monotonic()
            cycle(db, upstream, token)
            time.sleep(max(0, elapsed - (time.monotonic() - started)))
