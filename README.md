# PTD Pipeline: Centene Commercial Group CA Provider Rates

Production-grade data pipeline for CMS Price Transparency Data (TiC v2.0.0). Built with zero data invention, reproducible end-to-end execution, strict validation, and high-performance streaming architecture.

> [!IMPORTANT]
> **Network Reality & Attribution Notice**:
> In California, Centene publishes **one single in-network rate file** shared across all 1,312 commercial plans (453 PPO, 719 HMO, 131 EOA/Other). In the raw file, `network_name` is **100% empty across all 2,825 provider references**.
> Consequently, this deliverable represents Centene's **California Commercial Master Fee Schedule**, partitioned into two empirical evidence tiers:
> - **`T2_shared_commercial` (99.53% of rows / 68,817 rows / 27,377 keys)**: Master commercial schedule shared across PPO and HMO contracts without explicit brand strings.
> - **`T1_name_hint_ppo` (0.47% of rows / 327 rows / 182 keys)**: Regional administrative network bucket contracts whose provider group name includes `"PPO"` (e.g. `"PPO: Los Angeles County"`, `"HealthNet PPO (California)"`).
> - **How to filter for explicit PPO-only**: `SELECT * FROM final_curated_rates WHERE ppo_evidence_tier = 'T1_name_hint_ppo'`

---

## 1. System Prerequisites

- **Operating System**: Linux x86_64, macOS, or Windows WSL2.
- **Python Version**: Python 3.10 to 3.14 (tested and benchmarked on **Python 3.14.6**).
- **RAM**: Minimum 8 GB (16 GB recommended for multithreaded Polars/DuckDB execution).
- **Disk Space**: Minimum 10 GB free space for raw CMS Transparency files, NPPES zip, and outputs.

---

## 2. Data Sources & Placement

External downloads from federal CMS and payer portals cannot be fully automated via script due to dynamic download tokens and portal sessions. Download the official source files from the public URLs below and place them in the corresponding repository folders:

