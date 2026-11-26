import hashlib
import json
from uuid import uuid4

import httpx
import pytest

from quantcore.data.reference.securities import classification_asof
from quantcore.paper.client import PaperClient, PaperError
from quantcore.paper.corporate import reconcile_corporate
from quantcore.paper.runner import Journal, own_inventory


def publish(root, event):
    folder = root / "datasets/reference/one"
    folder.mkdir(parents=True)
    documents = {
        "securities.json": {
            "AAPL": {"risk_group": "TECHNOLOGY", "status": "verified", "available_at": "2026-11-20T00:00:00Z"}
        },
        "actions.json": [event],
    }
    for name, doc in documents.items():
        (folder / name).write_text(json.dumps(doc))
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "collected_at": "2026-11-20T00:00:00Z",
                "taxonomy": "test-sic",
                "hashes": {
                    name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in documents
                },
            }
        )
    )
    (folder.parent / "latest.json").write_text(json.dumps({"snapshot_directory": "one"}))
    return folder


def test_classification_is_point_in_time_and_checks_hash(tmp_path):
    folder = publish(tmp_path, {"id": "a"})
    assert classification_asof(tmp_path, "2026-11-19T12:00:00Z")[0] == {}
    assert classification_asof(tmp_path, "2026-11-21T12:00:00Z")[0] == {"AAPL": "TECHNOLOGY"}
    assert classification_asof(tmp_path, "2027-06-01T12:00:00Z")[0] == {}
    (folder / "securities.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        classification_asof(tmp_path, "2026-11-21T12:00:00Z")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    for name in ["ALPACA_API_URL", "ALPACA_BASE_URL", "APCA_API_BASE_URL"]:
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "artifacts/paper_trading"
    journal = Journal(directory)
    journal.configure("account-test", "momentum", 100000)
    cid = "qcp1-test-momentum-20261123-AAPL"
    payload = {
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "limit_price": "101.00",
        "type": "limit",
        "time_in_force": "day",
        "extended_hours": False,
        "client_order_id": cid,
    }
    remote = {
        **payload,
        "id": str(uuid4()),
        "status": "filled",
        "filled_qty": "10",
        "submitted_at": "2026-11-23T14:00:00Z",
    }
    journal.save(payload, "filled", remote)
    journal.close()
    event = {
        "id": "split-official",
        "type": "split",
        "kind": "forward_splits",
        "symbol": "AAPL",
        "ratio": "2",
        "available_at": "2026-11-20T00:00:00Z",
        "effective_date": "2026-11-24",
    }
    publish(tmp_path, event)
    positions = [{"symbol": "AAPL", "qty": "20", "side": "long", "current_price": "50"}]
    calls = []

    def transport(request):
        calls.append(request.method)
        path = request.url.path
        if path == "/v2/account":
            body = {"id": "account-test", "status": "ACTIVE", "currency": "USD"}
        elif path == "/v2/clock":
            body = {
                "timestamp": "2026-11-25T13:00:00Z",
                "is_open": False,
                "next_open": "2026-11-25T14:30:00Z",
            }
        elif path == "/v2/positions":
            body = positions
        elif path == "/v2/orders":
            body = []
        elif path == "/v2/account/activities":
            body = [
                {
                    "id": "fill-id",
                    "activity_type": "FILL",
                    "order_id": remote["id"],
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "10",
                    "price": "100",
                    "transaction_time": "2026-11-23T15:00:00Z",
                }
            ]
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=body)

    client = PaperClient(transport=httpx.MockTransport(transport))
    yield tmp_path, client, calls, positions
    client.close()


def test_split_adjustment_is_idempotent_and_ownership_matches_broker(setup):
    root, client, calls, _ = setup
    first = reconcile_corporate(client, root, refresh=False)
    again = reconcile_corporate(client, root, refresh=False)
    assert first["status"] == again["status"] == "reconciled"
    assert first["quantity_adjustments"] == {"AAPL": "10"}
    journal = Journal(root / "artifacts/paper_trading")
    assert journal.db.execute("SELECT COUNT(*) FROM corporate_adjustments").fetchone()[0] == 1
    assert own_inventory(client.context(), journal)["AAPL"] == 20
    journal.close()
    assert set(calls) == {"GET"}


def test_share_mismatch_does_not_apply_speculative_adjustment(setup):
    root, client, _, positions = setup
    positions[0]["qty"] = "19"
    with pytest.raises(PaperError, match="requires review"):
        reconcile_corporate(client, root, refresh=False)
    journal = Journal(root / "artifacts/paper_trading")
    assert journal.db.execute("SELECT COUNT(*) FROM corporate_adjustments").fetchone()[0] == 0
    journal.close()
    report = json.loads((root / "artifacts/corporate_public/status.json").read_text())
    assert not report["broker_positions_reconciled"]


