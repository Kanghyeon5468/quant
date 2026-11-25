import json
from pathlib import Path

import httpx
import pytest

from quantcore.data.reference.securities import classification_asof, collect_reference


def test_sec_asset_identity_and_hashes_publish_atomically_and_cached_refresh_is_bounded(
    tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/security_master.json").write_bytes(
        (root / "configs/security_master.json").read_bytes()
    )
    (tmp_path / ".env").write_text('SEC_USER_AGENT="QuantCore test contact@example.org"\n')
    config = json.loads((root / "configs/security_master.json").read_text())
    calls = []
    failure = [False]
    original = httpx.Client

    def sec(request):
        assert request.url.host == "data.sec.gov" and request.method == "GET"
        assert "contact@example.org" in request.headers["User-Agent"]
        cik = int(request.url.path.split("CIK")[-1].split(".")[0])
        symbol = next(s for s, c in config["companies"].items() if c == cik)
        calls.append(symbol)
        return httpx.Response(
            403 if failure[0] else 200,
            json={
                "cik": str(cik),
                "tickers": [symbol],
                "name": symbol,
                "sic": "3571",
                "sicDescription": "Electronic Computers",
            },
        )

    monkeypatch.setattr(
        "quantcore.data.reference.securities.httpx.Client",
        lambda **kw: original(**kw, transport=httpx.MockTransport(sec)),
    )
    monkeypatch.setattr("quantcore.data.reference.securities.time.sleep", lambda n: None)

    class Assets:
        def request(self, method, path):
            assert method == "GET"
            s = path.rsplit("/", 1)[-1]
            return {"symbol": s, "id": "asset-" + s, "exchange": "NASDAQ"}

    class Market:
        def __init__(self, env):
            pass

        def pages(self, path, params):
            assert path == "/v1/corporate-actions"
            yield {"corporate_actions": {"cash_dividends": []}}

        def close(self):
            pass

    monkeypatch.setattr("quantcore.data.reference.securities.AlpacaData", Market)
    result = collect_reference(tmp_path, None, Assets())
    assert len(calls) == 5 and result["securities"]["SPY"]["risk_group"] == "EQUITY_ETF"
    assert classification_asof(tmp_path, result["manifest"]["collected_at"])[0]["AAPL"] == "TECHNOLOGY"
    pointer = (tmp_path / "datasets/reference/latest.json").read_bytes()
    collect_reference(tmp_path, None, Assets())
    assert len(calls) == 5
    failure[0] = True
    with pytest.raises(ValueError, match="403"):
        collect_reference(tmp_path, None, Assets(), force=True)
    assert (tmp_path / "datasets/reference/latest.json").read_bytes() == pointer
