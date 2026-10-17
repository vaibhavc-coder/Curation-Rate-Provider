"""Unit tests for streaming rate file profiler and DuckDB indexing."""

import json
from pathlib import Path
import duckdb
import pytest
from ptd.config import load_config
from ptd.rate_stream import RateStreamProfiler


@pytest.fixture
def sample_rate_json(tmp_path) -> Path:
    """Create a minimal mock rate JSON following TiC v2.0.0 schema."""
    data = {
        "reporting_entity_name": "Health Net of California",
        "reporting_entity_type": "health insurance issuer",
        "version": "2.0.0",
        "last_updated_on": "2026-09-30",
        "provider_references": [
            {
                "provider_group_id": 101,
                "network_name": [],
                "provider_groups": [
                    {
                        "npi": [1234567890, 1987654321],
                        "tin": {
                            "type": "ein",
                            "value": "95-1234567",
                            "business_name": "California Medical Group"
                        }
                    }
                ]
            }
        ],
        "in_network": [
            {
                "negotiation_arrangement": "ffs",
                "name": "OFFICE VISIT EST PATIENT",
                "billing_code_type": "CPT",
                "billing_code_type_version": "2026",
                "billing_code": "99213",
                "description": "Office visit 20-29 mins",
                "negotiated_rates": [
                    {
                        "provider_references": [101],
                        "negotiated_prices": [
                            {
                                "negotiated_type": "negotiated",
                                "negotiated_rate": 145.50,
                                "expiration_date": "9999-12-31",
                                "service_code": ["11"],
                                "billing_class": "professional",
                                "setting": "outpatient"
                            }
                        ]
                    }
                ]
            }
        ]
    }
    file_path = tmp_path / "mock_rate_file.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return file_path


def test_provider_references_indexing(tmp_path, sample_rate_json):
    config = load_config()
    profiler = RateStreamProfiler(config)
    profiler.duckdb_path = tmp_path / "test_refs.duckdb"
    profiler.interim_dir = tmp_path

    res = profiler.index_provider_references(sample_rate_json)
    assert res["total_references"] == 1
    assert res["unique_tins"] == 1
    assert res["npi_stats"]["max"] == 2
    assert res["tin_types_distribution"]["ein"] == 1

    # Verify queryable in DuckDB
    con = duckdb.connect(str(profiler.duckdb_path))
    row = con.execute("SELECT provider_group_id, tin_value, npis FROM provider_references").fetchone()
    assert row[0] == 101
    assert row[1] == "95-1234567"
    assert len(row[2]) == 2
    con.close()


def test_in_network_profiling(tmp_path, sample_rate_json):
    config = load_config()
    profiler = RateStreamProfiler(config)
    res = profiler.profile_in_network(sample_rate_json, sample_n=5)

    assert res["total_in_network_items"] == 1
    assert res["unique_billing_codes"] == 1
    assert res["billing_code_types"]["CPT"] == 1
    assert res["negotiation_arrangements"]["ffs"] == 1
    assert res["negotiated_types"]["negotiated"] == 1
    assert res["billing_classes"]["professional"] == 1
    assert res["zero_or_negative_rates"] == 0
    assert res["rate_stats"]["median"] == 145.50
