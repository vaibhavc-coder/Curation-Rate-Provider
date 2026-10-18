"""Comprehensive UI Smoke Test for Streamlit Frontend using AppTest.

Tests all 5 pages across both data source modes (Production outputs & Test fixtures):
- Executive View
- Analyst View
- File Quality & Audits
- Network & Addresses
- Methodology & Downloads
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

MAIN_APP_PATH = str(Path(__file__).resolve().parent.parent / "app" / "main.py")

PAGES = [
    "📊 Executive View",
    "🔍 Analyst View",
    "🛡️ File Quality & Audits",
    "🗺️ Network & Addresses",
    "📚 Methodology & Downloads",
]


@pytest.mark.parametrize("data_source", ["Production outputs", "Test fixtures"])
def test_ui_all_pages_render_without_exception(data_source: str):
    """Verify that every view renders cleanly without exceptions across data modes."""
    at = AppTest.from_file(MAIN_APP_PATH, default_timeout=30).run()
    assert not at.exception, f"Initial launch failed with exception: {at.exception}"

    # Select data source
    at.sidebar.selectbox[0].set_value(data_source).run()
    assert not at.exception, f"Failed to switch data source to {data_source}: {at.exception}"

    # Iterate through all 5 views
    for page in PAGES:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, f"Page '{page}' raised exception in mode '{data_source}': {at.exception}"
        # Ensure title rendered on page
        assert len(at.title) > 0, f"Page '{page}' did not render any title"


def test_ui_reset_filters():
    """Verify that clicking the Reset Filters button runs without exception."""
    at = AppTest.from_file(MAIN_APP_PATH, default_timeout=30).run()
    assert not at.exception
    # Click reset button in sidebar
    if len(at.sidebar.button) > 0:
        at.sidebar.button[0].click().run()
        assert not at.exception
