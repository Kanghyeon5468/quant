"""Bounded Coinbase market-data GETs for local crypto research."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx

from quantcore.information.store import now, publish, read_snapshot

PRODUCTS = ("BTC-USD", "ETH-USD")
HOST = "https://api.exchange.coinbase.com"


def _number(value, positive=False):
    number = Decimal(str(value))
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        raise ValueError("invalid provider price or size")
    return number


def candles(rows, observed_at):
    cutoff = datetime.fromisoformat(observed_at)
    result = {}
    for time, low, high, opening, closing, volume in rows:
        start = datetime.fromtimestamp(time, timezone.utc)
        end = start + timedelta(days=1)
        if end > cutoff:
            continue
        lo, hi, op, cl = (_number(value, True) for value in (low, high, opening, closing))
        if lo > min(op, cl) or hi < max(op, cl):
            raise ValueError("invalid Coinbase candle")
        stamp = end.isoformat()
        if stamp in result:
            raise ValueError("duplicate Coinbase candle")
        result[stamp] = {"timestamp": stamp, "available_at": observed_at, "open": str(op), "high": str(hi),
                         "low": str(lo), "close": str(cl), "volume": str(_number(volume))}
    if not result:
        raise ValueError("no completed Coinbase candles")
    return [result[key] for key in sorted(result)]


def _microstructure(client, endpoint):
    book = client.get(endpoint+"/book", params={"level": 2})
    book.raise_for_status()
    raw_book = book.json()
    collected = now()
    bids, asks = ([
        {"price": str(_number(row[0], True)), "size": str(_number(row[1]))} for row in raw_book[side][:10]
    ] for side in ("bids", "asks"))
    if not bids or not asks or Decimal(bids[0]["price"]) > Decimal(asks[0]["price"]):
        raise ValueError("invalid Coinbase top of book")
    ticks = client.get(endpoint+"/trades", params={"limit": 50})
    ticks.raise_for_status()
    observed_at = now()
    cutoff = datetime.fromisoformat(observed_at)
    trades = []
    for row in ticks.json()[:50]:
        timestamp = datetime.fromisoformat(row["time"])
        if timestamp.tzinfo is None or timestamp > cutoff:
            raise ValueError("invalid Coinbase trade timestamp")
        trades.append({"timestamp": timestamp.astimezone(timezone.utc).isoformat(), "side": row["side"],
                       "price": str(_number(row["price"], True)), "size": str(_number(row["size"]))})
    return {"book": {"bids": bids, "asks": asks, "available_at": collected,
                     "sequence": str(raw_book["sequence"]), "source_url": endpoint+"/book"},
            "trades": {"rows": trades, "available_at": observed_at, "source_url": endpoint+"/trades"},
            "basis": "point observations from Coinbase public REST; updated by the collector"}


def collect(directory, transport=None):
    snapshot = read_snapshot(directory, "coinbase")
    products = json.loads((snapshot[0]/"products.json").read_text()) if snapshot else {}
    errors = {}
    with httpx.Client(timeout=12, follow_redirects=False, transport=transport) as client:
        for product in PRODUCTS:
            endpoint = f"{HOST}/products/{quote(product)}"
            try:
                response = client.get(endpoint+"/candles", params={"granularity": 86400})
                response.raise_for_status()
                observed = now()
                products[product] = {"symbol": product, "mode": "historical", "asset_class": "crypto",
                                     "currency": "USD", "volume_unit": product.split("-")[0],
                                     "source": "Coinbase Exchange", "source_url": endpoint+"/candles",
                                     "collected_at": observed, "bars": candles(response.json(), observed)}
            except (httpx.HTTPError, ValueError, TypeError, ArithmeticError) as error:
                errors[product] = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
                continue
            try:
                products[product]["microstructure"] = _microstructure(client, endpoint)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, ArithmeticError) as error:
                errors[product+"_market_depth"] = (
                    error.response.status_code if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
                )
    publish(directory, "coinbase", {"products.json": products}, {"collected_at": now(), "failures": errors})
    return {"products": list(products), "failures": errors}


def report(directory):
    snapshot = read_snapshot(directory, "coinbase")
    if not snapshot:
        return {"status": "unavailable", "reason": "crypto archive is unavailable"}
    products = json.loads((snapshot[0]/"products.json").read_text())
    return {"status": "partial" if snapshot[1]["failures"] else "ok", "products": products,
            "failures": snapshot[1]["failures"], "checked_at": snapshot[1]["collected_at"]}