@pytest.mark.parametrize("confirmed", [True, False])
def test_split_cancels_only_own_pending_order_and_requires_confirmation(setup, confirmed, monkeypatch):
    root, client, calls, positions = setup
    positions.clear()
    directory = root / "artifacts/paper_trading"
    journal = Journal(directory)
    record = journal.records()[0]
    remote = {
        **record["response"],
        "status": "accepted",
        "filled_qty": "0",
        "submitted_at": "2026-11-24T22:00:00Z",
    }
    journal.save(record["payload"], "accepted", remote)
    journal.close()
    path = root / "datasets/reference/one/actions.json"
    event = json.loads(path.read_text())[0]
    event["effective_date"] = "2026-11-25"
    path.write_text(json.dumps([event]))
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["hashes"]["actions.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    original = client.request
    deleted = []

    def request(method, path, **kwargs):
        if method == "DELETE":
            deleted.append(path)
            remote["status"] = "canceled" if confirmed else "pending_cancel"
            return None
        if path == "/v2/account/activities":
            return []
        if path == "/v2/orders:by_client_order_id":
            return remote
        if path == "/v2/orders":
            return [remote] if remote["status"] != "canceled" else []
        return original(method, path, **kwargs)

    monkeypatch.setattr(client, "request", request)
    if confirmed:
        report = reconcile_corporate(client, root, refresh=False)
        assert report["pending_orders_canceled"] == 1
    else:
        with pytest.raises(PaperError, match="not confirmed"):
            reconcile_corporate(client, root, refresh=False)
    assert deleted == ["/v2/orders/" + remote["id"]]


def test_rename_updates_book_but_unapproved_market_universe_cannot_trade(setup):
    root, client, _, positions = setup
    positions[0].update(symbol="NEW", qty="10")
    path = root / "datasets/reference/one/actions.json"
    row = json.loads(path.read_text())[0]
    row.update(type="rename", new_symbol="NEW")
    path.write_text(json.dumps([row]))
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["hashes"]["actions.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(PaperError, match="migration required"):
        reconcile_corporate(client, root, refresh=False)
    report = json.loads((root / "artifacts/corporate_public/status.json").read_text())
    assert report["broker_positions_reconciled"]
    assert report["quantity_adjustments"] == {"AAPL": "-10", "NEW": "10"}


def test_liquidity_history_uses_current_split_share_units_without_double_adjustment(tmp_path):
    import pandas as pd

    from quantcore.paper.corporate import share_unit_histories

    journal = Journal(tmp_path)
    journal.db.execute("CREATE TABLE corporate_adjustments (event_id TEXT PRIMARY KEY,data TEXT)")
    journal.db.execute(
        "INSERT INTO corporate_adjustments VALUES (?,?)",
        (
            "split",
            json.dumps(
                {
                    "symbol": "AAPL",
                    "type": "split",
                    "effective_at": "2026-11-24T14:30:00Z",
                    "before_qty": "10",
                    "after_qty": "20",
                }
            ),
        ),
    )
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-11-23T21:00:00Z", "2026-11-24T21:00:00Z"]),
            "available_at": pd.to_datetime(["2026-11-23T21:01:00Z", "2026-11-24T21:01:00Z"]),
            "close": [100.0, 50.0],
            "signal_close": [100.0, 100.0],
            "volume": [100.0, 200.0],
        }
    )
    adjusted = share_unit_histories({"AAPL": frame}, journal, "2026-11-25T13:00:00Z")["AAPL"]
    assert adjusted.volume.tolist() == [200.0, 200.0]
    assert frame.volume.tolist() == [100.0, 200.0]
    before_new_daily = share_unit_histories({"AAPL": frame.iloc[:1]}, journal, "2026-11-24T18:00:00Z")["AAPL"]
    assert before_new_daily.volume.tolist() == [200.0]
    journal.close()


def test_first_fill_refreshes_order_journal_before_corporate_quantity_comparison(setup, monkeypatch):
    root, client, _, _ = setup
    journal = Journal(root / "artifacts/paper_trading")
    try:
        original = journal.records()[0]
        remote = {**original["response"], "status": "filled"}
        journal.save(original["payload"], "new", {**remote, "status": "new", "filled_qty": "0"})
    finally:
        journal.close()
    monkeypatch.setattr(client, "by_client_id", lambda cid: remote)
    report = reconcile_corporate(client, root, refresh=False)
    assert report["status"] == "reconciled"
    journal = Journal(root / "artifacts/paper_trading")
    try:
        assert journal.records()[0]["state"] == "filled"
        assert journal.records()[0]["response"]["filled_qty"] == "10"
    finally:
        journal.close()
