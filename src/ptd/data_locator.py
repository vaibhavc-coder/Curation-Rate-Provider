"""Data Locator module for PTD Pipeline.

Resolves non-invasive, read-only pointers to source datasets without copying,
moving, renaming, or modifying original files.

Resolution Priority:
1. Environment variables (PTD_RATE_FILE_CA, PTD_NPPES_ZIP, PTD_DATA_ROOT, etc.)
2. config.local.yaml (gitignored local machine configuration)
3. Default project directories / config.yaml
4. Test fixtures fallback (when --fixtures is explicitly enabled)

Guarantees:
- Read-only access: Files are opened strictly in read-only binary mode.
- Invariant safety: Refuses pointers resolving inside data/interim/ or data/output/.
- Glob support: Resolves date-stamped filenames (e.g. *healthnet-ca*in-network*.json), choosing the newest.
- Format transparency: Streams .json and .json.gz seamlessly without extraction.
- Controlled remote streaming: Optional https:// URL streaming into data/interim/remote_cache only if allow_remote=True.
"""

from __future__ import annotations

import datetime
import gzip
import logging
import os
from pathlib import Path
import re
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union
import yaml

logger = logging.getLogger("ptd.data_locator")

# Environment variable map for logical dataset inputs
ENV_VAR_MAP = {
    "healthnet_ca_rate_file": ["PTD_RATE_FILE_CA", "PTD_RATE_FILE", "PTD_HEALTHNET_CA_RATE_FILE"],
    "healthnet_or_rate_file": ["PTD_RATE_FILE_OR", "PTD_HEALTHNET_OR_RATE_FILE"],
    "index_files": ["PTD_INDEX_FILES", "PTD_INDEX_DIR"],
    "nppes_zip": ["PTD_NPPES_ZIP"],
    "nucc_taxonomy": ["PTD_NUCC_TAXONOMY", "PTD_NUCC_CSV"],
    "cms_dac": ["PTD_CMS_DAC", "PTD_CMS_DAC_PARQUET"],
    "hospital_general_info": ["PTD_HOSPITAL_INFO", "PTD_HOSPITAL_GENERAL_INFO"],
    "hilabs_workbook": ["PTD_HILABS_WORKBOOK", "PTD_HILABS_BENCHMARK_WORKBOOK"],
}

# Default search patterns relative to data/
DEFAULT_SEARCH_PATTERNS = {
    "healthnet_ca_rate_file": [
        "raw/*healthnet-ca*in-network*.json*",
        "raw/*healthnet-ca*.json*",
        "raw/*in-network*.json*",
        "*healthnet-ca*in-network*.json*",
    ],
    "healthnet_or_rate_file": [
        "raw/*healthnet-or*in-network*.json*",
        "raw/*healthnet-or*.json*",
    ],
    "index_files": [
        "index/*index*.json*",
        "index/*.json*",
    ],
    "nppes_zip": [
        "reference/*NPPES*.zip",
        "reference/*nppes*.zip",
        "*NPPES*.zip",
    ],
    "nucc_taxonomy": [
        "reference/nucc_taxonomy.csv",
        "reference/*nucc*.csv",
        "*nucc*.csv",
    ],
    "cms_dac": [
        "reference/cms_dac_target_npis.parquet",
        "reference/*cms_dac*.parquet",
        "reference/*dac*.parquet",
    ],
    "hospital_general_info": [
        "reference/hospital_general_information.csv",
        "reference/*hospital*.csv",
    ],
    "hilabs_workbook": [
        "reference/Rate_Benchmarking_Individual_Weights_Hackathon.xlsx",
        "reference/*Rate_Benchmarking*.xlsx",
        "reference/*Hackathon*.xlsx",
    ],
}


class InputNotFoundError(FileNotFoundError):
    """Raised when a required logical dataset input cannot be located."""
    pass


def extract_date_from_filename(filename: str) -> Optional[datetime.date]:
    """Extract YYYY-MM-DD date from filename for sorting candidate files."""
    m = re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})', filename)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


class ResolvedInput:
    """Metadata container for a resolved dataset pointer."""

    def __init__(
        self,
        logical_name: str,
        path: Path,
        source_type: str,
        is_gz: bool = False,
        alternatives: Optional[List[Path]] = None,
        is_remote: bool = False,
    ):
        self.logical_name = logical_name
        self.path = path
        self.source_type = source_type
        self.is_gz = is_gz
        self.alternatives = alternatives or []
        self.is_remote = is_remote

    def __repr__(self) -> str:
        return f"ResolvedInput({self.logical_name} -> {self.path.name} [{self.source_type}])"


