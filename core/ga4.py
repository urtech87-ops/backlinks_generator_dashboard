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
        config.service_account_file(), scopes=config.GA4_SCOPES
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


def check_connection(property_id: str, days: int = 28) -> list[dict]:
    """
    Verify GA4 for one site. Same {'name', 'ok', 'detail'} shape as
    gsc.check_connection, and equally fail-soft.
    """
    import datetime as _dt

    if not property_id:
        return [{"name": "GA4", "ok": False,
                 "detail": "No GA4 property ID set for this site (that's fine — "
                           "the Audience view just stays empty)."}]
    if not _LIBS_OK:
        return [{"name": "GA4", "ok": False,
                 "detail": "The google-analytics-data library isn't installed. "
                           "Run: pip install -r requirements.txt"}]
    if not config.credentials_available():
        return [{"name": "GA4", "ok": False,
                 "detail": "No service-account JSON found — see the Google section above."}]

    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    s = summary(property_id, start.isoformat(), end.isoformat())
    if s:
        return [{"name": "GA4 Data API", "ok": True,
                 "detail": f"Property {property_id}: {s['activeUsers']} active users / "
                           f"{s['sessions']} sessions in the last {days} days."}]
    return [{"name": "GA4 Data API", "ok": False,
             "detail": f"No data back from property {property_id}. Check the ID is the "
                       "numeric property ID, and that the service-account email has "
                       "Viewer access in GA4 → Admin → Property access management."}]
