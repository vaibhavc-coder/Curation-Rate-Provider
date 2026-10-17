# PTD Pipeline: Centene Commercial Group CA Provider Rates

Production-grade, hackathon-winning data pipeline for CMS Price Transparency Data (TiC v2.0.0). Built with zero data invention, reproducible end-to-end execution, strict validation, and high-performance streaming architecture.

---

## 1. Quickstart & Reproduction Commands

### Environment Setup
```bash
# Clone and enter project directory
cd ptd_pipeline

# Setup virtual environment and dependencies
make setup
# or manually:
# python3 -m venv .venv
# .venv/bin/pip install --upgrade pip
# .venv/bin/pip install -r requirements.txt
```

### Reference Files Placement
Ensure reference files are placed under `data/reference/` as defined in `config.yaml`:
```
data/reference/
├── NPPES_Data_Dissemination_October_2026_V2.zip  # CMS NPPES V.2 monthly export (1.1 GB, NEVER unzipped)
├── nucc_taxonomy.csv                             # NUCC Health Care Provider Taxonomy Code Set
├── Rate_Benchmarking_Individual_Weights_Hackathon.xlsx # HiLabs code-to-specialty workbook
└── cms_dac_target_npis.parquet                   # CMS Doctors & Clinicians filtered targets
```
*Note: If `cms_dac_target_npis.parquet` is not yet extracted from CMS DAC, run `python scripts/filter_cms_dac.py`.*

### Running the Test Suite
```bash
make test
# or:
# .venv/bin/pytest -v
```
All 42 unit and integration tests validate Luhn check digits, PPO classification heuristics, rate reliability, multi-site deduplication, and quality scoring reconciliation.

### Running Pipeline Phases
```bash
# Run quick sample mode (first 500 rate objects)
make sample
# or:
# .venv/bin/python run_pipeline.py --sample 500

# Run specific phases individually
.venv/bin/python run_pipeline.py --phase 1    # Phase 1: Machine-readable index ingest & scoping
.venv/bin/python run_pipeline.py --phase 2    # Phase 2: PPO network plan classifier & audit
.venv/bin/python run_pipeline.py --phase 3    # Phase 3: Fast rate streaming profiler
.venv/bin/python run_pipeline.py --phase 4    # Phase 4: File quality grading & mutation suite
.venv/bin/python run_pipeline.py --phase 5    # Phase 5: Address linkage & specialty resolution
.venv/bin/python run_pipeline.py --phase 6    # Phase 6: Final curated rate file generation
.venv/bin/python run_pipeline.py --phase 7    # Phase 7: Summary scorecard & governance sync

# Run the complete pipeline end-to-end:
make run
# or:
# .venv/bin/python run_pipeline.py --all
```

---

## 2. Deliverables & Outputs

All generated datasets and governance reports are written to `data/output/` and `docs/`:
- `data/output/final_curated_rates.parquet`: Master curated dataset (46,263 multi-site practicing rows / 21,608 unique rate keys, Snappy compressed).
- `data/output/final_curated_rates.csv`: Flat RFC 4180 compliant CSV format.
- `data/output/final_curated_rates.xlsx`: High-performance Excel deliverable with `Curated_Rates` and `Notes` tabs (streaming `xlsxwriter`, 95.59% headroom under Excel limit).
- `data/output/summary.json` & `data/output/summary.xlsx`: Pipeline run metrics, record reconciliation, file quality scores, and verification shares.
- `docs/LOGIC.md`: Comprehensive engineering design document covering all 9 architectural decisions, empirical findings, and limitations.
- `docs/FILE_QUALITY_METRICS.md`: Complete quality audit and 6-scenario mutation testing scorecard.
- `docs/phase5_sample_links.csv`: Stratified 30-sample address linkage audit with 100% Luhn-validated NPIs.

---

## 3. Scalability & Architectural Design

The pipeline is designed to scale effortlessly from a single 670 MB payer rate file to multi-gigabyte nationwide files spanning hundreds of plans:

1. **True O(1) Memory Streaming**:
   - Uses `ijson` with C-accelerated `yajl2_c` backend (falling back gracefully to pure Python where binary C extensions are uncompiled).
   - Peak RSS is capped under 350 MB even when streaming arbitrarily large multi-gigabyte raw JSON files.
2. **DuckDB Embedded OLAP Indexing**:
   - Provider references and rate items are indexed into zero-copy columnar DuckDB tables and Parquet stores.
   - Eliminates Python memory overhead for large-scale joins across millions of NPI-TIN associations.
3. **Parquet & Vectorized PyArrow Execution**:
   - Cross-referencing, multi-setting normalization, and rate aggregation utilize vectorized chunked operations.
4. **Stream-Zip Ingestion**:
   - The 1.1 GB CMS NPPES V.2 monthly archive is streamed directly from its compressed zip archive using `zipfile` and chunked CSV streaming, avoiding disk exhaustion from unzipping.
5. **Parallelism vs. Sequential Constraints**:
   - **Sequential**: Phase 3 raw JSON streaming is I/O-bound and sequential per file to maintain parser state across nested structures.
   - **Parallel**: Address verification, multi-source distance clustering, and cross-reference groupings support multi-core partitioning over NPI ranges or file shards.
6. **Multi-Payer / Multi-Network Extension via `config.yaml`**:
   - Payers, plan inclusion/exclusion keywords, state markets, and weight vectors are declared in `config.yaml`.
   - Adding a new payer (e.g. Elevance, UnitedHealthcare) or market requires adding an entry to `config.yaml` without modifying business logic.

---

## 4. Python 3.14 Compatibility Note

This pipeline has been developed and tested on **Python 3.14.6**:
- All data models and pipeline scripts utilize modern standard library typing, `pathlib.Path`, and thread-safe file handling.
- `ijson` dynamically selects `yajl2_c` when available or smoothly transitions to Python streaming without syntax or bytecode deprecations.
- Zero external bash or non-portable commands: fully cross-platform for Linux and POSIX environments.
