"""Stream CMS DAC National Downloadable File from stdin and filter for target NPIs."""

import csv
import sys
import polars as pl
from pathlib import Path
from ptd.config import load_config

cfg = load_config()
df_rates = pl.read_parquet(cfg.interim_dir / "extracted_rates.parquet")
target_npis = set(df_rates.filter(pl.col("npi") > 0)["npi"].unique().to_list())
print(f"Target NPIs count: {len(target_npis)}", file=sys.stderr)

matched_rows = []
lines_count = 0

reader = csv.DictReader(sys.stdin)
for row in reader:
    lines_count += 1
    npi_str = row.get("NPI", "")
    if npi_str.isdigit():
        npi_int = int(npi_str)
        if npi_int in target_npis:
            matched_rows.append({
                "npi": npi_int,
                "org_pac_id": row.get("org_pac_id", ""),
                "facility_name": row.get("Facility Name", ""),
                "pri_spec": row.get("pri_spec", ""),
                "sec_spec_all": row.get("sec_spec_all", ""),
                "line1": row.get("adr_ln_1", ""),
                "line2": row.get("adr_ln_2", ""),
                "city": row.get("City/Town", ""),
                "state": row.get("State", ""),
                "zip": row.get("ZIP Code", ""),
            })

print(f"Processed {lines_count:,} lines, matched {len(matched_rows):,} rows.", file=sys.stderr)

out_path = cfg.reference_dir / "cms_dac_target_npis.parquet"
if matched_rows:
    df_out = pl.DataFrame(matched_rows)
    df_out.write_parquet(out_path)
    print(f"Wrote {df_out.height:,} rows to {out_path}", file=sys.stderr)
else:
    pl.DataFrame([]).write_parquet(out_path)
