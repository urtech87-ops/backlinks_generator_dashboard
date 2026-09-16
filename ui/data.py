"""
The dashboard's data layer: fetch once, share across pages.

Every live Google call in this app — Search Console coverage (URL Inspection),
Search Console performance (Search Analytics) and GA4 — happens in exactly one
place: `refresh_live()`, wired to the sidebar's "🔄 Refresh live data" button.
Nothing else in the dashboard calls Google on its own, no matter how many
times a page reruns or a tab is opened — Streamlit reruns the whole script on
every interaction, so anything fetched outside this one gate would spend API
quota on every click, not just "on open". Every page reads whatever this
button last loaded (or the sample snapshot, before it's ever been pressed)
and says plainly which one it's showing.
Session state alone isn't enough, though: it's wiped by a browser tab reload
(Streamlit starts a brand new session), which used to mean a fresh reload
silently fell back to the sample snapshot even right after a successful
refresh. So every successful `refresh_live()` also writes its result to a
small JSON file under `data/live_cache/<site>.json`, and the first read of
any cached value in a session hydrates it from that file first. This is
reading a cache, not calling Google, so it doesn't reopen the "no fetching
on load" rule above — it's the same one gate, just surviving a reload.
"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import analysis
from core import config, ga4, gsc, seed
from core.classifier import recommend

_CACHE_DIR = config.ROOT / "data" / "live_cache"


def _coverage_key(site: config.Site) -> str:
    return f"coverage_{site.key}"


def _perf_key(site: config.Site) -> str:
    return f"perf_{site.key}"


def _ga4_key(site: config.Site) -> str:
    return f"ga4_{site.key}"


def _refreshed_at_key(site: config.Site) -> str:
    return f"refreshed_at_{site.key}"


def _cache_path(site: config.Site) -> Path:
    return _CACHE_DIR / f"{site.key}.json"


def _hydrate_from_disk(site: config.Site) -> None:
    """
    Once per session per site: if nothing has been loaded into session_state
    yet, load the last successful `refresh_live()` result from disk. Never
    touches the network — the site may have been refreshed in a previous
    session entirely.
    """
    flag = f"_disk_hydrated_{site.key}"
    if st.session_state.get(flag):
        return
    st.session_state[flag] = True

    try:
        payload = json.loads(_cache_path(site).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    if payload.get("coverage") and not st.session_state.get(_coverage_key(site)):
        # JSON round-trips tuples as lists; put them back so this looks
        # exactly like what a same-session refresh_live() would have stored.
        st.session_state[_coverage_key(site)] = [tuple(row) for row in payload["coverage"]]
    if payload.get("perf") and not st.session_state.get(_perf_key(site)):
        st.session_state[_perf_key(site)] = payload["perf"]
    if payload.get("ga4") and not st.session_state.get(_ga4_key(site)):
        st.session_state[_ga4_key(site)] = payload["ga4"]
    if payload.get("refreshed_at"):
        st.session_state.setdefault(_refreshed_at_key(site), payload["refreshed_at"])


def _persist_to_disk(site: config.Site, refreshed_at: str) -> None:
    """Save this session's live cache for the site so a reload can find it."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "refreshed_at": refreshed_at,
        "coverage": st.session_state.get(_coverage_key(site)),
        "perf": st.session_state.get(_perf_key(site)),
        "ga4": st.session_state.get(_ga4_key(site)),
    }
    _cache_path(site).write_text(json.dumps(payload), encoding="utf-8")


def last_refreshed(site: config.Site) -> str:
    """
    When this site's live data was last successfully refreshed (this session
    or, thanks to the disk cache, an earlier one) — "" if it never has been.
    """
    _hydrate_from_disk(site)
    return st.session_state.get(_refreshed_at_key(site), "")


def has_live(site: config.Site) -> bool:
    _hydrate_from_disk(site)
    return bool(st.session_state.get(_coverage_key(site)))


def has_live_performance(site: config.Site) -> bool:
    _hydrate_from_disk(site)
    return bool(st.session_state.get(_perf_key(site)))


def has_live_ga4(site: config.Site) -> bool:
    _hydrate_from_disk(site)
    return bool(st.session_state.get(_ga4_key(site)))


