# Executive Summary: Centene California Commercial Group Price Transparency Data Curation

**Pipeline System**: Centene Price Transparency Data (PTD) Engine  
**Payer / Entity**: Centene Management Company LLC / Health Net of California  
**Publication Date**: 2026-10-06 | **Run & Audit Date**: 2026-10-17  
**Operating Environment**: TiC Schema v2.0.0, Linux x86_64, Python 3.14.6 Virtualenv  

> [!IMPORTANT]
> **Payer Network Reality & Contract Schedule Notice**:
> In California, Centene publishes **one single in-network rate file** shared across all 1,312 commercial plans (453 PPO, 719 HMO, 131 EOA/Other). In the raw file, `network_name` is **100% empty across all 2,825 provider references**.
> Consequently, the raw rate file **cannot isolate PPO from HMO or EOA plans**.
> This deliverable represents Centene's **California Commercial Group Master Fee Schedule**, covering in-network commercial contracts. Contract attribution tiers are documented honestly:
> - **`T2_shared_commercial` (27,377 curated rate keys / 68,817 lossless rows)**: Commercial master fee schedule shared across PPO and HMO contracts without explicit network markers.
> - **`T1_explicit_ppo` / `name_hint_ppo` (182 curated rate keys / 327 lossless rows)**: Provider groups whose business name string in the raw file contains the keyword `"PPO"` (e.g. `"PPO: Sacramento County"`, `"PPO: Los Angeles County"`).
> - **PPO Network Participation**: Because the raw file provides no plan link or network confirmation, `network_participation_ppo` is set to **`"Unknown"` across all rows** unless external directory participation is confirmed.

---

## 1. Technical Architecture & End-to-End Pipeline

The production pipeline executes across 7 deterministic, memory-bounded phases:

```
[Phase 1: TiC Index Ingest] -> [Phase 2: Explainable PPO Classifier] -> [Phase 3: Rate Profiling (DuckDB)]
                                                                                |
[Phase 6: Final Deliverable] <- [Phase 5: Multi-Source Linkage]   <- [Phase 4: Tiebreaking & Grading]
         |                                                                      |
  (Parquet/CSV/Excel)                                                [C7: Cost-Effectiveness]
```

- **Phase 1 (Index Ingestion)**: Streaming parser reads 4 Centene/Health Net monthly index files (3,275 raw plan entries), extracting 3,271 deduplicated plan-file associations.
- **Phase 2 (PPO Network Classification)**: Regex token parser classifies 1,312 California group plans: **453 PPO plans confirmed**, 719 HMO plans excluded, 127 Exclusive Open Access (EOA) plans isolated, and 13 other variants.
- **Phase 3 (Rate File Streaming & Profiling)**: High-speed DuckDB indexing parses 2,825 provider reference groups (2,856 unique TINs; 4,576 provider group records) and profiles 1,717 in-network billing code items.
- **Phase 4 (C3 File Quality Grading & C4 Rate Extraction)**: Streams 1,511,720 raw prices, eliminates 1,480,048 structural fan-out duplicates, enforces hierarchical tie-breaking (base modifiers > class-matched POS > negotiated rates > expiration dates > deterministic medians), and extracts **27,559 curated rate keys**.
- **Phase 5 (C5 Multi-Source Address Linkage)**: Streams 3,694 target NPIs directly from CMS NPPES October 2026 V.2 (1.1 GB zip archive) and CMS Doctors & Clinicians; standardizes addresses with regex suite/street adapters; scores candidates across 2 independent source groups; and applies conflict rules R1–R8.
- **Phase 6 (C6 Deliverable Generation)**: Produces the **42-column lossless curated master schedule** (69,144 multi-site rows) in Parquet, CSV, and multi-sheet Excel (via `xlsxwriter` constant memory), along with the clean 6-column problem-statement CSV (`final_rates_ps_grain.csv`, exactly 48,006 unique rows).
- **Challenge C7 (Cost-Effectiveness Provider Frontier)**: Establishes regional peer cohorts across 19 California counties, computing procedure benchmark medians and provider efficiency indices.

---

## 2. Core Deliverables & Grain Reconciliation

The pipeline cleanly separates the required problem-statement grain from the lossless relational deliverable:

