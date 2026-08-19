"""
Small, reusable UI pieces so every page looks and reads the same.

House rules (see CLAUDE.md → UI principle):
  - every screen says what it's for in one line
  - every option has a plain-language label + a one-line helper
  - an empty screen still tells you what to do next
"""

import streamlit as st

# Status colours, matching .streamlit/config.toml
OK = "#30a46c"        # green — working
WARN = "#f5a623"      # amber — works, but on fallback/seed data
BAD = "#e5484d"       # red — broken or missing
IDLE = "#8b8d98"      # grey — not built / not applicable

_STATE_COLOR = {"ok": OK, "warn": WARN, "bad": BAD, "idle": IDLE}


def page_header(title: str, subtitle: str) -> None:
    """Title + the one line that explains what this page is for."""
    st.markdown(f"## {title}")
    st.caption(subtitle)


def section(title: str, helper: str = "") -> None:
    """A labelled block inside a page."""
    st.markdown(f"#### {title}")
    if helper:
        st.caption(helper)


def status_badge(state: str, text: str) -> str:
    """
    An inline coloured pill, e.g. status_badge("ok", "live data").
    Returns markdown — pass it to st.markdown(..., unsafe_allow_html=True).
    """
    color = _STATE_COLOR.get(state, IDLE)
    return (f"<span style='background:{color}1a;color:{color};border-radius:999px;"
            f"padding:2px 10px;font-size:0.8rem;font-weight:600;white-space:nowrap'>"
            f"{text}</span>")


def show_badge(state: str, text: str) -> None:
    st.markdown(status_badge(state, text), unsafe_allow_html=True)


def metric_row(items: list) -> None:
    """
    A row of headline numbers.
    `items` = [(label, value), ...] or [(label, value, helper), ...]
    """
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        helper = item[2] if len(item) > 2 else None
        col.metric(label, value, help=helper)


def empty_state(title: str, body: str, steps: list | None = None,
                icon: str = "🧭") -> None:
    """
    What a screen shows when there's nothing to show yet: what it will do,
    and the exact next steps to make it do it.
    """
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.write(body)
        if steps:
            st.markdown("**To switch this on:**")
            for i, step in enumerate(steps, 1):
                st.markdown(f"{i}. {step}")


def status_rows(rows: list, widths=(2, 1, 4)) -> None:
    """
    The house readiness strip, used on every page: one line per moving part,
    with a coloured badge and a plain-language explanation of what it means.

    `rows` = [{'name', 'state', 'label', 'detail'}, ...] where state is one of
    ok / warn / bad / idle. Every page draws these the same way, so "ready" and
    "not set" mean the same thing wherever you see them.
    """
    for row in rows:
        cols = st.columns(list(widths))
        cols[0].markdown(f"**{row['name']}**")
        with cols[1]:
            show_badge(row.get("state", "idle"), row.get("label", ""))
        cols[2].caption(row.get("detail", ""))


def check_list(checks: list) -> None:
    """Render connection-test results: [{'name', 'ok', 'detail'}, ...]."""
    for c in checks:
        state = "ok" if c.get("ok") else "bad"
        mark = "✅" if c.get("ok") else "❌"
        st.markdown(
            f"{mark} **{c['name']}** &nbsp; {status_badge(state, 'pass' if c.get('ok') else 'fail')}",
            unsafe_allow_html=True,
        )
        st.caption(c.get("detail", ""))


def nav_button(label: str, page: str, key: str = "", help: str = "",
               type: str = "secondary") -> None:
    """
    A button that jumps to another sidebar page. Works because the sidebar's
    radio is bound to session_state["nav"] (see app.py).
    """
    st.button(label, key=key or f"nav_{page}_{label}", help=help, type=type,
              on_click=lambda: st.session_state.update(nav=page))


def data_source_note(source: str) -> None:
    """One consistent line telling the user whether they're on live or seed data."""
    if source == "live":
        show_badge("ok", "🟢 Live data from Search Console")
    else:
        show_badge("warn", "🟡 Seed data — your 16 Aug Search Console snapshot")
