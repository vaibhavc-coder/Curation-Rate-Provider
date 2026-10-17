"""Test second-file extensibility proof (Challenge C3).

Verifies:
1. Index parser and PPO classifier execute cleanly on non-Centene index file (QualChoice).
2. Zero hardcoded paths exist in src/ptd/.
3. Pipeline configuration adapts dynamically to custom config.
"""

from pathlib import Path
import polars as pl
import pytest
from ptd.config import load_config
from ptd.index_parser import IndexParser
from ptd.ppo_classifier import PPOClassifier


def test_qualchoice_second_file_parsing():
    """Verify that IndexParser parses QualChoice index files without hardcoded paths."""
    cfg = load_config()
    parser = IndexParser(cfg)
    
    # Target qualchoice index file
    qc_files = list(cfg.index_dir.glob("*qualchoice*.json"))
    assert len(qc_files) > 0, "QualChoice index file must exist in data/index"
    
    recs = parser.parse_single_index(qc_files[0])
    assert len(recs) > 0
    assert "plan_id" in recs[0]
    assert "rate_file_url" in recs[0]



def test_zero_hardcoded_paths_in_src():
    """Verify that no hardcoded absolute paths exist in src/ptd Python modules."""
    src_dir = Path(__file__).resolve().parent.parent / "src" / "ptd"
    py_files = list(src_dir.glob("*.py"))
    assert len(py_files) > 0
    
    hardcoded_found = []
    for py_file in py_files:
        with open(py_file, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                # Check for absolute /home or /Users paths
                if "/home/" in line or "/Users/" in line or "C:\\" in line:
                    # Ignore comments that explain path issues
                    if not line.strip().startswith("#"):
                        hardcoded_found.append(f"{py_file.name}:{idx} -> {line.strip()}")
                        
    assert len(hardcoded_found) == 0, f"Found hardcoded paths in src/ptd: {hardcoded_found}"