| Deliverable Artifact | Row Count | Column Count | Key Definition & Grain Description |
| :--- | :---: | :---: | :--- |
| **`final_rates_ps_grain.csv`** | **48,006** | 6 | **Exact Problem Statement Grain**: Unique `(NPI, TIN, Address, Billing Code)` tuples with deterministic median rate aggregation. Zero duplicate keys. |
| **`final_curated_rates.xlsx` (Sheet 1: `Final_Rates_PS_Grain`)** | **48,006** | 6 | Problem-statement grain with formatted currency columns, fully fitting in Excel (capacity: 1,048,576 rows; **95.42% headroom**). |
| **`final_curated_rates.parquet`** | **69,144** | 42 | **Lossless Relational Schedule**: Multi-site practicing locations (2.51x expansion) and complete relational metadata. |
| **`final_curated_rates.csv`** | **69,144** | 42 | Full RFC 4180 flat file matching Parquet schema bit-for-bit. |
| **`final_curated_rates.xlsx` (Sheet 2: `Lossless_Curated_Rates`)** | **69,144** | 42 | Lossless table with 42 relational governance columns and audit flags. |
| **`final_curated_rates.xlsx` (Sheet 3: `Notes`)** | Metadata | 2 | Technical definitions, column dictionary, and documented assumptions. |

### Arithmetic Grain Reconciliation:
$$\begin{aligned}
\text{Curated Contract Rate Keys (Base)} &= \mathbf{27,559} \\
\text{Multi-Site Physical Address Expansion} &\to \mathbf{48,006} \quad (\text{Unique } [NPI, TIN, Address, Code] \text{ keys}) \\
\text{Lossless Modifier/Service Sub-Items} &\to \mathbf{69,144} \quad (\text{Full relational deliverable})
\end{aligned}$$

---

## 3. File Quality Scorecard & Score Transparency Bridge

The overall composite score is **82.21 (Grade B)**, combining raw data stream quality (60%) and HiLabs procedure coverage (40%):

$$\text{Combined Score} = 0.60 \times 91.14 + 0.40 \times 68.81 = 54.684 + 27.524 = \mathbf{82.21} \quad (\mathbf{Grade\ B})$$

### Raw Quality Metrics Table (60% Weight, Score = 91.14 / 100.00, Grade A)
Evaluated across all 1,511,720 raw expanded prices in `raw_price_audit.parquet`:

| Metric ID | Metric Name | Weight | Measured Raw Value | Metric Score | Weighted Points | Relational Significance & Formula |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| **Q1_NPI_LUHN** | NPI Luhn Checksum | 0.15 | 99.97% valid (1 placeholder: NPI 0) | 99.97 | 15.00 | Modulo-10 check digit verification over `80840 + NPI` |
| **Q2_ZERO_RATE** | Zero / Null Rate Share | 0.05 | 0.00% zero or missing rates | 100.00 | 5.00 | Saturated contractual baseline: $\max(0, 100 - \text{zero\_pct} \times 10)$ |
| **Q3_OUTLIER_SHARE**| Outlier Share (Robust MAD) | 0.20 | 4.90% log-rate outliers per code/class | 67.30 | 13.46 | Outliers exceeding $2.5 \times \text{MAD}$ on $\log(\text{rate})$ |
| **Q4_NEGOTIATED_MIX**| Negotiated Dollar Rate Mix | 0.10 | 99.98% explicit negotiated dollar rates | 99.98 | 10.00 | Explicit dollar rates over percentage fee schedules |
| **Q5_DUPLICATE_RATIO**| True Duplicate Rate Ratio | 0.10 | 0.76% within-block duplicate prices | 99.24 | 9.92 | True duplicates within rate blocks (11,432 rows) |
| **Q6_STALENESS** | Expiration Date Currency | 0.05 | 80.00 pts (11d publication age, 30pt evergreen penalty) | 80.00 | 4.00 | 50% publication freshness (100 pts) / 50% evergreen penalty (70 pts) |
| **Q7_SCHEMA_VALIDITY**| Schema Completeness | 0.15 | 100.00% mandatory TiC fields populated | 100.00 | 15.00 | Presence of `tin`, `billing_code`, `negotiated_rate`, `class` |
| **Q8_INTERNAL_CONSISTENCY**| Internal Consistency | 0.20 | 3.09% multi-rate finest keys | 93.82 | 18.76 | Conflict rate on finest key: $\max(0, 100 - \text{conflict\_pct} \times 2)$ |
| **TOTALS** | | **1.0000** | | | **91.14** | **Quality Score = 91.14 (Grade A)** |

### +9.64 Point Quality Score Bridge (Method v1 $\to$ Method v2)
- **Method v1 Baseline Score (Checkpoint D/E)**: **81.50** (Quality Grade B)
  - In Method v1, Q5 scored the entire structural cross-reference fan-out (97.90% duplicates) as file defects, yielding a Q5 score of 2.10 points ($2.10 \times 0.10 = 0.21$ weighted points).
