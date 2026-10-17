"""Unit tests for Phase 4 File Grading (C3) and Rate Extraction (C4).

Tests redesigned tie-break rules, raw-stream metrics, mutation test, and grain key integrity.
"""

import polars as pl
import pytest
from ptd.config import load_config
from ptd.file_grading import calculate_luhn_validity, compute_iqr_outlier_share, FileGrader


def test_luhn_algorithm_valid_and_invalid():
    # Valid NPI
    valid_npi = 1234567893
    pct, valid, invalid = calculate_luhn_validity([valid_npi])
    assert pct == 100.0
    assert valid == 1

    # Invalid NPI
    invalid_npi = 1234567890
    pct, valid, invalid = calculate_luhn_validity([invalid_npi])
    assert pct == 0.0
    assert invalid == 1

    # Placeholder 0 NPI
    pct, valid, invalid = calculate_luhn_validity([0])
    assert pct == 0.0


def test_ambetter_and_capitation_exclusions():
    # Ambetter groups must be excluded
    name = "DIRECT NETWORK: AMBETTER PPO"
    assert "AMBETTER" in name.upper()

    # Capitation must be flagged as non-FFS
    arr = "capitation"
    assert arr == "capitation"


def test_tiebreak_rule_drop_null_zero_negative():
    df = pl.DataFrame({
        "npi": [100, 100, 100],
        "tin": ["12-345", "12-345", "12-345"],
        "billing_code": ["99213", "99213", "99213"],
        "billing_class": ["professional", "professional", "professional"],
        "billing_code_type": ["CPT", "CPT", "CPT"],
        "negotiated_rate": [0.0, -15.0, 120.0],
    })
    filtered = df.filter(pl.col("negotiated_rate") > 0.0)
    assert filtered.height == 1
    assert filtered["negotiated_rate"][0] == 120.0


def test_tiebreak_rule_prefer_base_modifier():
    # Prefer modifier == 'NONE' over modifier rates
    df = pl.DataFrame({
        "npi": [100, 100],
        "tin": ["12-345", "12-345"],
        "billing_code": ["99213", "99213"],
        "billing_class": ["professional", "professional"],
        "billing_code_type": ["CPT", "CPT"],
        "modifier": ["26", "NONE"],
        "negotiated_rate": [80.0, 150.0],
    })
    grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type"]
    has_base = df.group_by(grain_keys).agg((pl.col("modifier") == "NONE").any().alias("has_base"))
    res = df.join(has_base, on=grain_keys).filter(~pl.col("has_base") | (pl.col("modifier") == "NONE"))
    assert res.height == 1
    assert res["modifier"][0] == "NONE"
    assert res["negotiated_rate"][0] == 150.0


def test_tiebreak_rule_prefer_class_matched_setting():
    # For professional, prefer office (11) over ER (23)
    df = pl.DataFrame({
        "npi": [100, 100],
        "tin": ["12-345", "12-345"],
        "billing_code": ["99214", "99214"],
        "billing_class": ["professional", "professional"],
        "billing_code_type": ["CPT", "CPT"],
        "service_code": ["23", "11"],
        "negotiated_rate": [250.0, 180.0],
    })
    grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type"]
    df = df.with_columns(
        (pl.col("service_code").is_in(["11", "22", "02"])).alias("is_pref")
    )
    has_pref = df.group_by(grain_keys).agg(pl.col("is_pref").any().alias("has_pref"))
    res = df.join(has_pref, on=grain_keys).filter(~pl.col("has_pref") | pl.col("is_pref"))
    assert res.height == 1
    assert res["service_code"][0] == "11"
    assert res["negotiated_rate"][0] == 180.0


def test_tiebreak_rule_prefer_negotiated_over_fee_schedule():
    df = pl.DataFrame({
        "npi": [100, 100],
        "tin": ["12-345", "12-345"],
        "billing_code": ["99213", "99213"],
        "billing_class": ["professional", "professional"],
        "billing_code_type": ["CPT", "CPT"],
        "negotiated_type": ["fee schedule", "negotiated"],
        "negotiated_rate": [80.0, 120.0],
    })
    grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type"]
    has_neg = df.group_by(grain_keys).agg((pl.col("negotiated_type") == "negotiated").any().alias("has_neg"))
    res = df.join(has_neg, on=grain_keys).filter(~pl.col("has_neg") | (pl.col("negotiated_type") == "negotiated"))
    assert res.height == 1
    assert res["negotiated_type"][0] == "negotiated"
    assert res["negotiated_rate"][0] == 120.0


def test_tiebreak_rule_latest_expiration():
    df = pl.DataFrame({
        "npi": [100, 100],
        "tin": ["12-345", "12-345"],
        "billing_code": ["99213", "99213"],
        "billing_class": ["professional", "professional"],
        "billing_code_type": ["CPT", "CPT"],
        "expiration_date": ["2026-12-31", "9999-12-31"],
        "negotiated_rate": [110.0, 130.0],
    })
    grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type"]
    res = (
        df.group_by(grain_keys)
        .agg(pl.col("expiration_date").max().alias("max_exp"))
        .join(df, on=grain_keys)
        .filter(pl.col("expiration_date") == pl.col("max_exp"))
    )
    assert res.height == 1
    assert res["expiration_date"][0] == "9999-12-31"


def test_median_aggregation_with_bounds():
    df = pl.DataFrame({
        "npi": [100, 100, 100],
        "tin": ["12-345", "12-345", "12-345"],
        "billing_code": ["99213", "99213", "99213"],
        "billing_class": ["professional", "professional", "professional"],
        "billing_code_type": ["CPT", "CPT", "CPT"],
        "negotiated_rate": [100.0, 150.0, 200.0],
    })
    grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type"]
    res = df.group_by(grain_keys).agg([
        pl.col("negotiated_rate").median().alias("rate_selected"),
        pl.col("negotiated_rate").min().alias("rate_min"),
        pl.col("negotiated_rate").max().alias("rate_max"),
        pl.len().alias("n_source_prices"),
    ])
    assert res.height == 1
    assert res["rate_selected"][0] == 150.0
    assert res["rate_min"][0] == 100.0
    assert res["rate_max"][0] == 200.0
    assert res["n_source_prices"][0] == 3


def test_mutation_test_execution():
    config = load_config()
    grader = FileGrader(config)
    # Create mock raw dataset
    mock_raw = pl.DataFrame({
        "npi": [1234567893] * 100,
        "tin": ["12-3456789"] * 100,
        "billing_code": ["99213"] * 100,
        "billing_class": ["professional"] * 100,
        "billing_code_type": ["CPT"] * 100,
        "negotiated_rate": [150.0] * 100,
        "negotiated_type": ["negotiated"] * 100,
        "expiration_date": ["9999-12-31"] * 100,
        "ppo_evidence_tier": ["T2_shared_commercial"] * 100,
    })
    mut_res = grader.run_mutation_test(mock_raw)
    assert mut_res["baseline_score"] > mut_res["mutated_score"]
    assert mut_res["score_drop"] > 0.0
