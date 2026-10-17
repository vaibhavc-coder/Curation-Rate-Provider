"""Independent Row Trace and Verification Script (Challenge C4 Verification).

Re-reads raw JSON directly by in_network item index, extracts candidate prices
for the corresponding provider_reference_id, executes the tie-breaking rules independently,
and verifies exact match against the curated pipeline output.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
import ijson
import polars as pl
import yaml


def trace_and_verify_sample_rows() -> dict:
    # Completely independent: zero imports from src/ptd
    config_path = Path("config.yaml")
    if not config_path.exists():
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    data_dir = Path(cfg["paths"]["data_dir"])
    output_dir = Path(cfg["paths"]["output_dir"])
    raw_dir = Path(cfg["paths"]["raw_dir"])
    sample_csv = output_dir / "extracted_rates_sample.csv"
    rate_candidates = list(raw_dir.glob("*healthnet-ca*.json"))
    if not rate_candidates:
        rate_candidates = list(raw_dir.glob("*in-network*.json"))
    rate_file = rate_candidates[0]

    if not sample_csv.exists():
        raise FileNotFoundError(f"Sample CSV not found at {sample_csv}")

    df_sample = pl.read_csv(sample_csv)
    print(f"Loaded {df_sample.height} sample rows to trace against raw JSON: {rate_file.name}")

    target_indices = set(df_sample["in_network_item_index"].to_list())
    matches = 0
    total = df_sample.height
    audit_results = []

    # Stream raw JSON and pull matching items
    raw_items_by_index = {}
    with open(rate_file, "rb") as f:
        items = ijson.items(f, "in_network.item", use_float=True)
        for idx, item in enumerate(items, start=1):
            if idx in target_indices:
                raw_items_by_index[idx] = item
            if len(raw_items_by_index) >= len(target_indices):
                break

    import duckdb
    con = duckdb.connect(str(Path("data/interim/provider_references.duckdb")), read_only=True)

    for row in df_sample.iter_rows(named=True):
        item_idx = row["in_network_item_index"]
        ref_id = row["provider_reference_id"]
        row_npi = int(row["npi"])
        row_tin = str(row["tin"])
        b_class = row["billing_class"]
        expected_rate = float(row["rate_selected"])
        row_add_info = str(row.get("additional_information") or "NONE").strip()

        item = raw_items_by_index.get(item_idx)
        if not item:
            audit_results.append({
                "item_index": item_idx,
                "status": "FAIL_ITEM_NOT_FOUND",
                "expected": expected_rate,
                "recomputed": None,
            })
            continue

        # Look up all provider references containing this (TIN, NPI)
        target_refs = {
            r[0] for r in con.execute(
                "SELECT provider_group_id FROM provider_references WHERE tin_value = ? AND (list_contains(npis, ?) OR ? = 0)",
                [row_tin, row_npi, row_npi],
            ).fetchall()
        }
        if not target_refs:
            target_refs = {ref_id}

        candidate_prices = []
        for nr in item.get("negotiated_rates", []):
            item_refs = set(nr.get("provider_references", []))
            if item_refs.intersection(target_refs):
                for np in nr.get("negotiated_prices", []):
                    r_val = np.get("negotiated_rate")
                    if r_val is not None and r_val > 0:
                        add_info = str(np.get("additional_information") or "NONE").strip()
                        if add_info != row_add_info:
                            continue
                        sc_list = np.get("service_code", ["NONE"])
                        sc = sc_list[0] if sc_list else "NONE"
                        mod_list = np.get("billing_code_modifier", [])
                        mod = mod_list[0] if mod_list else "NONE"
                        candidate_prices.append({
                            "rate": float(r_val),
                            "billing_class": np.get("billing_class", "institutional"),
                            "service_code": sc,
                            "modifier": mod,
                        })

        # Apply Tie-Break Rules:
        # 1. Base modifier filter
        has_base = any(p["modifier"] == "NONE" for p in candidate_prices)
        if has_base:
            candidate_prices = [p for p in candidate_prices if p["modifier"] == "NONE"]

        # 2. Preferred setting for billing class
        def is_pref(c: str, s: str) -> bool:
            return s in ("11", "22", "02") if c == "professional" else s in ("22", "23")

        has_pref = any(is_pref(p["billing_class"], p["service_code"]) for p in candidate_prices)
        if has_pref:
            candidate_prices = [p for p in candidate_prices if is_pref(p["billing_class"], p["service_code"])]

        # 3. Median of remaining prices
        rates = [p["rate"] for p in candidate_prices]
        recomputed_rate = statistics.median(rates) if rates else None

        is_match = (
            recomputed_rate is not None and math.isclose(expected_rate, recomputed_rate, rel_tol=1e-4)
        )
        if is_match:
            matches += 1

        audit_results.append({
            "item_index": item_idx,
            "provider_ref_id": ref_id,
            "billing_code": row["billing_code"],
            "class": b_class,
            "expected_rate": expected_rate,
            "recomputed_rate": recomputed_rate,
            "n_candidate_prices": len(rates),
            "match": is_match,
        })

    print(f"\n=== TRACE AND VERIFICATION RESULT: {matches} / {total} MATCHED ===")
    for res in audit_results[:10]:
        print(f"  Item #{res['item_index']} Ref {res['provider_ref_id']} Code {res['billing_code']}: Expected ${res['expected_rate']:.2f} | Recomputed ${res['recomputed_rate']:.2f} | Match: {res['match']}")

    return {
        "total_tested": total,
        "matches": matches,
        "match_rate_pct": (matches / total) * 100.0 if total > 0 else 0.0,
        "audit_results": audit_results,
    }


if __name__ == "__main__":
    trace_and_verify_sample_rows()
