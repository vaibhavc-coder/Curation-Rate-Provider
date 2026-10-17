"""Unit tests for Phase 6: Final Curated Rate File Generation (Challenge C6)."""

import polars as pl
import pytest
from ptd.config import load_config
from ptd.final_output import FinalOutputGenerator


def test_required_column_ordering():
    expected_order = [
        "NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate",
        "address_confidence", "address_status", "source_file", "file_quality_score",
        "billing_code_type", "billing_class", "npi_type", "npi_status", "tin_canonical_name",
        "ppo_evidence_tier", "rate_min", "rate_max", "n_source_prices", "rate_reliability",
        "spread_flag", "review_flag", "address_rank", "is_primary_address", "status_basis",
        "specialty_plausible", "class_npi_type_match"
    ]
    assert FinalOutputGenerator.REQUIRED_COLUMNS == expected_order
    assert len(FinalOutputGenerator.REQUIRED_COLUMNS) == 27


def test_format_address_string_handling():
    cfg = load_config()
    gen = FinalOutputGenerator(cfg)

    # Valid full address
    addr1 = gen.format_address_string("1555 Soquel Dr", "Suite 100", "Santa Cruz", "CA", "95065")
    assert addr1 == "1555 Soquel Dr, Suite 100, Santa Cruz, CA 95065"

    # Valid address without line2
    addr2 = gen.format_address_string("1200 Pecan St", "", "Washington", "DC", "20001")
    assert addr2 == "1200 Pecan St, Washington, DC 20001"

    # Unverified / Unlinked address -> NO_ADDRESS
    addr3 = gen.format_address_string("Address Unverified", "", "CA", "CA", "00000")
    assert addr3 == "NO_ADDRESS"

    # Missing line1 -> NO_ADDRESS
    addr4 = gen.format_address_string(None, "", "Sacramento", "CA", "95814")
    assert addr4 == "NO_ADDRESS"


def test_excel_sheet_split_and_headroom():
    cfg = load_config()
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    if final_parquet.exists():
        df = pl.read_parquet(final_parquet)
        total_rows = df.height
        excel_limit = 1048576
        assert total_rows < excel_limit
        headroom = (excel_limit - total_rows) / excel_limit
        assert headroom > 0.90  # >90% headroom on single sheet


def test_exactly_one_primary_address_per_npi_tin():
    cfg = load_config()
    links_parquet = cfg.interim_dir / "npi_tin_address_links.parquet"
    if links_parquet.exists():
        df_links = pl.read_parquet(links_parquet)
        prim_df = df_links.filter(pl.col("is_primary_address"))
        # Group by (npi, tin) and verify count is exactly 1
        prim_counts = prim_df.group_by(["npi", "tin"]).len()
        assert prim_counts["len"].max() == 1
        assert prim_counts["len"].min() == 1
