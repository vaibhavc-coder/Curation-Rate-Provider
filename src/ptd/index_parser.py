"""Index file stream parser and deduplicator for Price Transparency Data (TiC v2.0.0).

Streams index JSON files using ijson, produces deduplicated plan tables,
file tables, and many-to-many plan-file mappings with clear audit reasons.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple
import ijson
import polars as pl

from ptd.config import PipelineConfig

logger = logging.getLogger("ptd.index_parser")


def infer_brand_from_filename(filename: str) -> str:
    """Extract brand name from index filename (e.g. 2026-09-30_healthnet_index.json -> healthnet)."""
    parts = filename.replace(".json", "").split("_")
    if len(parts) >= 2:
        return parts[1].lower()
    return "unknown"


def determine_plan_scope(
    brand: str,
    market_type: str,
    file_url: str,
    plan_name: str,
    plan_id: str,
    plan_id_type: str,
) -> Tuple[bool, str, str]:
    """Determine whether a plan is within commercial-group California scope.

    Returns:
        (in_scope: bool, scope_reason: str, state_hint: str)
    """
    url_lower = file_url.lower()
    name_upper = plan_name.upper()

    # Determine state hint
    state_hint = "UNKNOWN"
    if "healthnet-ca" in url_lower or "ambetter-ca" in url_lower or name_upper.startswith("CA ") or " CA " in name_upper:
        state_hint = "CA"
    elif "healthnet-or" in url_lower:
        state_hint = "OR"
    elif "fidelis" in brand.lower():
        state_hint = "NY"
    elif "qualchoice" in brand.lower():
        state_hint = "AR"
    elif "-in_" in url_lower:
        state_hint = "IN"
    elif "-ok_" in url_lower:
        state_hint = "OK"
    elif "-la_" in url_lower:
        state_hint = "LA"

    # Evaluate Scope Rules
    # Rule 1: Market Type must be 'group'
    if market_type.lower() != "group":
        return (
            False,
            f"Market type '{market_type}' excluded (commercial group required)",
            state_hint,
        )

    # Rule 2: Exclude non-CA brands or files
    if brand.lower() == "fidelis":
        return False, "Fidelis is New York individual market", state_hint

    if brand.lower() == "qualchoice":
        return False, "QualChoice is Arkansas group market (HIOS 37903/70525), not California", state_hint

    if brand.lower() == "ambetter":
        return False, "Ambetter plans are individual exchange market", state_hint

    if "healthnet-or" in url_lower:
        return False, "Health Net Oregon rate file (healthnet-or), out of California scope", state_hint

    # Rule 3: Target Health Net CA commercial group
    if "healthnet-ca" in url_lower:
        return True, "Commercial Group California (Health Net CA)", "CA"

    return False, "Does not match California commercial group criteria", state_hint


class IndexParser:
    """Stream-parses index files into clean, deduplicated relational structures."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.index_dir = config.index_dir
        self.interim_dir = config.interim_dir
        self.output_dir = config.output_dir

    def parse_single_index(self, file_path: Path) -> List[Dict[str, Any]]:
        """Stream a single TiC index file and return list of plan-file associations."""
        brand = infer_brand_from_filename(file_path.name)
        records = []

        logger.info(f"Streaming index file: {file_path.name} (brand: {brand})")

        with open(file_path, "rb") as f:
            # TiC schema v2.0.0: reporting_structure is a list of objects
            # Each object contains reporting_plans list and in_network_files list
            structures = ijson.items(f, "reporting_structure.item")
            for struct in structures:
                in_network_files = struct.get("in_network_files", [])
                reporting_plans = struct.get("reporting_plans", [])

                # If no in_network_files, skip structure
                if not in_network_files:
                    continue

                for inf in in_network_files:
                    file_url = inf.get("location", "")
                    file_desc = inf.get("description", "")

                    for plan in reporting_plans:
                        p_name = plan.get("plan_name", "")
                        p_id = str(plan.get("plan_id", ""))
                        p_id_type = plan.get("plan_id_type", "")
                        p_market = plan.get("plan_market_type", "")
                        issuer = plan.get("issuer_name", "")
                        sponsor = plan.get("plan_sponsor_name", "")

                        in_scope, reason, state_hint = determine_plan_scope(
                            brand=brand,
                            market_type=p_market,
                            file_url=file_url,
                            plan_name=p_name,
                            plan_id=p_id,
                            plan_id_type=p_id_type,
                        )

                        records.append({
                            "brand": brand,
                            "plan_name": p_name,
                            "plan_id": p_id,
                            "plan_id_type": p_id_type,
                            "market_type": p_market,
                            "issuer_name": issuer,
                            "plan_sponsor_name": sponsor,
                            "rate_file_url": file_url,
                            "file_description": file_desc,
                            "source_index_file": file_path.name,
                            "state_hint": state_hint,
                            "in_scope": in_scope,
                            "scope_reason": reason,
                        })

        logger.info(f"Extracted {len(records)} plan-file entries from {file_path.name}")
        return records

    def run(self) -> Dict[str, Any]:
        """Parse all index files in index_dir, deduplicate, and persist outputs."""
        all_records = []
        brand_raw_counts = {}

        index_files = sorted(self.index_dir.glob("*.json"))
        if not index_files:
            raise FileNotFoundError(f"No index json files found in {self.index_dir}")

        for f in index_files:
            records = self.parse_single_index(f)
            brand = infer_brand_from_filename(f.name)
            brand_raw_counts[brand] = brand_raw_counts.get(brand, 0) + len(records)
            all_records.extend(records)

        df_all = pl.DataFrame(all_records)
        total_before = len(df_all)

        # Deduplicate on (brand, plan_id, plan_name, rate_file_url)
        dedup_keys = ["brand", "plan_id", "plan_name", "rate_file_url"]
        df_plans_dedup = df_all.unique(subset=dedup_keys)
        total_after = len(df_plans_dedup)

        # Build deduplicated file table with plan counts
        df_files = (
            df_plans_dedup.group_by(["brand", "rate_file_url", "file_description", "state_hint", "in_scope"])
            .agg(
                pl.len().alias("plan_count"),
                pl.col("plan_id").n_unique().alias("unique_eins"),
                pl.col("source_index_file").first().alias("source_index_file"),
            )
            .sort(["in_scope", "plan_count"], descending=[True, True])
        )

        # Plan-file map (many-to-many)
        df_plan_file_map = df_plans_dedup.select([
            "brand", "plan_id", "plan_name", "rate_file_url", "in_scope", "scope_reason"
        ])

        # Calculate per-brand before/after counts
        brand_stats = []
        for brand in sorted(brand_raw_counts.keys()):
            raw_c = brand_raw_counts[brand]
            dedup_c = df_plans_dedup.filter(pl.col("brand") == brand).height
            in_scope_c = df_plans_dedup.filter((pl.col("brand") == brand) & (pl.col("in_scope") == True)).height
            brand_stats.append({
                "brand": brand,
                "plans_before_dedup": raw_c,
                "plans_after_dedup": dedup_c,
                "in_scope_plans": in_scope_c,
            })

        # Persist artifacts
        interim_dir = self.interim_dir
        interim_dir.mkdir(parents=True, exist_ok=True)

        plan_table_parquet = interim_dir / "deduplicated_plans.parquet"
        plan_table_csv = interim_dir / "deduplicated_plans.csv"
        file_table_parquet = interim_dir / "deduplicated_files.parquet"
        file_table_csv = interim_dir / "deduplicated_files.csv"
        plan_file_map_parquet = interim_dir / "plan_file_map.parquet"
        plan_file_map_csv = interim_dir / "plan_file_map.csv"

        df_plans_dedup.write_parquet(plan_table_parquet)
        df_plans_dedup.write_csv(plan_table_csv)
        df_files.write_parquet(file_table_parquet)
        df_files.write_csv(file_table_csv)
        df_plan_file_map.write_parquet(plan_file_map_parquet)
        df_plan_file_map.write_csv(plan_file_map_csv)

        logger.info(f"Phase 1 complete: {total_before} before dedup -> {total_after} after dedup.")

        return {
            "total_before": total_before,
            "total_after": total_after,
            "brand_stats": brand_stats,
            "df_plans": df_plans_dedup,
            "df_files": df_files,
            "df_plan_file_map": df_plan_file_map,
        }
