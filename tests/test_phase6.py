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
        "network_label", "ppo_evidence_tier", "network_participation_ppo", "entity_kind",
        "rate_min", "rate_max", "n_source_prices",
        "negotiated_type", "negotiation_arrangement", "rate_basis",
        "rate_reliability", "spread_flag", "outlier_flag", "review_flag",
        "address_rank", "is_primary_address", "status_basis",
        "tin_corroboration_eligible", "specialty_plausible", "class_npi_type_match",
        "address_line1", "address_line2", "city", "state", "zip5",
        "billing_code_description", "raw_item_name", "raw_item_description",
        "modifier_used", "service_code_used"
    ]
    assert FinalOutputGenerator.REQUIRED_COLUMNS == expected_order
    assert len(FinalOutputGenerator.REQUIRED_COLUMNS) == 45



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


def test_problem_statement_grain_uniqueness():
    """Assert that final_rates_ps_grain.csv has 100% unique 4-column keys."""
    cfg = load_config()
    ps_csv = cfg.output_dir / "final_rates_ps_grain.csv"
    if ps_csv.exists():
        df_ps = pl.read_csv(ps_csv)
        assert df_ps.columns == ["NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate"]
        n_unique = df_ps.unique(subset=["NPI", "TIN", "Address", "Billing Code"]).height
        assert n_unique == df_ps.height, f"Found {df_ps.height - n_unique} duplicate 4-column keys!"


def test_revenue_code_descriptions_no_cpt_bleed():
    """Assert that no Revenue Code row carries a CPT-style procedure description."""
    cfg = load_config()
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    if final_parquet.exists():
        df = pl.read_parquet(final_parquet)
        rc_rows = df.filter(pl.col("billing_code_type") == "RC")
        assert rc_rows.height > 0

        # Specifically check RC 300: must be 'Laboratory - General Classification', never 'SEX HORMONE BINDING GLOBULIN'
        rc_300 = rc_rows.filter(pl.col("Billing Code") == "300")
        if rc_300.height > 0:
            for desc in rc_300["billing_code_description"].to_list():
                assert "SEX HORMONE" not in desc
                assert "Laboratory - General Classification" in desc

        # Assert no RC row contains inappropriate CPT bleed
        forbidden_cpt_substrings = ["SEX HORMONE", "COLONOSCOPY, FLEXIBLE", "ASSAY OF ESTRADIOL"]
        for row in rc_rows.iter_rows(named=True):
            desc = row["billing_code_description"]
            for bad in forbidden_cpt_substrings:
                assert bad not in desc, f"RC {row['Billing Code']} contains CPT bleed: {desc}"


def test_network_participation_ppo_unknown():
    """Assert that network_participation_ppo is Unknown for all rows."""
    cfg = load_config()
    final_parquet = cfg.output_dir / "final_curated_rates.parquet"
    if final_parquet.exists():
        df = pl.read_parquet(final_parquet)
        assert (df["network_participation_ppo"] == "Unknown").all()

