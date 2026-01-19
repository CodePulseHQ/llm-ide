"""Test helpers for MCP responses."""

import json


def unwrap(result: str, allow_error: bool = False):
    payload = json.loads(result)
    if isinstance(payload, dict) and "success" in payload:
        if not payload["success"]:
            if allow_error:
                return payload
            assert False, payload.get("error")
        return payload.get("data")
    return payload
