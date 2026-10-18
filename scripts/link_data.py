#!/usr/bin/env python3
"""PTD Pipeline Symlink Helper.

Creates non-invasive symbolic links from external dataset locations into
the project data directory without copying or moving files.
Tracks created links in data/interim/.linked_symlinks.json for safe cleanup.

Usage:
  python scripts/link_data.py --source /path/to/downloads
  python scripts/link_data.py --ca-rate-file /path/to/ca.json --index-dir /path/to/indices
  python scripts/link_data.py --dry-run --source /path/to/downloads
  python scripts/link_data.py --remove
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure src/ on path
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from ptd.data_locator import DEFAULT_SEARCH_PATTERNS


def get_tracking_file(project_root: Path) -> Path:
    return project_root / "data" / "interim" / ".linked_symlinks.json"


def load_tracked_links(tracking_file: Path) -> List[str]:
    if tracking_file.exists():
        try:
            with open(tracking_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("symlinks", [])
        except Exception:
            return []
    return []


def save_tracked_links(tracking_file: Path, links: List[str]) -> None:
    tracking_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tracking_file, "w", encoding="utf-8") as f:
            json.dump({"symlinks": sorted(list(set(links)))}, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not save symlink tracking file: {e}\n")


def remove_links(project_root: Path, dry_run: bool = False) -> None:
    """Safely remove only symlinks previously created by this tool."""
    tracking_file = get_tracking_file(project_root)
    links = load_tracked_links(tracking_file)
    if not links:
        print("No previously tracked symlinks found to remove.")
        return

    print(f"Cleaning up {len(links)} tracked symbolic links...")
    remaining = []
    for link_str in links:
        p = Path(link_str)
        if not p.is_absolute():
            p = project_root / p

        if p.is_symlink():
            if dry_run:
                print(f"  [DRY-RUN] Would remove symlink: {p}")
                remaining.append(str(p))
            else:
                try:
                    p.unlink()
                    print(f"  ✅ Removed symlink: {p}")
                except Exception as e:
                    print(f"  ❌ Failed to remove {p}: {e}")
                    remaining.append(str(p))
        elif p.exists():
            print(f"  ⚠️ Skipping {p}: Exists but is a real file/dir, not a symlink!")
            remaining.append(str(p))
        else:
            print(f"  ℹ️ Symlink already gone: {p}")

    if not dry_run:
        save_tracked_links(tracking_file, remaining)
    print("Symlink removal complete.")


def create_safe_symlink(
    src: Path,
    dst: Path,
    dry_run: bool = False,
    tracked: Optional[List[str]] = None,
) -> bool:
    """Create a symbolic link from dst -> src without overwriting real files."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_res = src.resolve()

    if dst.is_symlink():
        curr_target = dst.resolve()
        if curr_target == src_res:
            print(f"  ℹ️ Already linked: {dst.name} -> {src_res.name}")
            if tracked is not None:
                tracked.append(str(dst.resolve()))
            return True
        else:
            if dry_run:
                print(f"  [DRY-RUN] Would update symlink: {dst.name} -> {src_res}")
                return True
            dst.unlink()

    elif dst.exists():
        print(f"  ⛔ REFUSING TO OVERWRITE real file with symlink: {dst}")
        return False

    if dry_run:
        print(f"  [DRY-RUN] Would symlink: {dst} -> {src_res}")
        return True

    try:
        dst.symlink_to(src_res)
        print(f"  ✅ Linked: {dst.name} -> {src_res}")
        if tracked is not None:
            tracked.append(str(dst.resolve()))
        return True
    except OSError as e:
        sys.stderr.write(
            f"\n❌ Error creating symlink for {dst.name}: {e}\n"
            "NOTE FOR WINDOWS USERS:\n"
            "  Creating symbolic links on Windows requires Developer Mode or Administrator privileges.\n"
            "  Alternative (Zero-Copy): Use config.local.yaml instead of symlinks!\n"
            "  Example: Copy config.local.example.yaml to config.local.yaml and set your paths there.\n\n"
        )
        return False


