"""Configuration management for PTD Pipeline.

Loads configuration from config.yaml, environment variables, or CLI overrides.
Ensures zero hardcoded paths across the entire codebase.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class PipelineConfig:
    """Central configuration container resolving paths dynamically via pathlib."""

    def __init__(self, config_dict: Dict[str, Any], project_root: Path):
        self._raw = config_dict
        self.project_root = project_root

        # Resolve paths relative to project_root or respect env vars
        paths_cfg = config_dict.get("paths", {})
        data_root = os.getenv("PTD_DATA_DIR", paths_cfg.get("data_dir", "data"))
        self.data_dir = (self.project_root / data_root).resolve()
        self.raw_dir = (self.project_root / paths_cfg.get("raw_dir", "data/raw")).resolve()
        self.index_dir = (self.project_root / paths_cfg.get("index_dir", "data/index")).resolve()
        self.reference_dir = (self.project_root / paths_cfg.get("reference_dir", "data/reference")).resolve()
        self.interim_dir = (self.project_root / paths_cfg.get("interim_dir", "data/interim")).resolve()
        self.output_dir = (self.project_root / paths_cfg.get("output_dir", "data/output")).resolve()
        self.docs_dir = (self.project_root / paths_cfg.get("docs_dir", "docs")).resolve()
        self.reports_dir = (self.project_root / paths_cfg.get("reports_dir", "data/output/reports")).resolve()

        # Ensure write directories exist
        for d in [self.data_dir, self.raw_dir, self.index_dir, self.reference_dir,
                  self.interim_dir, self.output_dir, self.docs_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.scope = config_dict.get("scope", {})
        self.classifier_cfg = config_dict.get("classifier", {})
        self.rate_extraction_cfg = config_dict.get("rate_extraction", {})
        self.address_linking_cfg = config_dict.get("address_linking", {})
        self.cost_effectiveness_cfg = config_dict.get("cost_effectiveness", {})
        self.parser_cfg = config_dict.get("parser", {})

    @property
    def raw_config(self) -> Dict[str, Any]:
        return self._raw


def find_project_root() -> Path:
    """Traverse up from current file until config.yaml or pyproject/git root is found."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "config.yaml").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def load_config(config_path: Optional[str | Path] = None) -> PipelineConfig:
    """Load configuration from specified path, env var PTD_CONFIG_PATH, or default config.yaml."""
    if config_path:
        cfg_file = Path(config_path).resolve()
        root = cfg_file.parent
    elif "PTD_CONFIG_PATH" in os.environ:
        cfg_file = Path(os.environ["PTD_CONFIG_PATH"]).resolve()
        root = cfg_file.parent
    else:
        root = find_project_root()
        cfg_file = root / "config.yaml"

    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found at {cfg_file}")

    with open(cfg_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return PipelineConfig(data, root)
