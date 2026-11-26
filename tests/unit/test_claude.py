"""Native Claude protocol tests use isolated test responses, never operational substitute data."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from dotenv import set_key

from quantcore.analysis.anthropic import ANTHROPIC_API_VERSION, DEFAULT_OPUS_MODEL, supported_schema
from quantcore.analysis.llm import AnalysisOutput, Analyzer, readiness, settings
from quantcore.analysis.usage import publish_usage, read_usage


def config():
    return {
        "enabled": True,
        "provider": "anthropic",
        "model": DEFAULT_OPUS_MODEL,
        "key": "unit-anthropic-key",
        "remote_allowed": True,
        "base_url": "http://127.0.0.1:11434",
        "max_daily_calls": 20,
    }


def document():
    return {
        "kind": "news",
        "source_sha256": "unit-claude",
        "available_at": "2026-01-01T00:00Z",
        "segments": [{"id": "s1", "speaker": None, "text": "Revenue rose."}],
    }


def content():
    return {
        "claims": [
            {
                "kind": "sentiment",
                "summary": "단위 테스트용 해석",
                "polarity": 0.4,
                "confidence": 0.9,
                "guidance": None,
                "segment_id": "s1",
                "speaker": None,
                "quote": "Revenue rose.",
                "start": None,
                "end": None,
            }
        ]
    }


def test_provider_key_isolation_and_default_opus(tmp_path, monkeypatch):
    for key in (
        "QUANTCORE_LLM_PROVIDER",
        "QUANTCORE_LLM_MODEL",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=unit-anthropic-key\nOPENAI_API_KEY=unit-openai-key\n")
    actual = settings(tmp_path)
    assert (
        actual["provider"] == "anthropic"
        and actual["model"] == DEFAULT_OPUS_MODEL
        and actual["key"] == "unit-anthropic-key"
    )
    assert not actual["enabled"]
    set_key(env, "QUANTCORE_LLM_PROVIDER", "openai")
    assert settings(tmp_path)["key"] == "unit-openai-key"
    set_key(env, "QUANTCORE_LLM_PROVIDER", "ollama")
    assert settings(tmp_path)["key"] == ""


def test_schema_removes_only_unsupported_bounds_and_keeps_original_validation():
    original = AnalysisOutput.model_json_schema()
    converted = supported_schema(original)
    text = json.dumps(converted)

    def visit(node):
        if isinstance(node, dict):
            assert not set(node) & {"maximum", "minimum", "maxLength", "minLength", "maxItems"}
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(converted)
    assert "Locally enforced constraints" in text
    assert original["$defs"]["Claim"]["properties"]["polarity"]["maximum"] == 1


def test_native_messages_auth_schema_model_and_evidence(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert request.url == httpx.URL("https://api.anthropic.com/v1/messages")
        assert request.headers["authorization"] == "Bearer unit-anthropic-key"
        assert request.headers["anthropic-version"] == ANTHROPIC_API_VERSION
        assert body["model"] == DEFAULT_OPUS_MODEL and body["stream"] is False
        assert (
            body["output_config"]["format"]["type"] == "json_schema"
            and body["output_config"]["effort"] == "low"
        )
        assert "tools" not in body and "store" not in body
        return httpx.Response(
            200,
            json={
                "model": DEFAULT_OPUS_MODEL,
                "stop_reason": "end_turn",
                "content": [
                    {"type": "thinking", "thinking": "private unit thought"},
                    {"type": "text", "text": json.dumps(content())},
                ],
                "usage": {"input_tokens": 40, "output_tokens": 30},
            },
        )

    analyzer = Analyzer(tmp_path, config(), httpx.MockTransport(handler))
    try:
        result = analyzer.analyze(document())
        assert result["status"] == "ok" and result["sentiment"] == pytest.approx(0.4)
        assert result["claims"][0]["end"] == len("Revenue rose.")
        assert result["response_model"] == DEFAULT_OPUS_MODEL and result["usage"]["input_tokens"] == 40
        assert "private unit thought" not in json.dumps(result)
        assert analyzer.analyze(document()) == result and len(calls) == 1
    finally:
        analyzer.close()


@pytest.mark.parametrize(
    "stop,model",
    [("max_tokens", DEFAULT_OPUS_MODEL), ("refusal", DEFAULT_OPUS_MODEL), ("end_turn", "claude-other-model")],
)
def test_incomplete_refused_or_substituted_model_is_rejected(tmp_path, stop, model):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "stop_reason": stop,
                "model": model,
                "content": [{"type": "text", "text": json.dumps(content())}],
            },
        )

    analyzer = Analyzer(tmp_path, config(), httpx.MockTransport(handler))
    try:
        assert analyzer.analyze(document())["status"] == "failed"
    finally:
        analyzer.close()


def test_missing_key_or_remote_permission_never_calls_anthropic(tmp_path):
    def forbidden(request):
        raise AssertionError("unauthorized provider request")

    for c in ({**config(), "key": ""}, {**config(), "remote_allowed": False}):
        assert readiness(c)["status"] == "unavailable"
        analyzer = Analyzer(tmp_path, c, httpx.MockTransport(forbidden))
        try:
            assert analyzer.analyze(document())["status"] == "unavailable"
        finally:
            analyzer.close()


def test_dashboard_usage_counts_failed_attempts_cache_and_reported_anthropic_limits(tmp_path, monkeypatch):
    at = datetime(2026, 11, 25, 23, 45, tzinfo=timezone.utc)
    monkeypatch.setattr('quantcore.analysis.llm.now', at.isoformat)

    def handler(request):
        return httpx.Response(
            200,
            headers={
                'anthropic-ratelimit-input-tokens-remaining': '9000',
                'anthropic-ratelimit-input-tokens-reset': '2026-11-25T23:46:00Z',
                'anthropic-ratelimit-output-tokens-remaining': 'missing',
                'anthropic-workspace-id': 'private-workspace',
            },
            json={
                'model': DEFAULT_OPUS_MODEL, 'stop_reason': 'max_tokens',
                'usage': {'input_tokens': 7, 'cache_creation_input_tokens': 11,
                          'cache_read_input_tokens': 13, 'output_tokens': 19},
            },
        )

    analyzer = Analyzer(tmp_path, config(), httpx.MockTransport(handler))
    try:
        result = analyzer.analyze(document())
        assert result['status'] == 'failed' and analyzer.analyze(document()) == result
        assert analyzer.db.execute('SELECT count(*) FROM requests').fetchone()[0] == 1
    finally:
        analyzer.close()
    assert read_usage(tmp_path / 'datasets') == {'status': 'unavailable'}
    publish_usage(tmp_path, {**readiness(config()), 'key': 'private-key'}, 20, at=at)
    report = read_usage(tmp_path / 'datasets', at=at)
    assert not report['stale']
    assert report['daily_requests'] == {
        'date_utc': '2026-11-25', 'reset_at': '2026-11-26T00:00:00+00:00',
        'limit': 20, 'started': 1, 'failed': 1, 'pending': 0, 'remaining': 19,
    }
    assert report['today_tokens'] == {'input': 31, 'output': 19, 'requests_with_usage': 1}
    assert report['recorded_tokens'] == report['today_tokens']
    assert report['anthropic_rate_limit']['limits'] == {
        'input': {'remaining': 9000, 'reset_at': '2026-11-25T23:46:00+00:00'},
    }
    assert 'private-' not in json.dumps(report) and 'claims' not in json.dumps(report)
    tomorrow = at + timedelta(minutes=16)
    assert read_usage(tmp_path / 'datasets', at=tomorrow)['stale']
    publish_usage(tmp_path, readiness(config()), 20, at=tomorrow)
    updated = read_usage(tmp_path / 'datasets', at=tomorrow)
    assert updated['daily_requests']['remaining'] == 20
    assert updated['today_tokens']['requests_with_usage'] == 0
    assert updated['recorded_tokens'] == report['recorded_tokens']


def test_analysis_worker_lock_prevents_competing_manual_and_recurring_calls(tmp_path):
    import fcntl

    from quantcore.analysis.worker import run

    directory = tmp_path / "artifacts/llm"
    directory.mkdir(parents=True)
    with (directory / "worker.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run(tmp_path)
    assert result["status"] == "pending" and result["requests"] == 0