_REFRESH_SEQ = "_live_refresh_seq"


def refresh_seq() -> int:
    """
    Bumped on every press of "Refresh live data", whatever the outcome. Pages
    that memoize a computed report (Overview) fold this into their memo key,
    so a stale memoized report gets recomputed from the fresh cache the
    moment you refresh — without a second button press.
    """
    return st.session_state.get(_REFRESH_SEQ, 0)


def refresh_live(site: config.Site, start: str = "", end: str = "") -> tuple[int, str]:
    """
    The one place this dashboard calls Google. Pulls live coverage (URL
    Inspection), and — when a date range is given — live Search Console
    performance (Search Analytics) and GA4, and caches all of it for the rest
    of the session. Never raises: on failure it returns 0 and an explanation,
    and whatever was cached before stays in place.

    Returns (row_count, message). `row_count` is the number of URLs Search
    Console actually gave a real coverage verdict for — a URL Inspection call
    that errors (auth, quota, a property/URL mismatch) is stored too, as a
    "Couldn't check" row, but does NOT count toward `row_count`, so a refresh
    where every single call failed correctly reports as a failure rather than
    a false success.
    """
    st.session_state[_REFRESH_SEQ] = st.session_state.get(_REFRESH_SEQ, 0) + 1

    if not config.credentials_available():
        return 0, ("No Google service-account file found. Add it on the Settings page, "
                   "then try again.")

    urls = gsc.discover_urls(site.sitemap_url)
    if not urls:
        return 0, (f"Couldn't read any URLs from {site.sitemap_url}. Check the sitemap "
                   "URL on the Settings page.")

    bar = st.progress(0.0, text=f"Inspecting {len(urls)} URLs via Search Console…")
    results = gsc.inspect_urls(
        site.gsc_property, urls,
        progress=lambda done, total: bar.progress(
            done / total, text=f"Inspecting URLs… {done}/{total}"),
    )
    bar.empty()

    if not results:
        return 0, ("Search Console returned nothing. Run the connection test on the "
                   "Settings page to see which step is failing.")

    ok = [(url, coverage) for url, coverage, error in results if not error]
    failed = [(url, error) for url, coverage, error in results if error]

    # Every row is kept — including failed ones, marked so the classifier puts
    # them in the honest "Couldn't check" bucket instead of "not indexed".
    st.session_state[_coverage_key(site)] = ok + [
        (url, f"Couldn't check: {error}") for url, error in failed
    ]

    if failed and not ok:
        sample = f' (e.g. "{failed[0][1]}")' if failed[0][1] else ""
        return 0, (f"Search Console couldn't be checked for any of the {len(results)} URLs"
                   f"{sample} — that's an API failure, not a real answer from Google. "
                   "None of these pages should be read as 'not indexed'. Run Settings → "
                   "Test connections to see exactly which step is failing.")

    perf_note = _refresh_performance(site, start, end)
    ga4_note = _refresh_ga4(site, start, end)
    extra = (" " + perf_note if perf_note else "") + (" " + ga4_note if ga4_note else "")

    refreshed_at = dt.datetime.now().isoformat(timespec="seconds")
    st.session_state[_refreshed_at_key(site)] = refreshed_at
    _persist_to_disk(site, refreshed_at)

    if failed:
        sample = f' (e.g. "{failed[0][1]}")' if failed[0][1] else ""
        return len(ok), (f"Loaded live coverage for {len(ok)} URLs — {len(failed)} couldn't "
                         f"be checked{sample} and are marked \"Couldn't check\" on the Fix "
                         f"Plan rather than counted as not indexed.{extra}")
    return len(ok), f"Loaded live coverage for {len(ok)} URLs.{extra}"


def _refresh_performance(site: config.Site, start: str, end: str) -> str:
    """Search Console Search Analytics, cached for the rest of the session."""
    if not (start and end):
        return ""
    pages = gsc.search_analytics(site.gsc_property, start, end, ["page"], row_limit=500)
    queries = gsc.search_analytics(site.gsc_property, start, end, ["query"], row_limit=500)
    page_queries = gsc.search_analytics(site.gsc_property, start, end, ["page", "query"],
                                        row_limit=1000)
    st.session_state[_perf_key(site)] = {
        "range": f"{start} → {end}", "start": start, "end": end,
        "pages": pages, "queries": queries, "page_queries": page_queries,
    }
    return f"Performance loaded for {len(pages)} pages and {len(queries)} searches."


