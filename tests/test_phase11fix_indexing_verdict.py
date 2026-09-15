"""
Phase 11-fix — the "every page shows Not indexed" correctness bug.

Bug report: on Analysis > Performance for toolshall.com, every page read
"Not indexed" even though Search Console genuinely had 143 pages indexed and
GA4/Search Console both had real live data for the date range. Root cause,
confirmed by reading the code (see the diagnosis in the PR/commit this test
ships with):

  1. `ui/views/analysis.py::_with_verdicts()` decided "indexed" by set
     membership in `coverage_df` and silently defaulted to `False` (=
     "Not indexed") for ANY page missing from that frame — whether that's
     because the coverage snapshot was never refreshed this session, or
     because this site (ToolsHall) has no seed fallback at all
     (`core/seed.py`'s `SEED_BY_SITE` only lists "toolsvenue"), so a fresh
     session starts with an EMPTY coverage frame regardless of what the live
     Search Console Performance API (queried separately, and successfully)
     reports.
  2. `agents/analysis.py::page_verdict()` had no way to say "unknown" — its
     `indexed` parameter was a plain bool, so "we never checked" and "Google
     confirmed not indexed" were indistinguishable.
  3. `core/gsc.py::inspect_urls()` discarded the per-URL `error` that
     `inspect_url()` already captured, so even a full URL Inspection sweep
     that failed for every URL (auth/quota/property mismatch) silently
     produced coverage="" for every row — read by the classifier as bucket
     OTHER (not HEALTHY) — and `ui/data.py::refresh_live()` reported that as
     a plain SUCCESS ("Loaded live coverage for N URLs").

The fix: `indexed` is now a tri-state (`True` / `False` / `None`), a new
`UNKNOWN` ("Couldn't check") bucket carries a real inspection failure without
being folded into "not indexed", and `refresh_live()` reports failures
honestly instead of claiming success. This file proves each piece and the
end-to-end scenario together.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import analysis as ag  # noqa: E402
from core import classifier as cl  # noqa: E402
from core import config, gsc  # noqa: E402
from ui import data as d  # noqa: E402
from ui.views import analysis as av  # noqa: E402


# ── 1. page_verdict(): a missing/failed check is never a silent "no" ───────
def test_page_verdict_unknown_is_not_not_indexed():
    v = ag.page_verdict(indexed=None, position=0, impressions=0, ctr=0,
                        has_metrics=False)
    assert v["label"] == ag.V_UNCHECKED
    assert v["label"] != ag.V_NOT_INDEXED


def test_page_verdict_confirmed_not_indexed_still_works():
    """A page the classifier actually checked and confirmed isn't indexed
    (e.g. a 404 or a quality rejection) must still read as Not indexed —
    the fix must not turn a real "no" into a fake "unknown" either."""
    v = ag.page_verdict(indexed=False, position=0, impressions=0, ctr=0,
                        has_metrics=False)
    assert v["label"] == ag.V_NOT_INDEXED


def test_page_verdict_indexed_true_is_unaffected():
    v = ag.page_verdict(indexed=True, position=2.0, impressions=500, ctr=10.0,
                        has_metrics=True)
    assert v["label"] == ag.V_WINNING


# ── 2. The classifier's new UNKNOWN bucket ──────────────────────────────────
def test_inspection_failure_buckets_as_unknown_not_other_or_plumbing():
    verdict = cl.recommend("https://toolshall.com/some-tool/",
                           "Couldn't check: <HttpError 403 quotaExceeded>")
    assert verdict.bucket == cl.UNKNOWN
    assert verdict.bucket != cl.OTHER
    assert verdict.bucket != cl.PLUMBING


def test_error_text_containing_404_is_not_misread_as_plumbing():
    """An API failure message can itself contain words like '404' — that
    must not be mistaken for Google's own coverage verdict."""
    verdict = cl.recommend("https://toolshall.com/some-tool/",
                           "Couldn't check: HTTP 404 from the inspection endpoint")
    assert verdict.bucket == cl.UNKNOWN


def test_a_real_plumbing_state_is_untouched():
    verdict = cl.recommend("https://toolshall.com/broken/", "Redirect error")
    assert verdict.bucket == cl.PLUMBING


# ── 3. gsc.inspect_urls() no longer drops the error ─────────────────────────
def test_inspect_urls_preserves_per_url_errors(monkeypatch):
    class FakeInspection:
        def index(self):
            return self

        def inspect(self, body):
            self._url = body["inspectionUrl"]
            return self

        def execute(self):
            if "broken" in self._url:
                raise RuntimeError("<HttpError 403 quotaExceeded>")
            return {"inspectionResult": {"indexStatusResult":
                    {"coverageState": "Submitted and indexed"}}}

    class FakeService:
        def urlInspection(self):
            return FakeInspection()

    monkeypatch.setattr(gsc, "_service", lambda: FakeService())
    results = gsc.inspect_urls("https://toolshall.com/",
                               ["https://toolshall.com/ok/",
                                "https://toolshall.com/broken/"])
    by_url = {url: (coverage, error) for url, coverage, error in results}
    assert by_url["https://toolshall.com/ok/"] == ("Submitted and indexed", "")
    coverage, error = by_url["https://toolshall.com/broken/"]
    assert coverage == ""
    assert "quotaExceeded" in error, "the real error must survive, not be dropped"


