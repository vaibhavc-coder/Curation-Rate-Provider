#!/usr/bin/env python3
"""PTD Pipeline Input Doctor & Integrity Checker.

Checks all logical dataset inputs, resolves their non-invasive pointers,
computes chunked SHA-256 checksums with mtime-aware caching in data/interim/checksum_cache.json,
compares against data/input_manifest.json, and prints a formatted report table.
Saves data/interim/doctor_report.json for Streamlit frontend integration.

Exit Code:
  0: All required inputs are present (even if optional files or checksum mismatches exist).
  1: One or more required inputs are missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure src/ is on sys.path
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from ptd.config import load_config
from ptd.data_locator import InputNotFoundError

LOGICAL_INPUTS_SPEC = [
    {"name": "healthnet_ca_rate_file", "required": True, "description": "Centene CA Commercial Rate File"},
    {"name": "index_files", "required": True, "description": "TiC Payer Index JSON Files", "is_multi": True},
    {"name": "nppes_zip", "required": True, "description": "CMS NPPES Monthly Zip Archive"},
    {"name": "nucc_taxonomy", "required": True, "description": "NUCC Health Care Taxonomy CSV"},
    {"name": "cms_dac", "required": False, "description": "CMS Doctors and Clinicians Dataset"},
    {"name": "hospital_general_info", "required": False, "description": "CMS Hospital General Information CSV"},
    {"name": "hilabs_workbook", "required": False, "description": "HiLabs Benchmark & Weights Workbook"},
    {"name": "healthnet_or_rate_file", "required": False, "description": "Centene OR Commercial Rate File"},
]


def compute_sha256(path: Path, cache: Dict[str, str], chunk_size: int = 8 * 1024 * 1024) -> Tuple[str, int]:
    """Compute SHA-256 using chunked streaming, cached by path:size:mtime."""
    stat = path.stat()
    size = stat.st_size
    mtime = stat.st_mtime
    cache_key = f"{path.resolve()}:{size}:{mtime}"

    if cache_key in cache:
        return cache[cache_key], size

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)

    digest = h.hexdigest()
    cache[cache_key] = digest
    return digest, size


def load_checksum_cache(cache_file: Path) -> Dict[str, str]:
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_checksum_cache(cache: Dict[str, str], cache_file: Path) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not save checksum cache: {e}\n")


def load_manifest(manifest_file: Path) -> Dict[str, Any]:
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def format_size(bytes_count: int) -> str:
    if bytes_count >= 1024 * 1024 * 1024:
        return f"{bytes_count / (1024**3):.2f} GB"
    elif bytes_count >= 1024 * 1024:
        return f"{bytes_count / (1024**2):.1f} MB"
    elif bytes_count >= 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count} B"


def main():
    parser = argparse.ArgumentParser(description="Check pipeline inputs integrity and locations.")
    parser.add_argument("--config", type=str, default=None, help="Custom config.yaml path")
    parser.add_argument("--fixtures", action="store_true", help="Check against test fixtures")
    parser.add_argument("--json", action="store_true", help="Print doctor report as JSON to stdout")
    args = parser.parse_args()

    cfg = load_config(args.config, use_fixtures=args.fixtures)
    cache_file = cfg.interim_dir / "checksum_cache.json"
    doctor_report_file = cfg.interim_dir / "doctor_report.json"
    manifest_file = cfg.project_root / "data" / "input_manifest.json"

    cache = load_checksum_cache(cache_file)
    manifest = load_manifest(manifest_file)

    report_entries = []
    missing_required = []
    warnings = []

    for spec in LOGICAL_INPUTS_SPEC:
        name = spec["name"]
        required = spec["required"]
        desc = spec["description"]
        is_multi = spec.get("is_multi", False)

        if is_multi:
            # Multi-file input (e.g. index_files)
            try:
                paths = cfg.locator.get_index_files()
            except InputNotFoundError as e:
                paths = []
                if required:
                    missing_required.append(name)
                report_entries.append({
                    "logical_name": name,
                    "description": desc,
                    "required": required,
                    "status": "MISSING",
                    "resolved_path": "NOT FOUND",
                    "size_bytes": 0,
                    "size_str": "—",
                    "sha256": "—",
                    "manifest_status": "MISSING",
                    "notes": "No index files found in data/index or via PTD_INDEX_DIR",
                })
                continue

            for idx_path in paths:
                try:
                    digest, sz = compute_sha256(idx_path, cache)
                    # Check against manifest
                    m_status = "NO-MANIFEST"
                    m_key = None
                    for k, v in manifest.items():
                        if v.get("filename") == idx_path.name or v.get("path") == str(idx_path):
                            m_key = k
                            if v.get("sha256") == digest:
                                m_status = "MATCH"
                            else:
                                m_status = "MISMATCH"
                            break

                    report_entries.append({
                        "logical_name": f"{name} ({idx_path.name.split('_')[1] if '_' in idx_path.name else idx_path.name})",
                        "description": desc,
                        "required": required,
                        "status": "FOUND",
                        "resolved_path": str(idx_path.resolve()),
                        "size_bytes": sz,
                        "size_str": format_size(sz),
                        "sha256": digest,
                        "manifest_status": m_status,
                        "notes": "Verified readable",
                    })
                except Exception as ex:
                    report_entries.append({
                        "logical_name": f"{name} ({idx_path.name})",
                        "description": desc,
                        "required": required,
                        "status": "ERROR",
                        "resolved_path": str(idx_path.resolve()),
                        "size_bytes": 0,
                        "size_str": "—",
                        "sha256": "—",
                        "manifest_status": "ERROR",
                        "notes": f"Read error: {ex}",
                    })
        else:
            # Single file input
            try:
                p = cfg.locator.get_path(name, required=False)
            except InputNotFoundError:
                p = None

            if not p or not p.exists():
                if required:
                    missing_required.append(name)
                    status_str = "MISSING"
                    notes = f"Required: Set PTD_{name.upper()} or check config.local.yaml"
                else:
                    status_str = "NOT_ATTACHED (OPTIONAL)"
                    notes = "Optional enrichment; pipeline will run without it"

                report_entries.append({
                    "logical_name": name,
                    "description": desc,
                    "required": required,
                    "status": status_str,
                    "resolved_path": "NOT FOUND",
                    "size_bytes": 0,
                    "size_str": "—",
                    "sha256": "—",
                    "manifest_status": "NOT_ATTACHED" if not required else "MISSING",
                    "notes": notes,
                })
            else:
                try:
                    digest, sz = compute_sha256(p, cache)
                    # Compare against manifest
                    m_entry = manifest.get(name)
                    if m_entry:
                        exp_sha = m_entry.get("sha256")
                        if exp_sha == digest:
                            m_status = "MATCH"
                        else:
                            m_status = "MISMATCH"
                            warnings.append(f"{name}: SHA-256 differs from manifest (new month data?)")
                    else:
                        m_status = "NO-MANIFEST"

                    res_obj = cfg.locator._resolved_cache.get(name)
                    src_tag = f"via {res_obj.source_type}" if res_obj else "resolved"

                    report_entries.append({
                        "logical_name": name,
                        "description": desc,
                        "required": required,
                        "status": "FOUND",
                        "resolved_path": str(p.resolve()),
                        "size_bytes": sz,
                        "size_str": format_size(sz),
                        "sha256": digest,
                        "manifest_status": m_status,
                        "notes": src_tag,
                    })
                except Exception as ex:
                    report_entries.append({
                        "logical_name": name,
                        "description": desc,
                        "required": required,
                        "status": "ERROR",
                        "resolved_path": str(p.resolve()),
                        "size_bytes": 0,
                        "size_str": "—",
                        "sha256": "—",
                        "manifest_status": "ERROR",
                        "notes": f"Read error: {ex}",
                    })

    # Save updated checksum cache
    save_checksum_cache(cache, cache_file)

    # Doctor report dict
    doctor_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "status": "PASS" if not missing_required else "FAIL",
        "missing_required": missing_required,
        "warnings": warnings,
        "entries": report_entries,
    }

    try:
        doctor_report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(doctor_report_file, "w", encoding="utf-8") as f:
            json.dump(doctor_data, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not save doctor report: {e}\n")

    if args.json:
        print(json.dumps(doctor_data, indent=2))
        sys.exit(0 if not missing_required else 1)

    # Print formatted ASCII / Markdown table
    header = (
        f"{'Logical Name':<28} | {'Resolved Path':<48} | {'Size':<10} | {'SHA-256 (12)':<12} | {'Manifest':<11} | {'Notes'}"
    )
    divider = "-" * len(header)
    print("\n" + "=" * len(header))
    print("PTD PIPELINE INPUT DOCTOR & DATA PROVENANCE REPORT")
    print("=" * len(header))
    print(header)
    print(divider)

    for entry in report_entries:
        l_name = entry["logical_name"][:28]
        p_str = entry["resolved_path"]
        if len(p_str) > 48:
            p_str = "..." + p_str[-45:]
        sz_str = entry["size_str"]
        sha_sub = entry["sha256"][:12] if entry["sha256"] != "—" else "—"
        m_stat = entry["manifest_status"]
        notes = entry["notes"][:35]
        print(f"{l_name:<28} | {p_str:<48} | {sz_str:<10} | {sha_sub:<12} | {m_stat:<11} | {notes}")

    print(divider)
    if missing_required:
        print("\n❌ DOCTOR CHECK FAILED: The following REQUIRED inputs are missing:")
        for m in missing_required:
            print(f"  • {m}: Check environment variables (e.g. export PTD_{m.upper()}=/path) or config.local.yaml")
        print("\nFix missing pointers and re-run: make doctor\n")
        sys.exit(1)
    else:
        print("\n✅ DOCTOR CHECK PASSED: All required logical datasets successfully resolved and verified.")
        if warnings:
            print("Notice:")
            for w in warnings:
                print(f"  ⚠️ {w}")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
