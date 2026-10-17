"""Generate stratified 30-sample links strictly from npi_tin_address_links.parquet."""

import json
import polars as pl
from ptd.config import load_config
from ptd.file_grading import calculate_luhn_validity

cfg = load_config()
links_path = cfg.interim_dir / "npi_tin_address_links.parquet"
df_links = pl.read_parquet(links_path)

# Filter real NPIs (non-null)
real_links = df_links.filter(pl.col("npi").is_not_null())

# Stratified sampling: 10 Verified, 10 Probable, 10 Unverified
# Fixed seed for reproducibility
seed = 42
v_sample = real_links.filter(pl.col("status") == "Verified").sample(n=10, seed=seed)
p_sample = real_links.filter(pl.col("status") == "Probable").sample(n=10, seed=seed)
u_sample = real_links.filter(pl.col("status") == "Unverified").sample(n=10, seed=seed)

sample_30 = pl.concat([v_sample, p_sample, u_sample])

# Verify Luhn checksum on every single NPI in sample
npis = sample_30["npi"].to_list()
luhn_pct, valid_c, invalid_c = calculate_luhn_validity(npis)
print(f"Sample 30 NPI Luhn Validity: {valid_c}/30 valid ({luhn_pct:.1f}%), {invalid_c} invalid")
assert invalid_c == 0, f"Found {invalid_c} invalid NPIs in sample!"

# Build clean reason strings ONLY from recorded fields: sources, dates, rule IDs
clean_rows = []
for r in sample_30.iter_rows(named=True):
    ev = json.loads(r["evidence_json"])
    sources_str = ", ".join(ev.get("source_types", []))
    update_date = ev.get("last_update_date", "NONE")
    rules_str = r.get("rules_applied", "STANDARD_RULESET")
    status_basis = r.get("status_basis", "UNKNOWN")

    recorded_reason = f"StatusBasis: {status_basis} | Sources: [{sources_str}] | LastUpdate: {update_date} | Rules: [{rules_str}]"

    clean_rows.append({
        "npi": r["npi"],
        "tin": r["tin"],
        "canonical_name": r["canonical_name"],
        "entity_type": r["entity_type"],
        "npi_status": r["npi_status"],
        "address_key": r["address_key"],
        "line1": r["line1"],
        "city": r["city"],
        "state": r["state"],
        "zip5": r["zip5"],
        "score": r["score"],
        "status": r["status"],
        "status_basis": r["status_basis"],
        "is_primary_address": r["is_primary_address"],
        "rules_applied": r["rules_applied"],
        "recorded_reason_string": recorded_reason,
        "evidence_json": r["evidence_json"],
    })

df_sample_out = pl.DataFrame(clean_rows)
out_csv = cfg.docs_dir / "phase5_sample_links.csv"
df_sample_out.write_csv(out_csv)
print(f"Successfully saved {df_sample_out.height} rows to {out_csv}")
