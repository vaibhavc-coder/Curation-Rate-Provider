"""Streaming profiler and parser for Price Transparency Rate Files (TiC v2.0.0).

Processes large rate JSON files (670+ MB) strictly via streaming (ijson with yajl2_c backend),
maintaining low memory footprints (<150 MB RAM) by utilizing disk-backed DuckDB / Parquet indexing.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import duckdb
import ijson
import polars as pl

from ptd.config import PipelineConfig
from ptd.io_utils import get_ijson_backend_info, get_process_memory_mb

logger = logging.getLogger("ptd.rate_stream")


class RateStreamProfiler:
    """Streams and profiles rate files without full-file deserialization."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.raw_dir = config.raw_dir
        self.interim_dir = config.interim_dir
        self.output_dir = config.output_dir
        self.duckdb_path = self.interim_dir / "provider_references.duckdb"

    def get_rate_file_path(self) -> Path:
        """Find the target rate file dynamically from config pattern or fallback."""
        pat = self.config.scope.get("rate_file_pattern", "*healthnet-ca*.json") if isinstance(self.config.scope, dict) else "*healthnet-ca*.json"
        candidates = list(self.raw_dir.glob(pat))
        if not candidates:
            candidates = list(self.raw_dir.glob("*healthnet-ca*.json"))
        if not candidates:
            candidates = list(self.raw_dir.glob("*in-network*.json"))
        if not candidates:
            raise FileNotFoundError(f"Rate file not found in {self.raw_dir}")
        return candidates[0]

    def index_provider_references(self, rate_file: Path) -> Dict[str, Any]:
        """First pass / top-level stream: index provider_references into DuckDB & Parquet."""
        start_t = time.time()
        start_mem = get_process_memory_mb()
        logger.info(f"Indexing provider_references from {rate_file.name} into DuckDB...")

        if self.duckdb_path.exists():
            self.duckdb_path.unlink()

        con = duckdb.connect(str(self.duckdb_path))
        con.execute("""
            CREATE TABLE provider_references (
                provider_group_id INTEGER,
                tin_type VARCHAR,
                tin_value VARCHAR,
                business_name VARCHAR,
                ppo_evidence_tier VARCHAR,
                npis BIGINT[]
            )
        """)

        def classify_group_evidence_tier(b_name: str) -> str:
            b_upper = (b_name or "").upper()
            if "AMBETTER" in b_upper:
                return "EXCLUDED_AMBETTER_MARKET"
            if "HMO" in b_upper and "PPO" not in b_upper:
                return "EXCLUDED_HMO_DIRECT"
            if "PPO" in b_upper:
                return "T1_name_hint_ppo"
            return "T2_shared_commercial"

        all_keys_seen = set()
        tin_types = Counter()
        network_names_found = set()
        npi_counts_per_group = []
        total_references = 0
        total_provider_group_records = 0
        records_to_insert = []

        batch_size = 500
        with open(rate_file, "rb") as f:
            items = ijson.items(f, "provider_references.item", use_float=True)
            for r in items:
                total_references += 1
                all_keys_seen.update(r.keys())
                pg_id = r.get("provider_group_id")
                net_name = r.get("network_name", [])
                if net_name:
                    if isinstance(net_name, list):
                        network_names_found.update(net_name)
                    else:
                        network_names_found.add(str(net_name))

                for pg in r.get("provider_groups", []):
                    total_provider_group_records += 1
                    tin_info = pg.get("tin", {})
                    t_type = tin_info.get("type", "unknown")
                    t_val = tin_info.get("value", "")
                    b_name = tin_info.get("business_name", "")
                    tin_types[t_type] += 1

                    tier = classify_group_evidence_tier(b_name)
                    npis = pg.get("npi", [])
                    npi_counts_per_group.append(len(npis))
                    records_to_insert.append((pg_id, t_type, t_val, b_name, tier, npis))

                    if len(records_to_insert) >= batch_size:
                        con.executemany(
                            "INSERT INTO provider_references VALUES (?, ?, ?, ?, ?, ?)",
                            records_to_insert,
                        )
                        records_to_insert = []

        if records_to_insert:
            con.executemany(
                "INSERT INTO provider_references VALUES (?, ?, ?, ?, ?, ?)",
                records_to_insert,
            )

        # Create indexes in DuckDB
        con.execute("CREATE INDEX idx_ref_id ON provider_references (provider_group_id)")
        con.execute("CREATE INDEX idx_tin_val ON provider_references (tin_value)")

        # Export to Parquet for fast columnar analysis
        parquet_path = self.interim_dir / "provider_references.parquet"
        con.execute(f"COPY provider_references TO '{parquet_path}' (FORMAT PARQUET)")

        # Aggregate stats via DuckDB
        summary = con.execute("""
            SELECT 
                COUNT(DISTINCT provider_group_id) as unique_ref_ids,
                COUNT(DISTINCT tin_value) as unique_tins,
                COUNT(*) as total_groups
            FROM provider_references
        """).fetchone()

        dur = time.time() - start_t
        mem_peak = get_process_memory_mb() - start_mem
        logger.info(f"Indexed {total_references} provider references ({summary[1]} unique TINs) in {dur:.2f}s.")

        npi_series = pl.Series(npi_counts_per_group) if npi_counts_per_group else pl.Series([0])

        con.close()

        return {
            "total_references": total_references,
            "unique_reference_ids": summary[0],
            "unique_tins": summary[1],
            "total_provider_groups": summary[2],
            "tin_types_distribution": dict(tin_types),
            "network_names_found": list(network_names_found),
            "all_keys_seen": list(all_keys_seen),
            "npi_stats": {
                "min": int(npi_series.min()),
                "median": float(npi_series.median()),
                "mean": float(npi_series.mean()),
                "max": int(npi_series.max()),
                "p95": float(npi_series.quantile(0.95)),
            },
            "runtime_s": dur,
            "memory_delta_mb": mem_peak,
        }

    def profile_in_network(self, rate_file: Path, sample_n: Optional[int] = None) -> Dict[str, Any]:
        """Stream profile the in_network array with deep inspection of all nested keys."""
        start_t = time.time()
        start_mem = get_process_memory_mb()
        logger.info(f"Profiling in_network items from {rate_file.name} (sample_n={sample_n})...")

        billing_code_types = Counter()
        negotiation_arrangements = Counter()
        negotiated_types = Counter()
        billing_classes = Counter()
        expiration_dates = Counter()
        service_codes = Counter()
        modifier_usage = Counter()

        item_keys_seen = set()
        rates_keys_seen = set()
        price_keys_seen = set()

        total_items = 0
        total_negotiated_rates = 0
        total_price_entries = 0
        zero_or_negative_rates = 0
        null_rates = 0
        items_with_provider_refs = 0
        items_with_inline_groups = 0

        rate_values = []
        distinct_codes = set()

        with open(rate_file, "rb") as f:
            items = ijson.items(f, "in_network.item", use_float=True)
            for item in items:
                total_items += 1
                item_keys_seen.update(item.keys())

                b_type = item.get("billing_code_type", "UNKNOWN")
                b_code = item.get("billing_code", "")
                neg_arr = item.get("negotiation_arrangement", "UNKNOWN")

                billing_code_types[b_type] += 1
                negotiation_arrangements[neg_arr] += 1
                distinct_codes.add(b_code)

                for nr in item.get("negotiated_rates", []):
                    total_negotiated_rates += 1
                    rates_keys_seen.update(nr.keys())

                    has_refs = bool(nr.get("provider_references"))
                    has_groups = bool(nr.get("provider_groups"))
                    if has_refs:
                        items_with_provider_refs += 1
                    if has_groups:
                        items_with_inline_groups += 1

                    for np in nr.get("negotiated_prices", []):
                        total_price_entries += 1
                        price_keys_seen.update(np.keys())

                        n_type = np.get("negotiated_type", "UNKNOWN")
                        b_class = np.get("billing_class", "UNKNOWN")
                        exp_date = np.get("expiration_date", "MISSING")
                        rate_val = np.get("negotiated_rate")

                        negotiated_types[n_type] += 1
                        billing_classes[b_class] += 1
                        expiration_dates[exp_date] += 1

                        if rate_val is None:
                            null_rates += 1
                        elif rate_val <= 0.0:
                            zero_or_negative_rates += 1
                        else:
                            # sample rate values for distribution
                            if len(rate_values) < 50000:
                                rate_values.append(rate_val)

                        # Modifiers
                        mods = np.get("billing_code_modifier", [])
                        if mods:
                            for m in mods:
                                modifier_usage[m] += 1
                        else:
                            modifier_usage["NONE"] += 1

                        # Service code
                        scs = np.get("service_code", [])
                        if scs:
                            for sc in scs:
                                service_codes[sc] += 1
                        else:
                            service_codes["NONE"] += 1

                if sample_n and total_items >= sample_n:
                    logger.info(f"Reached sample limit of {sample_n} in_network items.")
                    break

        dur = time.time() - start_t
        mem_peak = get_process_memory_mb() - start_mem
        logger.info(f"Profiled {total_items} in_network items ({total_price_entries} prices) in {dur:.2f}s.")

        rates_s = pl.Series(rate_values) if rate_values else pl.Series([0.0])

        return {
            "sample_mode": sample_n is not None,
            "sample_n": sample_n,
            "total_in_network_items": total_items,
            "unique_billing_codes": len(distinct_codes),
            "total_negotiated_rates": total_negotiated_rates,
            "total_price_entries": total_price_entries,
            "items_with_provider_refs": items_with_provider_refs,
            "items_with_inline_groups": items_with_inline_groups,
            "zero_or_negative_rates": zero_or_negative_rates,
            "null_rates": null_rates,
            "zero_share_pct": (zero_or_negative_rates / total_price_entries * 100) if total_price_entries > 0 else 0.0,
            "billing_code_types": dict(billing_code_types),
            "negotiation_arrangements": dict(negotiation_arrangements),
            "negotiated_types": dict(negotiated_types),
            "billing_classes": dict(billing_classes),
            "top_expiration_dates": dict(expiration_dates.most_common(10)),
            "top_service_codes": dict(service_codes.most_common(10)),
            "modifier_usage": dict(modifier_usage.most_common(10)),
            "all_level_keys": {
                "in_network_item_keys": sorted(list(item_keys_seen)),
                "negotiated_rates_keys": sorted(list(rates_keys_seen)),
                "negotiated_prices_keys": sorted(list(price_keys_seen)),
            },
            "rate_stats": {
                "min": float(rates_s.min()),
                "median": float(rates_s.median()),
                "mean": float(rates_s.mean()),
                "max": float(rates_s.max()),
                "p95": float(rates_s.quantile(0.95)),
            },
            "runtime_s": dur,
            "memory_delta_mb": mem_peak,
        }

    def run(self, sample_n: Optional[int] = None) -> Dict[str, Any]:
        """Run complete Phase 3 profiling pass."""
        rate_file = self.get_rate_file_path()
        backend_info = get_ijson_backend_info()

        # Step 1: Provider references indexing
        ref_profile = self.index_provider_references(rate_file)

        # Step 2: in_network profiling
        in_network_profile = self.profile_in_network(rate_file, sample_n=sample_n)

        # Combine into profile report
        profile_report = {
            "rate_file_name": rate_file.name,
            "file_size_mb": round(rate_file.stat().st_size / (1024 * 1024), 2),
            "ijson_backend": backend_info["active_backend"],
            "top_level_keys": [
                "reporting_entity_name",
                "reporting_entity_type",
                "version",
                "last_updated_on",
                "provider_references",
                "in_network",
            ],
            "provider_references_profile": ref_profile,
            "in_network_profile": in_network_profile,
        }

        # Save profile report to json
        out_json = self.output_dir / "rate_file_profile.json"
        with open(out_json, "w") as f:
            json.dump(profile_report, f, indent=2)

        logger.info(f"Phase 3 profiling complete. Results saved to {out_json}")
        return profile_report
