"""Smoke test for Streamlit application using AppTest."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


def test_streamlit_app_smoke():
    app_path = Path(__file__).resolve().parent.parent / "app" / "main.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception
    # Check that navigation radio button rendered
    assert len(at.sidebar.radio) > 0
    # Check that metrics or title rendered
    assert len(at.title) > 0
