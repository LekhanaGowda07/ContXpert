"""Optional LLM helper (Anthropic Messages API over plain HTTP). Returns None when no key / on any error,
so every feature keeps working without it."""
import logging

import requests

import config

log = logging.getLogger("llm")


def enabled():
    return bool(config.ANTHROPIC_API_KEY)


def complete(system, user, max_tokens=400):
    if not enabled():
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=25)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip() or None
    except Exception as e:  # network, auth, quota ...
        log.warning("LLM call failed: %s", e)
        return None
