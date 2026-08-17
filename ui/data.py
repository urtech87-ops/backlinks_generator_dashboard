"""
The dashboard's data layer: fetch once, share across pages.

Live coverage comes from the URL Inspection API, which is one call per URL —
slow and rate-limited — so it only runs when you press "Refresh live data",
and the result is kept for the rest of the session. Everything else reads
whatever is already loaded, or falls back to the seed snapshot.
"""

import pandas as pd
import streamlit as st

from core import config, gsc, seed
from core.classifier import recommend, HEALTHY


def _state_key(site: config.Site) -> str:
    return f"coverage_{site.key}"


def has_live(site: config.Site) -> bool:
    return bool(st.session_state.get(_state_key(site)))


def refresh_live(site: config.Site) -> tuple[int, str]:
    """
    Pull live coverage for a site. Returns (row_count, message). Never raises —
    on failure it returns 0 and an explanation, and the seed stays in place.
    """
    if not config.credentials_available():
        return 0, ("No Google service-account file found. Add it on the Settings page, "
                   "then try again.")

    urls = gsc.discover_urls(site.sitemap_url)
    if not urls:
        return 0, (f"Couldn't read any URLs from {site.sitemap_url}. Check the sitemap "
                   "URL on the Settings page.")

    bar = st.progress(0.0, text=f"Inspecting {len(urls)} URLs via Search Console…")
    rows = gsc.inspect_urls(
        site.gsc_property, urls,
        progress=lambda done, total: bar.progress(
            done / total, text=f"Inspecting URLs… {done}/{total}"),
    )
    bar.empty()

    if not rows:
        return 0, ("Search Console returned nothing. Run the connection test on the "
                   "Settings page to see which step is failing.")

    st.session_state[_state_key(site)] = rows
    return len(rows), f"Loaded live coverage for {len(rows)} URLs."


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
    """Headline indexing numbers used by Overview and Analysis."""
    total = len(df)
    healthy = int((df["Bucket"] == HEALTHY).sum()) if total else 0
    return {
        "total": total,
        "healthy": healthy,
        "problems": total - healthy,
        "pct": round(healthy / total * 100) if total else 0,
        "counts": df["Bucket"].value_counts().to_dict() if total else {},
    }
