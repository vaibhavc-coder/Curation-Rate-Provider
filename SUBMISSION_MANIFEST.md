# Submission Package Manifest: Centene Commercial Group CA Provider Rates

**Generated**: 2026-10-18  
**Project Repository**: `ptd_pipeline`  
**Target Payer & Scope**: Centene California Commercial Group PPO Rate Curation (CMS TiC v2.0.0)  

---

## 1. Primary Submission Archives

| Package Archive | Size | SHA-256 Checksum | Rubric Criterion / Deliverable Purpose |
| :--- | :--- | :--- | :--- |
| **`ptd_deliverables.zip`** | 19.03 MB | `5b8728ca7c5367603160fca258f3d572078bebee3d58e5e76f4532bcd5e11462` | Complete Submission Package (All Curated Datasets & Governance Documentation) |
| **`ptd_code.zip`** | 263.6 KB | `643c89fe9cad0856fb8784cdb34e895c69df90954c3025a959367e787c5d45cc` | Source Code & Test Suite (Clean Git Archive of Entire Pipeline, Brownie 7a UI, & 65 Unit Tests) |

---

## 2. Individual Deliverables Inventory (Packaged in `ptd_deliverables.zip`)

| Deliverable File | Size | SHA-256 Checksum | Target Rubric Criterion & Deliverable Role |
| :--- | :--- | :--- | :--- |
| **`final_curated_rates.xlsx`** | 17.48 MB | `13aa9c3f53dc5d8c9a33a1fe849ef586010711b668b113dc496026f0bbca4db3` | **Core Rate Deliverable**: C6: Production Deliverables (Sheet 1: PS Grain; Sheet 2: Lossless 45-col; Sheet 3: Notes) |
| **`final_rates_ps_grain.csv`** | 4.60 MB | `ce110c2851a6546bc75bbfb846d3e1543925212fa4cd70c4212004584bcbf512` | **Core Rate Deliverable**: C6: Production Deliverables (Problem Statement Grain: 48,006 rows on NPI, TIN, Address, Billing Code, Specialty, Rate) |
| **`final_curated_rates.parquet`** | 1.56 MB | `53478f3bddcabb78bfff44fedb34c39727a833b2d6edcc2e44a8392b573b1292` | **Core Rate Deliverable**: C6: Production Deliverables (Master Lossless Schema: 69,144 rows, 45 columns, Snappy compressed) |
| **`summary.json`** | 6.5 KB | `8c2e9a40aab06be984fc210a1442a4356623fb259c75ab54318ce0677eddda19` | **Summary Metric Report**: Governance & Reconciliation Metrics (Machine-readable pipeline run audit) |
| **`summary.xlsx`** | 5.7 KB | `59a9cd6524b4f102dc7386a3b8ec1ed62af54b4b8967dd33ca6628cbee15c6fc` | **Summary Metric Report**: Governance & Reconciliation Metrics (Formatted executive workbook) |
| **`file_scores.csv`** | 291 B | `8ba5177bf54866cd6f89f12fba9617ea102e4f577ae80d149a80932124a20fdc` | **Quality Audit Deliverable**: C3: Raw Stream File Quality Grading (Overall Score: 91.14 / Grade A across 8 TiC dimensions) |
| **`ppo_plans.csv`** | 138.1 KB | `94cb2e918dcca1f02b22af0ed9fcf852dc6603291a12eef11c7719546528c8f4` | **Network Ingestion Deliverable**: C1/C2: Index Ingestion & PPO Classification (453 PPO plans, 719 HMOs, 127 EOAs, regex-explained) |
| **`rate_outlier_review.csv`** | 249.8 KB | `10c6d790e674f3cca7f83c0fc0ad2ea1006c8ceb1d4b06e0145a516fb68fab71` | **Rate Audit Deliverable**: C4: Deterministic Rate Extraction & Governance (Outlier flags, 2.5x spread audit) |
| **`manual_check_sample.csv`** | 26.1 KB | `511492745f76350f2f8429df458f10ad9adf118d9f396dd1a172df401f5dc15a` | **Validation Sample Deliverable**: C5: Address Linkage & Ground Truth Evaluation (Stratified 40-row manual inspection sample across 4 tiers) |
| **`docs/LOGIC.md`** | 51.6 KB | `4253462d336a5991e37e1dad1770dff1b9eef5f76ba3067400d0715f65dd3623` | **Engineering Documentation**: Architecture, Methodology & Design Decisions (Comprehensive 12 ADRs, benchmarks, math proofs) |
| **`docs/FILE_QUALITY_METRICS.md`** | 11.4 KB | `2b32b1305e17780e78543aea79454d81e9d582076dd67fdebc819adf72100430` | **Quality Documentation**: C3: Quality Metrics & Mutation Testing (81.50 -> 91.14 bridge, 6 mutation scorecards) |
| **`docs/EXEC_SUMMARY.md`** | 18.6 KB | `22b6655132196cdea943b2f3d75d70a15895a68a92dd8225f5163adcbc627465` | **Executive Documentation**: Executive Summary & Commercial Context (Payer contracting analysis & business impact) |
| **`docs/VIDEO_SCRIPT.md`** | 8.8 KB | `fa2ae170d8e603a9393c94bd16de26366a141010e3f05625ca706c96004aa717` | **Video Script Deliverable**: Presentation & Video Submission (5-minute timed script with 45s live UI demo) |

---

## 3. Rubric Verification Crosswalk

- **C1/C2 Index Ingestion & PPO Classification (15 pts)**: Verified via `ppo_plans.csv` and `docs/LOGIC.md` Section 3. Exactly 453 PPO plans classified, 719 HMOs excluded, 127 EOAs isolated.
- **C3 Raw Stream File Quality Grading (15 pts)**: Verified via `file_scores.csv` and `docs/FILE_QUALITY_METRICS.md`. TiC Quality Score = 91.14 (Grade A). Full 6-scenario mutation scorecard.
- **C4 Deterministic Rate Extraction (15 pts)**: Verified via `rate_outlier_review.csv` and `docs/LOGIC.md` Section 5. 27,559 curated rate keys; hierarchical tie-breaking; Revenue Code 636 disambiguated.
- **C5 Non-Circular Address Linkage (35 pts)**: Verified via `manual_check_sample.csv` and `docs/LOGIC.md` Section 6. 100% cross-source physical agreement on Strict Verified tier; 4 mutually exclusive tiers; group TIN corroboration.
- **C6 Production Deliverables & Schemas (15 pts)**: Verified via `final_curated_rates.xlsx`, `final_rates_ps_grain.csv` (48,006 rows, 0 duplicate keys), and `final_curated_rates.parquet` (69,144 rows, 45 columns).
- **C7 Cost-Effectiveness Frontier & Brownie 7a UI**: Evaluated across 19 regional cohorts; provider efficiency index computed in `docs/COST_EFFECTIVENESS.md` and interactive Streamlit modular dashboard (`app/main.py`).
- **Engineering Scalability & Quality (5 pts)**: 65 unit tests passing; zero hardcoded paths; peak memory bounded under 4.58 GB during Polars tie-breaking (~250 MB during streaming ingestion, < 280 MB during Streamlit app).

