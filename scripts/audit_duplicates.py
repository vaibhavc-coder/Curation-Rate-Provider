"""Standalone duplicate price record auditor.

Audits within-block duplicate rates and structural cross-reference fan-out across raw price records
extracted during Phase 4 profiling.
"""

from __future__ import annotations

import sys
from pathlib import Path
import polars as pl

# Ensure src is on path
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from ptd.config import load_config


def audit_duplicates() -> None:
    """Analyze exact duplicate pricing records from raw_price_audit.parquet."""
    cfg = load_config()
    audit_file = cfg.interim_dir / "raw_price_audit.parquet"
    if not audit_file.exists():
        print(f"Audit file not found: {audit_file}. Run Phase 4 first.")
        return

    df = pl.read_parquet(audit_file)

    exact_keys = [
        "npi", "tin", "billing_code", "billing_class", "modifier",
        "service_code", "setting", "negotiated_rate", "additional_information"
    ]
    print("Exact keys evaluated:", exact_keys)

    n_total = df.height
    n_unique = df.unique(subset=exact_keys).height
    n_dups = n_total - n_unique
    pct_dups = (n_dups / n_total * 100) if n_total > 0 else 0.0
    print(f"Total rows: {n_total:,}, Unique tuples: {n_unique:,}, Duplicates: {n_dups:,} ({pct_dups:.2f}%)")

    dups = (
        df.group_by(exact_keys)
        .agg([
            pl.len().alias("dup_count"),
            pl.col("in_network_item_index").alias("items"),
            pl.col("provider_reference_id").alias("refs"),
            pl.col("business_name").alias("businesses"),
        ])
        .filter(pl.col("dup_count") > 1)
        .sort("dup_count", descending=True)
    )

    print(f"Total duplicate groups: {dups.height:,}")

    top_n = min(3, dups.height)
    for i in range(top_n):
        row = dups.row(i, named=True)
        print(f"\n--- Example Duplicate Group {i+1} ---")
        print(f"NPI: {row['npi']}, TIN: {row['tin']}, Business: {row['businesses'][0]}")
        print(f"Billing Code: {row['billing_code']}, Class: {row['billing_class']}, Setting: {row['setting']}")
        print(f"Service Code: {row['service_code']}, Modifier: {row['modifier']}, Rate: ${row['negotiated_rate']:.2f}")
        print(f"Additional Information: '{row['additional_information']}'")
        print(f"Repeats: {row['dup_count']} times across in_network items: {row['items'][:6]}")
        print(f"Provider Reference IDs: {row['refs'][:6]}")


if __name__ == "__main__":
    audit_duplicates()
