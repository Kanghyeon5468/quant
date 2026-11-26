"""Audited paper-only policy activation; preserve cash, fills, budget, latches and history."""

import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

from quantcore.core.files import atomic_json
from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS, load_snapshot
from quantcore.information.store import now
from quantcore.paper.client import PaperError
from quantcore.paper.journal import TERMINAL, Journal
from quantcore.paper.runner import make_plan, own_inventory
from quantcore.strategies.information import decision_context, policy_at


def activate(root, client, snapshot):
    root = Path(root)
    directory = root / "artifacts/paper_trading"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "STOP").touch()
    mutex = Journal(directory / "automation")
    try:
        with mutex.lock():
            journal = Journal(directory)
            try:
                with journal.lock():
                    journal.reconcile(client)
                    context = client.context()
                    own_inventory(context, journal)
                    config = journal.configuration()
                    if not config:
                        raise PaperError("initialize the paper journal first")
                    journal.configure(str(context["account"]["id"]), config["strategy"], journal.budget())
                    _, _, manifest = load_snapshot(snapshot)
                    stamp = pd.Timestamp(context["clock"]["timestamp"])
                    complete = sessions(stamp.date() - pd.Timedelta(days=15), stamp.date(), stamp)
                    if manifest["end"] != complete.index[-1]:
                        raise PaperError("stale input during policy activation")
                    policy = policy_at(root)
                    if not policy.enabled:
                        raise PaperError("information policy is disabled")
                    preview = decision_context(root, SYMBOLS, stamp)
                    if any(r["status"] == "blocked" for r in preview["rows"].values()):
                        raise PaperError("invalid information inputs; activation stopped")
                    history = directory / "information_policy_changes"
                    history.mkdir(exist_ok=True)
                    label = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%fZ")
                    backup = sqlite3.connect(history / (label + ".sqlite3"))
                    try:
                        journal.db.backup(backup)
                    finally:
                        backup.close()
                    changed = config.get("decision_policy_version") != policy.version
                    canceled = []
                    if changed:
                        for row in journal.records():
                            if row["state"] not in TERMINAL | {"rejected_locally"}:
                                if not row.get("response"):
                                    raise PaperError("unknown order state; inspect before migration")
                                client.request("DELETE", "/v2/orders/" + row["response"]["id"])
                                canceled.append(
                                    {"symbol": row["payload"]["symbol"], "side": row["payload"]["side"]}
                                )
                        for attempt in range(4):
                            journal.reconcile(client)
                            if all(r["state"] in TERMINAL | {"rejected_locally"} for r in journal.records()):
                                break
                            if attempt < 3:
                                time.sleep(1)
                        else:
                            raise PaperError("cancellation not final; automation remains paused")
                        context = client.context()
                        own_inventory(context, journal)
                        old = config.get("decision_policy_version")
                        config["decision_policy_version"] = policy.version
                        journal.db.execute(
                            "CREATE TABLE IF NOT EXISTS decision_policy_changes (version TEXT PRIMARY KEY, activated_at TEXT, data TEXT)"
                        )
                        audit = {
                            "old_version": old,
                            "new_version": policy.version,
                            "policy": policy.model_dump(),
                            "activated_at": now(),
                            "budget_usd": str(journal.budget()),
                            "budget_revision": journal.revision(),
                            "cancellations": canceled,
                            "source_analysis": preview,
                        }
                        journal.db.execute(
                            "INSERT INTO decision_policy_changes VALUES (?,?,?)",
                            (policy.version, now(), json.dumps(audit)),
                        )
                        journal.db.execute(
                            "UPDATE config SET value=? WHERE id=1", (json.dumps(config, sort_keys=True),)
                        )
                        journal.db.commit()
                        atomic_json(history / (label + ".json"), audit)
                    opened = context["clock"]["is_open"]
                    local_day = stamp.tz_convert("America/New_York").date()
                    missed_window = opened and stamp > sessions(local_day, local_day).iloc[0][
                        "open"
                    ] + pd.Timedelta(minutes=5)
                    plan = (
                        None if missed_window else make_plan(snapshot, context, journal, config["strategy"])
                    )
                    result = {
                        "status": "active",
                        "activated_at": now(),
                        "policy_version": policy.version,
                        "changed": changed,
                        "budget_usd": str(journal.budget()),
                        "budget_revision": journal.revision(),
                        "cancellations": canceled,
                        "planned_orders": [
                            {k: v for k, v in o.items() if k != "client_order_id"}
                            for o in (plan["orders"] if plan else [])
                        ],
                        "orders_deferred_to_next_session": missed_window,
                        "analysis": preview,
                        "risk_status": plan["risk"].get("status")
                        if plan
                        else "checked by existing risk monitor",
                        "submitted": False,
                        "note": "new orders are submitted by the existing scheduler; no past information backfill",
                    }
                    atomic_json(
                        root / "datasets/information/policy_activation.json",
                        {k: v for k, v in result.items() if k != "analysis"},
                    )
                    atomic_json(directory / "latest_information_activation.json", result)
                    return result
            finally:
                journal.close()
    finally:
        mutex.close()
