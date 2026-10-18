"""Streaming Rate Extraction, Provenance, and Granular Tie-Breaking Engine (Challenge C4).

Streams and expands in_network items with provider references from DuckDB.
Implements the redesigned tie-breaking and aggregation hierarchy:
  1. Base rates preferred over modifier rates (26, TC, 95, etc.)
  2. Setting matched to billing class (professional -> office/outpatient, institutional -> facility)
  3. Negotiated rates preferred over fee schedule
  4. Latest expiration date
  5. Deterministic median aggregation of remaining collision sets with rate_min, rate_max, n_source_prices.

Carries ppo_evidence_tier and review_flag (for integrated HMO networks like Kaiser).
Retains full raw price audit Parquet for 100% end-to-end traceability.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import duckdb
import ijson
import polars as pl

from ptd.config import PipelineConfig
from ptd.io_utils import get_process_memory_mb

logger = logging.getLogger("ptd.rate_extract")


class RateExtractor:
    """Streams, filters, tie-breaks, and aggregates rates with full traceability."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.raw_dir = config.raw_dir
        self.interim_dir = config.interim_dir
        self.output_dir = config.output_dir
        self.docs_dir = config.docs_dir
        self.duckdb_path = self.interim_dir / "provider_references.duckdb"

    def get_rate_file_path(self) -> Path:
        """Find target rate file dynamically via DataLocator."""
        return self.config.locator.get_path("healthnet_ca_rate_file", required=True)

    def load_provider_reference_lookup(self) -> Dict[int, List[Dict[str, Any]]]:
        con = duckdb.connect(str(self.duckdb_path), read_only=True)
        rows = con.execute("""
            SELECT provider_group_id, tin_type, tin_value, business_name, ppo_evidence_tier, npis
            FROM provider_references
        """).fetchall()
        con.close()

        lookup: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            pg_id, t_type, t_val, b_name, tier, npis = r
            if pg_id not in lookup:
                lookup[pg_id] = []
            lookup[pg_id].append({
                "tin_type": t_type,
                "tin": t_val,
                "business_name": b_name,
                "ppo_evidence_tier": tier,
                "npis": npis if npis else [0],
            })
        return lookup

    def run(self, sample_n: Optional[int] = None) -> Dict[str, Any]:
        start_t = time.time()
        start_mem = get_process_memory_mb()
        rate_file = self.get_rate_file_path()
        ref_lookup = self.load_provider_reference_lookup()

        import pyarrow as pa
        import pyarrow.parquet as pq

        schema = pa.schema([
            ("npi", pa.int64()),
            ("tin", pa.string()),
            ("business_name", pa.string()),
            ("billing_code", pa.string()),
            ("billing_code_type", pa.string()),
            ("description", pa.string()),
            ("raw_item_name", pa.string()),
            ("raw_item_description", pa.string()),
            ("negotiation_arrangement", pa.string()),
            ("negotiated_type", pa.string()),
            ("negotiated_rate", pa.float64()),
            ("billing_class", pa.string()),
            ("service_code", pa.string()),
            ("modifier", pa.string()),
            ("setting", pa.string()),
            ("additional_information", pa.string()),
            ("expiration_date", pa.string()),
            ("ppo_evidence_tier", pa.string()),
            ("npi_status", pa.string()),
            ("in_network_item_index", pa.int64()),
            ("provider_reference_id", pa.int64()),
        ])

        raw_audit_path = self.interim_dir / "raw_price_audit.parquet"
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        writer = pq.ParquetWriter(raw_audit_path, schema=schema, compression="zstd")

        batch = []
        BATCH_SIZE = 50_000
        total_raw_rows = 0
        dropped_counts = Counter()
        item_index = 0

        logger.info(f"Streaming raw prices from {rate_file.name} (sample_n={sample_n})...")

        with self.config.locator.open_readonly(rate_file, "rb") as f:
            items = ijson.items(f, "in_network.item", use_float=True)
            for item in items:
                item_index += 1
                b_code = item.get("billing_code", "")
                b_type = item.get("billing_code_type", "")
                neg_arr = item.get("negotiation_arrangement", "ffs")
                desc = item.get("description", "")
                name = item.get("name", "")

                is_capitation = (neg_arr == "capitation")

                for nr in item.get("negotiated_rates", []):
                    ref_ids = nr.get("provider_references", [])
                    neg_prices = nr.get("negotiated_prices", [])

                    for ref_id in ref_ids:
                        pg_list = ref_lookup.get(ref_id, [])
                        for pg in pg_list:
                            tier = pg["ppo_evidence_tier"]

                            for np in neg_prices:
                                rate_val = np.get("negotiated_rate")
                                n_type = np.get("negotiated_type", "negotiated")
                                b_class = np.get("billing_class", "institutional")
                                exp_date = np.get("expiration_date", "9999-12-31")
                                sc_list = np.get("service_code", ["NONE"])
                                sc = sc_list[0] if sc_list else "NONE"
                                mod_list = np.get("billing_code_modifier", [])
                                mod = mod_list[0] if mod_list else "NONE"
                                setting = np.get("setting", "outpatient")

                                add_info = np.get("additional_information", "")
                                for npi in pg["npis"]:
                                    npi_int = int(npi)
                                    batch.append({
                                        "npi": npi_int,
                                        "tin": str(pg["tin"] or ""),
                                        "business_name": str(pg["business_name"] or ""),
                                        "billing_code": str(b_code or ""),
                                        "billing_code_type": str(b_type or ""),
                                        "description": str(desc or ""),
                                        "raw_item_name": str(name or ""),
                                        "raw_item_description": str(desc or ""),
                                        "negotiation_arrangement": str(neg_arr or "ffs"),
                                        "negotiated_type": str(n_type or "negotiated"),
                                        "negotiated_rate": float(rate_val) if rate_val is not None else 0.0,
                                        "billing_class": str(b_class or "institutional"),
                                        "service_code": str(sc or "NONE"),
                                        "modifier": str(mod or "NONE"),
                                        "setting": str(setting or "outpatient"),
                                        "additional_information": str(add_info if add_info else "NONE"),
                                        "expiration_date": str(exp_date or "9999-12-31"),
                                        "ppo_evidence_tier": str(tier or "T2_shared_commercial"),
                                        "npi_status": "PLACEHOLDER_ZERO" if npi_int == 0 else "VALID_NPI",
                                        "in_network_item_index": int(item_index),
                                        "provider_reference_id": int(ref_id),
                                    })
                                    total_raw_rows += 1
                                    if len(batch) >= BATCH_SIZE:
                                        tbl = pa.Table.from_pylist(batch, schema=schema)
                                        writer.write_table(tbl)
                                        batch.clear()

                if sample_n and item_index >= sample_n:
                    break

        if batch:
            tbl = pa.Table.from_pylist(batch, schema=schema)
            writer.write_table(tbl)
            batch.clear()
        writer.close()

        logger.info(f"Extracted {total_raw_rows:,} raw expanded price records.")

        df_raw = pl.read_parquet(raw_audit_path)

        # ---------------------------------------------------------------------
        # 1. SCOPE AND VALIDITY DROPS (Logged to dropped_rows_audit.csv)
        # ---------------------------------------------------------------------
        # Capitation
        df_non_cap = df_raw.filter(pl.col("negotiation_arrangement") != "capitation")
        dropped_counts["ASSUMPTION_CAPITATION_NOT_FFS"] = df_raw.height - df_non_cap.height

        # Ambetter Market
        df_non_ambetter = df_non_cap.filter(pl.col("ppo_evidence_tier") != "EXCLUDED_AMBETTER_MARKET")
        dropped_counts["EXCLUDED_AMBETTER_MARKET"] = df_non_cap.height - df_non_ambetter.height

        # HMO Direct Networks
        df_in_scope = df_non_ambetter.filter(pl.col("ppo_evidence_tier") != "EXCLUDED_HMO_DIRECT")
        dropped_counts["EXCLUDED_HMO_DIRECT"] = df_non_ambetter.height - df_in_scope.height

        # Drop Null, $0, Negative Rates
        df_valid_rate = df_in_scope.filter(
            pl.col("negotiated_rate").is_not_null() & (pl.col("negotiated_rate") > 0.0)
        )
        dropped_counts["RULE_DROP_NULL_ZERO_NEGATIVE"] = df_in_scope.height - df_valid_rate.height

        # Drop Expired Rates
        df_unexpired = df_valid_rate.filter(
            (pl.col("expiration_date") == "9999-12-31") | (pl.col("expiration_date") >= "2026-10-17")
        )
        dropped_counts["RULE_DROP_EXPIRED"] = df_valid_rate.height - df_unexpired.height

        # ---------------------------------------------------------------------
        # 2. TIE-BREAKING PRIOR TO AGGREGATION
        # Defined on grain: npi, tin, billing_code, billing_class, billing_code_type, additional_information
        # ---------------------------------------------------------------------
        grain_keys = ["npi", "tin", "billing_code", "billing_class", "billing_code_type", "additional_information"]

        # Step 2A: Prefer base rate with NO modifier over modifier rates (26, TC, 95, etc.)
        has_base_modifier = (
            df_unexpired.group_by(grain_keys)
            .agg((pl.col("modifier") == "NONE").any().alias("has_base"))
        )
        df_mod_filtered = df_unexpired.join(has_base_modifier, on=grain_keys).filter(
            ~pl.col("has_base") | (pl.col("modifier") == "NONE")
        ).drop("has_base")
        dropped_counts["RULE_PREFER_BASE_MODIFIER"] = df_unexpired.height - df_mod_filtered.height

        # Step 2B: Prefer service_code (place of service) matching billing class
        # Note: setting in this file is 100% 'outpatient'; this rule filters service_code (POS)
        # Professional -> prefer Office (POS 11) or Outpatient Clinic (POS 22, 02)
        # Institutional -> prefer facility settings (POS 22, 23)
        def is_preferred_service_code(b_class: str, sc: str) -> bool:
            if b_class == "professional":
                return sc in ("11", "22", "02")
            return sc in ("22", "23")

        df_with_pref_sc = df_mod_filtered.with_columns(
            pl.struct(["billing_class", "service_code"]).map_elements(
                lambda s: is_preferred_service_code(s["billing_class"], s["service_code"]),
                return_dtype=pl.Boolean,
            ).alias("is_pref_sc")
        )
        has_pref_sc = (
            df_with_pref_sc.group_by(grain_keys)
            .agg(pl.col("is_pref_sc").any().alias("has_pref"))
        )
        df_sc_filtered = df_with_pref_sc.join(has_pref_sc, on=grain_keys).filter(
            ~pl.col("has_pref") | pl.col("is_pref_sc")
        ).drop(["is_pref_sc", "has_pref"])
        dropped_counts["RULE_PREFER_CLASS_MATCHED_SERVICE_CODE"] = df_mod_filtered.height - df_sc_filtered.height

        # Step 2C: Prefer negotiated over fee schedule
        has_neg = (
            df_sc_filtered.group_by(grain_keys)
            .agg((pl.col("negotiated_type") == "negotiated").any().alias("has_negotiated"))
        )
        df_neg_filtered = df_sc_filtered.join(has_neg, on=grain_keys).filter(
            ~pl.col("has_negotiated") | (pl.col("negotiated_type") == "negotiated")
        ).drop("has_negotiated")
        dropped_counts["RULE_PREFER_NEGOTIATED_OVER_FEE_SCHEDULE"] = df_sc_filtered.height - df_neg_filtered.height

        # Step 2D: Latest expiration date
        df_latest_exp = (
            df_neg_filtered.group_by(grain_keys)
            .agg(pl.col("expiration_date").max().alias("max_exp"))
            .join(df_neg_filtered, on=grain_keys)
            .filter(pl.col("expiration_date") == pl.col("max_exp"))
            .drop("max_exp")
        )
        dropped_counts["RULE_LATEST_EXPIRATION"] = df_neg_filtered.height - df_latest_exp.height

        # ---------------------------------------------------------------------
        # 3. AGGREGATION STAGE (Distinct Grain Resolution)
        # ---------------------------------------------------------------------
        def assign_review_flag(b_name: str) -> str:
            upper = (b_name or "").upper()
            if "KAISER" in upper or "PERMANENTE" in upper:
                return "POTENTIAL_INTEGRATED_HMO_KAISER"
            elif "IPA" in upper or "ALLIANCE" in upper:
                return "POTENTIAL_INTEGRATED_IPA"
            return "STANDARD_COMMERCIAL"

        resolved_rates = (
            df_latest_exp.group_by(grain_keys)
            .agg([
                pl.col("negotiated_rate").median().alias("rate_selected"),
                pl.col("negotiated_rate").mean().alias("rate_mean"),
                pl.col("negotiated_rate").min().alias("rate_min"),
                pl.col("negotiated_rate").max().alias("rate_max"),
                pl.len().alias("n_source_prices"),
                pl.col("business_name").first().alias("business_name"),
                pl.col("description").first().alias("description"),
                pl.col("raw_item_name").first().alias("raw_item_name"),
                pl.col("raw_item_description").first().alias("raw_item_description"),
                pl.col("negotiation_arrangement").first().alias("negotiation_arrangement"),
                pl.col("negotiated_type").first().alias("negotiated_type"),
                pl.col("service_code").first().alias("service_code_used"),
                pl.col("modifier").first().alias("modifier_used"),
                pl.col("setting").first().alias("setting"),
                pl.col("expiration_date").first().alias("expiration_date"),
                pl.col("ppo_evidence_tier").first().alias("ppo_evidence_tier"),
                pl.col("in_network_item_index").first().alias("in_network_item_index"),
                pl.col("provider_reference_id").first().alias("provider_reference_id"),
            ])
            .with_columns(
                pl.when(pl.col("n_source_prices") == 1)
                .then(pl.lit("EXACT_UNIQUE_MATCH"))
                .when(pl.col("rate_min") == pl.col("rate_max"))
                .then(pl.lit("IDENTICAL_MULTI_PRICE_MATCH"))
                .otherwise(pl.lit("MEDIAN_COLLISION_RESOLVED"))
                .alias("selection_rule"),
                pl.when(pl.col("rate_min") > 0.0)
                .then(pl.col("rate_max") / pl.col("rate_min"))
                .otherwise(1.0)
                .alias("rate_spread_ratio"),
                pl.when(pl.col("npi") == 0)
                .then(pl.lit("PLACEHOLDER_ZERO"))
                .otherwise(pl.lit("VALID_NPI"))
                .alias("npi_status"),
                pl.col("business_name").map_elements(assign_review_flag, return_dtype=pl.String).alias("review_flag"),
            )
            .with_columns(
                (pl.col("rate_spread_ratio") > 3.0).alias("spread_flag")
            )
        )

        # ---------------------------------------------------------------------
        # 4. AUDIT TABLES & PERSISTENCE
        # ---------------------------------------------------------------------
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        parquet_path = self.interim_dir / "extracted_rates.parquet"
        resolved_rates.write_parquet(parquet_path)

        # Dropped rows audit
        df_dropped = pl.DataFrame([
            {"rule_or_exclusion_reason": k, "rows_removed_count": v}
            for k, v in dropped_counts.items()
        ])
        df_dropped.write_csv(self.output_dir / "dropped_rows_audit.csv")

        # Aggregation stage audit
        rule_agg_counts = resolved_rates.group_by("selection_rule").len()
        df_agg_audit = rule_agg_counts.rename({"len": "resolved_keys_count"})
        df_agg_audit.write_csv(self.output_dir / "aggregation_stage_audit.csv")

        # Top 25 Kaiser/IPA review-flag list by rate rows count
        top25_flags = (
            resolved_rates.filter(pl.col("review_flag") != "STANDARD_COMMERCIAL")
            .group_by(["tin", "business_name", "review_flag"])
            .agg(pl.len().alias("rate_rows_count"))
            .sort("rate_rows_count", descending=True)
            .head(25)
        )
        top25_flags.write_csv(self.docs_dir / "review_flags_top25.csv")

        # Stratified 25 Sample Rows for Verification Trace
        # Include at least 5 T1 rows and 2 modifier rows
        t1_sample = resolved_rates.filter(pl.col("ppo_evidence_tier") == "T1_name_hint_ppo").head(5)
        mod_sample = resolved_rates.filter(pl.col("modifier_used") != "NONE").head(4)
        prof_sample = resolved_rates.filter(
            (pl.col("billing_class") == "professional") & (pl.col("ppo_evidence_tier") == "T2_shared_commercial")
        ).head(8)
        inst_sample = resolved_rates.filter(
            (pl.col("billing_class") == "institutional") & (pl.col("ppo_evidence_tier") == "T2_shared_commercial")
        ).head(8)

        sample_25 = pl.concat([t1_sample, mod_sample, prof_sample, inst_sample]).unique(
            subset=grain_keys
        ).head(25)
        if sample_25.height < 25:
            remaining = resolved_rates.filter(~pl.col("billing_code").is_in(sample_25["billing_code"])).head(25 - sample_25.height)
            sample_25 = pl.concat([sample_25, remaining])

        sample_csv = self.output_dir / "extracted_rates_sample.csv"
        sample_25.write_csv(sample_csv)

        # Build full docs/trace_report.csv with ALL raw candidate prices feeding each
        trace_rows = []
        for s_row in sample_25.iter_rows(named=True):
            k_npi = s_row["npi"]
            k_tin = s_row["tin"]
            k_code = s_row["billing_code"]
            k_class = s_row["billing_class"]
            k_type = s_row["billing_code_type"]
            k_add_info = s_row.get("additional_information", "NONE")

            # Filter raw records feeding this key
            raw_feed = df_raw.filter(
                (pl.col("npi") == k_npi)
                & (pl.col("tin") == k_tin)
                & (pl.col("billing_code") == k_code)
                & (pl.col("billing_class") == k_class)
                & (pl.col("billing_code_type") == k_type)
                & (pl.col("additional_information") == k_add_info)
                & (pl.col("negotiation_arrangement") != "capitation")
                & (pl.col("ppo_evidence_tier").is_in(["T1_name_hint_ppo", "T2_shared_commercial"]))
            )

            raw_prices_summary = "; ".join([
                f"${r:.2f} (POS:{sc}, Mod:{m}, Set:{st})"
                for r, sc, m, st in zip(
                    raw_feed["negotiated_rate"].to_list(),
                    raw_feed["service_code"].to_list(),
                    raw_feed["modifier"].to_list(),
                    raw_feed["setting"].to_list(),
                )
            ])

            trace_rows.append({
                "in_network_item_index": s_row["in_network_item_index"],
                "provider_reference_id": s_row["provider_reference_id"],
                "tin": s_row["tin"],
                "business_name": s_row["business_name"],
                "npi": s_row["npi"],
                "billing_code": s_row["billing_code"],
                "billing_class": s_row["billing_class"],
                "additional_information": k_add_info,
                "ppo_evidence_tier": s_row["ppo_evidence_tier"],
                "n_source_prices": s_row["n_source_prices"],
                "selection_rule": s_row["selection_rule"],
                "modifier_used": s_row["modifier_used"],
                "service_code_used": s_row["service_code_used"],
                "rate_selected": s_row["rate_selected"],
                "rate_mean": s_row["rate_mean"],
                "rate_spread_ratio": s_row["rate_spread_ratio"],
                "spread_flag": s_row["spread_flag"],
                "raw_prices_feeding_key": raw_prices_summary,
            })

        df_trace_report = pl.DataFrame(trace_rows)
        df_trace_report.write_csv(self.docs_dir / "trace_report.csv")

        dur = time.time() - start_t
        mem_peak = get_process_memory_mb() - start_mem
        logger.info(f"Rate extraction complete: {resolved_rates.height:,} distinct provider rates in {dur:.2f}s.")

        tier_counts = resolved_rates.group_by("ppo_evidence_tier").len()

        return {
            "total_raw_rows": total_raw_rows,
            "total_resolved_rates": resolved_rates.height,
            "unique_codes": resolved_rates["billing_code"].n_unique(),
            "unique_npis": resolved_rates["npi"].n_unique(),
            "unique_tins": resolved_rates["tin"].n_unique(),
            "tier_counts": dict(zip(tier_counts["ppo_evidence_tier"].to_list(), tier_counts["len"].to_list())),
            "dropped_counts": dict(dropped_counts),
            "df_rates": resolved_rates,
            "df_dropped": df_dropped,
            "df_agg_audit": df_agg_audit,
            "sample_25": sample_25,
            "runtime_s": dur,
            "memory_delta_mb": mem_peak,
        }
