import polars as pl
from ptd.config import load_config

cfg = load_config()
df = pl.read_parquet(cfg.interim_dir / "raw_price_audit.parquet")

exact_keys = [
    "npi", "tin", "billing_code", "billing_class", "modifier",
    "service_code", "setting", "negotiated_rate", "additional_information"
]
print("Exact keys used:", exact_keys)

n_total = df.height
n_unique = df.unique(subset=exact_keys).height
print(f"Total rows: {n_total:,}, Unique tuples: {n_unique:,}, Duplicates: {n_total - n_unique:,} ({(n_total - n_unique)/n_total*100:.2f}%)")

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

for i in range(3):
    row = dups.row(i, named=True)
    print(f"\n--- Example Duplicate Group {i+1} ---")
    print(f"NPI: {row['npi']}, TIN: {row['tin']}, Business: {row['businesses'][0]}")
    print(f"Billing Code: {row['billing_code']}, Class: {row['billing_class']}, Setting: {row['setting']}")
    print(f"Service Code: {row['service_code']}, Modifier: {row['modifier']}, Rate: ${row['negotiated_rate']:.2f}")
    print(f"Additional Information: '{row['additional_information']}'")
    print(f"Repeats: {row['dup_count']} times across in_network items: {row['items'][:6]}")
    print(f"Provider Reference IDs: {row['refs'][:6]}")
