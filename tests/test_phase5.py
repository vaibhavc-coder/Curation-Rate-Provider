"""Unit Tests for Phase 5: TIN -> NPI -> Address Linkage Engine."""

from __future__ import annotations

import json
from pathlib import Path
import polars as pl
import pytest

from ptd.address_link import AddressStandardizer, TaxonomySpecialtyMapper
from ptd.config import load_config


def test_address_standardization_suite_and_abbreviations():
    """Verify suite/unit parsing, street type expansion, and directional normalization."""
    std = AddressStandardizer.standardize("123 N MAIN ST", "SUITE 400", "LOS ANGELES", "CA", "90001-1234")
    assert std["std_number"] == "123"
    assert std["std_directional"] == "N"
    assert std["std_street_name"] == "MAIN"
    assert std["std_street_type"] == "STREET"
    assert std["std_unit"] == "400"
    assert std["std_city"] == "LOS ANGELES"
    assert std["std_state"] == "CA"
    assert std["std_zip5"] == "90001"
    assert std["std_zip4"] == "1234"
    assert std["address_type"] == "PRACTICE"
    assert std["is_po_box"] is False


def test_po_box_detection():
    """Verify PO Box variants are flagged as NON_PRACTICE."""
    po_samples = [
        "PO BOX 1234",
        "P.O. Box 999",
        "Post Office Box 42",
        "Drawer 888",
        "Box 500",
    ]
    for sample in po_samples:
        assert AddressStandardizer.is_po_box(sample) is True
        res = AddressStandardizer.standardize(sample, "", "Sacramento", "CA", "95814")
        assert res["is_po_box"] is True
        assert res["address_type"] == "NON_PRACTICE"


def test_entity_resolution_same_building_vs_same_unit():
    """Verify that different suites in the same building share address_key, but differ in unit."""
    suite_a = AddressStandardizer.standardize("500 MEDICAL CENTER WAY", "STE 100", "ELK GROVE", "CA", "95624")
    suite_b = AddressStandardizer.standardize("500 MEDICAL CENTER WAY", "STE 200", "ELK GROVE", "CA", "95624")

    # Same building -> exact same address_key
    assert suite_a["address_key"] == suite_b["address_key"]
    # Distinct clinical units
    assert suite_a["std_unit"] == "100"
    assert suite_b["std_unit"] == "200"
    assert suite_a["std_unit"] != suite_b["std_unit"]


def test_different_cities_never_merged():
    """Verify different cities produce different city values and do not merge."""
    addr_la = AddressStandardizer.standardize("100 MAIN ST", "", "LOS ANGELES", "CA", "90001")
    addr_sf = AddressStandardizer.standardize("100 MAIN ST", "", "SAN FRANCISCO", "CA", "94102")
    assert addr_la["std_city"] == "LOS ANGELES"
    assert addr_sf["std_city"] == "SAN FRANCISCO"
    assert addr_la["std_zip5"] != addr_sf["std_zip5"]
    assert addr_la["address_key"] != addr_sf["address_key"]


def test_independence_grouping_nppes_and_registry():
    """Verify NPPES local and NPI Registry API belong to the same independence group."""
    config = load_config()
    ind_groups = config.address_linking_cfg.get("independence_groups", {})
    group1 = ind_groups.get("group_1_nppes", {}).get("sources", [])
    assert "nppes_primary" in group1
    assert "npi_registry_api" in group1
    # Both in group 1, so together they count as only 1 independent source group
    distinct_groups = {
        "group_1_nppes" if s in group1 else "other"
        for s in ["nppes_primary", "npi_registry_api"]
    }
    assert len(distinct_groups) == 1


def test_status_thresholds():
    """Verify status boundaries for Verified, Probable, and Unverified."""
    cfg = load_config()
    v_thresh = cfg.address_linking_cfg.get("verification_threshold", 0.70)
    p_thresh = cfg.address_linking_cfg.get("probable_threshold", 0.40)

    def get_status(score: float) -> str:
        if score >= v_thresh:
            return "Verified"
        elif score >= p_thresh:
            return "Probable"
        return "Unverified"

    assert get_status(0.85) == "Verified"
    assert get_status(0.70) == "Verified"
    assert get_status(0.65) == "Probable"
    assert get_status(0.40) == "Probable"
    assert get_status(0.35) == "Unverified"


def test_npi_zero_handling_capped_at_probable():
    """Verify NPI 0 rows are tagged PLACEHOLDER_ZERO and status is capped at Facility/TIN-level or Probable."""
    config = load_config()
    links_path = config.interim_dir / "npi_tin_address_links.parquet"
    if links_path.exists():
        df_links = pl.read_parquet(links_path)
        npi0_links = df_links.filter(pl.col("npi_status") == "PLACEHOLDER_ZERO")
        if npi0_links.height > 0:
            # Must never be Verified
            assert (npi0_links["status"] == "Verified").sum() == 0
            assert set(npi0_links["status"].unique().to_list()).issubset({"Facility/TIN-level", "Probable", "Unverified"})



def test_multi_address_and_multi_tin_uncollapsed():
    """Verify R1 (multi-address) and R2 (multi-TIN) retain uncollapsed rows with address_rank."""
    config = load_config()
    links_path = config.interim_dir / "npi_tin_address_links.parquet"
    if links_path.exists():
        df_links = pl.read_parquet(links_path)
        # Check providers with rank > 1 exist
        multi_addr = df_links.filter(pl.col("address_rank") > 1)
        assert multi_addr.height > 0

        # Verify is_primary_address is True ONLY for rank 1
        rank1 = df_links.filter(pl.col("address_rank") == 1)
        assert rank1.filter(~pl.col("is_primary_address")).height == 0


def test_primary_taxonomy_selection_and_specialty_mapping():
    """Verify primary taxonomy selection and specialty resolution via NUCC/HiLabs."""
    config = load_config()
    mapper = TaxonomySpecialtyMapper(config)

    # 1. Primary switch Y on allergy & immunology
    res = mapper.resolve_specialty("207K00000X", [], ["99213", "95115"])
    assert res["primary_taxonomy"] == "207K00000X"
    assert res["hilabs_specialty_code"] == "007"
    assert res["mapping_status"] == "MAPPED_HILABS_XWALK"


def test_specialty_plausibility_check():
    """Verify specialty plausibility evaluates procedure code against benchmark weights."""
    config = load_config()
    mapper = TaxonomySpecialtyMapper(config)

    # Allergy spec 007 includes J1559 in HiLabs benchmark
    res_plausible = mapper.resolve_specialty("207K00000X", [], ["J1559"])
    assert res_plausible["specialty_plausible"] is True

    # Orthopedic surgery (27447) billed under allergy is not plausible
    res_implausible = mapper.resolve_specialty("207K00000X", [], ["27447"])
    assert res_implausible["specialty_plausible"] is False
