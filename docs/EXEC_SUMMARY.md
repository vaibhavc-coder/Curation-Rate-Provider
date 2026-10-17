# Executive Summary: Centene California Commercial Group PPO Rate Transparency Curation

**Pipeline System**: Centene Price Transparency Data (PTD) Engine  
**Payer / Entity**: Centene Management Company LLC / Health Net of California  
**Publication Date**: 2026-10-06 | **Run & Audit Date**: 2026-10-17  
**Operating Environment**: TiC Schema v2.0.0, Linux x86_64, Python 3.14.6 Virtualenv  

---

## 1. Context & Business Problem

Under the federal Transparency in Coverage (TiC) final rules, major health insurers publish monthly machine-readable files (MRFs) detailing in-network negotiated rates with healthcare providers. For enterprise analytics, actuarial benchmarking, and provider contracting, extracting actionable pricing intelligence from these files presents immense technical challenges:
1. **Massive File Sizes & Structural Multiplicity**: Centene publishes in-network files exceeding 700 MB of uncompressed JSON containing over 1.5 million price lines, where 97.90% of raw records are redundant cross-reference duplicates across provider reference blocks.
2. **Missing Practicing Physical Addresses**: TiC in-network rate files provide only billing Tax Identification Numbers (TINs) and National Provider Identifiers (NPIs)—omitting physical service location addresses required to evaluate local market access and network adequacy.
3. **Plan Isolation & Network Mingling**: Payers frequently bundle multiple commercial, HMO, and open-access plans into single shared fee schedules without explicit network tags on individual rate lines.
4. **Data Quality Anomalies**: Unverified entity syntax, unbundled billing anomalies, and evergreen contract placeholders (`9999-12-31`) distort fee comparisons unless systematically audited.

---

## 2. Technical Architecture & End-to-End Pipeline

Our production data curation pipeline executes across 7 deterministic, memory-bounded phases:

```
[Phase 1: TiC Index Parsing] -> [Phase 2: Explainable PPO Classification] -> [Phase 3: Rate Profiling (DuckDB)]
                                                                                       |
[Phase 6: Final Deliverable] <- [Phase 5: Multi-Source Linkage] <- [Phase 4: Tiebreaking & Grading]
          |                                                                            |
   (Parquet/CSV/Excel)                                                      [C7: Cost-Effectiveness]
```

- **Phase 1 (Index Ingestion)**: Streaming parser reads 4 Centene/Health Net monthly index files (3,275 raw plan entries), extracting 3,271 deduplicated plan-file associations.
- **Phase 2 (PPO Network Classification)**: Regex token parser classifies 1,312 California group plans: **453 PPO plans confirmed**, 719 HMO plans excluded, 127 Exclusive Open Access (EOA) plans isolated, and 13 other variants.
- **Phase 3 (Rate File Streaming & Profiling)**: High-speed DuckDB indexing parses 2,825 provider reference groups (2,856 unique TINs) and profiles 1,717 in-network billing code items.
- **Phase 4 (C3 File Quality Grading & C4 Rate Extraction)**: Streams 1,511,720 raw prices, eliminates 1,480,048 structural fan-out duplicates, enforces hierarchical tie-breaking (base modifiers > class-matched POS > negotiated rates > expiration dates > deterministic medians), and extracts **27,559 curated rate keys**.
- **Phase 5 (C5 Multi-Source Address Linkage)**: Streams 3,694 target NPIs directly from CMS NPPES October 2026 V.2 (1.1 GB zip archive) and CMS Doctors & Clinicians; standardizes addresses with regex suite/street adapters; scores candidates across 2 independent source groups; and applies conflict rules R1–R8.
- **Phase 6 (C6 Deliverable Generation)**: Produces the **42-column lossless curated master schedule** (69,144 multi-site rows) in Parquet, CSV, and multi-sheet Excel (via `xlsxwriter` constant memory), along with the clean 6-column problem-statement CSV (`final_rates_ps_grain.csv`).
- **Challenge C7 (Cost-Effectiveness Provider Frontier)**: Establishes regional peer cohorts across 19 California counties, computing procedure benchmark medians and provider efficiency indices.

---

## 3. Key Curation Metrics & Quality Scorecard

### Core Deliverable Figures
- **Curated Primary Rate Keys**: **27,559 distinct keys** (1:1 with contract keys)
- **Multi-Site Curated Rows**: **69,144 rows** (2.51x expansion factor reflecting multi-site practice locations)
- **Distinct Billing TINs**: **2,856 TINs** (100.00% matching standard EIN format `XX-XXXXXXX`)
- **Distinct Rendering NPIs**: **3,694 NPIs** (641 Type 1, 3,044 Type 2, 8 unknown/deactivated, 1 null facility group)
- **Excel Capacity Headroom**: **93.41% headroom** on a single worksheet (capacity: 1,048,576 rows)