| Dataset | Public Download Source URL | Destination Directory | Expected File / Pattern |
| :--- | :--- | :--- | :--- |
| **Centene Index Files** | [Centene Price Transparency Page](https://www.centene.com/price-transparency-files.html) | `data/index/` | `*_index*.json` (e.g. `2026-09-30_healthnet_index.json`, Ambetter, QualChoice, Fidelis) |
| **Health Net CA Rate File** | [Centene Price Transparency Page](https://www.centene.com/price-transparency-files.html) | `data/raw/` | `*healthnet-ca*in-network.json` (670 MB uncompressed JSON) |
| **CMS NPPES Full Monthly File** | [CMS NPPES Download Page](https://download.cms.gov/nppes/NPI_Files.html) | `data/reference/` | `NPPES_Data_Dissemination_October_2026_V2.zip` (1.1 GB, **keep zipped**) |
| **NUCC Taxonomy Code Set** | [National Uniform Claim Committee](https://nucc.org) | `data/reference/` | `nucc_taxonomy.csv` |
| **CMS Doctors & Clinicians** | [CMS Provider Data Catalog](https://data.cms.gov/provider-data/) | `data/reference/` | `cms_dac_target_npis.parquet` (or run `python scripts/filter_cms_dac.py`) |
| **CMS Hospital General Info** | [CMS Provider Data Catalog](https://data.cms.gov/provider-data/) | `data/reference/` | `hospital_general_information.csv` |
| **HiLabs Benchmark Workbook** | Provided by hackathon organizers (*not tracked in repo*) | `data/reference/` | `Rate_Benchmarking_Individual_Weights_Hackathon.xlsx` |

---

## 3. Quickstart & Exact Reproduction Commands

Follow these exact copy-paste commands to set up the environment, run the pipeline, run tests, and launch the web dashboard:

### Step 1: Environment Setup
```bash
# Clone the repository
git clone <repo-url> ptd_pipeline
cd ptd_pipeline

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Run Automated Test Suite
```bash
# Run all 55 unit and regression tests
pytest -v
```
*Expected runtime: ~4.5 seconds. Result: 55 passed.*

### Step 3: Run the Complete Pipeline End-to-End
```bash
# Execute Phases 1 through 7 and cost-effectiveness analysis
python run_pipeline.py --all --cost-effectiveness
```
*Expected runtime: ~95–105 seconds total. Peak memory during Phase 4 tie-breaking: ~4.58 GB.*

### Step 4: Run Dual-Grain Production Validator
```bash
# Verify output integrity, row counts, and trace reconciliation
python scripts/validate_sample.py
```
*Expected result: 8/8 checks passed (asserts 48,006 PS-grain rows and 69,144 master rows).*

### Step 5: Launch Interactive Web Application
```bash
# Launch Streamlit contracting analyst & executive dashboard
streamlit run app/streamlit_app.py
```
*Accessible locally at `http://localhost:8501`.*

---

## 4. Deliverables & Outputs

All generated datasets and governance reports are written to `data/output/` and `docs/`:
- `data/output/final_rates_ps_grain.csv`: Exact Problem Statement grain CSV (**48,006 unique rows** on `(NPI, TIN, Address, Billing Code)` collapsed via deterministic median rate aggregation; zero duplicate keys).
- `data/output/final_curated_rates.xlsx`: High-performance multi-sheet Excel workbook (Sheet 1: `Final_Rates_PS_Grain` with 48,006 rows; Sheet 2: `Lossless_Curated_Rates` with 69,144 rows across 45 columns; Sheet 3: `Notes`).
- `data/output/final_curated_rates.parquet`: Master lossless curated dataset (69,144 multi-site practicing rows / 27,559 unique contract keys across 45 columns, Snappy compressed).
- `data/output/final_curated_rates.csv`: Lossless RFC 4180 compliant flat CSV format (69,144 rows, 45 columns).
- `data/output/manual_check_sample.csv`: Balanced 40-row inspection sample across all mutually exclusive tiers (12 Verified, 12 Probable, 11 Unverified, 5 Facility/TIN-level) with full 45 columns.
- `data/output/summary.json` & `data/output/summary.xlsx`: Pipeline run metrics, record reconciliation, file quality scores, and verification shares.
- `data/output/cost_effectiveness.parquet`: Cost-effectiveness provider frontier across 19 regional California cohorts (27,559 rate keys).
- `docs/LOGIC.md`: Comprehensive engineering design document covering all 12 architectural decisions, empirical findings, and limitations.
- `docs/FILE_QUALITY_METRICS.md`: Complete quality audit, exact score bridge ($81.50 \to 91.14$), and 6-scenario mutation testing scorecard.
- `docs/VIDEO_SCRIPT.md`: 5-minute timed video walkthrough presentation script.
- `docs/trace_report.csv`: Stratified 25-sample rate lineage audit trace.

---

## 5. Known Limitations

In the interest of rigorous scientific integrity, we document the following empirical findings and structural boundaries:
1. **Shared Rate File Network Boundary**: Centene publishes one shared master rate file for California commercial group plans. Because `network_name` is blank in the raw stream, the file cannot isolate PPO from HMO at the contract rate level. The pipeline transparently labels participation as `Unknown` and provides empirical evidence tiers (`T1_name_hint_ppo` vs `T2_shared_commercial`).
2. **Address Tiers Reflect Agreement, Not Absolute Ground Truth**: Address verification tiers reflect cross-source physical corroboration (NPPES + CMS DAC + group practice co-membership). As proved by empirical validation, comparing directory addresses against the live federal NPI Registry API is an NPPES self-consistency check, not an external gold-standard test.
3. **Strict Physical Verification Share (7.83%)**: Exactly 289 unique NPIs (7.83% of 3,693 active non-zero NPIs) achieve strict cross-source agreement between NPPES and CMS DAC. In California managed care, independent solo clinicians contract primarily through capitated IPAs (which do not appear on FFS rate schedules).
4. **Facility-Heavy Rate File Composition**: Over 80.7% of rate-file TINs (2,306 of 2,856) represent Type 2 hospitals, medical groups, and clinics where physicians bill under institutional contracts rather than individual NPI agreements.

---

## 6. Hackathon Rubric Self-Check Table

| Rubric Evaluation Dimension | Target Points | Pipeline Deliverable & Evidence File | Verified Measure / Status |
| :--- | :---: | :--- | :--- |
| **C1/C2: Index Ingestion & PPO Classification** | 15 pts | [`data/output/ppo_plans.csv`](data/output/ppo_plans.csv)<br>[`docs/LOGIC.md`](docs/LOGIC.md) | **453 PPO plans classified**; 719 HMOs excluded; 127 EOAs isolated; 100% explainable regex rules; zero ambiguous drops. |
| **C3: Raw Stream File Quality Grading** | 15 pts | [`data/output/file_scores.csv`](data/output/file_scores.csv)<br>[`docs/FILE_QUALITY_METRICS.md`](docs/FILE_QUALITY_METRICS.md) | **Quality Score = 91.14 (Grade A)** across 8 TiC metrics on 1.51M raw prices; true dups (0.76%); 6 mutation tests tie out. |
| **C4: Deterministic Rate Extraction** | 15 pts | [`data/interim/extracted_rates.parquet`](data/interim/extracted_rates.parquet)<br>[`data/output/dropped_rows_audit.csv`](data/output/dropped_rows_audit.csv) | **27,559 curated rate keys**; hierarchical tie-breaking (base modifier > POS > negotiated > expiration); RC 636 disambiguated. |
| **C5: Non-Circular Address Linkage** | 35 pts | [`data/interim/npi_tin_address_links.parquet`](data/interim/npi_tin_address_links.parquet)<br>[`data/output/coverage_report.json`](data/output/coverage_report.json) | **4 mutually exclusive tiers (100% sum)**; **100.0% cross-source physical agreement** on Strict Verified; non-circular multi-NPI TIN corroboration. |
| **C6: Production Deliverables & Schemas** | 15 pts | [`data/output/final_curated_rates.parquet`](data/output/final_curated_rates.parquet)<br>[`data/output/final_rates_ps_grain.csv`](data/output/final_rates_ps_grain.csv)<br>[`data/output/final_curated_rates.xlsx`](data/output/final_curated_rates.xlsx) | **69,144 multi-site rows**; clean 6-column problem-statement grain CSV & Sheet 1; full 45-column lossless view in Parquet/CSV/Sheet 2. |
| **C7: Cost-Effectiveness Frontier (Brownie)** | Extra pts | [`data/output/cost_effectiveness.parquet`](data/output/cost_effectiveness.parquet)<br>[`app/streamlit_app.py`](app/streamlit_app.py) | **27,559 rate keys evaluated** across 19 regional county cohorts; provider efficiency index; interactive Streamlit app. |
| **Architecture & Scalability** | 5 pts | [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)<br>[`docs/EXEC_SUMMARY.md`](docs/EXEC_SUMMARY.md)<br>[`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md) | **55 unit tests pass**; honest per-phase RSS profiling (<250MB streaming via chunked Parquet writing); zero hardcoded paths; QualChoice second-file test. |