def _refresh_ga4(site: config.Site, start: str, end: str) -> str:
    """GA4's four reports, cached for the rest of the session."""
    if not (start and end and config.ga4_ready(site)):
        return ""
    st.session_state[_ga4_key(site)] = {
        "range": f"{start} → {end}",
        "summary": ga4.summary(site.ga4_property_id, start, end),
        "channels": ga4.channels(site.ga4_property_id, start, end),
        "countries": ga4.countries(site.ga4_property_id, start, end),
        "top_pages": ga4.top_pages(site.ga4_property_id, start, end),
    }
    return "GA4 refreshed."


def performance_cache(site: config.Site) -> dict | None:
    """The last-refreshed Search Console performance for this site, or None."""
    _hydrate_from_disk(site)
    return st.session_state.get(_perf_key(site))


def performance_metrics(site: config.Site) -> dict:
    """{url without trailing slash: Search Analytics row}. {} until refreshed."""
    cache = performance_cache(site)
    if not cache:
        return {}
    out = {}
    for row in cache.get("pages") or []:
        url = (row.get("page") or "").rstrip("/")
        if url:
            out[url] = row
    return out


def performance_pages(site: config.Site) -> list:
    return (performance_cache(site) or {}).get("pages") or []


def performance_queries(site: config.Site) -> list:
    return (performance_cache(site) or {}).get("queries") or []


def performance_page_queries(site: config.Site) -> list:
    """Raw page+query Search Analytics rows — what `core.keywords` needs for
    per-page keyword lookups, without fetching them again."""
    return (performance_cache(site) or {}).get("page_queries") or []


def performance_range(site: config.Site) -> str:
    return (performance_cache(site) or {}).get("range", "")


def keywords(site: config.Site) -> list:
    """
    Every query this site's cached performance covers, as `core.keywords`
    `Keyword` objects — built from whatever the last refresh loaded, with no
    network call of its own. [] until a refresh has actually run.
    """
    from core import keywords as kw
    cache = performance_cache(site)
    if not cache:
        return []
    found = kw.gsc_keywords(site, cache.get("start", ""), cache.get("end", ""),
                            rows=cache.get("queries"), page_rows=cache.get("page_queries"))
    return found["keywords"] if found["ok"] else []


def ga4_cache(site: config.Site) -> dict | None:
    """The last-refreshed GA4 reports for this site, or None until refreshed."""
    _hydrate_from_disk(site)
    return st.session_state.get(_ga4_key(site))


def coverage_rows(site: config.Site) -> tuple[list, str]:
    """
    [(url, coverage_state), ...] plus 'live' or 'seed'. Never touches the
    network — 'live' here may be this session's own refresh, or the disk
    cache from the last successful one, whichever this session has. Sample
    ('seed') only comes back for a site that has never been refreshed at all.
    """
    _hydrate_from_disk(site)
    live = st.session_state.get(_coverage_key(site))
    if live:
        return live, "live"
    return seed.seed_rows(site.key, site.homepage), "seed"


def coverage_frame(site: config.Site) -> tuple[pd.DataFrame, str]:
    """
    Every page classified into a bucket with a recommended action, as a
    DataFrame. Columns: URL, Page, Coverage, Bucket, Priority, Action, Flags.
    """
    rows, source = coverage_rows(site)
    base = site.homepage.rstrip("/")
    verdicts = [recommend(url, cov) for url, cov in rows]
    df = pd.DataFrame([{
        "URL": v.url,
        "Page": v.url.replace(base, "") or "/",
        "Coverage": v.coverage,
        "Bucket": v.bucket,
        "Priority": v.priority,
        "Action": v.action,
        "Flags": ", ".join(v.flags),
    } for v in verdicts])
    return df, source


def health_summary(df: pd.DataFrame) -> dict:
    """
    Headline indexing numbers used by Overview and Analysis. The Analysis agent
    owns the sums, so the two pages can never quote different figures.
    """
    return analysis.health(df)