### File Quality & Coverage Scorecard
- **TiC Raw Quality Sub-Score (60% weight)**: **91.14 / 100.00 (Grade A)**
  - *Q1 Luhn Checksum*: 99.97% valid (15.00 / 15.00 pts)
  - *Q2 Zero Rates*: 0.00% missing rates (5.00 / 5.00 pts)
  - *Q3 Statistical Outliers*: 4.90% log-rate outliers (13.46 / 20.00 pts)
  - *Q4 Negotiated Mix*: 99.98% explicit negotiated dollar rates (10.00 / 10.00 pts)
  - *Q5 True Duplicates*: 0.76% within-block duplicate rate records (9.92 / 10.00 pts)
  - *Q6 Staleness & Currency*: 80.00 pts (11-day publication age with 30-pt evergreen contract penalty; 4.00 / 5.00 pts)
  - *Q7 Schema Completeness*: 100.00% mandatory fields populated (15.00 / 15.00 pts)
  - *Q8 Internal Consistency*: 93.82 pts (3.09% conflicting multi-rate keys; 18.76 / 20.00 pts)
- **HiLabs Benchmark Coverage Sub-Score (40% weight)**: **68.81%**
  - Matched **134 distinct procedure codes** with combined benchmark weight of **14,590,967,314** out of 21,205,590,948 across 583 distinct benchmark codes (**22.98% unweighted distinct code coverage**).
- **Combined File Score & Letter Grade**:
  $$\mathbf{0.60 \times 91.14 + 0.40 \times 68.81 = 82.21 \quad (Grade\ B)}$$

---

## 4. Address Linkage & Hold-Out Precision

Provider physical practicing locations are classified into 5 mutually exclusive tiers summing to exactly 100.00%:
- **`Verified-Strict`**: **289 NPIs (7.82%)** — Multi-source corroborated by $\ge 2$ independent source groups (NPPES primary/secondary + CMS Doctors & Clinicians).
- **`Verified-TIN-corroborated`**: **204 NPIs (5.52%)** — Multi-NPI group TIN practice location co-membership with fresh update dates.
- **`Probable`**: **1,234 NPIs (33.41%)** — Single-source practicing location with source update within 3 years.
- **`Unverified`**: **1,966 NPIs (53.22%)** — Stale single-source records (>3 years without update) or deactivated NPIs.
- **`Facility/TIN-level`**: **1 NPI (0.03%)** — Null/0 facility group placeholder fees (5 deliverable rows), capped strictly at facility level.

*Cumulative Headlines*: **Strict V1 = 7.83%** of valid NPIs (289 NPIs); **Full V2 = 13.35%** of valid NPIs (493 NPIs).

### Empirical Hold-Out Precision (N=302 CMS DAC Clinicians)
Benchmarking NPPES primary practice addresses against CMS Doctors & Clinicians independent practice data demonstrates monotonic tier precision:
1. **Strict Verified**: **100.00% precision** (203 / 203 matched; 95% Wilson CI: [98.1%, 100.0%])
2. **TIN-corroborated Verified**: **83.33% precision** (10 / 12 matched; 95% Wilson CI: [55.2%, 95.3%])
3. **Probable**: **76.00% precision** (57 / 75 matched; 95% Wilson CI: [65.2%, 84.2%])
4. **Unverified**: **0.00% precision** (0 / 14 matched; 95% Wilson CI: [0.0%, 21.5%])

---

## 5. Honest Technical Limitations & Structural Findings

1. **Shared Commercial Fee Schedule (Network Isolation)**:
   Centene/Health Net publishes a single unified in-network file (`2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json`) referenced identically across PPO, HMO, and EOA plan IDs. While plans are classified by name, the underlying rate file cannot isolate PPO from HMO rates. Deliverables are truthfully labeled as `network_label = "CA_COMMERCIAL_GROUP_SHARED_SCHEDULE"`, with contract attribution documented under `ppo_evidence_tier` (`T1_explicit_ppo`: 182 keys, `T2_shared_commercial`: 27,377 keys).
2. **Thin Type 1 Clinician Coverage (Hospital/Facility Heavy)**:
   Of 3,694 NPIs in the file, **3,044 (82.4%) are Type 2 organizations** and only **641 (17.4%) are Type 1 clinicians**. In California commercial group contracting, Health Net contracts with medical groups, IPAs, and hospital systems; individual clinicians bill through group TINs or are capitated under IPAs. This file reflects institutional and incorporated group practice schedules rather than a comprehensive census of California solo clinicians.
3. **Public FHIR Provider Directory Accessibility**:
   Centene's published DaVinci PDEX Plan Net Provider Directory endpoint (`https://iopc-provider.api.centene.com/iopc/provider/ca/metadata`) returns **HTTP 403 Forbidden** on public unauthenticated requests, requiring registered developer portal credentials. Network participation is attributed based on file metadata (`network_participation_ppo: True` for T1, `"Unknown (FHIR Unreachable)"` for T2).
4. **Evergreen Contracts & Rate Outliers**:
   100% of contracts utilize the `9999-12-31` placeholder. An empirical peer median audit identified 1,064 statistical outliers ($>10\times$ or $<0.1\times$ peer median), such as CPT 36415 at \$238.67 (18.4x median) and RC 300 at \$24,241.13. All outliers are capped at `rate_reliability = "MEDIUM"` and exported for review in `data/output/rate_outlier_review.csv`.
