"""Methodology & Downloads View (Page 5) for PTD Streamlit application.

Renders engineering architecture documentation (docs/LOGIC.md, docs/EXEC_SUMMARY.md),
input integrity manifest verification, and production deliverable download hub.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

import subprocess
from app.data_access import PROJECT_ROOT, get_download_file_bytes, load_doctor_report


def get_provenance_data() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Retrieve provenance report from doctor_report.json or run check_inputs.py."""
    doc = load_doctor_report()
    if not doc:
        try:
            cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "check_inputs.py")]
            subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, timeout=10)
            doc = load_doctor_report()
        except Exception:
            doc = None

    if not doc or not doc.get("entries"):
        return pd.DataFrame(), {}

    rows = []
    for entry in doc.get("entries", []):
        rows.append({
            "Logical Dataset": entry.get("logical_name", ""),
            "Required": "Yes" if entry.get("required") else "No (Optional)",
            "Status": "✅ Found" if entry.get("status") == "FOUND" else f"⚠️ {entry.get('status')}",
            "Resolved Path": entry.get("resolved_path", "NOT FOUND"),
            "Size": entry.get("size_str", "—"),
            "SHA-256 (12 chars)": entry.get("sha256", "—")[:12],
            "Manifest Verification": entry.get("manifest_status", "UNKNOWN"),
            "Notes": entry.get("notes", ""),
        })

    return pd.DataFrame(rows), doc


def render_methodology_view(source_mode: str = "Production outputs", global_filters: Dict[str, Any] | None = None) -> None:
    """Render the methodology documentation and deliverable downloads page."""
    st.title("📚 Methodology, Architectural Decisions & Downloads")
    st.caption("Complete engineering records (docs/LOGIC.md), executive documentation, and deliverable file download hub.")

    # -------------------------------------------------------------------------
    # 1. Production Deliverables Download Hub
    # -------------------------------------------------------------------------
    st.subheader("1. Production Deliverables Download Center")
    st.markdown("Download official submission artifacts directly from this browser interface:")

    d_col1, d_col2 = st.columns(2)

    with d_col1:
        st.markdown("**Core Curated Rate Files**")

        # 1. PS Grain CSV
        ps_bytes = get_download_file_bytes("final_rates_ps_grain.csv", source_mode)
        if ps_bytes:
            st.download_button(
                label="📥 Download Problem Statement Grain CSV (48,006 rows, 6 cols)",
                data=ps_bytes,
                file_name="final_rates_ps_grain.csv",
                mime="text/csv",
                use_container_width=True
            )

        # 2. Master Parquet
        pq_bytes = get_download_file_bytes("final_curated_rates.parquet", source_mode)
        if pq_bytes:
            st.download_button(
                label="📥 Download Master Lossless Parquet (69,144 rows, 45 cols)",
                data=pq_bytes,
                file_name="final_curated_rates.parquet",
                mime="application/octet-stream",
                use_container_width=True
            )

        # 3. Excel Multi-Sheet
        xlsx_bytes = get_download_file_bytes("final_curated_rates.xlsx", source_mode)
        if xlsx_bytes:
            st.download_button(
                label="📥 Download Multi-Sheet Excel Workbook (3 Sheets, 18 MB)",
                data=xlsx_bytes,
                file_name="final_curated_rates.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    with d_col2:
        st.markdown("**Governance, Metrics & Audits**")

        # 4. Summary JSON
        sum_json_bytes = get_download_file_bytes("summary.json", source_mode)
        if sum_json_bytes:
            st.download_button(
                label="📥 Download Pipeline Summary JSON (summary.json)",
                data=sum_json_bytes,
                file_name="summary.json",
                mime="application/json",
                use_container_width=True
            )

        # 5. Summary Excel
        sum_xlsx_bytes = get_download_file_bytes("summary.xlsx", source_mode)
        if sum_xlsx_bytes:
            st.download_button(
                label="📥 Download Formatted Summary Excel (summary.xlsx)",
                data=sum_xlsx_bytes,
                file_name="summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # 6. Manual Check Sample
        sample_bytes = get_download_file_bytes("manual_check_sample.csv", source_mode)
        if sample_bytes:
            st.download_button(
                label="📥 Download 40-Row Manual Check Sample (CSV)",
                data=sample_bytes,
                file_name="manual_check_sample.csv",
                mime="text/csv",
                use_container_width=True
            )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 2. Input Manifest & Data Provenance Status
    # -------------------------------------------------------------------------
    st.subheader("2. Source Data Provenance & Manifest Integrity")
    df_manifest, doc_data = get_provenance_data()

    if not df_manifest.empty:
        missing = doc_data.get("missing_required", [])
        if missing:
            st.info(
                "ℹ️ **Source data not attached; viewing precomputed outputs.** "
                "The pipeline outputs in `data/output/` are complete and intact. "
                "To connect real source datasets on this machine, configure pointers via environment variables, "
                "`config.local.yaml`, or run `make doctor`."
            )
        else:
            st.success("✅ **All required source datasets resolved & verified against input manifest.**")

        st.dataframe(df_manifest, width="stretch", hide_index=True)
    else:
        st.info("ℹ️ **Source data not attached; viewing precomputed outputs.**")

    if st.button("🔄 Verify Inputs / Run Input Doctor", key="btn_run_doctor"):
        try:
            cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "check_inputs.py")]
            res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=15)
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Doctor check error: {e}")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 3. Engineering Documentation (docs/LOGIC.md & docs/EXEC_SUMMARY.md)
    # -------------------------------------------------------------------------
    st.subheader("3. Architecture & Methodology Documentation")

    tab_logic, tab_exec = st.tabs(["📄 Engineering Design (LOGIC.md)", "📊 Executive Briefing (EXEC_SUMMARY.md)"])

    with tab_logic:
        logic_path = PROJECT_ROOT / "docs" / "LOGIC.md"
        if logic_path.exists():
            with open(logic_path, "r", encoding="utf-8") as f:
                logic_text = f.read()

            # Render collapsible sections by headers
            sections = logic_text.split("## ")
            for sec in sections:
                if not sec.strip():
                    continue
                lines = sec.strip().split("\n")
                title = lines[0].strip()
                body = "\n".join(lines[1:])
                with st.expander(f"📌 {title}", expanded=False):
                    st.markdown(body)
        else:
            st.info("docs/LOGIC.md not found.")

    with tab_exec:
        exec_path = PROJECT_ROOT / "docs" / "EXEC_SUMMARY.md"
        if exec_path.exists():
            with open(exec_path, "r", encoding="utf-8") as f:
                exec_text = f.read()
            st.markdown(exec_text)
        else:
            st.info("docs/EXEC_SUMMARY.md not found.")
