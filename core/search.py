"""
Web search — the pluggable adapter Lane B prospects with.

Same pattern as the image and keyword adapters: pick a provider in Settings,
paste a key, and every caller keeps working. The default provider needs no key
at all, so prospecting works on day one; a paid provider is steadier if you run
it often.

  duckduckgo   free, no key. Reads DuckDuckGo's HTML endpoint. Unofficial, so
               it can be throttled or blocked — when that happens the UI says so
               rather than pretending it found nothing.
  serper       google.serper.dev — Google results, cheap, needs SEARCH_API_KEY.
  serpapi      serpapi.com — same idea, needs SEARCH_API_KEY.
  brave        Brave Search API — needs SEARCH_API_KEY.

Fails soft everywhere: every function returns a dict with `ok` and a
plain-language `detail`, and never raises into the dashboard.
"""

import re
import urllib.parse
from dataclasses import dataclass

import requests

from . import config

TIMEOUT = 20
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

PROVIDERS = {
    "duckduckgo": "DuckDuckGo (free, no key — best effort)",
    "serper": "Serper.dev (Google results, needs a key)",
    "serpapi": "SerpAPI (needs a key)",
    "brave": "Brave Search API (needs a key)",
}

DEFAULT_PROVIDER = "duckduckgo"
KEYLESS = ("duckduckgo",)


@dataclass
class Result:
    """One search hit, normalised across providers."""
    title: str
    url: str
    snippet: str = ""


def provider() -> str:
    """The provider currently selected in Settings."""
    name = config.get("SEARCH_API_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    return name if name in PROVIDERS else DEFAULT_PROVIDER


def needs_key(name: str = "") -> bool:
    return (name or provider()) not in KEYLESS


def missing() -> list:
    """Which settings are still empty for the selected provider."""
    if needs_key() and not config.is_set("SEARCH_API_KEY"):
        return ["search API key"]
    return []


def _ok(results: list, detail: str) -> dict:
    return {"ok": True, "results": results, "detail": detail}


def _fail(detail: str) -> dict:
    return {"ok": False, "results": [], "detail": detail}


# ── Providers ──────────────────────────────────────────────────────────────
def _serper(query: str, limit: int) -> dict:
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": config.get("SEARCH_API_KEY"),
                 "Content-Type": "application/json"},
        json={"q": query, "num": min(limit, 20)}, timeout=TIMEOUT,
    )
    if r.status_code in (401, 403):
        return _fail("Serper rejected the key (401/403). Check it in Settings.")
    r.raise_for_status()
    hits = r.json().get("organic") or []
    return _ok([Result(h.get("title", ""), h.get("link", ""), h.get("snippet", ""))
                for h in hits if h.get("link")][:limit], "Serper")


def _serpapi(query: str, limit: int) -> dict:
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"q": query, "num": min(limit, 20), "engine": "google",
                "api_key": config.get("SEARCH_API_KEY")},
        timeout=TIMEOUT,
    )
    if r.status_code in (401, 403):
        return _fail("SerpAPI rejected the key (401/403). Check it in Settings.")
    r.raise_for_status()
    hits = r.json().get("organic_results") or []
    return _ok([Result(h.get("title", ""), h.get("link", ""), h.get("snippet", ""))
                for h in hits if h.get("link")][:limit], "SerpAPI")


def _brave(query: str, limit: int) -> dict:
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": config.get("SEARCH_API_KEY"),
                 "Accept": "application/json"},
        params={"q": query, "count": min(limit, 20)}, timeout=TIMEOUT,
    )
    if r.status_code in (401, 403):
        return _fail("Brave rejected the key (401/403). Check it in Settings.")
    if r.status_code == 429:
        return _fail("Brave says you're over its rate limit (429). Wait a minute "
                     "and try again.")
    r.raise_for_status()
    hits = (r.json().get("web") or {}).get("results") or []
    return _ok([Result(h.get("title", ""), h.get("url", ""), h.get("description", ""))
                for h in hits if h.get("url")][:limit], "Brave Search")


_DDG_LINK = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                       re.IGNORECASE | re.DOTALL)
_DDG_SNIPPET = re.compile(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                          re.IGNORECASE | re.DOTALL)


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _ddg_url(href: str) -> str:
    """DuckDuckGo wraps results in a redirect: pull the real URL back out."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and "uddg" in parsed.query:
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        return urllib.parse.unquote(target)
    return href if href.startswith("http") else ""


def _duckduckgo(query: str, limit: int) -> dict:
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                      headers={"User-Agent": UA}, timeout=TIMEOUT)
    if r.status_code in (202, 403, 429):
        return _fail("DuckDuckGo is throttling this dashboard right now. Wait a few "
                     "minutes, or add a Serper/SerpAPI/Brave key in Settings for a "
                     "steadier feed.")
    r.raise_for_status()
    html = r.text
    snippets = [_strip_html(s) for s in _DDG_SNIPPET.findall(html)]
    results = []
    for i, (href, title) in enumerate(_DDG_LINK.findall(html)):
        url = _ddg_url(href)
        if not url:
            continue
        results.append(Result(_strip_html(title), url,
                              snippets[i] if i < len(snippets) else ""))
        if len(results) >= limit:
            break
    if not results:
        return _fail("DuckDuckGo returned a page with no results in it — usually its "
                     "bot check. Try again shortly, or add a search API key in Settings.")
    return _ok(results, "DuckDuckGo")


_DISPATCH = {"duckduckgo": _duckduckgo, "serper": _serper, "serpapi": _serpapi,
             "brave": _brave}


# ── Public API ─────────────────────────────────────────────────────────────
def search(query: str, limit: int = 10) -> dict:
    """
    One search. Returns {'ok': bool, 'results': [Result], 'detail': str}.
    Never raises — the caller shows `detail` and carries on.
    """
    name = provider()
    gaps = missing()
    if gaps:
        return _fail(f"{PROVIDERS[name]} needs a key — missing: {', '.join(gaps)}. "
                     "Add it in Settings → Prospecting, or switch the provider to "
                     "DuckDuckGo.")
    try:
        return _DISPATCH[name](query, max(1, limit))
    except requests.HTTPError as e:
        return _fail(f"{PROVIDERS[name]} returned an error: {e}")
    except Exception as e:
        return _fail(f"Couldn't reach {PROVIDERS[name]}: {e}")


def check() -> dict:
    """A real 'is search working?' test for the UI. {'ok': bool, 'detail': str}."""
    result = search("site:example.com", limit=3)
    if result["ok"]:
        return {"ok": True,
                "detail": f"Search is working via {result['detail']} — "
                          f"{len(result['results'])} results returned."}
    return {"ok": False, "detail": result["detail"]}
