"""Verify the configured native Claude Opus without printing keys or changing paper orders."""

import argparse
import json
from pathlib import Path

import httpx
from dotenv import set_key

from quantcore.analysis.anthropic import DEFAULT_OPUS_MODEL, api_headers
from quantcore.analysis.llm import settings
from quantcore.core.files import atomic_json
from quantcore.information.store import now


def run(root, enable=False):
    root = Path(root)
    config = settings(root)
    if config["provider"] != "anthropic" or not config["key"]:
        raise RuntimeError("ANTHROPIC_API_KEY is missing for the selected Anthropic provider")
    model = config["model"] or DEFAULT_OPUS_MODEL
    if model != DEFAULT_OPUS_MODEL:
        raise RuntimeError("set the explicitly selected Claude Opus model before verification")
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(
            "https://api.anthropic.com/v1/models/" + model, headers=api_headers(config["key"])
        )
    if response.status_code != 200:
        report = {
            "status": "failed",
            "checked_at": now(),
            "provider": "anthropic",
            "model": model,
            "http_status": response.status_code,
        }
        atomic_json(root / "artifacts/claude/connection.json", report)
        raise RuntimeError(f"Claude model lookup HTTP {response.status_code}; no model fallback or retry")
    body = response.json()
    if body.get("id") != model:
        raise RuntimeError("Claude model lookup returned a different model")
    if enable:
        env_file = root / ".env"
        for key, value in {
            "QUANTCORE_LLM_PROVIDER": "anthropic",
            "QUANTCORE_LLM_MODEL": model,
            "QUANTCORE_LLM_REMOTE_ALLOWED": "true",
            "QUANTCORE_LLM_ENABLED": "true",
        }.items():
            set_key(env_file, key, value, quote_mode="auto")
        env_file.chmod(0o600)
    report = {
        "status": "connected",
        "checked_at": now(),
        "provider": "anthropic",
        "model": model,
        "display_name": body.get("display_name"),
        "http_status": response.status_code,
        "enabled": enable,
        "generative_requests_in_this_check": 0,
    }
    atomic_json(root / "artifacts/claude/connection.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable",
        action="store_true",
        help="enable the explicitly authorized remote analysis after model verification",
    )
    args = parser.parse_args()
    print(json.dumps(run(Path(__file__).resolve().parents[1], args.enable), ensure_ascii=False, indent=2))
