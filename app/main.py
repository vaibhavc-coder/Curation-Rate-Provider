"""Streamlit Web Application: TiC Provider Rate Curation & Cost-Effectiveness Explorer.

Main entry point for the PTD Frontend (Challenge Brownie 7a).
Coordinates modular views across:
- Executive Overview (app/views/executive.py)
- Contracting Analyst Workspace (app/views/analyst.py)
- Raw File Quality & Audits (app/views/files_quality.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.components import (
    render_footer,
    render_sidebar_controls,
    render_top_banner,
)
from app.data_access import load_summary_json
from app.views.analyst import render_analyst_view
from app.views.executive import render_executive_view
from app.views.files_quality import render_files_quality_view

# Streamlit Page Configuration
st.set_page_config(
    page_title="PTD Rate Transparency: Centene CA PPO",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Main application loop."""
    # 1. Top Regulatory Notice Banner (collapsible, visible by default)
    render_top_banner()

    # 2. Sidebar controls (Data source selector, Page navigation, Global filters, Reset button)
    controls = render_sidebar_controls()
    source_mode = controls["source_mode"]
    nav_page = controls["nav_page"]

    # 3. Dispatch to View (3 core pages with Executive fallback)
    if nav_page == "📊 Executive View":
        render_executive_view(source_mode=source_mode, global_filters=controls)
    elif nav_page == "🔍 Analyst View":
        render_analyst_view(source_mode=source_mode, global_filters=controls)
    elif nav_page == "🛡️ File Quality & Audits":
        render_files_quality_view(source_mode=source_mode, global_filters=controls)
    else:
        # Fallback to Executive View if unrecognized or removed page name is encountered
        render_executive_view(source_mode=source_mode, global_filters=controls)

    # 4. Global Footer with provenance metadata and resident memory
    summary = load_summary_json(source_mode)
    render_footer(summary)


if __name__ == "__main__":
    main()
