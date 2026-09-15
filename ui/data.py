"""
The dashboard's data layer: fetch once, share across pages.

Live coverage comes from the URL Inspection API, which is one call per URL —
slow and rate-limited — so it only runs when you press "Refresh live data",
and the result is kept for the rest of the session. Everything else reads
whatever is already loaded, or falls back to the seed snapshot.
"""

import pandas as pd
import streamlit as st

from agents import analysis
from core import config, gsc, seed
from core.classifier import recommend


def _state_key(site: config.Site) -> str:
    return f"coverage_{site.key}"


def has_live(site: config.Site) -> bool:
    return bool(st.session_state.get(_state_key(site)))


def refresh_live(site: config.Site) -> tuple[int, str]:
    """
    Pull live coverage for a site. Returns (row_count, message). Never raises —
    on failure it returns 0 and an explanation, and the seed stays in place.

    `row_count` is the number of URLs Search Console actually gave a real
    verdict for. A URL Inspection call that errors (auth, quota, a
    property/URL mismatch) is stored too — as a "Couldn't check" row, never
    silently folded into "not indexed" — but it does NOT count toward
    `row_count`, so a refresh where every single call failed correctly reports
    as a failure (0, an error message) rather than a false success.
    """
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
    st.session_state[_state_key(site)] = ok + [
        (url, f"Couldn't check: {error}") for url, error in failed
    ]

    if failed and not ok:
        sample = f' (e.g. "{failed[0][1]}")' if failed[0][1] else ""
        return 0, (f"Search Console couldn't be checked for any of the {len(results)} URLs"
                   f"{sample} — that's an API failure, not a real answer from Google. "
                   "None of these pages should be read as 'not indexed'. Run Settings → "
                   "Test connections to see exactly which step is failing.")
    if failed:
        sample = f' (e.g. "{failed[0][1]}")' if failed[0][1] else ""
        return len(ok), (f"Loaded live coverage for {len(ok)} URLs — {len(failed)} couldn't "
                         f"be checked{sample} and are marked \"Couldn't check\" on the Fix "
                         "Plan rather than counted as not indexed.")
    return len(ok), f"Loaded live coverage for {len(ok)} URLs."


def coverage_rows(site: config.Site) -> tuple[list, str]:
    """[(url, coverage_state), ...] plus 'live' or 'seed'."""
    live = st.session_state.get(_state_key(site))
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
