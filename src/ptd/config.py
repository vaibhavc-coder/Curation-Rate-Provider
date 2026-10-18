"""Configuration management for PTD Pipeline.

Loads configuration from config.yaml, environment variables, config.local.yaml,
or CLI overrides. Ensures zero hardcoded paths across the entire codebase.
Integrates DataLocator for non-invasive, read-only pointer resolution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from ptd.data_locator import DataLocator, get_locator


class PipelineConfig:
    """Central configuration container resolving paths dynamically via pathlib and DataLocator."""

    def __init__(self, config_dict: Dict[str, Any], project_root: Path, use_fixtures: bool = False):
        self._raw = config_dict
        self.project_root = project_root
        self.use_fixtures = use_fixtures or config_dict.get("use_fixtures", False)

        # Initialize non-invasive DataLocator
        self.locator = DataLocator(
            project_root=self.project_root,
            config=self._raw,
            use_fixtures=self.use_fixtures,
        )

        # Output and working directory resolution
        paths_cfg = config_dict.get("paths", {})
        data_root = os.getenv("PTD_DATA_DIR", paths_cfg.get("data_dir", "data"))
        self.data_dir = (self.project_root / data_root).resolve()
        self.interim_dir = (self.project_root / paths_cfg.get("interim_dir", "data/interim")).resolve()
        self.output_dir = (self.project_root / paths_cfg.get("output_dir", "data/output")).resolve()
        self.docs_dir = (self.project_root / paths_cfg.get("docs_dir", "docs")).resolve()
        self.reports_dir = (self.project_root / paths_cfg.get("reports_dir", "data/output/reports")).resolve()

        # Backward compatibility properties for directory references
        self.raw_dir = (self.project_root / paths_cfg.get("raw_dir", "data/raw")).resolve()
        self.index_dir = (self.project_root / paths_cfg.get("index_dir", "data/index")).resolve()
        self.reference_dir = (self.project_root / paths_cfg.get("reference_dir", "data/reference")).resolve()

        # Read-Only Guarantee: Ensure ONLY writable project directories exist
        for d in [self.interim_dir, self.output_dir, self.docs_dir, self.reports_dir]:
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

    # Dynamic logical dataset pointer properties
    @property
    def healthnet_ca_rate_file(self) -> Path:
        return self.locator.get_path("healthnet_ca_rate_file", required=True)

    @property
    def healthnet_or_rate_file(self) -> Optional[Path]:
        return self.locator.get_path("healthnet_or_rate_file", required=False)

    @property
    def nppes_zip(self) -> Path:
        return self.locator.get_path("nppes_zip", required=True)

    @property
    def nucc_taxonomy(self) -> Path:
        return self.locator.get_path("nucc_taxonomy", required=True)

    @property
    def cms_dac(self) -> Optional[Path]:
        return self.locator.get_path("cms_dac", required=False)

    @property
    def hospital_general_info(self) -> Optional[Path]:
        return self.locator.get_path("hospital_general_info", required=False)

    @property
    def hilabs_workbook(self) -> Optional[Path]:
        return self.locator.get_path("hilabs_workbook", required=False)

    @property
    def index_files(self) -> List[Path]:
        return self.locator.get_index_files()


def find_project_root() -> Path:
    """Traverse up from current file until config.yaml or pyproject/git root is found."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "config.yaml").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def load_config(config_path: Optional[str | Path] = None, use_fixtures: bool = False) -> PipelineConfig:
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

    return PipelineConfig(data, root, use_fixtures=use_fixtures)
