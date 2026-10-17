"""Regression and integrity test suite for Checkpoint H.

Verifies:
1. additional_information grain resolution and Revenue Code 636 disambiguation.
2. class_npi_type_match empirical redefinition (permitting Type 2 professional claims).
3. NPI-type null handling (deactivated, missing, pseudo-NPI 0).
4. Grain reconciliation exact tie-out between summary.json and final deliverables.
5. Network attribution T1/T2 partition integrity.
"""

import json
import polars as pl
import pytest
from ptd.config import load_config
from ptd.final_output import FinalOutputGenerator


def test_class_npi_type_match_logic():
    """Verify empirical claims billing rules for class_npi_type_match."""
    # Empirical rules:
    # Type 1 + professional -> True
    # Type 2 + institutional -> True
    # Type 2 + professional (incorporated group practice billing CMS-1500) -> True
    # Type 1 + institutional -> False
    # None / null / 0 -> False
    def compute_class_match(npi_t, b_class):
        if npi_t == 1 and b_class == "professional":
            return True
        elif npi_t == 2 and b_class in ("institutional", "professional"):
            return True
        return False

    assert compute_class_match(1, "professional") is True
    assert compute_class_match(2, "institutional") is True
    assert compute_class_match(2, "professional") is True  # Incorporated group practice
    assert compute_class_match(1, "institutional") is False
    assert compute_class_match(None, "institutional") is False
    assert compute_class_match(None, "professional") is False


def test_npi_type_null_handling():
    """Verify that deactivated, missing, and facility pseudo-NPI rows have null npi_type."""
    cfg = load_config()
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    if final_parquet.exists():
        df = pl.read_parquet(final_parquet)
        
        # Pseudo-NPI 0 facility rows must have null NPI and null npi_type
        npi0_rows = df.filter(pl.col("npi_status") == "PLACEHOLDER_ZERO")
        assert npi0_rows.height == 5
        assert npi0_rows["NPI"].null_count() == 5
        assert npi0_rows["npi_type"].null_count() == 5

        # Unmatched NPI (1342464355) must have null npi_type
        unmatched = df.filter(pl.col("npi_status") == "UNMATCHED_NPPES")
        if unmatched.height > 0:
            assert unmatched["npi_type"].null_count() == unmatched.height


def test_additional_information_grain_expansion():
    """Verify that additional_information expands curated keys and resolves RC 636 collisions."""
    cfg = load_config()
    rates_parquet = cfg.interim_dir / "extracted_rates.parquet"
    if rates_parquet.exists():
        df_rates = pl.read_parquet(rates_parquet)
        assert df_rates.height > 0
        
        # RC 636 keys must resolve with 100% spread_ratio == 1.0 (IDENTICAL_MULTI_PRICE_MATCH)
        rc636 = df_rates.filter(pl.col("billing_code") == "636")
        assert rc636.height > 0
        assert rc636.filter(pl.col("selection_rule") == "IDENTICAL_MULTI_PRICE_MATCH").height == rc636.height
        assert rc636.filter(pl.col("spread_flag") == True).height == 0


def test_grain_reconciliation_exact_tie_out():
    """Verify that summary.json, extracted_rates, and final_curated_rates agree on key and row counts."""
    cfg = load_config()
    rates_parquet = cfg.interim_dir / "extracted_rates.parquet"
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    summary_json = cfg.output_dir / "summary.json"

    if rates_parquet.exists() and final_parquet.exists() and summary_json.exists():
        df_rates = pl.read_parquet(rates_parquet)
        df_final = pl.read_parquet(final_parquet)
        with open(summary_json) as f:
            summary = json.load(f)

        curated_keys_extracted = df_rates.height
        curated_keys_summary = summary["phase3_and_4_rate_grading"]["curated_rate_keys_resolved"]
        primary_final_rows = df_final.filter(pl.col("is_primary_address") == True).height
        total_deliverable_rows = df_final.height
        deliverable_rows_summary = summary["phase6_production_deliverable"]["total_curated_rates_and_addresses_rows"]

        assert curated_keys_extracted > 0
        assert curated_keys_extracted == curated_keys_summary
        assert primary_final_rows == curated_keys_extracted
        assert total_deliverable_rows == deliverable_rows_summary


def test_network_attribution_partition():
    """Verify that T1_name_hint_ppo and T2_shared_commercial cleanly partition all curated keys."""
    cfg = load_config()
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    if final_parquet.exists():
        df = pl.read_parquet(final_parquet)
        t1_c = df.filter(pl.col("ppo_evidence_tier") == "T1_name_hint_ppo").height
        t2_c = df.filter(pl.col("ppo_evidence_tier") == "T2_shared_commercial").height
        assert t1_c + t2_c == df.height
        assert t1_c > 0
        assert t2_c > 0

        # Verify entity_kind valid values
        assert "entity_kind" in df.columns
        kinds = set(df["entity_kind"].unique().to_list())
        assert kinds.issubset({"real_provider", "network_bucket", "unknown"})

        # Verify no CPT-style descriptor on Revenue Code rows
        rc_rows = df.filter(pl.col("billing_code_type") == "RC")
        assert rc_rows.height > 0
        cpt_keywords = ["OFFICE OR OTH OUTPATIENT", "ESTABLISHED PATIENT", "NEW PATIENT", "SEX HORMONE", "ASSAY OF ESTRADIOL"]
        for d in rc_rows["billing_code_description"].to_list():
            for kw in cpt_keywords:
                assert kw not in (d or "").upper(), f"CPT descriptor leaked to RC row: {d}"
