"""Comprehensive UI Smoke Test for Streamlit Frontend using AppTest.

Tests all 3 pages across both data source modes (Production outputs & Test fixtures):
- Executive View
- Analyst View
- File Quality & Audits
"""

from pathlib import Path
import pytest

try:
    from streamlit.testing.v1 import AppTest
    HAS_STREAMLIT = True
except ImportError:
    AppTest = None
    HAS_STREAMLIT = False

pytestmark = pytest.mark.skipif(not HAS_STREAMLIT, reason="streamlit not installed in test environment")

MAIN_APP_PATH = str(Path(__file__).resolve().parent.parent / "app" / "main.py")


PAGES = [
    "📊 Executive View",
    "🔍 Analyst View",
    "🛡️ File Quality & Audits",
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


def test_ui_filter_defaults_and_reset():
    """Verify that global filters default to ALL and Reset Filters restores ALL."""
    at = AppTest.from_file(MAIN_APP_PATH, default_timeout=30).run()
    assert not at.exception

    # Assert default values are 'ALL'
    labels = [sb.label for sb in at.sidebar.selectbox]
    for label in ['Billing Code Type', 'Billing Class', 'Provider Specialty', 'Address Verification Tier', 'Entity Classification']:
        assert label in labels, f"Expected filter '{label}' in sidebar"
        idx = labels.index(label)
        assert at.sidebar.selectbox[idx].value == "ALL", f"{label} did not default to ALL, was {at.sidebar.selectbox[idx].value}"

    # Mutate filters
    cpt_idx = labels.index("Billing Code Type")
    at.sidebar.selectbox[cpt_idx].set_value("CPT").run()
    assert at.sidebar.selectbox[cpt_idx].value == "CPT"

    # Click reset button in sidebar
    assert len(at.sidebar.button) > 0
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert at.sidebar.selectbox[cpt_idx].value == "ALL"


def test_ui_session_state_fallback_for_removed_page():
    """Verify that if session state holds a removed page name, it falls back to Executive View."""
    at = AppTest.from_file(MAIN_APP_PATH, default_timeout=30)
    at.session_state["nav_page"] = "Deprecated Page"
    at.run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "📊 Executive View"
    assert "Executive View" in at.title[0].value
