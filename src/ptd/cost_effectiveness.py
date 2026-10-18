"""PTD Cost-Effectiveness Provider Frontier.

Evaluates price competitiveness across peer groups:
Peer Group = (billing_code, billing_class, npi_type, specialty, geography).
Geography = 3-digit California Zip Region prefix -> widened to CA_STATEWIDE fallback.
Minimum peer count = 10 providers.
Excludes rate_reliability LOW and review-flagged integrated-HMO rows from peer statistics.
Produces provider-code metrics and provider-level efficiency indices.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import openpyxl
import polars as pl

from ptd.config import PipelineConfig

logger = logging.getLogger("ptd.cost_effectiveness")


def map_zip5_to_region(zip5: Optional[str]) -> str:
    """Map 5-digit California ZIP code to standard regional healthcare market prefix."""
    if not zip5 or len(str(zip5).strip()) < 3:
        return "UNKNOWN_REGION"
    p = str(zip5).strip()[:3]
    if p in ("900", "901", "902", "903", "904", "905", "906", "907", "908", "910", "911", "912", "913", "914", "915", "916", "917", "918"):
        return "LOS_ANGELES_METRO"
    elif p in ("919", "920", "921"):
        return "SAN_DIEGO_METRO"
    elif p in ("922", "923", "924", "925"):
        return "INLAND_EMPIRE"
    elif p in ("926", "927", "928"):
        return "ORANGE_COUNTY"
    elif p in ("930", "931", "932", "933", "934", "935"):
        return "CENTRAL_COAST_VALLEY"
    elif p in ("936", "937", "938"):
        return "FRESNO_CENTRAL"
    elif p == "939":
        return "MONTEREY_SALINAS"
    elif p in ("940", "941", "942", "943", "944"):
        return "SAN_FRANCISCO_PENINSULA"
    elif p in ("945", "946", "947", "948"):
        return "EAST_BAY_OAKLAND"
    elif p in ("949", "950", "951", "952", "953", "954", "955"):
        return "SAN_JOSE_NORTH_COAST"
    elif p in ("956", "957", "958", "959", "960", "961"):
        return "SACRAMENTO_NORTH_CA"
    return "CA_OTHER"


class CostEffectivenessAnalyzer:
    """Computes price competitiveness metrics and provider-level efficiency index."""

    def __init__(self, config: PipelineConfig, min_peers: int = 10, min_codes_for_provider_index: int = 3):
        self.config = config
        self.min_peers = min_peers
        self.min_codes_for_provider_index = min_codes_for_provider_index
        self.output_dir = config.output_dir
        self.reference_dir = config.reference_dir
        self.spec_proc_weights: Dict[Tuple[str, str], float] = {}
        self.load_hilabs_weights()

    def load_hilabs_weights(self):
        """Load procedure benchmarking weights from HiLabs workbook."""
        wb_path = self.config.locator.get_path("hilabs_workbook", required=False)
        if not wb_path or not wb_path.exists():
            return
        try:
            wb = openpyxl.load_workbook(wb_path, data_only=True)
            if "Spec-Proc Weights" in wb.sheetnames:
                ws = wb["Spec-Proc Weights"]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row and row[0] and row[2]:
                        spec_cd = str(row[0]).strip().upper()
                        proc_cd = str(row[2]).strip().upper()
                        wt = float(row[4]) if len(row) > 4 and row[4] is not None else 1.0
                        self.spec_proc_weights[(spec_cd, proc_cd)] = wt
        except Exception as e:
            logger.warning(f"Error loading HiLabs procedure weights: {e}")

    def run_analysis(self, df_final: pl.DataFrame) -> Dict[str, Any]:
        """Compute provider-code and provider-level price competitiveness frontier at curated-key grain."""
        logger.info(f"Starting cost-effectiveness analysis on incoming {df_final.height:,} deliverable rows...")

        # Filter strictly to primary address rows (21,608 curated rate keys)
        # Prevents multi-site secondary locations from inflating peer counts
        if "is_primary_address" in df_final.columns:
            df = df_final.filter(pl.col("is_primary_address") == True).with_columns(
                pl.col("zip5").map_elements(map_zip5_to_region, return_dtype=pl.String).alias("geography_region")
            )
        else:
            df = df_final.with_columns(
                pl.col("zip5").map_elements(map_zip5_to_region, return_dtype=pl.String).alias("geography_region")
            )

        n_primary_keys = df.height
        logger.info(f"Scoped C7 analysis strictly to {n_primary_keys:,} primary curated rate keys (1:1 with contract keys).")

        # Baseline peer qualification: exclude LOW reliability and integrated HMO from peer baseline
        low_rel_count = df.filter(pl.col("rate_reliability") == "LOW").height
        int_hmo_count = df.filter(pl.col("review_flag").str.contains("INTEGRATED_HMO")).height

        peer_eligible_df = df.filter(
            (pl.col("rate_reliability") != "LOW")
            & (~pl.col("review_flag").str.contains("INTEGRATED_HMO"))
            & (pl.col("Rate") > 0)
        )
        logger.info(
            f"Peer cohort qualification: {peer_eligible_df.height:,} qualified peer contracts "
            f"({low_rel_count:,} excluded for LOW reliability, {int_hmo_count:,} excluded for INTEGRATED_HMO)."
        )

        # Collect peer rates at (code, class, npi_type, specialty, region) level
        local_peers: Dict[Tuple[str, str, int, str, str], List[float]] = defaultdict(list)
        state_peers: Dict[Tuple[str, str, int, str], List[float]] = defaultdict(list)

        for row in peer_eligible_df.iter_rows(named=True):
            code = str(row["Billing Code"])
            b_class = str(row["billing_class"])
            npi_type = int(row["npi_type"]) if row["npi_type"] is not None else 1
            spec = str(row["Specialty"])
            geo = str(row["geography_region"])
            rate = float(row["Rate"])

            local_peers[(code, b_class, npi_type, spec, geo)].append(rate)
            state_peers[(code, b_class, npi_type, spec)].append(rate)

        # Precompute peer distribution statistics
        def get_dist_stats(rates: List[float]) -> Dict[str, float]:
            if not rates:
                return {}
            arr = np.array(rates, dtype=float)
            med = float(np.median(arr))
            log_arr = np.log(np.clip(arr, 0.001, None))
            log_med = float(np.median(log_arr))
            mad = float(np.median(np.abs(log_arr - log_med)))
            return {
                "median": med,
                "count": len(rates),
                "log_median": log_med,
                "mad": mad if mad > 0 else 0.001,
                "all_rates": sorted(rates),
            }

        local_stats = {k: get_dist_stats(v) for k, v in local_peers.items()}
        state_stats = {k: get_dist_stats(v) for k, v in state_peers.items()}

        # Score every row in df
        scored_rows = []
        for row in df.iter_rows(named=True):
            code = str(row["Billing Code"])
            b_class = str(row["billing_class"])
            npi_type = int(row["npi_type"]) if row["npi_type"] is not None else 1
            spec = str(row["Specialty"])
            geo = str(row["geography_region"])
            rate = float(row["Rate"])

            local_key = (code, b_class, npi_type, spec, geo)
            state_key = (code, b_class, npi_type, spec)

            stats = local_stats.get(local_key)
            peer_level = "REGIONAL"

            if not stats or stats["count"] < self.min_peers:
                # Fallback to statewide
                stats = state_stats.get(state_key)
                peer_level = "STATEWIDE"

            if stats and stats["count"] >= self.min_peers:
                p_med = stats["median"]
                p_cnt = stats["count"]
                ratio = round(rate / p_med, 4) if p_med > 0 else 1.0

                # Percentile rank
                all_r = stats["all_rates"]
                pct_rank = round(float(np.searchsorted(all_r, rate, side="right") / len(all_r) * 100.0), 2)

                # Robust z-score on log(rate)
                log_r = math.log(max(0.001, rate))
                mad_z = round((log_r - stats["log_median"]) / (1.4826 * stats["mad"]), 3)
                is_scoreable = True
            else:
                p_med = None
                p_cnt = stats["count"] if stats else 0
                ratio = None
                pct_rank = None
                mad_z = None
                peer_level = "INSUFFICIENT_PEERS"
                is_scoreable = False

            scored_rows.append({
                **row,
                "geography_region": geo,
                "peer_level": peer_level,
                "peer_count": p_cnt,
                "peer_median_rate": p_med,
                "rate_to_peer_median": ratio,
                "percentile_rank": pct_rank,
                "mad_robust_zscore": mad_z,
                "is_scoreable": is_scoreable,
            })

        df_scored = pl.DataFrame(scored_rows)

        # Provider-Level Efficiency Index
        # Weighted median of code-level ratios for each provider (NPI, TIN)
        provider_scores: Dict[Tuple[Any, str], List[Tuple[float, float]]] = defaultdict(list)
        for r in df_scored.filter(pl.col("is_scoreable") == True).iter_rows(named=True):
            npi_val = r["NPI"]
            tin_val = r["TIN"]
            spec = r["Specialty"]
            code = str(r["Billing Code"])
            ratio = r["rate_to_peer_median"]
            wt = self.spec_proc_weights.get((spec, code), 1.0)
            provider_scores[(npi_val, tin_val)].append((ratio, wt))

        provider_index_map = {}
        for (npi_val, tin_val), items in provider_scores.items():
            if len(items) >= self.min_codes_for_provider_index:
                ratios = [it[0] for it in items]
                wts = [it[1] for it in items]
                # Weighted median
                sorted_idx = np.argsort(ratios)
                sorted_ratios = np.array(ratios)[sorted_idx]
                sorted_wts = np.array(wts)[sorted_idx]
                cum_wts = np.cumsum(sorted_wts)
                cutoff = cum_wts[-1] / 2.0
                med_idx = np.searchsorted(cum_wts, cutoff)
                prov_index = round(float(sorted_ratios[med_idx]), 4)
                provider_index_map[(npi_val, tin_val)] = (prov_index, len(items))

        # Join provider index back to df_scored
        prov_indices = []
        prov_n_codes = []
        for r in df_scored.iter_rows(named=True):
            p_key = (r["NPI"], r["TIN"])
            if p_key in provider_index_map:
                prov_indices.append(provider_index_map[p_key][0])
                prov_n_codes.append(provider_index_map[p_key][1])
            else:
                prov_indices.append(None)
                prov_n_codes.append(0)

        df_scored = df_scored.with_columns([
            pl.Series("provider_efficiency_index", prov_indices),
            pl.Series("provider_scored_codes_count", prov_n_codes),
        ])

        # Write output deliverables
        parquet_out = self.output_dir / "cost_effectiveness.parquet"
        csv_out = self.output_dir / "cost_effectiveness.csv"
        df_scored.write_parquet(parquet_out)
        df_scored.write_csv(csv_out)
        logger.info(f"Exported cost-effectiveness analysis: {parquet_out} ({df_scored.height:,} rows)")

        # Export stratified sample of 25 rows for C7 price competitiveness audit
        sample_cols = [
            c for c in [
                "NPI", "TIN", "tin_canonical_name", "Billing Code", "Specialty", "Rate",
                "geography_region", "peer_level", "peer_count", "peer_median_rate",
                "rate_to_peer_median", "percentile_rank", "mad_robust_zscore",
                "provider_efficiency_index", "provider_scored_codes_count"
            ] if c in df_scored.columns
        ]
        s_reg_low = df_scored.filter((pl.col("peer_level") == "REGIONAL") & (pl.col("rate_to_peer_median") < 0.90)).head(5)
        s_reg_med = df_scored.filter((pl.col("peer_level") == "REGIONAL") & (pl.col("rate_to_peer_median") >= 0.95) & (pl.col("rate_to_peer_median") <= 1.05)).head(5)
        s_reg_high = df_scored.filter((pl.col("peer_level") == "REGIONAL") & (pl.col("rate_to_peer_median") > 1.20)).head(5)
        s_state = df_scored.filter(pl.col("peer_level") == "STATEWIDE").head(5)
        s_insuf = df_scored.filter(pl.col("peer_level") == "INSUFFICIENT_PEERS").head(5)
        sample_df = pl.concat([s_reg_low, s_reg_med, s_reg_high, s_state, s_insuf]).select(sample_cols)
        sample_df.write_csv(self.output_dir / "sample_c7_scores.csv")
        logger.info(f"Exported C7 audit sample: {self.output_dir / 'sample_c7_scores.csv'} ({sample_df.height} rows)")

        # Summary statistics
        total_rows = df_scored.height
        scoreable_rows = df_scored.filter(pl.col("is_scoreable") == True).height
        regional_rows = df_scored.filter(pl.col("peer_level") == "REGIONAL").height
        statewide_rows = df_scored.filter(pl.col("peer_level") == "STATEWIDE").height
        insufficient_rows = df_scored.filter(pl.col("peer_level") == "INSUFFICIENT_PEERS").height
        providers_with_index = len(provider_index_map)

        return {
            "total_rows": total_rows,
            "scoreable_rows": scoreable_rows,
            "scoreable_pct": round(scoreable_rows / total_rows * 100.0, 2),
            "regional_peers_count": regional_rows,
            "regional_peers_pct": round(regional_rows / total_rows * 100.0, 2),
            "statewide_fallback_count": statewide_rows,
            "statewide_fallback_pct": round(statewide_rows / total_rows * 100.0, 2),
            "insufficient_peers_count": insufficient_rows,
            "insufficient_peers_pct": round(insufficient_rows / total_rows * 100.0, 2),
            "providers_with_index_count": providers_with_index,
            "parquet_path": parquet_out,
            "csv_path": csv_out,
            "df_scored": df_scored,
        }
