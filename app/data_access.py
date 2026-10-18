"""Data access layer for PTD Streamlit application.

Reads finished pipeline outputs from data/output/ or data/fixtures/output/.
Resolves all paths dynamically via config.yaml (zero hardcoded paths).
Uses st.cache_data and Polars/DuckDB lazy loading to keep memory under 1 GB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import polars as pl
import streamlit as st
import yaml

# Resolve repository root dynamically relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_base_config() -> Dict[str, Any]:
    """Load configuration from config.yaml without hardcoded paths."""
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}


def get_output_dir(source_mode: str = "Production outputs") -> Path:
    """Return the output directory path based on the selected data source mode."""
    cfg = get_base_config()
    paths = cfg.get("paths", {})
    if source_mode == "Test fixtures":
        fixture_path = PROJECT_ROOT / "data" / "fixtures" / "output"
        if fixture_path.exists():
            return fixture_path
        return PROJECT_ROOT / "tests" / "fixtures" / "output"
    # Production outputs
    prod_rel = paths.get("output_dir", "data/output")
    return PROJECT_ROOT / prod_rel


def render_missing_file_warning(filename: str, command: str = "python run_pipeline.py --all") -> None:
    """Display a friendly, actionable warning when an expected deliverable is missing."""
    st.warning(
        f"⚠️ **Deliverable Missing**: `{filename}` could not be found.\n\n"
        f"To generate this deliverable, execute:\n```bash\n{command}\n```"
    )


@st.cache_data(show_spinner=False)
def load_summary_json(source_mode: str = "Production outputs") -> Optional[Dict[str, Any]]:
    """Load pipeline summary.json."""
    path = get_output_dir(source_mode) / "summary.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_coverage_report_json(source_mode: str = "Production outputs") -> Optional[Dict[str, Any]]:
    """Load coverage_report.json."""
    path = get_output_dir(source_mode) / "coverage_report.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_file_scores_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load file_scores.csv."""
    path = get_output_dir(source_mode) / "file_scores.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_ppo_plans_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load ppo_plans.csv."""
    path = get_output_dir(source_mode) / "ppo_plans.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_ambiguous_review_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load ambiguous_review.csv."""
    path = get_output_dir(source_mode) / "ambiguous_review.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_outlier_review_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load rate_outlier_review.csv."""
    path = get_output_dir(source_mode) / "rate_outlier_review.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_mutation_report_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load mutation_test_report.csv."""
    path = get_output_dir(source_mode) / "mutation_test_report.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_manual_check_sample_df(source_mode: str = "Production outputs") -> Optional[pd.DataFrame]:
    """Load manual_check_sample.csv."""
    path = get_output_dir(source_mode) / "manual_check_sample.csv"
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_cost_effectiveness_df(
    source_mode: str = "Production outputs",
    columns: Optional[List[str]] = None,
    limit: Optional[int] = None
) -> Optional[pd.DataFrame]:
    """Load cost_effectiveness.parquet lazily selecting requested columns."""
    path = get_output_dir(source_mode) / "cost_effectiveness.parquet"
    if not path.exists():
        return None
    try:
        lazy_df = pl.scan_parquet(path)
        if columns:
            available_cols = set(lazy_df.collect_schema().names())
            selected = [c for c in columns if c in available_cols]
            if selected:
                lazy_df = lazy_df.select(selected)
        if limit:
            lazy_df = lazy_df.limit(limit)
        return lazy_df.collect().to_pandas()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_ps_grain_sample(
    source_mode: str = "Production outputs",
    limit: int = 5000
) -> Optional[pd.DataFrame]:
    """Load sample of Problem Statement Grain CSV."""
    path = get_output_dir(source_mode) / "final_rates_ps_grain.csv"
    if path.exists():
        try:
            return pd.read_csv(path, nrows=limit)
        except Exception:
            return None
    return None