- **Q5 Duplication Realignment**: **+9.71 points**
  - Distinguishing true within-block rate duplicates (0.76%, 11,432 rows $\to$ 99.24 pts) from structural cross-reference fan-out (reported descriptively) added $+9.71$ weighted points ($9.92 - 0.21$).
- **Q6 Staleness & Currency Calibration**: **+0.50 points**
  - Moving from an arbitrary 70.0 baseline to the documented 50/50 blend (100 pts publication freshness + 70 pts evergreen contract penalty = 80.0 pts) added $+0.50$ weighted points ($4.00 - 3.50$).
- **Minor Adjustments across Q1, Q3, Q8**: **-0.57 points**
  - Full-file reconciliation of robust MAD log-rate outliers and check digit checks.
- **Method v2 Production Score**: $\mathbf{81.50 + 9.71 + 0.50 - 0.57 = 91.14}$ (Grade A).

*Q6 Blend Sensitivity*: If scored 100% on publication freshness (100 pts), quality score is 92.14 (+1.00 pt). If scored 100% on evergreen penalty (70 pts), quality score is 90.64 (-0.50 pt). The combined score remains Grade B (81.91 to 82.81) across all blend assumptions.

---

## 4. Address Linkage & Non-Circular Hold-Out Precision

Provider physical practicing locations are classified into mutually exclusive tiers summing to 100.00% across all 3,694 unique NPIs and 2,856 TINs:

| Status Tier | Primary NPIs | Primary NPI Share | Unique TINs | TIN Share | Evidentiary Qualification Basis |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`Verified-Strict` (V1)** | 288 | 7.80% | 185 | 6.48% | Multi-source agreement between $\ge 2$ independent groups (NPPES + CMS DAC). |
| **`Verified-TIN-corroborated` (V2)** | 203 | 5.50% | 152 | 5.32% | Single high-trust source with multi-NPI TIN group practice location co-membership. |
| **`Probable`** | 1,242 | 33.62% | 1,084 | 37.96% | Single-source active practice location in California (both fresh and stale NPPES records). |
| **`Unverified`** | 1,956 | 52.95% | 1,432 | 50.14% | Deactivated NPIs (R4), non-CA addresses (R5), or unlinked records. |
| **`Facility/TIN-level`** | 5 | 0.14% | 3 | 0.11% | NPI 0 / NULL facility fee placeholders, strictly capped at facility/TIN level. |
| **TOTALS** | **3,694** | **100.00%** | **2,856** | **100.00%** | Mutually exclusive, 100.00% reconciled partition. |

### Non-Circular Independent Hold-Out Validation (Federal NPI Registry API)
To remove tautological bias, a stratified random sample of **325 primary NPIs** was drawn across tiers and entity types and validated against the independent **federal NPI Registry API** practice location endpoint (`https://npiregistry.cms.hhs.gov/api/`):

| Evaluation Segment | Sample Size (N) | API Location Matched (K) | Measured Precision | Wilson 95% Confidence Interval |
| :--- | :---: | :---: | :---: | :---: |
| **OVERALL SAMPLE** | **325** | **273** | **84.00%** | **[79.6%, 87.6%]** |
| **Verified Tier** | 101 | 85 | **84.16%** | **[75.8%, 90.0%]** |
| **Probable Tier** | 123 | 88 | **71.54%** | **[63.0%, 78.8%]** |
| **Unverified Tier (Stale/Uncorroborated)** | 101 | 100 | **99.01%** | **[94.6%, 99.8%]** |

### Empirical Finding on 3-Year Staleness Demotion:
Evaluating agreement between NPPES practice addresses and CMS Doctors & Clinicians data across last update age cohorts revealed:
- `< 1 year`: **64.52% agreement** (20 / 31; 95% CI: [46.9%, 78.9%])
- `1 - 3 years`: **70.37% agreement** (38 / 54; 95% CI: [57.2%, 80.9%])
- `3 - 5 years`: **58.97% agreement** (23 / 39; 95% CI: [43.4%, 72.9%])
- `> 5 years`: **61.24% agreement** (109 / 178; 95% CI: [53.9%, 68.1%])
- **Conclusion**: Established brick-and-mortar clinical facilities do not change physical location frequently. Because >5-year stale addresses agree with CMS DAC at 61.24% (indistinguishable from <1-year at 64.52%), **outright demotion of stale NPPES records to Unverified is empirically unjustified**. The pipeline retains them as `Probable` and recalibrates their confidence score to the measured precision of ~0.612.

---

## 5. Measured California Healthcare Provider Coverage Context

