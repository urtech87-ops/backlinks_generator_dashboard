"""
Shared test setup.

Phase 15 made `ui.data` persist a successful "Refresh live data" to
`data/live_cache/<site>.json` on disk, so a browser tab reload doesn't lose
it. Without this fixture, any test that actually calls `refresh_live()` (or
drives the sidebar's Refresh button) would write real files into the repo's
own `data/live_cache/` — and since pytest runs the whole suite in one
process, an earlier test's write would leak into a later test that expects
a site to look "never refreshed". Every test gets its own throwaway
directory instead, so this cache never crosses a test boundary or touches
the real repo.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui import data as d  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_live_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "_CACHE_DIR", tmp_path / "live_cache")