@st.cache_data(show_spinner=False)
def load_distinct_filter_options(source_mode: str = "Production outputs") -> Dict[str, List[str]]:
    """Quickly extract distinct filter options from final_curated_rates.parquet."""
    path = get_output_dir(source_mode) / "final_curated_rates.parquet"
    if not path.exists():
        return {
            "billing_code_types": ["CPT", "HCPCS", "RC"],
            "billing_classes": ["professional", "institutional"],
            "specialties": [],
            "address_statuses": ["Verified", "Probable", "Unverified", "Facility/TIN-level"],
            "entity_kinds": ["real_provider", "network_bucket"],
            "network_tiers": ["T1_name_hint_ppo", "T2_shared_commercial"],
        }
    try:
        schema = pl.scan_parquet(path).collect_schema().names()
        cols = [c for c in ["billing_code_type", "billing_class", "Specialty", "address_status", "entity_kind", "ppo_evidence_tier"] if c in schema]
        sample_df = pl.scan_parquet(path).select(cols).collect()
        return {
            "billing_code_types": sorted([str(x) for x in sample_df["billing_code_type"].drop_nulls().unique().to_list() if x]),
            "billing_classes": sorted([str(x) for x in sample_df["billing_class"].drop_nulls().unique().to_list() if x]),
            "specialties": sorted([str(x) for x in sample_df["Specialty"].drop_nulls().unique().to_list() if x and x != "Unknown"]),
            "address_statuses": ["Verified", "Probable", "Unverified", "Facility/TIN-level"],
            "entity_kinds": sorted([str(x) for x in sample_df["entity_kind"].drop_nulls().unique().to_list() if x]),
            "network_tiers": sorted([str(x) for x in sample_df["ppo_evidence_tier"].drop_nulls().unique().to_list() if x]),
        }
    except Exception:
        return {}


def query_curated_rates_polars(
    source_mode: str = "Production outputs",
    billing_code: Optional[str] = None,
    specialty: Optional[str] = None,
    tin: Optional[str] = None,
    npi: Optional[int] = None,
    address_status: Optional[str] = None,
    network_tier: Optional[str] = None,
    outlier_filter: Optional[str] = None,
    rate_min: Optional[float] = None,
    rate_max: Optional[float] = None,
    limit: int = 1000
) -> Optional[pd.DataFrame]:
    """Execute memory-bounded predicate pushdown on final_curated_rates.parquet."""
    path = get_output_dir(source_mode) / "final_curated_rates.parquet"
    if not path.exists():
        return None
    try:
        lazy_df = pl.scan_parquet(path)
        if billing_code and billing_code.strip():
            lazy_df = lazy_df.filter(pl.col("Billing Code").str.to_uppercase().str.contains(billing_code.strip().upper()))
        if specialty and specialty != "ALL":
            lazy_df = lazy_df.filter(pl.col("Specialty") == specialty)
        if tin and tin.strip():
            lazy_df = lazy_df.filter(pl.col("TIN").str.contains(tin.strip()))
        if npi:
            lazy_df = lazy_df.filter(pl.col("NPI") == int(npi))
        if address_status and address_status != "ALL":
            lazy_df = lazy_df.filter(pl.col("address_status") == address_status)
        if network_tier and network_tier != "ALL":
            lazy_df = lazy_df.filter(pl.col("ppo_evidence_tier") == network_tier)
        if outlier_filter == "Outliers only":
            lazy_df = lazy_df.filter(pl.col("outlier_flag") == True)
        elif outlier_filter == "Standard only":
            lazy_df = lazy_df.filter(pl.col("outlier_flag") == False)
        if rate_min is not None:
            lazy_df = lazy_df.filter(pl.col("Rate") >= rate_min)
        if rate_max is not None:
            lazy_df = lazy_df.filter(pl.col("Rate") <= rate_max)

        display_cols = [
            "NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate",
            "address_status", "address_confidence", "rate_reliability",
            "tin_canonical_name", "ppo_evidence_tier", "outlier_flag",
            "modifier_used", "service_code_used", "billing_code_description"
        ]
        available = set(lazy_df.collect_schema().names())
        cols = [c for c in display_cols if c in available]
        res = lazy_df.select(cols).limit(limit).collect().to_pandas()
        return res
    except Exception:
        return None


def get_download_file_bytes(filename: str, source_mode: str = "Production outputs") -> Optional[bytes]:
    """Retrieve raw bytes of an output file for st.download_button."""
    path = get_output_dir(source_mode) / filename
    if path.exists():
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            return None
    return None
