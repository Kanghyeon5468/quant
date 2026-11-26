"""Paper protocol migration tests use the existing isolated broker test double only."""

import json

import pytest
from test_paper_trading import setup_paper as existing_paper_fixture

from quantcore.paper.client import PaperError
from quantcore.paper.information_policy import activate
from quantcore.paper.journal import Journal
from quantcore.paper.performance import execution_rows
from quantcore.paper.runner import make_plan, run_once
from quantcore.strategies.information import DecisionPolicy

setup_paper = existing_paper_fixture


@pytest.mark.parametrize("cancel_failure", [None, "cancel_partial_fill", "cancel_pending"])
def test_policy_activation_preserves_history_and_deduplicates_new_orders(
    setup_paper, monkeypatch, cancel_failure
):
    client, broker, snapshot, _, frame, manifest = setup_paper
    root = snapshot.parent
    directory = root / "artifacts/paper_trading"
    before = run_once(client, directory, snapshot, submit=True)
    (root / "configs").mkdir()
    (root / "configs/decision_policy.json").write_text(DecisionPolicy(enabled=True).model_dump_json())
    policy = DecisionPolicy(enabled=True)

    def evidence(root, symbols, cutoff):
        return {
            "policy_version": policy.version,
            "rows": {
                s: {"status": "applied", "multiplier": 0.5, "scores": {"news": None}, "sources": {}}
                for s in symbols
            },
        }

    monkeypatch.setattr("quantcore.paper.runner.decision_context", evidence)
    monkeypatch.setattr("quantcore.paper.information_policy.decision_context", evidence)
    monkeypatch.setattr("quantcore.paper.information_policy.load_snapshot", lambda p: (frame, {}, manifest))
    broker.failure = cancel_failure
    if cancel_failure == "cancel_pending":
        with pytest.raises(PaperError, match="cancellation not final"):
            activate(root, client, snapshot)
        journal = Journal(directory)
        try:
            assert not journal.configuration().get("decision_policy_version")
        finally:
            journal.close()
        assert (directory / "STOP").exists()
        return
    result = activate(root, client, snapshot)
    assert (
        result["budget_usd"] == before["budget_usd"]
        and result["budget_revision"] == before["budget_revision"]
    )
    assert len(result["cancellations"]) == len(before["orders"])
    assert result["submitted"] is False and (directory / "STOP").exists()
    broker.failure = None
    (directory / "STOP").unlink()
    after = run_once(client, directory, snapshot, submit=True)
    assert all(
        "-a" + policy.version[:6] in o["client_order_id"] and len(o["client_order_id"]) <= 48
        for o in after["orders"]
    )
    assert all(int(o["qty"]) < int(before["orders"][i]["qty"]) for i, o in enumerate(after["orders"]))
    journal = Journal(directory)
    try:
        assert len(journal.records()) == len(before["orders"]) + len(after["orders"])
        assert all(
            json.loads(raw[0])["information"] is not None
            for raw in journal.db.execute(
                "SELECT data FROM order_evidence WHERE client_id LIKE ?", ("%-a" + policy.version[:6],)
            )
        )
    finally:
        journal.close()
    again = run_once(client, directory, snapshot, submit=True)
    assert again["orders"] == []


def test_active_policy_version_must_match_before_new_orders(setup_paper, monkeypatch):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot)
    monkeypatch.setattr(
        "quantcore.paper.runner.decision_context", lambda *a: {"policy_version": "different", "rows": {}}
    )
    journal = Journal(directory)
    try:
        with pytest.raises(PaperError, match="activate"):
            make_plan(snapshot, client.context(), journal)
    finally:
        journal.close()
    assert not any(method == "POST" for method, _ in broker.calls)


def test_budget_revision_remains_correct_with_analysis_policy_suffix():
    cid = "qcp1-unit-mom-20261125-AAPL-r1-aabcdef"
    record = {
        "client_id": cid,
        "state": "accepted",
        "payload": {"symbol": "AAPL", "qty": "2", "limit_price": "100", "side": "buy"},
        "response": {"filled_qty": "0"},
    }
    row = execution_rows([record], {"fills": []}, {}, {})[0]
    assert row["budget_revision"] == 1


def test_activation_after_opening_window_defers_orders(setup_paper, monkeypatch):
    client, broker, snapshot, _, frame, manifest = setup_paper
    root = snapshot.parent
    directory = root / "artifacts/paper_trading"
    run_once(client, directory, snapshot, submit=True)
    (root / "configs").mkdir()
    policy = DecisionPolicy(enabled=True)
    (root / "configs/decision_policy.json").write_text(policy.model_dump_json())
    monkeypatch.setattr("quantcore.paper.information_policy.load_snapshot", lambda p: (frame, {}, manifest))
    monkeypatch.setattr(
        "quantcore.paper.information_policy.decision_context",
        lambda *args: {"policy_version": policy.version, "rows": {}},
    )
    broker.clock.update(timestamp="2026-11-25T11:00:00-05:00", is_open=True)
    result = activate(root, client, snapshot)
    assert result["orders_deferred_to_next_session"] and result["planned_orders"] == []
    assert not result["submitted"] and (directory / "STOP").exists()
