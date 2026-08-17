"""
Google Analytics 4 (GA4 Data API) access — the live audience layer.

Answers: how many real people are here, where do they come from, what do they
land on, do they stick. Fails soft: no property id or no libs -> empty results.
"""

from . import config

try:
    from google.oauth2.service_account import Credentials
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )
    _LIBS_OK = True
except Exception:
    _LIBS_OK = False


def _client():
    if not (_LIBS_OK and config.credentials_available()):
        return None
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=config.GA4_SCOPES
    )
    return BetaAnalyticsDataClient(credentials=creds)


def _run(property_id: str, dimensions, metrics, start: str, end: str, limit=100):
    client = _client()
    if client is None or not property_id:
        return []
    try:
        req = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start, end_date=end)],
            limit=limit,
        )
        resp = client.run_report(req)
        rows = []
        for r in resp.rows:
            row = {d.name: v.value for d, v in zip(req.dimensions, r.dimension_values)}
            row.update({m.name: v.value for m, v in zip(req.metrics, r.metric_values)})
            rows.append(row)
        return rows
    except Exception:
        return []


def summary(property_id: str, start: str, end: str) -> dict:
    """Top-line numbers for the header cards."""
    rows = _run(
        property_id, [],
        ["activeUsers", "sessions", "screenPageViews",
         "averageSessionDuration", "engagementRate"],
        start, end,
    )
    if not rows:
        return {}
    r = rows[0]
    return {
        "activeUsers": int(float(r.get("activeUsers", 0))),
        "sessions": int(float(r.get("sessions", 0))),
        "pageViews": int(float(r.get("screenPageViews", 0))),
        "avgDuration": round(float(r.get("averageSessionDuration", 0)), 1),
        "engagementRate": round(float(r.get("engagementRate", 0)) * 100, 1),
    }


def top_pages(property_id: str, start: str, end: str, limit=25):
    return _run(property_id, ["pagePath"],
                ["screenPageViews", "activeUsers", "engagementRate"],
                start, end, limit)


def channels(property_id: str, start: str, end: str, limit=20):
    return _run(property_id, ["sessionDefaultChannelGroup"],
                ["sessions", "activeUsers"], start, end, limit)


def countries(property_id: str, start: str, end: str, limit=15):
    return _run(property_id, ["country"],
                ["activeUsers", "sessions"], start, end, limit)