# ── 4. refresh_live() reports a total failure honestly ─────────────────────
def test_refresh_live_all_failed_is_reported_as_failure(monkeypatch):
    site = config.SITES_BY_KEY["toolshall"]
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls",
                        lambda sitemap, limit=500: ["https://toolshall.com/a/",
                                                    "https://toolshall.com/b/"])
    monkeypatch.setattr(
        gsc, "inspect_urls",
        lambda prop, urls, progress=None: [
            (u, "", "<HttpError 403 quotaExceeded>") for u in urls
        ],
    )

    import streamlit as st
    st.session_state.clear()

    count, message = d.refresh_live(site)
    assert count == 0, "a 100%-failed refresh must not be reported as a success"
    assert "quotaExceeded" in message
    assert "not" in message.lower() and "indexed" in message.lower()

    # The failed URLs are still stored, so the Fix Plan can show them, but
    # bucketed as UNKNOWN rather than silently read as "not indexed".
    stored = dict(st.session_state["coverage_toolshall"])
    assert stored["https://toolshall.com/a/"].startswith("Couldn't check:")
    assert cl.bucket_for_coverage(stored["https://toolshall.com/a/"]) == cl.UNKNOWN


def test_refresh_live_partial_failure_keeps_the_good_rows(monkeypatch):
    site = config.SITES_BY_KEY["toolshall"]
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls",
                        lambda sitemap, limit=500: ["https://toolshall.com/a/",
                                                    "https://toolshall.com/b/"])
    monkeypatch.setattr(
        gsc, "inspect_urls",
        lambda prop, urls, progress=None: [
            ("https://toolshall.com/a/", "Submitted and indexed", ""),
            ("https://toolshall.com/b/", "", "<HttpError 403 quotaExceeded>"),
        ],
    )

    import streamlit as st
    st.session_state.clear()

    count, message = d.refresh_live(site)
    assert count == 1
    assert "1" in message and "couldn't be checked" in message
    stored = dict(st.session_state["coverage_toolshall"])
    assert stored["https://toolshall.com/a/"] == "Submitted and indexed"
    assert cl.bucket_for_coverage(stored["https://toolshall.com/b/"]) == cl.UNKNOWN


# ── 5. The exact reported scenario: real live performance, empty coverage ──
def test_with_verdicts_never_defaults_a_missing_page_to_not_indexed():
    """
    This is the toolshall bug, reproduced directly: a page Search Console's
    Performance API genuinely reports (real clicks/impressions/position) but
    that has no row at all in coverage_df — exactly ToolsHall's situation on
    a session where "Refresh live data" hasn't been pressed (no seed, empty
    frame). Before the fix this rendered "Not indexed"; it must now render
    the honest "Couldn't check yet" instead.
    """
    empty_coverage = pd.DataFrame(columns=["URL", "Page", "Coverage", "Bucket",
                                           "Priority", "Action", "Flags"])
    pdf = pd.DataFrame([
        {"page": "https://toolshall.com/pdf-compressor/", "clicks": 14,
         "impressions": 620, "ctr": 2.3, "position": 6.1},
    ])
    out = av._with_verdicts(empty_coverage, pdf)
    assert out.iloc[0]["Verdict"] == f'{ag.VERDICT_ICON[ag.V_UNCHECKED]} {ag.V_UNCHECKED}'
    assert "not" in out.iloc[0]["Why"].lower()


def test_with_verdicts_still_reports_a_confirmed_indexed_page_correctly():
    """The fix must not break the ordinary, working case: a page genuinely
    marked Healthy in coverage_df should never read as unchecked or as
    not-indexed."""
    coverage = pd.DataFrame([{
        "URL": "https://toolshall.com/pdf-compressor/", "Page": "/pdf-compressor/",
        "Coverage": "Submitted and indexed", "Bucket": cl.HEALTHY, "Priority": 5,
        "Action": "", "Flags": "",
    }])
    pdf = pd.DataFrame([
        {"page": "https://toolshall.com/pdf-compressor/", "clicks": 14,
         "impressions": 620, "ctr": 2.3, "position": 6.1},
    ])
    out = av._with_verdicts(coverage, pdf)
    label = out.iloc[0]["Verdict"]
    assert ag.V_NOT_INDEXED not in label
    assert ag.V_UNCHECKED not in label


def test_with_verdicts_a_genuinely_unindexed_page_still_says_so():
    """The other direction: coverage_df that actually checked this page and
    found it broken/rejected must still say Not indexed — the fix only
    changes the "we never checked" case, not real negatives."""
    coverage = pd.DataFrame([{
        "URL": "https://toolshall.com/broken/", "Page": "/broken/",
        "Coverage": "Redirect error", "Bucket": cl.PLUMBING, "Priority": 1,
        "Action": "", "Flags": "",
    }])
    pdf = pd.DataFrame([
        {"page": "https://toolshall.com/broken/", "clicks": 0,
         "impressions": 30, "ctr": 0.0, "position": 55.0},
    ])
    out = av._with_verdicts(coverage, pdf)
    assert ag.V_NOT_INDEXED in out.iloc[0]["Verdict"]


def test_with_verdicts_unknown_bucket_page_is_also_unchecked_not_not_indexed():
    """A page that WAS in this session's coverage sweep but whose own
    inspection call failed (bucket UNKNOWN) must be treated the same as a
    page missing entirely — an unknown, never a "not indexed"."""
    coverage = pd.DataFrame([{
        "URL": "https://toolshall.com/pdf-compressor/", "Page": "/pdf-compressor/",
        "Coverage": "Couldn't check: <HttpError 403 quotaExceeded>",
        "Bucket": cl.UNKNOWN, "Priority": 1, "Action": "", "Flags": "",
    }])
    pdf = pd.DataFrame([
        {"page": "https://toolshall.com/pdf-compressor/", "clicks": 14,
         "impressions": 620, "ctr": 2.3, "position": 6.1},
    ])
    out = av._with_verdicts(coverage, pdf)
    assert ag.V_UNCHECKED in out.iloc[0]["Verdict"]
