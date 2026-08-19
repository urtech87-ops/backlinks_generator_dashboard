"""
SEO Command Center
==================
Run:  streamlit run app.py

The conductor. This file is deliberately thin: it draws the sidebar (which
site, which dates, which page), then hands off to one module per page in
`ui/views/`.

Page order mirrors the system: Overview → Analysis → Content → Backlinks →
Settings. Works day one on the seed of your real Search Console state; connect
the APIs on the Settings page and press "Refresh live data" to go live.
"""

import datetime as dt

import streamlit as st

from core import config
from ui import views
from ui import data as d

st.set_page_config(page_title="SEO Command Center", page_icon="🧭", layout="wide")


# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("🧭 SEO Command Center")

page = st.sidebar.radio(
    "Go to", list(views.PAGES), key="nav",
    format_func=lambda name: f"{views.PAGES[name][0]}  {name}",
)
st.sidebar.caption(views.PAGES[page][2])

st.sidebar.divider()

site_key = st.sidebar.selectbox(
    "Site", [s.key for s in config.SITES],
    format_func=lambda k: config.SITES_BY_KEY[k].label,
    help="Every page below shows this site.",
)
site = config.SITES_BY_KEY[site_key]

today = dt.date.today()
default_start = today - dt.timedelta(days=28)
date_range = st.sidebar.date_input(
    "Date range", (default_start, today),
    help="Applies to the Search Console and GA4 reports.",
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
else:
    start_d, end_d = default_start, today

creds = config.credentials_available()

st.sidebar.divider()
if creds:
    st.sidebar.markdown("**Live data:** 🟢 credentials found")
else:
    st.sidebar.markdown("**Live data:** 🟡 seed mode")
    st.sidebar.caption("No Google key file yet — indexing views use your 16 Aug snapshot.")

if st.sidebar.button("🔄 Refresh live data", disabled=not creds, width="stretch",
                     help="Re-checks every URL in your sitemap with the Search Console "
                          "URL Inspection API. Takes a minute on a big site."):
    count, message = d.refresh_live(site)
    (st.sidebar.success if count else st.sidebar.error)(message)

if d.has_live(site):
    st.sidebar.caption("Showing live coverage for this site.")

st.sidebar.divider()
with st.sidebar.expander("🛡️ What this app will never do"):
    st.markdown(
        "- **WordPress posts are always drafts.** Nothing here can publish a live post.\n"
        "- **Auto-publishing only ever goes to platforms you own** — your dev.to, your "
        "Blogger, your WordPress.\n"
        "- **Guest posts wait for you.** The agent prospects, scores and drafts; you "
        "approve every send, and the host decides whether to publish.\n"
        "- **No invented numbers.** A figure with nothing measuring it is labelled "
        "*unvalidated* rather than filled in.\n"
        "- **Your keys stay here.** Everything saves to the local `.env`."
    )


# ── Page ───────────────────────────────────────────────────────────────────
ctx = views.Ctx(site=site, start=start_d.isoformat(), end=end_d.isoformat(), creds=creds)
views.PAGES[page][1](ctx)
