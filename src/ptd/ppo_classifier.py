"""Explainable, rule-based PPO Network Classifier.

Classifies healthcare plan names into PPO, HMO, EPO, POS, Conflict, or Unknown.
Generates comprehensive audit trails with rule IDs, confidence scores, and evidence lists.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import polars as pl

from ptd.config import PipelineConfig

logger = logging.getLogger("ptd.ppo_classifier")


# Regex patterns with false-positive guards
# Guard against DEPOT, EPOCH, EPOXY: must be preceded by boundary or non-letter, and followed by non-letter, $, digits, or boundary
REGEX_EPO = re.compile(r"\bEPO\b|(?<=[^A-Za-z])EPO(?=[\$0-9\/]|\b)|^EPO(?=[\$0-9\/]|\b)", re.IGNORECASE)

# Standalone or glued PPO: \bPPO\b, Preferred Provider Organization, or CUSPPO, guarded against words like HIPPO/OPPOSITION
REGEX_PPO = re.compile(r"\b(PPO|PREFERRED PROVIDER ORGANIZATION)\b|(?<=\bCUS)PPO\b|\bCUSPPO\b", re.IGNORECASE)

# Standalone POS: \bPOS\b, guard strictly against POST, POST DOC, DEPOSIT, POSITION
REGEX_POS = re.compile(r"\b(POS|POINT OF SERVICE)\b", re.IGNORECASE)

# Standalone HMO or full term
REGEX_HMO = re.compile(r"\b(HMO|HEALTH MAINTENANCE ORGANIZATION)\b", re.IGNORECASE)

# Known HMO product families
HMO_FAMILIES = [
    "WHOLECARE",
    "SMARTCARE",
    "SALUD",
    "FULL NETWORK",
    "CALCHOICE",
    "COMMUNITYCARE",
]

# Metal tiers
METAL_TIERS = ["PLATINUM", "GOLD", "SILVER", "BRONZE", "BRZ", "GLD", "SVR"]


class NetworkClassificationResult:
    """Container for single plan classification decision."""

    def __init__(
        self,
        label: str,
        confidence: float,
        evidence: List[str],
        rule_ids: List[str],
        in_ppo_network: bool,
        exclusion_reason: Optional[str] = None,
    ):
        self.label = label
        self.confidence = confidence
        self.evidence = evidence
        self.rule_ids = rule_ids
        self.in_ppo_network = in_ppo_network
        self.exclusion_reason = exclusion_reason


def classify_plan_name(plan_name: str, market_type: str = "group") -> NetworkClassificationResult:
    """Classify a plan name into a network category using explainable priority rules."""
    name_clean = plan_name.strip()
    name_upper = name_clean.upper()

    evidence = []
    rule_ids = []

    # Detect metal tier
    matched_tier = [tier for tier in METAL_TIERS if re.search(rf"\b{tier}\b", name_upper)]
    if matched_tier:
        evidence.append(f"TIER:{matched_tier[0]}")
        rule_ids.append("RULE_METAL_TIER")

    # Guard: check for false positives like POST DOC or DEPOT
    if "POST DOC" in name_upper or "POST-DOC" in name_upper:
        evidence.append("GUARD:POST_DOC_NOT_POS")
        rule_ids.append("RULE_GUARD_POST_DOC")

    if "DEPOT" in name_upper:
        evidence.append("GUARD:DEPOT_NOT_EPO")
        rule_ids.append("RULE_GUARD_DEPOT")

    # 1. Match Network Patterns
    ppo_match = REGEX_PPO.findall(name_clean)
    has_ppo = bool(ppo_match)
    if has_ppo:
        matched_str = ppo_match[0] if isinstance(ppo_match[0], str) else [x for x in ppo_match[0] if x][0]
        evidence.append(f"MATCH_PPO:{matched_str}")
        if matched_str.upper() == "PPO":
            rule_ids.append("RULE_EXPLICIT_PPO")
        else:
            rule_ids.append("RULE_GLUED_PPO")

    epo_match = REGEX_EPO.findall(name_clean)
    has_epo = bool(epo_match)
    if has_epo:
        evidence.append(f"MATCH_EPO:{epo_match[0]}")
        rule_ids.append("RULE_EXPLICIT_EPO")

    # Guard: POS must not match POST
    pos_match = False
    if REGEX_POS.search(name_clean) and not ("POST DOC" in name_upper or "POST-DOC" in name_upper):
        pos_match = True
        evidence.append("MATCH_POS")
        rule_ids.append("RULE_EXPLICIT_POS")

    hmo_match = bool(REGEX_HMO.search(name_clean))
    matched_families = [fam for fam in HMO_FAMILIES if fam in name_upper]

    if hmo_match:
        evidence.append("MATCH_HMO")
        rule_ids.append("RULE_EXPLICIT_HMO")

    if matched_families:
        evidence.append(f"HMO_FAMILY:{','.join(matched_families)}")
        rule_ids.append("RULE_HMO_FAMILY")

    has_eoa = "EOA" in name_upper
    if has_eoa:
        evidence.append("MATCH_EOA")
        rule_ids.append("RULE_EOA_PRODUCT")

    # 2. Decision Tree & Conflict Handling
    # Priority A: Conflicting networks in the same plan name
    if (
        (has_ppo and has_epo)
        or (has_ppo and hmo_match)
        or (has_epo and hmo_match)
        or (has_ppo and pos_match)
        or (has_epo and pos_match)
        or (hmo_match and pos_match)
    ):
        rule_ids.append("RULE_CONFLICT_NETWORK")
        return NetworkClassificationResult(
            label="Conflict",
            confidence=0.50,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=False,
            exclusion_reason="Name contains contradictory network keywords (e.g. PPO/EPO, PPO/HMO, or PPO/POS). Excluded pending human review.",
        )

    # Priority B: Pure PPO
    if has_ppo:
        conf = 1.0 if "RULE_EXPLICIT_PPO" in rule_ids else 0.95
        return NetworkClassificationResult(
            label="PPO",
            confidence=conf,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=True,
            exclusion_reason=None,
        )

    # Priority C: HMO (either explicit HMO keyword or HMO product family with HMO)
    if hmo_match:
        return NetworkClassificationResult(
            label="HMO",
            confidence=1.0,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=False,
            exclusion_reason="HMO plan excluded from PPO network scope.",
        )

    # Priority D: POS
    if pos_match:
        return NetworkClassificationResult(
            label="POS",
            confidence=1.0,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=False,
            exclusion_reason="Point-of-Service (POS) plan excluded from PPO scope.",
        )

    # Priority E: Pure EPO
    if has_epo:
        return NetworkClassificationResult(
            label="EPO",
            confidence=0.95,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=False,
            exclusion_reason="Exclusive Provider Organization (EPO) plan excluded from PPO scope.",
        )

    # Priority F: EOA (Elect Open Access / Exclusive Open Access)
    if has_eoa:
        return NetworkClassificationResult(
            label="Unknown",
            confidence=0.40,
            evidence=evidence,
            rule_ids=rule_ids,
            in_ppo_network=False,
            exclusion_reason="EOA represents Health Net Elect Open Access (typically EPO/open-access product, not standard PPO). Excluded due to lack of PPO confirmation.",
        )

    # Priority G: No network word
    rule_ids.append("RULE_NO_NETWORK_WORD")
    return NetworkClassificationResult(
        label="Unknown",
        confidence=0.10,
        evidence=evidence,
        rule_ids=rule_ids,
        in_ppo_network=False,
        exclusion_reason="No explicit network keyword detected in plan name.",
    )


class PPOClassifier:
    """Orchestrates classification across in-scope plans, persists outputs, and logs metrics."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.interim_dir = config.interim_dir
        self.output_dir = config.output_dir

    def run(self, df_plans: Optional[pl.DataFrame] = None) -> Dict[str, Any]:
        """Classify all plans and produce audit tables."""
        if df_plans is None:
            plans_path = self.interim_dir / "deduplicated_plans.parquet"
            if not plans_path.exists():
                raise FileNotFoundError(f"Deduplicated plans not found at {plans_path}")
            df_plans = pl.read_parquet(plans_path)

        # We classify all plans, but track in_scope plans separately
        results = []
        rule_counter: Dict[str, int] = {}

        for row in df_plans.iter_rows(named=True):
            res = classify_plan_name(row["plan_name"], row.get("market_type", "group"))
            for r_id in res.rule_ids:
                rule_counter[r_id] = rule_counter.get(r_id, 0) + 1

            results.append({
                "brand": row["brand"],
                "plan_id": row["plan_id"],
                "plan_name": row["plan_name"],
                "market_type": row["market_type"],
                "state_hint": row["state_hint"],
                "rate_file_url": row["rate_file_url"],
                "in_scope": row["in_scope"],
                "scope_reason": row["scope_reason"],
                "network_label": res.label,
                "confidence": res.confidence,
                "evidence": "; ".join(res.evidence),
                "rule_ids": "; ".join(res.rule_ids),
                "in_ppo_network": res.in_ppo_network and row["in_scope"],
                "exclusion_reason": res.exclusion_reason,
            })

        df_classified = pl.DataFrame(results)

        # Profile counts for in-scope California plans (Health Net CA)
        df_ca_in_scope = df_classified.filter(pl.col("in_scope") == True)
        ca_counts = df_ca_in_scope.group_by("network_label").len().sort("len", descending=True)

        # Detailed breakdown of EOA vs Other Unknown
        eoa_count = df_ca_in_scope.filter(
            (pl.col("network_label") == "Unknown") & (pl.col("evidence").str.contains("MATCH_EOA"))
        ).height
        other_unknown_count = df_ca_in_scope.filter(
            (pl.col("network_label") == "Unknown") & (~pl.col("evidence").str.contains("MATCH_EOA"))
        ).height

        # Rule hit counts table
        rule_hits = [{"rule_id": k, "hit_count": v} for k, v in sorted(rule_counter.items(), key=lambda x: x[1], reverse=True)]
        df_rule_hits = pl.DataFrame(rule_hits)

        # PPO plans table
        df_ppo_plans = df_classified.filter(pl.col("in_ppo_network") == True)

        # Ambiguous review table (Conflicts and Unknowns in California in-scope)
        df_ambiguous = df_ca_in_scope.filter(pl.col("network_label").is_in(["Conflict", "Unknown"]))

        # Persist deliverables
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        df_classified.write_parquet(self.interim_dir / "plan_network_labels.parquet")
        df_classified.write_csv(self.interim_dir / "plan_network_labels.csv")

        df_ppo_plans.write_csv(self.output_dir / "ppo_plans.csv")
        df_ambiguous.write_csv(self.output_dir / "ambiguous_review.csv")
        df_rule_hits.write_csv(self.output_dir / "rule_hit_counts.csv")

        logger.info(f"Phase 2 complete: CA In-scope labels -> {dict(zip(ca_counts['network_label'].to_list(), ca_counts['len'].to_list()))}")
        logger.info(f"EOA Unknowns: {eoa_count}, Other Unknowns: {other_unknown_count}, PPO Confirmed: {df_ppo_plans.height}")

        return {
            "df_classified": df_classified,
            "df_ppo_plans": df_ppo_plans,
            "df_ambiguous": df_ambiguous,
            "df_rule_hits": df_rule_hits,
            "ca_counts": dict(zip(ca_counts["network_label"].to_list(), ca_counts["len"].to_list())),
            "eoa_count": eoa_count,
            "other_unknown_count": other_unknown_count,
        }
