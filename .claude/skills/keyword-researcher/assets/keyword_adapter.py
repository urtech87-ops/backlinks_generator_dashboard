"""
Keyword data adapter for the keyword-researcher skill.

Two functions:
  autocomplete_suggestions(seed)  -> FREE keyword ideas from Google Suggest (no key)
  get_metrics(keywords)           -> volume/difficulty from a PLUGGABLE paid provider

Honest default: with no paid provider configured, get_metrics returns entries with
volume=None and difficulty=None. It never invents numbers. Swap the provider later:

    KEYWORD_API_PROVIDER=dummy      # dummy | dataforseo | semrush | ahrefs | keywords_everywhere
    KEYWORD_API_KEY=REPLACE_ME_LATER

GSC queries (your best free source) are NOT here — they come from the dashboard's
gsc.search_analytics(..., dimensions=["query"]). This file covers the extra sources.
"""

import os
import json

import requests
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.environ.get("KEYWORD_API_PROVIDER", "dummy").lower()
API_KEY = os.environ.get("KEYWORD_API_KEY", "REPLACE_ME_LATER")


def autocomplete_suggestions(seed: str, lang: str = "en", country: str = "us") -> list[str]:
    """
    Free Google Suggest expansion. Unofficial endpoint, no key required.
    Returns real query phrasings people type — good for keywords AND FAQ questions.
    Also try seed + ' a'..' z' and question words (how/what/best/free) for more.
    """
    out: list[str] = []
    seeds = [seed] + [f"{seed} {w}" for w in
                      ("how", "what", "best", "free", "vs", "online", "for")]
    for s in seeds:
        try:
            r = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": s, "hl": lang, "gl": country},
                timeout=15, headers={"User-Agent": "Mozilla/5.0 keyword-researcher"},
            )
            r.raise_for_status()
            data = json.loads(r.text)          # [seed, [suggestions...]]
            out.extend(data[1])
        except Exception:
            continue
    # de-dupe, keep order
    return list(dict.fromkeys(out))


def _dummy_metrics(keywords: list[str]) -> list[dict]:
    return [{"keyword": k, "volume": None, "difficulty": None, "source": "none"} for k in keywords]


def _dataforseo(keywords: list[str]) -> list[dict]:
    # Fill with your DataForSEO Labs / Keywords Data call. Kept as a clear stub.
    raise NotImplementedError(
        "DataForSEO not wired yet. Tell Claude your provider + key and it fills this in."
    )


def get_metrics(keywords: list[str]) -> list[dict]:
    """Return [{keyword, volume, difficulty, source}]. Never fabricates numbers."""
    if PROVIDER == "dummy" or API_KEY in ("", "REPLACE_ME_LATER"):
        return _dummy_metrics(keywords)
    try:
        if PROVIDER == "dataforseo":
            return _dataforseo(keywords)
        # semrush / ahrefs / keywords_everywhere stubs go here
        raise NotImplementedError(f"Provider '{PROVIDER}' not wired yet.")
    except Exception as e:
        print(f"  ! keyword metrics unavailable ({PROVIDER}): {e} — returning no numbers")
        return _dummy_metrics(keywords)


if __name__ == "__main__":
    print("autocomplete sample (needs network):")
    try:
        for s in autocomplete_suggestions("json formatter")[:10]:
            print("  -", s)
    except Exception as e:
        print("  (offline)", e)
    print("metrics (dummy):", get_metrics(["json formatter", "json beautifier"]))
