"""
OpenRouter helpers — just enough for Phase 2's Settings page.

Two jobs:
  1. list_models()  -> the live catalogue, so the model pickers show what your
                       key can actually call (rather than a list that goes stale)
  2. check_key()    -> a real "is this key working?" test

Fails soft: no key, no network, or an unhappy API returns empty results and the
UI falls back to the offline defaults below instead of crashing.
"""

import requests

from . import config

API_BASE = "https://openrouter.ai/api/v1"
TIMEOUT = 15

# Offline defaults, used when the live catalogue can't be reached. These follow
# OpenRouter's `vendor/model` convention; the live list above is authoritative,
# so confirm the exact slug there (or paste your own) before relying on one.
FALLBACK_MODELS = [
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-haiku-4-5",
]

# Sensible starting points per agent — cheap where volume is high, strongest
# where the writing has to rank.
SUGGESTED = {
    "ANALYSIS_MODEL": "anthropic/claude-haiku-4-5",
    "BACKLINK_MODEL": "anthropic/claude-haiku-4-5",
    "CONTENT_MODEL": "anthropic/claude-opus-5",
}


def _headers() -> dict:
    key = config.get("OPENROUTER_API_KEY")
    headers = {"HTTP-Referer": "https://toolsvenue.com", "X-Title": "SEO Command Center"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def list_models(timeout: int = 8) -> list[str]:
    """
    Every model id OpenRouter currently serves, sorted. [] on failure.
    Short timeout on purpose: this runs while the Settings page is drawing, and
    the offline defaults are a fine fallback.
    """
    try:
        r = requests.get(f"{API_BASE}/models", headers=_headers(), timeout=timeout)
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        return sorted(i for i in ids if i)
    except Exception:
        return []


def check_key() -> dict:
    """
    Verify the saved key. Returns {'ok': bool, 'detail': str} — never raises,
    so the Settings page can show a red/green line either way.
    """
    if not config.is_set("OPENROUTER_API_KEY"):
        return {"ok": False, "detail": "No OpenRouter API key saved yet."}
    try:
        r = requests.get(f"{API_BASE}/key", headers=_headers(), timeout=TIMEOUT)
        if r.status_code in (401, 403):
            return {"ok": False, "detail": "OpenRouter rejected this key (401/403). "
                                           "Check it was copied in full."}
        r.raise_for_status()
        data = r.json().get("data", {})
        label = data.get("label") or "key accepted"
        limit = data.get("limit")
        usage = data.get("usage")
        extra = ""
        if limit is not None:
            extra = f" · credit limit {limit}, used {usage}"
        elif usage is not None:
            extra = f" · used {usage}"
        return {"ok": True, "detail": f"Connected — {label}{extra}."}
    except Exception as e:
        return {"ok": False, "detail": f"Could not reach OpenRouter: {e}"}