class DataLocator:
    """Non-invasive data resolver for PTD Pipeline."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        config: Optional[Dict[str, Any]] = None,
        use_fixtures: bool = False,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.config = config or {}
        self.use_fixtures = use_fixtures or self.config.get("use_fixtures", False)
        self.allow_remote = self.config.get("allow_remote", False) or os.getenv("PTD_ALLOW_REMOTE", "false").lower() in ("true", "1")

        self.interim_dir = self.project_root / "data" / "interim"
        self.output_dir = self.project_root / "data" / "output"

        # Load config.local.yaml if present
        self.local_config = self._load_local_config()
        self._resolved_cache: Dict[str, ResolvedInput] = {}

    def _load_local_config(self) -> Dict[str, Any]:
        """Load per-machine pointers from config.local.yaml if it exists."""
        local_cfg_path = self.project_root / "config.local.yaml"
        if local_cfg_path.exists():
            try:
                with open(local_cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    logger.info("Loaded machine-specific data pointers from %s", local_cfg_path)
                    return data
            except Exception as e:
                logger.warning("Could not parse config.local.yaml: %s", e)
        return {}

    def _validate_safety(self, path: Path, logical_name: str) -> None:
        """Enforce that source pointers never resolve inside project write/output folders."""
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        # Check if inside output_dir
        try:
            resolved.relative_to(self.output_dir.resolve())
            raise ValueError(
                f"Safety Violation: Pointer for '{logical_name}' resolved inside output directory: {resolved}. "
                "Source datasets must remain separate from generated deliverables."
            )
        except ValueError as e:
            if "Safety Violation" in str(e):
                raise

        # Check if inside interim_dir (unless it's the remote_cache)
        remote_cache = (self.interim_dir / "remote_cache").resolve()
        try:
            resolved.relative_to(self.interim_dir.resolve())
            # If inside interim, allow only if inside remote_cache
            try:
                resolved.relative_to(remote_cache)
            except ValueError:
                raise ValueError(
                    f"Safety Violation: Pointer for '{logical_name}' resolved inside interim directory: {resolved}. "
                    "Source datasets cannot be located inside data/interim/."
                )
        except ValueError as e:
            if "Safety Violation" in str(e):
                raise

    def _select_newest_candidate(self, candidates: List[Path], pattern: str) -> Tuple[Path, List[Path]]:
        """Sort candidate files by date in filename (newest first), then mtime."""
        def sort_key(p: Path) -> Tuple[datetime.date, float]:
            d = extract_date_from_filename(p.name) or datetime.date.min
            try:
                mt = p.stat().st_mtime
            except Exception:
                mt = 0.0
            return (d, mt)

        sorted_cands = sorted(candidates, key=sort_key, reverse=True)
        chosen = sorted_cands[0]
        alternatives = sorted_cands[1:]
        if alternatives:
            logger.info(
                "Multiple candidates matched '%s': chosen newest '%s', alternatives: %s",
                pattern, chosen.name, [a.name for a in alternatives]
            )
        return chosen, alternatives

    def _resolve_remote_url(self, url: str, logical_name: str) -> Path:
        """Stream an https:// rate file into data/interim/remote_cache if allow_remote=True."""
        if not self.allow_remote:
            raise ValueError(
                f"Remote URL pointer '{url}' specified for '{logical_name}', but remote downloading is disabled. "
                "Set allow_remote: true in config.local.yaml or export PTD_ALLOW_REMOTE=true to enable."
            )
        import requests
        cache_dir = self.interim_dir / "remote_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = url.split("/")[-1].split("?")[0] or f"remote_{logical_name}.json"
        target_path = cache_dir / filename

        if target_path.exists() and target_path.stat().st_size > 0:
            logger.info("Using cached remote dataset for %s: %s", logical_name, target_path)
            return target_path

        logger.info("Streaming remote dataset from %s into %s (allow_remote=True)...", url, target_path)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024 * 8):
                    if chunk:
                        f.write(chunk)
        logger.info("Remote stream download complete: %s (%d bytes)", target_path, target_path.stat().st_size)
        return target_path

    def _find_matching_paths(self, base_dir: Path, pattern: str) -> List[Path]:
        """Expand glob patterns or check direct paths, supporting symlinks and external drives."""
        if not base_dir.exists():
            return []
        
        # If pattern has wildcards
        if any(char in pattern for char in ["*", "?", "["]):
            matches = list(base_dir.glob(pattern))
            return [m for m in matches if m.is_file() or m.is_symlink()]
        
        # Direct path
        candidate = (base_dir / pattern)
        if candidate.exists() and (candidate.is_file() or candidate.is_symlink()):
            return [candidate]
        return []

    def get_path(self, logical_name: str, required: bool = True) -> Optional[Path]:
        """Resolve the path for a logical dataset input in strict priority order."""
        if logical_name in self._resolved_cache:
            return self._resolved_cache[logical_name].path

        searched_locations: List[str] = []

        # ---------------------------------------------------------------------
        # Priority 0: Fixtures override (if use_fixtures=True)
        # ---------------------------------------------------------------------
        if self.use_fixtures:
            fixture_dirs = [
                self.project_root / "data" / "fixtures" / "output",
                self.project_root / "tests" / "fixtures",
            ]
            for f_dir in fixture_dirs:
                if f_dir.exists():
                    pats = DEFAULT_SEARCH_PATTERNS.get(logical_name, [f"*{logical_name}*"])
                    for pat in pats:
                        cands = self._find_matching_paths(f_dir, pat)
                        if cands:
                            chosen, alts = self._select_newest_candidate(cands, pat)
                            res = ResolvedInput(logical_name, chosen, "test_fixture", chosen.name.endswith(".gz"), alts)
                            self._resolved_cache[logical_name] = res
                            logger.info("Resolved '%s' from test fixtures: %s", logical_name, chosen.name)
                            return chosen

        # ---------------------------------------------------------------------
        # Priority 1: Environment Variables
        # ---------------------------------------------------------------------
        env_vars = ENV_VAR_MAP.get(logical_name, [])
        for ev in env_vars:
            val = os.getenv(ev)
            if val and val.strip():
                searched_locations.append(f"env:{ev}={val}")
                val_str = val.strip()
                if val_str.startswith("http://") or val_str.startswith("https://"):
                    p = self._resolve_remote_url(val_str, logical_name)
                    res = ResolvedInput(logical_name, p, f"env:{ev}(remote)", p.name.endswith(".gz"), is_remote=True)
                    self._resolved_cache[logical_name] = res
                    return p

                p = Path(val_str)
                if not p.is_absolute():
                    p = (self.project_root / p).resolve()
                if p.exists() and (p.is_file() or p.is_symlink()):
                    self._validate_safety(p, logical_name)
                    res = ResolvedInput(logical_name, p, f"env:{ev}", p.name.endswith(".gz"))
                    self._resolved_cache[logical_name] = res
                    return p
                elif any(char in val_str for char in ["*", "?", "["]):
                    parent = p.parent if p.parent.exists() else self.project_root
                    cands = list(parent.glob(p.name))
                    if cands:
                        chosen, alts = self._select_newest_candidate(cands, p.name)
                        self._validate_safety(chosen, logical_name)
                        res = ResolvedInput(logical_name, chosen, f"env:{ev}(glob)", chosen.name.endswith(".gz"), alts)
                        self._resolved_cache[logical_name] = res
                        return chosen

        # PTD_DATA_ROOT environment variable (general root directory)
        data_root_env = os.getenv("PTD_DATA_ROOT")
        if data_root_env and data_root_env.strip():
            root_dir = Path(data_root_env.strip())
            if not root_dir.is_absolute():
                root_dir = (self.project_root / root_dir).resolve()
            searched_locations.append(f"env:PTD_DATA_ROOT={root_dir}")
            if root_dir.exists():
                pats = DEFAULT_SEARCH_PATTERNS.get(logical_name, [])
                for pat in pats:
                    cands = self._find_matching_paths(root_dir, pat)
                    if not cands and "/" in pat:
                        # try without subfolder prefix
                        cands = self._find_matching_paths(root_dir, pat.split("/", 1)[-1])
                    if cands:
                        chosen, alts = self._select_newest_candidate(cands, pat)
                        self._validate_safety(chosen, logical_name)
                        res = ResolvedInput(logical_name, chosen, "env:PTD_DATA_ROOT", chosen.name.endswith(".gz"), alts)
                        self._resolved_cache[logical_name] = res
                        return chosen

        # ---------------------------------------------------------------------
        # Priority 2: config.local.yaml
        # ---------------------------------------------------------------------
        local_pointers = self.local_config.get("pointers", {})
        if logical_name in local_pointers:
            val = str(local_pointers[logical_name]).strip()
            searched_locations.append(f"config.local.yaml:pointers.{logical_name}={val}")
            if val.startswith("http://") or val.startswith("https://"):
                p = self._resolve_remote_url(val, logical_name)
                res = ResolvedInput(logical_name, p, "config.local.yaml(remote)", p.name.endswith(".gz"), is_remote=True)
                self._resolved_cache[logical_name] = res
                return p

            p = Path(val)
            if not p.is_absolute():
                p = (self.project_root / p).resolve()
            if p.exists() and (p.is_file() or p.is_symlink()):
                self._validate_safety(p, logical_name)
                res = ResolvedInput(logical_name, p, "config.local.yaml", p.name.endswith(".gz"))
                self._resolved_cache[logical_name] = res
                return p
            elif any(char in val for char in ["*", "?", "["]):
                parent = p.parent if p.parent.exists() else self.project_root
                cands = list(parent.glob(p.name))
                if cands:
                    chosen, alts = self._select_newest_candidate(cands, p.name)
                    self._validate_safety(chosen, logical_name)
                    res = ResolvedInput(logical_name, chosen, "config.local.yaml(glob)", chosen.name.endswith(".gz"), alts)
                    self._resolved_cache[logical_name] = res
                    return chosen

        # ---------------------------------------------------------------------
        # Priority 3: Base config.yaml & Default Project Directories
        # ---------------------------------------------------------------------
        base_pointers = self.config.get("pointers", {})
        base_orig = self.config.get("original_input_sources", {})
        base_ref = self.config.get("reference_files", {})
        configured_paths = [
            base_pointers.get(logical_name),
            base_orig.get(logical_name),
            base_ref.get(logical_name),
        ]
        for cp in configured_paths:
            if cp:
                cp_str = str(cp).strip()
                searched_locations.append(f"config.yaml:{cp_str}")
                p = Path(cp_str)
                if not p.is_absolute():
                    p = (self.project_root / p).resolve()
                if p.exists() and (p.is_file() or p.is_symlink()):
                    self._validate_safety(p, logical_name)
                    res = ResolvedInput(logical_name, p, "config.yaml", p.name.endswith(".gz"))
                    self._resolved_cache[logical_name] = res
                    return p
                elif any(char in cp_str for char in ["*", "?", "["]):
                    parent = p.parent if p.parent.exists() else self.project_root
                    cands = list(parent.glob(p.name))
                    if cands:
                        chosen, alts = self._select_newest_candidate(cands, p.name)
                        self._validate_safety(chosen, logical_name)
                        res = ResolvedInput(logical_name, chosen, "config.yaml(glob)", chosen.name.endswith(".gz"), alts)
                        self._resolved_cache[logical_name] = res
                        return chosen

        # Search default patterns in project data/
        data_dir = self.project_root / "data"
        pats = DEFAULT_SEARCH_PATTERNS.get(logical_name, [])
        for pat in pats:
            searched_locations.append(f"data/{pat}")
            cands = self._find_matching_paths(data_dir, pat)
            if cands:
                chosen, alts = self._select_newest_candidate(cands, pat)
                self._validate_safety(chosen, logical_name)
                res = ResolvedInput(logical_name, chosen, "default_data_dir", chosen.name.endswith(".gz"), alts)
                self._resolved_cache[logical_name] = res
                return chosen

        # ---------------------------------------------------------------------
        # Not found: Raise clear error or return None
        # ---------------------------------------------------------------------
        if required:
            env_hint = ", ".join(env_vars) if env_vars else f"PTD_{logical_name.upper()}"
            msg = (
                f"\n[PTD DATA LOCATOR ERROR] Input dataset '{logical_name}' could not be located!\n"
                f"Searched locations:\n" + "\n".join(f"  • {loc}" for loc in searched_locations) + "\n\n"
                f"How to set the pointer:\n"
                f"  1. Environment variable: export {env_hint}=/path/to/{logical_name}\n"
                f"  2. Or edit config.local.yaml:\n"
                f"       pointers:\n"
                f"         {logical_name}: /path/to/{logical_name}\n"
                f"  3. Or create symlinks via: python scripts/link_data.py --target /path/to/{logical_name}\n"
                f"  4. Or enable test fixtures: pass --fixtures or set use_fixtures: true in config.yaml\n"
            )
            raise InputNotFoundError(msg)

        return None

    def get_index_files(self) -> List[Path]:
        """Resolve all index files (from env, config.local, or data/index)."""
        # Check env PTD_INDEX_DIR or PTD_INDEX_FILES
        index_dir_env = os.getenv("PTD_INDEX_DIR") or os.getenv("PTD_INDEX_FILES")
        if index_dir_env and index_dir_env.strip():
            p = Path(index_dir_env.strip())
            if not p.is_absolute():
                p = (self.project_root / p).resolve()
            if p.is_dir():
                files = sorted(p.glob("*.json*"))
                if files:
                    logger.info("Resolved %d index files from env PTD_INDEX_DIR (%s)", len(files), p)
                    return files
            elif p.is_file():
                return [p]

        # Check config.local.yaml
        local_idx = self.local_config.get("pointers", {}).get("index_dir") or self.local_config.get("pointers", {}).get("index_files")
        if local_idx:
            p = Path(str(local_idx).strip())
            if not p.is_absolute():
                p = (self.project_root / p).resolve()
            if p.is_dir():
                files = sorted(p.glob("*.json*"))
                if files:
                    logger.info("Resolved %d index files from config.local.yaml (%s)", len(files), p)
                    return files

        # Default data/index
        idx_dir = self.project_root / "data" / "index"
        if idx_dir.exists():
            files = sorted(idx_dir.glob("*.json*"))
            if files:
                return files

        # Fixture fallback
        if self.use_fixtures:
            fix_idx = self.project_root / "data" / "fixtures" / "output"
            if fix_idx.exists():
                files = sorted(fix_idx.glob("*index*.json*")) or sorted(fix_idx.glob("*.json*"))
                if files:
                    return files

        raise InputNotFoundError(
            "No index JSON files found in data/index or via PTD_INDEX_DIR / config.local.yaml. "
            "Set PTD_INDEX_DIR=/path/to/indices or place files in data/index/."
        )

    def open_readonly(self, logical_name_or_path: Union[str, Path], mode: str = "rb") -> BinaryIO:
        """Open a source dataset strictly in read-only mode, transparently decompressing .gz."""
        if isinstance(logical_name_or_path, Path):
            p = logical_name_or_path
        elif "/" in logical_name_or_path or "\\" in logical_name_or_path:
            p = Path(logical_name_or_path)
        else:
            p = self.get_path(logical_name_or_path, required=True)

        if not ("r" in mode and not any(m in mode for m in ["w", "a", "+", "x"])):
            raise ValueError(f"Read-Only Invariant Violation: Attempted to open source dataset with write mode '{mode}'.")

        p_str = str(p)
        if p_str.endswith(".gz"):
            return gzip.open(p, mode)
        return open(p, mode)

    def log_resolution_summary(self) -> None:
        """Log a concise summary block listing each logical input and its resolved path."""
        logical_keys = [
            "healthnet_ca_rate_file",
            "index_files",
            "nppes_zip",
            "nucc_taxonomy",
            "cms_dac",
            "hospital_general_info",
            "hilabs_workbook",
        ]
        logger.info("================================================================================")
        logger.info("PTD DATA LOCATOR: RESOLVED INPUT SOURCES")
        logger.info("================================================================================")
        for key in logical_keys:
            try:
                if key == "index_files":
                    files = self.get_index_files()
                    logger.info("  %-24s: %d files in %s", key, len(files), files[0].parent.name)
                else:
                    path = self.get_path(key, required=False)
                    if path:
                        res = self._resolved_cache.get(key)
                        src_type = res.source_type if res else "resolved"
                        logger.info("  %-24s: %s (via %s)", key, path.name, src_type)
                    else:
                        logger.info("  %-24s: [NOT FOUND / OPTIONAL]", key)
            except Exception as e:
                logger.info("  %-24s: [ERROR: %s]", key, e)
        logger.info("================================================================================")


# Global singleton instance for easy import across modules
_GLOBAL_LOCATOR: Optional[DataLocator] = None


def get_locator(project_root: Optional[Path] = None, config: Optional[Dict[str, Any]] = None, use_fixtures: bool = False) -> DataLocator:
    """Return the global DataLocator instance or create one."""
    global _GLOBAL_LOCATOR
    if _GLOBAL_LOCATOR is None or use_fixtures != _GLOBAL_LOCATOR.use_fixtures:
        _GLOBAL_LOCATOR = DataLocator(project_root=project_root, config=config, use_fixtures=use_fixtures)
    return _GLOBAL_LOCATOR
