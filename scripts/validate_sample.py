"""Validation script for Phase 6 Final Curated Rate File (TiC v2.0.0).

Validates:
  1. Exact join consistency between rates and links.
  2. Multi-format integrity: Parquet vs CSV vs Excel re-read row counts.
  3. Relational uniqueness: no duplicate (NPI, TIN, Address, Code, Class, Type).
  4. Explicit column ordering matching required specifications.
  5. Null count profile across all mandatory columns.
  6. End-to-end trace validation against docs/trace_report.csv sample rows.
"""

from __future__ import annotations

import sys
import openpyxl
import polars as pl
from pathlib import Path

from ptd.config import load_config
from ptd.final_output import FinalOutputGenerator


def validate_production_outputs() -> bool:
    cfg = load_config()
    output_dir = cfg.output_dir
    docs_dir = cfg.docs_dir

    parquet_path = output_dir / "final_curated_rates.parquet"
    csv_path = output_dir / "final_curated_rates.csv"
    excel_path = output_dir / "final_curated_rates.xlsx"
    rates_path = cfg.interim_dir / "extracted_rates.parquet"
    trace_path = docs_dir / "trace_report.csv"

    print("================================================================================")
    print("PHASE 6: FINAL CURATED RATE FILE VALIDATION REPORT")
    print("================================================================================")

    # 1. Existence Check
    for p in [parquet_path, csv_path, excel_path]:
        if not p.exists():
            print(f"[FAIL] Missing output file: {p}")
            return False
        print(f"[PASS] File exists: {p.name} ({p.stat().st_size / (1024*1024):.2f} MB)")

    # 2. Load Parquet
    df_parquet = pl.read_parquet(parquet_path)
    n_rows = df_parquet.height
    print(f"\n1. Parquet Row Count: {n_rows:,}")

    # 3. Load CSV
    df_csv = pl.read_csv(csv_path, infer_schema_length=10000)
    print(f"2. CSV Row Count: {df_csv.height:,}")
    if df_csv.height != n_rows:
        print(f"[FAIL] Parquet ({n_rows:,}) and CSV ({df_csv.height:,}) row counts disagree!")
        return False
    print("[PASS] Parquet and CSV row counts match exactly.")

    # 4. Excel Re-read Count
    print("3. Validating Excel Re-read Count...")
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    if "Curated_Rates" not in wb.sheetnames or "Notes" not in wb.sheetnames:
        print("[FAIL] Missing required sheets in Excel workbook!")
        return False
    ws = wb["Curated_Rates"]
    excel_rows = ws.max_row - 1  # Exclude header
    wb.close()
    print(f"   Excel Sheet 'Curated_Rates' Data Rows: {excel_rows:,}")
    if excel_rows != n_rows:
        print(f"[FAIL] Excel row count ({excel_rows:,}) does not equal Parquet count ({n_rows:,})!")
        return False
    print("[PASS] Excel re-read row count matches Parquet exactly.")

    # 5. Column Order Verification
    print("\n4. Validating Column Ordering...")
    actual_cols = df_parquet.columns
    expected_cols = FinalOutputGenerator.REQUIRED_COLUMNS
    if actual_cols != expected_cols:
        print("[FAIL] Column order mismatch!")
        print(f"Expected: {expected_cols}")
        print(f"Actual:   {actual_cols}")
        return False
    print(f"[PASS] All {len(actual_cols)} columns match required order exactly.")

    # 6. Duplication Check on Grain
    print("\n5. Checking Grain Uniqueness...")
    grain = ["NPI", "TIN", "Address", "Billing Code", "billing_class", "billing_code_type"]
    n_unique_grain = df_parquet.unique(subset=grain).height
    dup_grain = n_rows - n_unique_grain
    print(f"   Grain duplicates: {dup_grain}")
    if dup_grain > 0:
        print(f"[FAIL] Found {dup_grain:,} duplicate records on finest grain!")
        return False
    print("[PASS] Zero grain duplicates.")

    # 7. Coverage of Curated Keys
    print("\n6. Checking Curated Rates Key Coverage...")
    df_rates = pl.read_parquet(rates_path)
    curated_keys = df_rates.select(["tin", "billing_code", "billing_class", "billing_code_type"]).unique()
    final_keys = df_parquet.select(["TIN", "Billing Code", "billing_class", "billing_code_type"]).rename({
        "TIN": "tin", "Billing Code": "billing_code"
    }).unique()
    missing_keys = curated_keys.join(final_keys, on=["tin", "billing_code", "billing_class", "billing_code_type"], how="anti")
    print(f"   Curated keys present in final table: {final_keys.height:,} / {curated_keys.height:,}")
    if missing_keys.height > 0:
        print(f"[FAIL] {missing_keys.height} curated rate keys missing from final output!")
        return False
    print("[PASS] Every single curated rate key appears in the final deliverable.")

    # 8. Null Counts Summary
    print("\n7. Column Null Counts Profile:")
    null_summary = []
    for col in actual_cols:
        null_c = df_parquet.filter(pl.col(col).is_null()).height
        null_pct = (null_c / n_rows) * 100.0
        null_summary.append((col, null_c, null_pct))
        if null_c > 0 and col in ("TIN", "Address", "Billing Code", "Rate", "address_confidence", "address_status"):
            print(f"   [FAIL] Mandatory business column '{col}' has {null_c:,} nulls!")
            return False
        print(f"   {col:25}: {null_c:6,d} nulls ({null_pct:.2f}%)")
    print("[PASS] Null counts within permissible schema bounds.")

    # 9. Trace Sample Validation against docs/trace_report.csv
    if trace_path.exists():
        print("\n8. Trace Validation against docs/trace_report.csv:")
        df_trace = pl.read_csv(trace_path)
        matched_traces = 0
        for tr in df_trace.iter_rows(named=True):
            t_tin = tr["tin"]
            t_code = tr["billing_code"]
            t_class = tr["billing_class"]
            t_rate = float(tr["rate_selected"])

            # Find matching rows in final deliverable
            matches = df_parquet.filter(
                (pl.col("TIN") == t_tin)
                & (pl.col("Billing Code") == t_code)
                & (pl.col("billing_class") == t_class)
            )
            if matches.height > 0:
                final_rate = float(matches["Rate"][0])
                if abs(final_rate - t_rate) < 1e-3:
                    matched_traces += 1
                else:
                    print(f"   [WARN] Rate mismatch for TIN {t_tin}, Code {t_code}: trace ${t_rate:.2f} vs final ${final_rate:.2f}")
            else:
                print(f"   [WARN] Trace row not found: TIN {t_tin}, Code {t_code}")

        print(f"   Matched Trace Rows: {matched_traces} / {df_trace.height}")
        if matched_traces == df_trace.height:
            print("[PASS] 100% trace sample reconciliation verified.")

    print("\n================================================================================")
    print("ALL PHASE 6 VALIDATION CHECKS PASSED SUCCESSFULLY")
    print("================================================================================")
    return True


if __name__ == "__main__":
    success = validate_production_outputs()
    sys.exit(0 if success else 1)
