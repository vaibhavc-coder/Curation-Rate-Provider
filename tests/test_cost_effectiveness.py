"""Unit tests for Cost-Effectiveness Provider Frontier."""

import polars as pl
import pytest
from ptd.config import PipelineConfig
from ptd.cost_effectiveness import CostEffectivenessAnalyzer, map_zip5_to_region


def test_map_zip5_to_region():
    assert map_zip5_to_region("90210") == "LOS_ANGELES_METRO"
    assert map_zip5_to_region("92101") == "SAN_DIEGO_METRO"
    assert map_zip5_to_region("94102") == "SAN_FRANCISCO_PENINSULA"
    assert map_zip5_to_region("95814") == "SACRAMENTO_NORTH_CA"
    assert map_zip5_to_region(None) == "UNKNOWN_REGION"


def test_cost_effectiveness_peer_grouping_and_fallback(tmp_path):
    cfg = PipelineConfig({
        "paths": {
            "output_dir": "data/output",
            "reference_dir": "data/reference",
            "interim_dir": "data/interim",
            "docs_dir": "docs",
        }
    }, tmp_path)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.reference_dir.mkdir(parents=True, exist_ok=True)

    # Create synthetic test dataset:
    # 12 providers in LA with Code 99213, Professional, Type 1, Primary Care
    rows = []
    for i in range(12):
        rows.append({
            "NPI": 1000000000 + i,
            "TIN": f"95-{i:07d}",
            "Billing Code": "99213",
            "billing_class": "professional",
            "npi_type": 1,
            "Specialty": "Primary Care",
            "zip5": "90210",  # LA Metro
            "Rate": 100.0 + i * 10.0,
            "rate_reliability": "HIGH",
            "review_flag": "STANDARD",
        })

    # Add 1 provider with a unique code (should mark INSUFFICIENT_PEERS)
    rows.append({
        "NPI": 1000000099,
        "TIN": "95-9999999",
        "Billing Code": "99999",
        "billing_class": "professional",
        "npi_type": 1,
        "Specialty": "Primary Care",
        "zip5": "90210",
        "Rate": 500.0,
        "rate_reliability": "HIGH",
        "review_flag": "STANDARD",
    })

    # Add 1 provider with LOW reliability (should still be scored, but excluded from peer baseline)
    rows.append({
        "NPI": 1000000100,
        "TIN": "95-8888888",
        "Billing Code": "99213",
        "billing_class": "professional",
        "npi_type": 1,
        "Specialty": "Primary Care",
        "zip5": "90210",
        "Rate": 1000.0,
        "rate_reliability": "LOW",
        "review_flag": "STANDARD",
    })

    df = pl.DataFrame(rows)
    analyzer = CostEffectivenessAnalyzer(cfg, min_peers=10, min_codes_for_provider_index=1)
    res = analyzer.run_analysis(df)

    df_scored = res["df_scored"]
    assert df_scored.height == 14

    # The 12 standard providers should have REGIONAL peer_level
    p1 = df_scored.filter(pl.col("NPI") == 1000000000).to_dicts()[0]
    assert p1["peer_level"] == "REGIONAL"
    assert p1["peer_count"] == 12
    assert p1["is_scoreable"] is True
    assert p1["rate_to_peer_median"] is not None
    assert p1["mad_robust_zscore"] is not None

    # The unique code should be INSUFFICIENT_PEERS
    p_uniq = df_scored.filter(pl.col("NPI") == 1000000099).to_dicts()[0]
    assert p_uniq["peer_level"] == "INSUFFICIENT_PEERS"
    assert p_uniq["is_scoreable"] is False

    # The LOW reliability provider should be scored
    p_low = df_scored.filter(pl.col("NPI") == 1000000100).to_dicts()[0]
    assert p_low["is_scoreable"] is True
    assert p_low["peer_count"] == 12  # Peer count did not include this LOW row
    assert p_low["rate_to_peer_median"] > 1.0  # $1000 vs median ~$155
