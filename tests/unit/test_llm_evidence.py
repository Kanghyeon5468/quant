"""Controlled protocol/evidence edge cases. These outputs never enter operational datasets."""

import copy

import httpx
import pytest

from quantcore.analysis.llm import Analyzer, readiness, verify
from quantcore.earnings.parsing import extract, segments


def config(provider="openai"):
    return {
        "enabled": True,
        "provider": provider,
        "model": "unit-model",
        "key": "unit-only-key",
        "remote_allowed": True,
        "base_url": "http://127.0.0.1:11434",
        "max_daily_calls": 20,
    }


def document():
    return {
        "kind": "news",
        "source_sha256": "unit-source",
        "available_at": "2026-01-01T00:00:00Z",
        "segments": [{"id": "s1", "speaker": None, "text": "Revenue increased 10%."}],
    }


def output():
    return {
        "claims": [
            {
                "kind": "sentiment",
                "summary": "Controlled unit interpretation",
                "polarity": 0.5,
                "confidence": 0.9,
                "guidance": None,
                "segment_id": "s1",
                "speaker": None,
                "quote": "Revenue increased 10%.",
                "start": 0,
                "end": 22,
            }
        ]
    }


def test_evidence_requires_literal_quote_and_real_speaker():
    original = output()
    assert verify(original, document()["segments"]) == original
    for field, value in [
        ("quote", "Invented revenue"),
        ("speaker", "Invented CEO"),
        ("segment_id", "s2"),
        ("end", 100),
    ]:
        row = copy.deepcopy(original)
        row["claims"][0][field] = value
        with pytest.raises(ValueError):
            verify(row, document()["segments"])


@pytest.mark.parametrize("provider", ["openai", "ollama"])
def test_real_protocol_shape_dedup_and_no_key_to_ollama(tmp_path, provider):
    calls = []

    def transport(request):
        import json

        calls.append(request)
        body = json.loads(request.content)
        if provider == "openai":
            assert request.url == httpx.URL("https://api.openai.com/v1/responses")
            assert body["store"] is False and body["text"]["format"]["strict"] is True
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [{"content": [{"type": "output_text", "text": json.dumps(output())}]}],
                },
            )
        assert "authorization" not in request.headers and body["stream"] is False
        return httpx.Response(
            200, json={"message": {"content": json.dumps(output())}, "done": True, "done_reason": "stop"}
        )

    analyzer = Analyzer(tmp_path, config(provider), httpx.MockTransport(transport))
    try:
        one = analyzer.analyze(document())
        two = analyzer.analyze(document())
        assert one["status"] == "ok" and one["sentiment"] == pytest.approx(0.5)
        assert one == two and len(calls) == 1
        assert one["available_at"] >= one["analyzed_at"]
    finally:
        analyzer.close()


def test_disabled_missing_key_or_quota_never_calls_provider(tmp_path):
    def forbidden(request):
        raise AssertionError("external call prohibited")

    for settings in [
        {**config(), "enabled": False},
        {**config(), "key": ""},
        {**config(), "remote_allowed": False},
        {**config(), "max_daily_calls": 0},
    ]:
        analyzer = Analyzer(tmp_path, settings, httpx.MockTransport(forbidden))
        try:
            assert analyzer.analyze(document())["status"] == "unavailable"
        finally:
            analyzer.close()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:11434",
        "http://remote.example:11434",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/api/chat",
    ],
)
def test_ollama_endpoint_cannot_exfiltrate_secrets(url):
    assert readiness({**config("ollama"), "base_url": url})["status"] == "unavailable"


def test_refusal_and_timeout_are_not_success_or_automatically_retried(tmp_path):
    calls = []

    def failed(request):
        calls.append(request)
        raise httpx.ReadTimeout("unit timeout")

    analyzer = Analyzer(tmp_path, config(), httpx.MockTransport(failed))
    try:
        assert analyzer.analyze(document())["status"] == "failed"
        assert analyzer.analyze(document())["status"] == "failed"
        assert len(calls) == 1
    finally:
        analyzer.close()


def test_unknown_speakers_stay_unknown_and_qa_is_separate():
    text = "Opening remarks\nPat Example - Chief Executive Officer\nDemand improved.\nQUESTION AND ANSWER SECTION\nAlex Example - Research Analyst\nWhat changed?\nPat Example - Chief Executive Officer\nOrders increased."
    parsed = segments(text, "transcript")
    assert parsed[0]["speaker"] is None
    assert any(r["role"] == "ceo" for r in parsed)
    assert any(r["role"] == "analyst" and r["section"] == "qa" for r in parsed)
    assert all(r["spoken_at"] is None for r in parsed)
    release = segments("“Demand improved,” said Pat Example, the company CEO.", "earnings_release")
    assert release[0]["speaker"] == "Pat Example" and release[0]["role"] == "ceo"


def test_short_or_script_only_document_is_unavailable():
    with pytest.raises(ValueError):
        extract(b"<html><script>fake content</script></html>", "text/html")


def test_unique_quote_offset_is_resolved_by_application():
    row = output()
    row["claims"][0].update(start=None, end=None)
    checked = verify(row, document()["segments"])
    assert checked["claims"][0]["start"] == 0 and checked["claims"][0]["end"] == 22
    with pytest.raises(ValueError, match="unique"):
        verify(row, [{**document()["segments"][0], "text": "Revenue increased 10%. Revenue increased 10%."}])


def test_future_document_never_calls_model(tmp_path):
    def forbidden(request):
        raise AssertionError("future document must not be sent")

    analyzer = Analyzer(tmp_path, config(), httpx.MockTransport(forbidden))
    try:
        assert analyzer.analyze({**document(), "available_at": "2099-01-01T00:00Z"})["status"] == "failed"
    finally:
        analyzer.close()