Rather than utilizing rough estimates, provider coverage was measured directly by streaming all 9 million records in the CMS NPPES October 2026 V.2 archive (`NPPES_Data_Dissemination_October_2026_V2.zip`):
- **Active California Type 1 Clinicians**: **997,026 NPIs**
- **Active California Type 2 Organizations**: **198,588 NPIs**
- **Total Active California NPIs**: **1,195,614 NPIs** (plus 538 deactivated NPIs)
- **Rate File California NPI Census**: **3,693 non-zero active NPIs** (641 Type 1, 3,044 Type 2) + 1 placeholder NPI 0.

### Top 20 California NUCC Specialties Measured Coverage:
| NUCC Code | Specialty Description | Active CA Census (NPPES) | Rate File Count | Measured Coverage |
| :--- | :--- | :---: | :---: | :---: |
| `106S00000X` | Behavior Technician | 175,093 | 0 | 0.00% |
| `106H00000X` | Marriage & Family Therapist | 57,609 | 246 | 0.43% |
| `390200000X` | Student in Health Care Training | 51,132 | 4 | 0.01% |
| `101YM0800X` | Mental Health Counselor | 41,208 | 93 | 0.23% |
| `183500000X` | Pharmacist | 33,558 | 0 | 0.00% |
| `1041C0700X` | Clinical Social Worker | 31,994 | 73 | 0.23% |
| `101YA0400X` | Addiction Counselor | 31,749 | 13 | 0.04% |
| `207R00000X` | Internal Medicine Physician | 25,877 | 169 | 0.65% |
| `225100000X` | Physical Therapist | 25,638 | 61 | 0.24% |
| `1223G0001X` | General Practice Dentistry | 24,461 | 0 | 0.00% |
| `103K00000X` | Behavior Analyst | 22,402 | 6 | 0.03% |
| `207Q00000X` | Family Medicine Physician | 21,133 | 182 | 0.86% |
| `171M00000X` | Case Manager / Care Coordinator | 21,014 | 0 | 0.00% |
| `122300000X` | General Dentist | 20,859 | 1 | 0.01% |
| `101Y00000X` | General Counselor | 20,102 | 16 | 0.08% |
| `363LF0000X` | Family Nurse Practitioner | 17,654 | 7 | 0.04% |
| `111N00000X` | Chiropractor | 16,386 | 1 | 0.01% |
| `363A00000X` | Physician Assistant | 15,821 | 6 | 0.04% |
| `163W00000X` | Registered Nurse | 14,714 | 0 | 0.00% |
| `235Z00000X` | Speech-Language Pathologist | 14,677 | 5 | 0.03% |

*Interpretation*: Health Net's commercial fee schedule covers medical groups, hospitals, and outpatient clinics. Solo clinicians are largely capitated under Independent Practice Associations (IPAs) or bill under facility TINs. Specialized lines (dental, pharmacy, autism behavioral technicians) are managed under carve-out benefit plans.

---

## 6. Raw Data Integrity & File Audit Findings

1. **UB-04 Revenue Code Descriptions**:
   In the raw JSON, Centene bundled CPT procedure names into institutional revenue code blocks (e.g. RC 300 carried `description: 'SEX HORMONE BINDING GLOBULIN (SHBG)'` from bundled item 217). The pipeline implements standard CMS/NUBC UB-04 category mappings (`src/ptd/ub04_revenue_codes.py`), ensuring RC 300 is correctly labeled as `"Laboratory - General clinical assay"` across all rows, preventing CPT bleeding.
2. **Rate Outliers Without Speculation**:
   CPT 96372 at \$1,907.88 (46.9x peer median) and CPT 81003 at \$671.84 were audited directly in the raw JSON:
   - CPT 96372 links to Provider Reference 1246 (`Regents Of The University Of California`, TIN `68-0344702` and `PALOMINO, M.D.`, TIN `68-0334324`).
   - CPT 81003 links to Provider Reference 1143 (`Direct Network: San Diego`, TIN `33-0235473`).
   - Both entries are published as explicit dollar amounts with no percentage or unit indicators. Because contract terms are not specified in TiC schema, they are objectively classified as **"unexplained outliers"** without speculative rationalization.
3. **Raw TIN Types**:
   Provider reference records contain **100.00% Employer Identification Numbers (`ein`)** across all 4,576 provider group records (0 NPI-as-TIN rows). TIN normalization formats EINs as `XX-XXXXXXX` while keeping NPIs as 10-digit integers, ensuring NPIs are never reformatted as EINs.
4. **Zero Mock Data Production Guarantee**:
   A repository-wide audit verified that zero mock, synthetic, or placeholder data feeds any production deliverables. Mock fixtures are strictly restricted to isolated unit test files (`tests/test_phase4.py`, `tests/test_rate_stream.py`).