def main():
    parser = argparse.ArgumentParser(description="PTD Pipeline Symlink Helper.")
    parser.add_argument("--source", type=str, default=None, help="Folder containing downloaded source datasets")
    parser.add_argument("--ca-rate-file", type=str, default=None, help="Explicit path to CA rate file")
    parser.add_argument("--or-rate-file", type=str, default=None, help="Explicit path to OR rate file")
    parser.add_argument("--index-dir", type=str, default=None, help="Folder containing index JSON files")
    parser.add_argument("--nppes-zip", type=str, default=None, help="Path to NPPES monthly zip")
    parser.add_argument("--nucc", type=str, default=None, help="Path to NUCC taxonomy CSV")
    parser.add_argument("--cms-dac", type=str, default=None, help="Path to CMS DAC parquet")
    parser.add_argument("--hospital-info", type=str, default=None, help="Path to Hospital General Info CSV")
    parser.add_argument("--hilabs-workbook", type=str, default=None, help="Path to HiLabs workbook XLSX")
    parser.add_argument("--target-root", type=str, default=None, help="Target project root (default: current project)")
    parser.add_argument("--dry-run", action="store_true", help="Preview links without creating them")
    parser.add_argument("--remove", action="store_true", help="Remove previously tracked symlinks")

    args = parser.parse_args()

    project_root = Path(args.target_root).resolve() if args.target_root else Path(__file__).resolve().parent.parent

    if args.remove:
        remove_links(project_root, dry_run=args.dry_run)
        return

    tracking_file = get_tracking_file(project_root)
    tracked_links = load_tracked_links(tracking_file)

    print("=" * 80)
    print("PTD PIPELINE NON-INVASIVE SYMLINK LINKER")
    print(f"Target Project Root: {project_root}")
    if args.dry_run:
        print("MODE: DRY RUN (No changes will be written to disk)")
    print("=" * 80)

    # 1. If explicit paths are provided
    if args.ca_rate_file:
        p = Path(args.ca_rate_file).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "raw" / p.name, args.dry_run, tracked_links)

    if args.or_rate_file:
        p = Path(args.or_rate_file).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "raw" / p.name, args.dry_run, tracked_links)

    if args.index_dir:
        idir = Path(args.index_dir).resolve()
        if idir.is_dir():
            for f in idir.glob("*.json*"):
                create_safe_symlink(f, project_root / "data" / "index" / f.name, args.dry_run, tracked_links)

    if args.nppes_zip:
        p = Path(args.nppes_zip).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "reference" / p.name, args.dry_run, tracked_links)

    if args.nucc:
        p = Path(args.nucc).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "reference" / p.name, args.dry_run, tracked_links)

    if args.cms_dac:
        p = Path(args.cms_dac).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "reference" / p.name, args.dry_run, tracked_links)

    if args.hospital_info:
        p = Path(args.hospital_info).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "reference" / p.name, args.dry_run, tracked_links)

    if args.hilabs_workbook:
        p = Path(args.hilabs_workbook).resolve()
        if p.exists():
            create_safe_symlink(p, project_root / "data" / "reference" / p.name, args.dry_run, tracked_links)

    # 2. If --source directory is provided, scan and link
    if args.source:
        src_dir = Path(args.source).resolve()
        if not src_dir.exists() or not src_dir.is_dir():
            sys.stderr.write(f"Error: Source directory does not exist: {src_dir}\n")
            sys.exit(1)

        print(f"\nScanning source directory: {src_dir} ...")
        # Find index files
        for f in src_dir.glob("*index*.json*"):
            create_safe_symlink(f, project_root / "data" / "index" / f.name, args.dry_run, tracked_links)

        # Find CA rate file
        for f in src_dir.glob("*healthnet-ca*.json*"):
            create_safe_symlink(f, project_root / "data" / "raw" / f.name, args.dry_run, tracked_links)

        # Find OR rate file
        for f in src_dir.glob("*healthnet-or*.json*"):
            create_safe_symlink(f, project_root / "data" / "raw" / f.name, args.dry_run, tracked_links)

        # Find NPPES zip
        for f in src_dir.glob("*NPPES*.zip"):
            create_safe_symlink(f, project_root / "data" / "reference" / f.name, args.dry_run, tracked_links)

        # Find reference tables
        for f in src_dir.glob("*nucc*.csv"):
            create_safe_symlink(f, project_root / "data" / "reference" / f.name, args.dry_run, tracked_links)

        for f in src_dir.glob("*dac*.parquet"):
            create_safe_symlink(f, project_root / "data" / "reference" / f.name, args.dry_run, tracked_links)

        for f in src_dir.glob("*hospital*.csv"):
            create_safe_symlink(f, project_root / "data" / "reference" / f.name, args.dry_run, tracked_links)

        for f in src_dir.glob("*Rate_Benchmarking*.xlsx"):
            create_safe_symlink(f, project_root / "data" / "reference" / f.name, args.dry_run, tracked_links)

    if not args.dry_run:
        save_tracked_links(tracking_file, tracked_links)

    print("\nSymlink operation complete. Run 'make doctor' to verify inputs.")


if __name__ == "__main__":
    main()
