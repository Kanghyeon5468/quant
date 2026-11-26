"""Claude native Messages API: official host, supported schema and explicit completion checks."""

import copy

ANTHROPIC_API_VERSION = "2026-10-21"
DEFAULT_OPUS_MODEL = "claude-opus-5-5"


def api_headers(key):
    return {"Authorization": "Bearer " + key, "anthropic-version": ANTHROPIC_API_VERSION}


def supported_schema(schema):
    """Keep unsupported numeric/length bounds in descriptions; validate originals locally."""

    def simplify(node):
        if isinstance(node, list):
            return [simplify(v) for v in node]
        if not isinstance(node, dict):
            return node
        result = {k: simplify(v) for k, v in node.items()}
        removed = {
            k: result.pop(k)
            for k in (
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "multipleOf",
                "minLength",
                "maxLength",
                "maxItems",
                "uniqueItems",
            )
            if k in result
        }
        if "minItems" in result and result["minItems"] not in (0, 1):
            removed["minItems"] = result.pop("minItems")
        if removed:
            result["description"] = (
                result.get("description", "") + " Locally enforced constraints: " + str(removed)
            ).strip()
        return result

    return simplify(copy.deepcopy(schema))


def create_message(client, config, data, schema):
    return client.post(
        "https://api.anthropic.com/v1/messages",
        headers=api_headers(config["key"]),
        json={
            "model": config["model"],
            "max_tokens": 8192,
            "stream": False,
            "system": config["instructions"],
            "messages": [{"role": "user", "content": data}],
            "output_config": {
                "effort": "low",
                "format": {"type": "json_schema", "schema": supported_schema(schema)},
            },
        },
    )


def message_text(body, expected_model):
    if body.get("stop_reason") != "end_turn":
        raise ValueError("Claude response refused or incomplete: " + str(body.get("stop_reason"))[:50])
    if body.get("model") != expected_model:
        raise ValueError("Claude response model differs from the explicitly configured model")
    parts = [r["text"] for r in body.get("content", []) if r.get("type") == "text"]
    if not parts:
        raise ValueError("Claude response contains no structured text")
    return "".join(parts)
