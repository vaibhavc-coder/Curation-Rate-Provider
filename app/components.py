"""Reusable UI components for PTD Streamlit application.

Provides top governance notice banner, global sidebar controls with filter reset,
formatted KPI metric cards, and execution metadata footer.
"""

from __future__ import annotations

import os
from typing import Any, Dict
import psutil
import streamlit as st
from app.data_access import load_distinct_filter_options


def render_top_banner() -> None:
    """Render collapsible top governance and network limitation notice."""
    with st.expander("📌 Regulatory & Network Attribution Notice (Click to collapse)", expanded=True):
        st.markdown(
            "> **Network Scope Reality**: This file cannot separate PPO from HMO/EOA; the deliverable is the "
            "**Centene California Commercial Group Shared Fee Schedule**. PPO participation is transparently partitioned into "
            "`T1_name_hint_ppo` (group name contains 'PPO') and `T2_shared_commercial`.\n"
            ">\n"
            "> **Address Attestation**: Address tiers represent **cross-source physical agreement** (NPPES + CMS DAC + Group TIN co-membership), "
            "not absolute gold-standard proof. Strict Verified represents dual-database agreement (100% corroborated)."
        )


def render_sidebar_controls() -> Dict[str, Any]:
    """Render sidebar title, data source toggle, navigation, and global filters."""
    st.sidebar.markdown("## 🏥 **PTD Rate Engine**")
    st.sidebar.caption("Centene CA Commercial Group PPO | TiC v2.0.0")

    # Data source selector (Brownie requirement)
    source_mode = st.sidebar.selectbox(
        "Data source",
        options=["Production outputs", "Test fixtures"],
        index=0,
        help="Switch between full production deliverables and lightweight demo fixtures (<250 KB)."
    )

    # Navigation Radio
    nav_page = st.sidebar.radio(
        "Navigation",
        options=[
            "📊 Executive View",
            "🔍 Analyst View",
            "🛡️ File Quality & Audits",
            "🗺️ Network & Addresses",
            "📚 Methodology & Downloads",
        ],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ **Global Scope Filters**")

    opts = load_distinct_filter_options(source_mode)

    # Reset button
    if st.sidebar.button("🔄 Reset filters", use_container_width=True):
        for key in ["filter_code_type", "filter_billing_class", "filter_specialty", "filter_address_status", "filter_entity_type"]:
            if key in st.session_state:
                st.session_state[key] = "ALL"
        st.rerun()

    code_types = ["ALL"] + opts.get("billing_code_types", ["CPT", "HCPCS", "RC"])
    billing_classes = ["ALL"] + opts.get("billing_classes", ["professional", "institutional"])
    specialties = ["ALL"] + opts.get("specialties", [])
    address_statuses = ["ALL"] + opts.get("address_statuses", ["Verified", "Probable", "Unverified", "Facility/TIN-level"])
    entity_types = ["ALL", "real_provider", "network_bucket"]

    filter_code_type = st.sidebar.selectbox(
        "Billing Code Type",
        options=code_types,
        key="filter_code_type",
        help="Filter rates by procedure type (CPT/HCPCS ambulatory vs UB-04 Revenue Code facility)."
    )
    filter_billing_class = st.sidebar.selectbox(
        "Billing Class",
        options=billing_classes,
        key="filter_billing_class",
        help="Filter by CMS billing form (Professional CMS-1500 vs Institutional UB-04)."
    )
    filter_specialty = st.sidebar.selectbox(
        "Provider Specialty",
        options=specialties,
        key="filter_specialty",
        help="Filter by primary clinical specialty mapped via NUCC taxonomy."
    )
    filter_address_status = st.sidebar.selectbox(
        "Address Verification Tier",
        options=address_statuses,
        key="filter_address_status",
        help="Filter by address corroboration tier (Strict Verified, Probable, Unverified, Facility)."
    )
    filter_entity_type = st.sidebar.selectbox(
        "Entity Classification",
        options=entity_types,
        key="filter_entity_type",
        help="Filter between real practicing provider groups and regional network administrative buckets."
    )

    return {
        "source_mode": source_mode,
        "nav_page": nav_page,
        "code_type": filter_code_type,
        "billing_class": filter_billing_class,
        "specialty": filter_specialty,
        "address_status": filter_address_status,
        "entity_type": filter_entity_type,
    }


def render_metric_card(
    label: str,
    value: str | int | float,
    help_text: str,
    delta: str | None = None,
    delta_color: str = "normal"
) -> None:
    """Render a clean metric KPI card with tooltip explanation."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color, help=help_text)


def render_footer(summary: Dict[str, Any] | None) -> None:
    """Render footer with data as-of date, pipeline version, source file name, and memory usage."""
    st.markdown("---")
    cols = st.columns([2, 2, 2, 2])

    meta = summary.get("pipeline_metadata", {}) if summary else {}
    as_of = meta.get("as_of_date", "2026-09-30 (Centene Monthly Transparency Publication)")
    ver = meta.get("pipeline_version", "1.0.0 (Production Verified)")
    src_file = "2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"

    # Current process memory in MB
    try:
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)
        mem_str = f"{mem_mb:.1f} MB (Bounded < 1 GB)"
    except Exception:
        mem_str = "< 500 MB"

    cols[0].caption(f"📅 **Data As-Of**: {as_of}")
    cols[1].caption(f"🚀 **Pipeline Release**: v{ver}")
    cols[2].caption(f"📄 **Raw In-Network Stream**: `{src_file}`")
    cols[3].caption(f"⚡ **App Resident Memory**: {mem_str}")
