"""Tests for DataLocator module in PTD Pipeline.

Verifies:
1. Priority order (Env var > config.local.yaml > default project directories).
2. Glob pattern resolution and newest-date selection.
3. Helpful error message naming searched places on missing inputs.
4. Safety invariant: Refusal of pointers resolving inside data/interim/ or data/output/.
5. Transparent .json.gz decompression and strict read-only mode enforcement.
6. Read-only source files guarantee: chmod 444 files run without errors and mtime/checksum remain unchanged.
"""

import gzip
import hashlib
import json
import os
import stat
import time
from pathlib import Path
import pytest
import yaml

from ptd.data_locator import DataLocator, InputNotFoundError, extract_date_from_filename


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_extract_date_from_filename():
    d1 = extract_date_from_filename("2026-09-30_centene_healthnet-ca_in-network.json")
    assert d1 is not None
    assert d1.year == 2026 and d1.month == 9 and d1.day == 30

    d2 = extract_date_from_filename("2026_10_01_rate.json.gz")
    assert d2 is not None
    assert d2.year == 2026 and d2.month == 10 and d2.day == 1

    d3 = extract_date_from_filename("no_date_file.csv")
    assert d3 is None


def test_priority_order_env_overrides_local_and_default(tmp_path, monkeypatch):
    """Test: Env Var > config.local.yaml > default directory."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "data" / "raw").mkdir(parents=True)
    (project_root / "external_env").mkdir(parents=True)
    (project_root / "external_local").mkdir(parents=True)

    # 1. Default file
    default_file = project_root / "data" / "raw" / "2026-09-01_healthnet-ca_in-network.json"
    default_file.write_text('{"source": "default"}')

    # 2. config.local.yaml file
    local_file = project_root / "external_local" / "local_rate.json"
    local_file.write_text('{"source": "local"}')
    local_cfg = {
        "pointers": {
            "healthnet_ca_rate_file": str(local_file)
        }
    }
    with open(project_root / "config.local.yaml", "w") as f:
        yaml.safe_dump(local_cfg, f)

    # 3. Env var file
    env_file = project_root / "external_env" / "env_rate.json"
    env_file.write_text('{"source": "env"}')

    # Case A: Env var is set -> should resolve to env_file
    monkeypatch.setenv("PTD_RATE_FILE_CA", str(env_file))
    locator = DataLocator(project_root=project_root)
    res_path = locator.get_path("healthnet_ca_rate_file")
    assert res_path.resolve() == env_file.resolve()

    # Case B: Env var unset -> should resolve to config.local.yaml
    monkeypatch.delenv("PTD_RATE_FILE_CA", raising=False)
    locator = DataLocator(project_root=project_root)
    res_path = locator.get_path("healthnet_ca_rate_file")
    assert res_path.resolve() == local_file.resolve()

    # Case C: config.local.yaml removed -> should fall back to default data/raw
    (project_root / "config.local.yaml").unlink()
    locator = DataLocator(project_root=project_root)
    res_path = locator.get_path("healthnet_ca_rate_file")
    assert res_path.resolve() == default_file.resolve()


def test_glob_pattern_resolution_and_newest_date(tmp_path):
    """Test glob resolution selects the newest file by date in filename."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)

    f_old = raw_dir / "2026-07-15_centene_healthnet-ca_in-network.json"
    f_mid = raw_dir / "2026-08-30_centene_healthnet-ca_in-network.json"
    f_new = raw_dir / "2026-09-30_centene_healthnet-ca_in-network.json"

    f_old.write_text("{}")
    f_mid.write_text("{}")
    f_new.write_text("{}")

    locator = DataLocator(project_root=tmp_path)
    chosen = locator.get_path("healthnet_ca_rate_file")
    assert chosen.name == "2026-09-30_centene_healthnet-ca_in-network.json"

    res_info = locator._resolved_cache.get("healthnet_ca_rate_file")
    assert res_info is not None
    assert len(res_info.alternatives) == 2


def test_missing_input_raises_helpful_error(tmp_path):
    """Test that missing required input raises InputNotFoundError with clear pointer instructions."""
    empty_root = tmp_path / "empty_proj"
    empty_root.mkdir()

    locator = DataLocator(project_root=empty_root)
    with pytest.raises(InputNotFoundError) as exc_info:
        locator.get_path("healthnet_ca_rate_file", required=True)

    msg = str(exc_info.value)
    assert "healthnet_ca_rate_file" in msg
    assert "PTD_RATE_FILE_CA" in msg
    assert "config.local.yaml" in msg
    assert "Searched locations:" in msg


def test_safety_refuses_pointer_inside_interim_or_output(tmp_path, monkeypatch):
    """Test safety invariant: pointers inside data/interim/ or data/output/ are rejected."""
    project_root = tmp_path / "project"
    interim_dir = project_root / "data" / "interim"
    output_dir = project_root / "data" / "output"
    interim_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    bad_interim_file = interim_dir / "bad_input.json"
    bad_interim_file.write_text("{}")

    bad_output_file = output_dir / "bad_input.json"
    bad_output_file.write_text("{}")

    # Inside interim
    monkeypatch.setenv("PTD_RATE_FILE_CA", str(bad_interim_file))
    locator = DataLocator(project_root=project_root)
    with pytest.raises(ValueError) as exc_info:
        locator.get_path("healthnet_ca_rate_file")
    assert "Safety Violation" in str(exc_info.value)

    # Inside output
    monkeypatch.setenv("PTD_RATE_FILE_CA", str(bad_output_file))
    locator = DataLocator(project_root=project_root)
    with pytest.raises(ValueError) as exc_info:
        locator.get_path("healthnet_ca_rate_file")
    assert "Safety Violation" in str(exc_info.value)


def test_json_gz_transparent_decompression(tmp_path):
    """Test that open_readonly seamlessly reads .json.gz files and rejects write modes."""
    gz_file = tmp_path / "test_rate.json.gz"
    payload = {"status": "ok", "count": 42}
    with gzip.open(gz_file, "wt", encoding="utf-8") as gf:
        json.dump(payload, gf)

    locator = DataLocator(project_root=tmp_path)
    # Read mode succeeds
    with locator.open_readonly(gz_file, "rb") as f:
        data = json.load(f)
    assert data["status"] == "ok"
    assert data["count"] == 42

    # Write mode raises invariant error
    with pytest.raises(ValueError) as exc_info:
        locator.open_readonly(gz_file, "wb")
    assert "Read-Only Invariant Violation" in str(exc_info.value)


def test_readonly_source_files_guarantee(tmp_path):
    """Test that read-only files (chmod 444) are successfully read without modification."""
    source_file = tmp_path / "2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"
    source_file.write_text('{"records": [1, 2, 3]}')

    # Compute initial hash and mtime
    init_sha = compute_sha256(source_file)
    init_stat = source_file.stat()
    init_mtime = init_stat.st_mtime

    # Set file permission to strict read-only (chmod 444)
    source_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    (tmp_path / "data" / "raw").mkdir(parents=True)
    symlink_file = tmp_path / "data" / "raw" / source_file.name
    symlink_file.symlink_to(source_file)

    locator = DataLocator(project_root=tmp_path)
    resolved = locator.get_path("healthnet_ca_rate_file")
    assert resolved == symlink_file

    # Read through locator
    with locator.open_readonly(resolved, "rb") as f:
        content = f.read()
        assert b'"records": [1, 2, 3]' in content

    # Verify post-read invariant: mtime and sha256 are unchanged
    post_stat = source_file.stat()
    post_sha = compute_sha256(source_file)

    assert post_stat.st_mtime == init_mtime
    assert post_sha == init_sha
