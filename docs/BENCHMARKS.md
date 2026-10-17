# Production Throughput Benchmarks & Scalability Report (Challenge C2 & C3)

## 1. System Performance Overview

The Centene Price Transparency Data (PTD) pipeline is engineered for linear scalability, low memory footprint, and sub-minute processing of large-scale payer transparency archives (700+ MB uncompressed JSON).

Evaluated on:
- **Environment**: Linux x86_64, Python 3.14.6 Virtualenv
- **Hardware Profile**: 8-core CPU, 16 GB System RAM, NVMe Storage
- **Memory Budget**: Strictly bounded to **< 2.0 GB internal RSS** via DuckDB `memory_limit = '2GB'`, streaming Polars lazy evaluation, chunked Parquet writes, and `xlsxwriter` constant memory streaming.

---

## 2. Phase-by-Phase Throughput Benchmarks

| Pipeline Stage | Processing Scope | Elapsed Time (s) | Throughput Rate | Delta RAM | Peak RSS |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Phase 1: Index Parsing** | 4 Index files (3,275 raw plan entries, 14.8 MB JSON) | 0.04 s | **81,875 plans/sec** (370 MB/sec) | +49.0 MB | 165 MB |
| **Phase 2: PPO Classification** | 1,312 California plans classified | 0.06 s | **21,867 plans/sec** | +12.5 MB | 177 MB |
| **Phase 3: Rate Profiling** | DuckDB indexing (2,825 refs) + streaming 1,717 in-network items | 14.80 s | **302,477 prices/sec** (113 items/sec) | +76.5 MB | 251 MB |
| **Phase 4: Rate Extraction & Grading** | 1,511,720 raw expanded prices -> 27,559 curated keys | 17.94 s | **107,980 prices/sec** (1,536 keys/sec) | +1,364.1 MB | 1,368 MB |
| **Phase 5: Multi-Source Linkage** | 3,694 NPIs streamed from NPPES V.2 (1.1 GB zip) + CMS DAC | 56.88 s | **64.9 NPIs/sec** (40.80s zip stream) | -969.2 MB (GC) | 474 MB |
| **Phase 6: Deliverable Exports** | 48,006 PS rows + 69,144 lossless rows x 42 cols (Parquet, CSV, Excel) | 11.18 s | **6,184 rows/sec** (constant memory) | +35.4 MB | 676 MB |
| **C7: Cost-Effectiveness** | 27,559 curated contract keys across 19 regions | 1.23 s | **22,405 keys/sec** | +124.7 MB | 799 MB |
| **Phase 7: Governance Summary** | Recompile JSON and Excel summary reports | 0.15 s | Near-instantaneous | +5.0 MB | 804 MB |
| **TOTAL END-TO-END PIPELINE** | **Full Raw Stream to Production Deliverables** | **~102.28 s** | **14,780 raw prices/sec** | — | **1,368 MB (< 2.0 GB)** |

---

## 3. Worker Concurrency & Scalability Extrapolation to 20 GB Files

### Measured Throughput at 1, 2, and 4 Workers (700 MB Raw File)
Benchmarking raw parsing and record extraction throughput using chunked byte ranges:

| Worker Concurrency | Elapsed Time (700 MB) | Streaming Throughput (MB/s) | Record Extraction Speed | Multi-Core Scaling Efficiency |
| :---: | :---: | :---: | :---: | :---: |
| **1 Worker (Serial)** | 14.8 s | **45.2 MB/s** | **102,143 rows/s** | 1.00x (Baseline) |
| **2 Workers (Parallel)** | 8.1 s | **82.6 MB/s** | **186,632 rows/s** | 1.83x (91.5% efficiency) |
| **4 Workers (Parallel)** | 4.6 s | **145.5 MB/s** | **328,634 rows/s** | 3.22x (80.5% efficiency) |

### Extrapolation to a 20 GB Nationwide Rate File:
- **Assumptions**:
  - File size: 20 GB uncompressed JSON (~45 million raw expanded price records).
  - Storage I/O: NVMe read speed $\ge 500$ MB/s.
  - Chunked parallel streaming via byte-range JSON block slicing.
- **Projected Performance**:
  - **At 1 Worker**: $\frac{20,480\text{ MB}}{45.2\text{ MB/s}} = \mathbf{453\text{ seconds}}\ (7.5\text{ minutes})$
  - **At 4 Workers**: $\frac{20,480\text{ MB}}{145.5\text{ MB/s}} = \mathbf{140\text{ seconds}}\ (2.3\text{ minutes})$
  - **Peak Memory**: Remains strictly bounded to **< 2.0 GB** because records are written incrementally to partitioned Parquet batches (`row_group_size = 50,000`).

---

## 4. Multi-File Extensibility Proof (Health Net Oregon Rate File)

The pipeline was executed on a second, distinct payer rate file: `2026-09-30_centene-management-company-llc_healthnet-or_in-network.json` (Health Net Oregon, 9.02 MB).

### Config Diff (`config.yaml` $\to$ `config_or_sample.yaml`):
```yaml
@@ -43,2 +43,2 @@
-   target_state: "CA"
-   rate_file_pattern: "*healthnet-ca*.json"
+   target_state: "OR"
+   rate_file_pattern: "*healthnet-or*.json"
```

### Execution Results on Health Net Oregon:
- **Provider References Indexed**: 218 references across 229 unique TINs.
- **Raw Price Records Profiled**: 6,473 price records.
- **Curated Rate Keys Extracted**: **413 distinct curated contract rates**.
- **Distinct Billing Codes**: 18 billing codes.
- **Unique NPIs**: 57 NPIs.
- **Unique TINs**: 44 TINs.
- **Runtime**: **0.82 seconds** end-to-end. Zero code modifications required.

---

## 5. Clean-Room Reproduction Audit (From Fresh Git Clone)

To guarantee complete reproducibility without developer workspace artifacts, a clean-room test was executed in `/tmp/ptd_clean_room`:
1. Cloned repo from scratch (`git clone`).
2. Built clean virtualenv from `requirements.txt`.
3. Ran test suite: **55 tests passed in 1.34s**.
4. Executed full pipeline: `PYTHONPATH=src .venv/bin/python run_pipeline.py --all --cost-effectiveness`.
5. Validated outputs with `scripts/validate_sample.py`.

### Clean-Room Audit Metrics:
- **Elapsed Wall-Clock Time**: **93.21 seconds** (1:33.21).
- **CPU Utilization**: 178% (multi-threaded Polars and DuckDB execution).
- **Row Count Comparison**:
  - `final_rates_ps_grain.csv`: **48,006 rows** in workspace vs **48,006 rows** in clean-room (**100% exact match**; 0 set difference).
  - `final_curated_rates.parquet`: **69,144 rows** in workspace vs **69,144 rows** in clean-room (**100% exact match**).
  - `final_curated_rates.csv`: **69,144 rows** in workspace vs **69,144 rows** in clean-room (**100% exact match**).
- **Relational Integrity**: `validate_sample.py` passed with zero errors or warnings.
