"""
Google Search Console access.

Three jobs:
  1. discover_urls()  -> read the sitemap to get the page list to inspect
  2. inspect_urls()   -> URL Inspection API, one call per URL, returns live
                         coverageState (this is how we rebuild the Fix Plan live,
                         since Google has no bulk coverage API)
  3. search_analytics() -> clicks / impressions / CTR / position per page + query

All functions fail soft: if creds or the property aren't set up yet, they return
empty results and the UI falls back to seed data instead of crashing.
"""

import re
import xml.etree.ElementTree as ET

import requests

from . import config

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    _LIBS_OK = True
except Exception:                      # libraries not installed yet
    _LIBS_OK = False


def _service():
    if not (_LIBS_OK and config.credentials_available()):
        return None
    creds = Credentials.from_service_account_file(
        config.service_account_file(), scopes=config.GSC_SCOPES
    )
    # searchconsole v1 exposes searchanalytics, urlInspection, sitemaps, sites
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


# ── 1. Sitemap -> URL list ─────────────────────────────────────────────────
def discover_urls(sitemap_url: str, limit: int = 500) -> list[str]:
    """Fetch a sitemap (and nested sitemaps) and return the page URLs."""
    urls: list[str] = []
    try:
        seen_maps = set()
        stack = [sitemap_url]
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        while stack and len(urls) < limit:
            sm = stack.pop()
            if sm in seen_maps:
                continue
            seen_maps.add(sm)
            r = requests.get(sm, timeout=20, headers={"User-Agent": "seo-command-center"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            # sitemap index -> push child sitemaps
            for node in root.findall(f"{ns}sitemap"):
                loc = node.find(f"{ns}loc")
                if loc is not None and loc.text:
                    stack.append(loc.text.strip())
            # urlset -> collect page urls
            for node in root.findall(f"{ns}url"):
                loc = node.find(f"{ns}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
    except Exception:
        return urls
    # de-dupe, keep order
    return list(dict.fromkeys(urls))[:limit]


# ── 2. URL Inspection API -> live coverage per page ────────────────────────
def inspect_url(service, site_property: str, url: str) -> dict:
    """Return {'coverage': str, 'last_crawl': str, 'verdict': str, 'canonical': str}."""
    try:
        body = {"inspectionUrl": url, "siteUrl": site_property}
        resp = service.urlInspection().index().inspect(body=body).execute()
        idx = resp.get("inspectionResult", {}).get("indexStatusResult", {})
        return {
            "coverage": idx.get("coverageState", ""),
            "verdict": idx.get("verdict", ""),
            "last_crawl": idx.get("lastCrawlTime", ""),
            "canonical": idx.get("googleCanonical", ""),
            "robots": idx.get("robotsTxtState", ""),
        }
    except Exception as e:
        return {"coverage": "", "verdict": "", "last_crawl": "", "canonical": "",
                "robots": "", "error": str(e)}


def inspect_urls(site_property: str, urls: list[str], progress=None):
    """
    Inspect a batch of URLs. `progress` is an optional callback(done, total)
    so the UI can show a progress bar. Rate limit is 2000/day, 600/min — fine
    for ~100 pages. Returns [(url, coverage_state, error), ...] — `error` is
    "" on success and the exception message on failure. Callers MUST check
    `error` rather than treating a blank `coverage_state` as "not indexed":
    a failed call (auth, quota, a property/URL mismatch) also leaves
    `coverage_state` blank, and collapsing the two would silently turn "we
    couldn't check" into a false "Google says no".
    """
    service = _service()
    if service is None:
        return []
    out = []
    total = len(urls)
    for i, url in enumerate(urls, 1):
        info = inspect_url(service, site_property, url)
        out.append((url, info.get("coverage", ""), info.get("error", "")))
        if progress:
            progress(i, total)
    return out


# ── 3. Search Analytics -> performance ─────────────────────────────────────
def search_analytics(site_property: str, start: str, end: str,
                     dimensions=None, row_limit: int = 250) -> list[dict]:
    """
    Query the Performance report. `dimensions` e.g. ['page'] or ['query'] or
    ['page','query']. Dates are 'YYYY-MM-DD'. Returns a list of row dicts.
    """
    service = _service()
    if service is None:
        return []
    dimensions = dimensions or ["page"]
    try:
        body = {
            "startDate": start,
            "endDate": end,
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        resp = service.searchanalytics().query(siteUrl=site_property, body=body).execute()
        rows = []
        for r in resp.get("rows", []):
            row = {dim: key for dim, key in zip(dimensions, r.get("keys", []))}
            row.update({
                "clicks": r.get("clicks", 0),
                "impressions": r.get("impressions", 0),
                "ctr": round(r.get("ctr", 0) * 100, 2),
                "position": round(r.get("position", 0), 1),
            })
            rows.append(row)
        return rows
    except Exception:
        return []


# ── 4. Connection check (Settings page) ────────────────────────────────────
def list_properties() -> list[str]:
    """Every Search Console property this service account can read. [] on failure."""
    service = _service()
    if service is None:
        return []
    try:
        resp = service.sites().list().execute()
        return [s.get("siteUrl", "") for s in resp.get("siteEntry", [])]
    except Exception:
        return []


def check_connection(site_property: str, sitemap_url: str = "",
                     homepage: str = "", days: int = 28) -> list[dict]:
    """
    Verify this site end to end and report each step as
    {'name', 'ok', 'detail'} — never raises, so Settings can show the whole
    list whether it passes or fails.
    """
    import datetime as _dt

    checks: list[dict] = []

    if sitemap_url:
        urls = discover_urls(sitemap_url, limit=500)
        checks.append({
            "name": "Sitemap reachable",
            "ok": bool(urls),
            "detail": (f"Found {len(urls)} page URLs." if urls else
                       "Couldn't read any URLs. Check the sitemap URL opens in a browser."),
        })

    service = _service()
    if service is None:
        checks.append({
            "name": "Search Console API",
            "ok": False,
            "detail": ("No usable service account. Add the JSON key file (Settings above) "
                       "and install the Google API libraries from requirements.txt."),
        })
        return checks

    # 1. Can we see the property at all?
    try:
        props = list_properties()
        if not props:
            checks.append({"name": "Search Console access", "ok": False,
                           "detail": "The service account can't see any properties. Add its "
                                     "email as a user in Search Console → Settings → Users."})
        elif site_property in props:
            checks.append({"name": "Search Console access", "ok": True,
                           "detail": f"Property found ({len(props)} available to this account)."})
        else:
            checks.append({"name": "Search Console access", "ok": False,
                           "detail": "This exact property isn't on the account. It can see: "
                                     + ", ".join(props[:5]) + ("…" if len(props) > 5 else "")})
    except Exception as e:
        checks.append({"name": "Search Console access", "ok": False, "detail": str(e)})

    # 2. Search Analytics (the Performance tab)
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    rows = search_analytics(site_property, start.isoformat(), end.isoformat(),
                            ["page"], row_limit=5)
    checks.append({
        "name": "Search Analytics (Performance)",
        "ok": bool(rows),
        "detail": (f"Returned {len(rows)} page rows for the last {days} days."
                   if rows else
                   f"No rows for the last {days} days. Either the property genuinely has no "
                   "impressions yet, or the service account lacks access."),
    })

    # 3. URL Inspection (the Fix Plan's live source)
    target = homepage or site_property
    info = inspect_url(service, site_property, target)
    if info.get("error"):
        detail = f"Failed on {target}: {info['error']}"
    elif info.get("coverage") or info.get("verdict"):
        detail = f"{target} → {info.get('coverage') or info.get('verdict')}"
    else:
        detail = f"No coverage state returned for {target}."
    checks.append({
        "name": "URL Inspection (Fix Plan)",
        "ok": bool(info.get("coverage") or info.get("verdict")),
        "detail": detail,
    })

    return checks
