"""
OpenRouter helpers.

Three jobs:
  1. list_models()  -> the live catalogue, so the model pickers show what your
                       key can actually call (rather than a list that goes stale)
  2. check_key()    -> a real "is this key working?" test
  3. chat()         -> the actual completion call the agents write with

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


def chat(messages: list, model: str = "", temperature: float = 0.7,
         max_tokens: int = 3000, timeout: int = 180) -> dict:
    """
    One chat completion. Returns {'ok': bool, 'text': str, 'detail': str} —
    never raises, so an agent can surface the reason in the UI instead of
    taking the dashboard down.

    `model` is an OpenRouter id; pass the per-agent one from settings, e.g.
    `config.get("BACKLINK_MODEL")`.
    """
    if not config.is_set("OPENROUTER_API_KEY"):
        return {"ok": False, "text": "",
                "detail": "No OpenRouter API key saved. Add one in Settings → AI models."}
    if not model:
        return {"ok": False, "text": "",
                "detail": "No model selected for this agent. Pick one in Settings → AI models."}

    try:
        r = requests.post(
            f"{API_BASE}/chat/completions",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=timeout,
        )
        if r.status_code in (401, 403):
            return {"ok": False, "text": "",
                    "detail": "OpenRouter rejected the key (401/403). Check it in Settings."}
        if r.status_code == 402:
            return {"ok": False, "text": "",
                    "detail": "OpenRouter says the account is out of credit (402)."}
        if r.status_code == 404:
            return {"ok": False, "text": "",
                    "detail": f"OpenRouter doesn't serve `{model}`. Pick another model "
                              "in Settings → AI models."}
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return {"ok": False, "text": "",
                    "detail": f"OpenRouter error: {data['error'].get('message', data['error'])}"}
        choices = data.get("choices") or []
        text = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        if not text:
            return {"ok": False, "text": "", "detail": f"`{model}` returned an empty reply."}
        return {"ok": True, "text": text, "detail": f"Written by {model}."}
    except Exception as e:
        return {"ok": False, "text": "", "detail": f"Could not reach OpenRouter: {e}"}
