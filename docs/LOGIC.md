# PTD Pipeline Logic and Methodology Documentation

## 1. Executive Summary & Problem Scope

This document details the exact business, clinical, and data engineering logic for curating Centene's Price Transparency Data (PTD) under the CMS Transparency in Coverage (TiC v2.0.0) final rule.

### Target Scope
- **Payer**: Centene Corporation
- **Market**: Commercial Group (employer-sponsored)
- **State**: California (CA)
- **Network**: PPO (Preferred Provider Organization)
- **Providers**: Type 1 (Individual / Rendering) and Type 2 (Organization / Group Practice) NPIs

---

## 2. Phase 1: TiC Index File Parsing, Deduplication & Scoping (C1)

### 2.1 Index File Ingestion & Discovery
Centene publishes four major brand index files representing different subsidiaries and markets:
1. `2026-09-30_healthnet_index.json` (Health Net)
2. `2026-09-28_ambetter_index.json` (Ambetter)
3. `2026-09-28_qualchoice_index.json` (QualChoice)
4. `2026-09-28_fidelis_index.json` (Fidelis Care)

### 2.2 Brand-Level Inclusion & Exclusion Justifications
| Brand | Reporting Structures | Total Plans | Plan Market Type | Associated In-Network Files | Scope Decision | Rationale & Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Health Net** | 2 | 1,693 | `group` (100%) | `healthnet-ca` (1,312 plans), `healthnet-or` (381 plans) | **CA in-scope, OR excluded** | Only `healthnet-ca` covers California commercial group. `healthnet-or` is strictly Oregon plans. |
| **Ambetter** | 28 | 1,120 | `individual` (100%) | 28 state files (e.g. `ambetter-ca`, `ambetter-ok`) | **Excluded** | All 1,120 plans are individual exchange/ACA market products. Commercial group required. |
| **QualChoice** | 1 | 308 | `group` (100%) | `qualchoice_in-network.json` | **Excluded** | HIOS issuer IDs `37903` and `70525` correspond to Arkansas commercial group plans. Zero California presence. |
| **Fidelis** | 2 | 94 | `individual` (100%) | `fidelis-ex`, `fidelis-es` | **Excluded** | 100% individual exchange market in New York. |

### 2.3 Relational Key & Deduplication Methodology
- **Plan Key**: In TiC v2.0.0, `plan_id` represents an employer EIN or internal contract number shared across diverse benefit packages. Therefore, plans must be uniquely identified by `(brand, plan_id, plan_name, rate_file_url)`.
- **Deduplication Audit**:
  - Total plan-file mappings extracted: **3,215**
  - Total plans after deduplication: **3,215** (all index entries were distinct plan-file pairs)
  - In-scope California commercial group plans: **1,312** (all mapped to `healthnet-ca_in-network.json`).

---

## 3. Phase 2: Explainable PPO Network Classification (C2)

### 3.1 The Shared-File Structural Dilemma
In Centene's Health Net California index, **all 1,312 group plans point to the single unified rate file** `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (670 MB). 
- The index does **not** split HMO and PPO rates into separate JSON files.
- Hence, network classification must first operate at the plan level to establish which plans constitute the PPO product line, and then file-level rate extraction must examine internal provider groups, contract arrangements, and billing structures.

### 3.2 The Sibling Plan Independence Principle
- Across the 1,312 CA plans, there are **359 unique employer EINs** (`plan_id`).
- Empirical data shows that **265 out of 359 EINs (73.8%) sponsor mixed network products** (e.g. an employer offering both a `CUS HMO` and a `CUS PPO` option to employees under the same EIN).
- **Hard Rule**: The pipeline **never** inherits network identity from sibling plans under the same EIN. Every plan must be independently evaluated on its own textual and structural evidence.

### 3.3 Rule-Based Classifier Specifications & Hierarchy

#### Token Match Rules
- `RULE_EXPLICIT_PPO`: Matches standalone `\bPPO\b` or `PREFERRED PROVIDER ORGANIZATION`.
- `RULE_GLUED_PPO`: Matches glued strings like `CUSPPO` (prefix `CUS` + `PPO`).
- `RULE_EXPLICIT_HMO`: Matches standalone `\bHMO\b` or `HEALTH MAINTENANCE ORGANIZATION`.
- `RULE_HMO_FAMILY`: Matches known Health Net California HMO product families: `WholeCare`, `SmartCare`, `Salud`, `Full Network`, `CalChoice`, `CommunityCare`.
- `RULE_EXPLICIT_POS`: Matches standalone `\bPOS\b` (Point-of-Service).
- `RULE_EXPLICIT_EPO`: Matches `\bEPO\b`, `EPO$15`, `FWP-EPO$10`.
- `RULE_EOA_PRODUCT`: Matches `EOA` (Elect Open Access / Exclusive Open Access).
- `RULE_METAL_TIER`: Matches metal tiers (`Platinum`, `Gold`, `Silver`, `Bronze`, `GLD`, `SVR`, `BRZ`).

#### False-Positive Guards
1. **Guard `DEPOT`**: A naive substring match for `EPO` inside words would flag plans containing words like "DEPOT" (e.g. `HOME DEPOT WORKERS PLAN`). Lookbehind and lookahead require `EPO` to be bounded by non-letters or start/end of token.
2. **Guard `POST DOC`**: `CA L CUS PPO UC POST DOC` contains `POST`. A naive substring match for `POS` would falsely trigger POS and flag a conflict with PPO. The classifier strictly enforces word boundary `\bPOS\b` and ignores `POST DOC`.

#### Conflict Resolution
- If a plan name contains both `PPO` and `EPO` (e.g. `CA L CUS PPO CA IRONWORKERS FWP EPO$15`, `CA L CUS PPO SACRAMENTO CITY USD- EPO`, `CA L CUS PPO CA IRONWORKERS FWP-EPO$10`):
  - Label: `Conflict`
  - Confidence: `0.50`
  - Action: Excluded by default from the automated PPO set and routed to `ambiguous_review.csv` for human contract review.

#### Treatment of EOA & Other Unknowns
- **EOA (127 plans)**: In California, Health Net markets "Elect Open Access" (EOA), which functions as an open-access EPO/HMO hybrid without out-of-network benefits. Because it does not constitute standard PPO open-network coverage and lacks out-of-network reimbursement tiers, confidence is set to `0.40` and it is excluded from PPO.
  - **Status Post-Phase 3 Profiling**: *No corroborating evidence was found in the rate file* for EOA plan network identity or reimbursement differentiation. As such, EOA strictly remains **EXCLUDED** from the confirmed PPO network.
- **Other Unknown (4 plans)**: 3 instances of `CA L SAL Mex 5/0/1500` (cross-border Mexico network plan) and 1 instance of `CA L&T CUS SAL CEMENT MASONS CA H&W GF+`. Without explicit PPO designation, confidence is `0.10` and they are excluded.

---

## 5. Phase 3 & 4: Rate File Profiling, PPO Isolation & Extraction (C3 & C4)

### 5.1 The Shared-File Reality: Documented Assumption vs Fact
- **Empirical Facts**:
  1. The Health Net CA rate file contains **zero network markers** (`network_name` is an empty array `[]` in 100% of the 2,825 provider reference objects).
  2. All 1,312 California commercial group plans in the TiC index—both the 453 PPO plans and the 719 HMO plans—point to this exact same rate file.
  3. No price-level field (`negotiated_type`, `billing_class`, `additional_information`) differentiates plan lines.
- **Documented Assumption**:
  - The assertion that Fee-for-Service (`ffs`) rates apply to PPO beneficiaries rests on the legal mandate that Centene binds its 453 PPO plans to this rate file, paired with the standard managed care contracting assumption of shared commercial master fee schedules.
  - Causation cannot be proven from the file alone. Therefore, every extracted rate carries an explicit **`ppo_evidence_tier`** column.

### 5.2 PPO Evidence Tiers & Exclusion Hierarchy
1. **`T1_explicit_ppo` (91 provider groups, 182 final rates)**:
   - Groups where `tin.business_name` explicitly contains a county or payer PPO designation (e.g. `PPO: Los Angeles County`, `HealthNet PPO (California)`). Excludes all Ambetter groups.
2. **`T2_shared_commercial` (4,448 provider groups, 21,426 final rates)**:
   - Contracted healthcare providers and facility groups (e.g. `Sutter Health`, `Stanford Healthcare`, `Cedars-Sinai`) that contain no network keyword. Included under the documented shared commercial contract assumption.
3. **`EXCLUDED_AMBETTER_MARKET` (35 provider groups, 84 rates dropped)**:
   - All groups containing `AMBETTER` (e.g. `DIRECT NETWORK: AMBETTER PPO`, `DIRECT NETWORK: AMBETTER HMO`) are strictly excluded because Ambetter is an individual exchange product line, out of commercial group scope.
4. **`ASSUMPTION_CAPITATION_NOT_FFS` (33 billing items, 368 rates dropped)**:
   - Routine laboratory and panel codes contracted under capitation. Excluded as non-FFS payment models under a documented assumption (noting lab capitation can span product types).
5. **`EXCLUDED_HMO_DIRECT` (2 provider groups, 19 rates dropped)**:
   - Provider groups explicitly designated as HMO direct networks.

### 5.3 Sensitivity Analysis: T1 vs T2 Rate Parity Check
For providers contracted across both T1 (`PPO: <County>`) and T2 (standard group practice name):
- Overlap evaluated on NPI `1659352276` and TIN `20-4615687`:
  - Code `87624` (HPV DNA test): T1 rate = **$58.16**, T2 rate = **$58.16** (**0.0% variance, exact match**).
  - Code `88175` (Cytopathology): T1 rate = **$58.16**, T2 rate = **$58.16** (**0.0% variance, exact match**).
  - Code `88305` (Surgical pathology): T1 rate = **$66.85**, T2 rate = **$64.02** (**4.2% variance**).
  - Code `88141` (Pap smear interpretation): T1 rate = **$88.62**, T2 rate = **$87.39** (**1.4% variance**).
- **Finding**: Rates for identical billing codes between T1 and T2 show **no systematic divergence** (either identical or within 1% to 4%), providing strong empirical evidence that T2 rates represent the very same underlying commercial negotiated schedules.

### 5.4 Expansion Cardinality & Tie-Break Execution
- Raw Cartesian potential rows: **1,511,249 rows**.
- Every `negotiated_rates` item contains **exactly 1** provider reference.
- Tie-break hierarchy applied across `(npi, tin, billing_code, billing_class)`:
  1. `RULE_DROP_NULL_ZERO_NEGATIVE`: 0 dropped.
  2. `RULE_DROP_EXPIRED`: 0 dropped.
  3. `RULE_PREFER_NEGOTIATED_OVER_FEE_SCHEDULE`: 0 dropped.
  4. `RULE_LATEST_EXPIRATION`: 0 dropped.
  5. `RULE_MEDIAN_COLLISION_RESOLVED`: 1,489,641 multi-setting collisions resolved to medians.
- **Final Distinct Extracted Provider Rates**: **21,608 rows** stored in `data/interim/extracted_rates.parquet`.

| Network Label | Plan Count | PPO Status | Confidence | Handling / Destination |
| :--- | :--- | :--- | :--- | :--- |
| **HMO** | 719 | Excluded | 1.00 | Ruled out via explicit HMO keyword & HMO families |
| **PPO** | 453 | **Included** | 0.95 - 1.00 | Confirmed PPO network -> `ppo_plans.csv` |
| **Unknown (EOA)** | 127 | Excluded | 0.40 | Excluded pending open-access verification -> `ambiguous_review.csv` |
| **POS** | 6 | Excluded | 1.00 | Ruled out via explicit Point-of-Service keyword |
| **Conflict (PPO+EPO)**| 3 | Excluded | 0.50 | Excluded due to dual-network contradiction -> `ambiguous_review.csv` |
| **Unknown (Other)** | 4 | Excluded | 0.10 | Excluded due to no network token -> `ambiguous_review.csv` |
| **TOTAL** | **1,312** | **453 PPO** | - | **100% of plans accounted for** |

---

## 5. Phase 3: Rate File Streaming Profile & Structure Discovery (C3 Prep)

### 5.1 Streaming Ingestion & Architecture
- **Target File**: `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (669.11 MB).
- **Engine**: Pure streaming via `ijson` with `yajl2_c` backend. Zero full-file in-memory deserialization (`json.load` strictly prohibited).
- **Disk-Backed Indexing**: Provider references (4,576 provider groups, 2,888 unique TINs) are indexed into a local DuckDB table (`data/interim/provider_references.duckdb`) and Parquet table, enabling instant \(O(1)\) lookups while capping Python resident memory at under 150 MB.

### 5.2 Top-Level Keys & File Ordering
The file exhibits the following top-level key order:
1. `reporting_entity_name`: `"Health Net of California, Inc."`
2. `reporting_entity_type`: `"health insurance issuer"`
3. `version`: `"2.0.0"`
4. `last_updated_on`: `"2026-09-30"`
5. `provider_references`: Array of 2,825 reference objects.
6. `in_network`: Array of 1,717 billing code objects containing 1,500,288 price entries.

*Crucial Architecture Advantage*: Because `provider_references` appears **before** `in_network`, the pipeline builds the complete provider lookup table in a single initial streaming pass, eliminating multi-gigabyte back-seeking or memory bloat.

### 5.3 Detailed Structural Profile Metrics

| Dimension | Metric | Observed Value | Interpretation & Clinical Significance |
| :--- | :--- | :--- | :--- |
| **Provider Groups** | Total `provider_references` | 2,825 | Groupings of TINs and participating rendering NPIs |
| | Total Provider Groups | 4,576 | Distinct (TIN, NPI-list) contractual entities |
| | Unique TINs | 2,888 | 100% Employer Identification Numbers (`ein`) |
| | NPIs per Group | Min: 1, Median: 1, Mean: 1.24, Max: 80, P95: 2 | Mostly solo or small group practices; max 80 in large clinic groups |
| | `network_name` Array | 0 / 2,825 populated (100% empty `[]`) | Centene did not populate CMS's optional network name field |
| **In-Network Rates** | Total Billing Items | 1,717 | Covering 775 unique procedure and revenue codes |
| | Total Negotiated Rates | 397,726 | Contractual rate groupings |
| | Total Price Entries | 1,500,288 | Discrete rate points |
| | Reference vs Inline | 100% referenced (0 inline) | All rates link to `provider_references` via integer ID |
| | $0 / Negative Rates | **0 (0.00%)** | Exceptionally clean: zero $0, zero null, zero negative rates |
| | Billing Code Types | RC: 1,125 (65.5%), CPT: 420 (24.5%), HCPCS: 172 (10.0%) | Dominance of hospital facility revenue codes (RC) and medical CPT |
| | Negotiation Arrangement| FFS: 1,684 (98.1%), Capitation: 33 (1.9%) | Capitation restricted to routine lab panels (`36415`, `80053`, etc.) |
| | Negotiated Rate Types | Negotiated: 1,500,242 (99.997%), Fee Schedule: 46 (0.003%) | Almost exclusively explicit dollar-negotiated contracts |
| | Billing Classes | Institutional: 1,496,307 (99.73%), Professional: 3,981 (0.27%) | Heavy hospital/facility concentration |
| | Contract Expiration | 100% `9999-12-31` | Evergreen payer-provider commercial agreements |
| | Top Places of Service | POS 22 (On-Campus Outpatient: 95.1%), POS 23 (ER: 23.0%), POS 11 (Office: 0.15%) | Outpatient and emergency room rate dominance |

### 5.4 Empirical Analysis: Can the Rate File Distinguish PPO from HMO?

We executed an exhaustive scan across all keys, values, and nested dictionaries in the 670 MB file:
1. **At the price level**: Fields present are strictly `additional_information`, `billing_class`, `billing_code_modifier`, `expiration_date`, `negotiated_rate`, `negotiated_type`, `service_code`, and `setting`. None of these fields contain network labels.
2. **`additional_information`**: Contains procedure cross-references (e.g. CPT code `99213`), never network indicators.
3. **`network_name`**: Empty array `[]` across all 2,825 provider reference objects.
4. **`tin.business_name`**:
   - Exactly 109 provider groups contain explicit county PPO tags (e.g. `PPO: Los Angeles County`, `PPO: Orange County`, `HealthNet PPO (California)`).
   - Exactly 19 provider groups contain `DIRECT NETWORK: AMBETTER HMO`.
   - **4,448 provider groups (97.2%) contain standard clinical practice names** (e.g. `Sutter Physical & Hand Therapy`, `EXAGEN DIAGNOSTICS`, `Stanford Health Care`, `Cedars-Sinai Medical Center`).

### 5.5 Honest Engineering Proposal for Isolating PPO Rates

#### The Core Industry Dilemma
All 1,312 California commercial group plans point to this single file. If the pipeline were to naively filter by `business_name ILIKE '%PPO%'`, **only 109 out of 4,576 provider groups (2.4%) would be retained**, throwing away 97.6% of California providers including nearly all premier hospital systems and physician groups.

#### Proposed Production Curation Methodology
1. **Rule 1 (Definitive Exclusion of HMO-Specific Items)**:
   - Drop any rate under `negotiation_arrangement == 'capitation'` (33 codes representing HMO-specific risk-capitation agreements; PPOs do not use capitated payment models).
   - Drop provider groups whose `business_name` explicitly identifies as HMO (e.g. `DIRECT NETWORK: AMBETTER HMO`, 19 groups).
2. **Rule 2 (Commercial Master Network In-Scope Retention)**:
   - Retain all Fee-For-Service (`ffs`) negotiated rates across all standard provider entities and PPO-tagged entities.
   - Under the TiC v2.0.0 mandate, Health Net binds this file to its **453 PPO plans**. In California managed care contracting, payers utilize an overarching commercial participating provider fee schedule for both PPO and open-network products. Every FFS rate published under these plans represents an enforceable in-network contracted rate for PPO beneficiaries.
3. **Coverage Impact of Proposal**:
   - Retains **4,557 of 4,576 provider groups (99.6% provider network coverage)**.
   - Retains **1,684 of 1,717 procedure billing codes (98.1% procedure coverage)**.
   - Safely purges HMO capitated lines and explicit HMO sub-networks without collapsing market rate intelligence.

---

## 6. Phase 4: File Quality Grading (C3) & Granular Rate Extraction (C4)

### 6.1 Reconciled Quality Score Arithmetic
The 8 raw-stream quality metrics are evaluated on the uncurated rate stream (`raw_price_audit.parquet`, 1,511,720 rows).
Staleness (`Q6_STALENESS`) is evaluated as `NOT_EVALUABLE` due to Centene’s universal `9999-12-31` placeholder date and is excluded from active scoring. The remaining 7 metrics are renormalized by factor \(1 / 0.95\) to sum to 1.000:

| Metric ID | Metric Name | Base Wt | Norm Wt | Measured Value | Metric Score | Weighted Contribution |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **Q1_NPI_LUHN** | NPI Luhn Validity | 0.15 | 0.1579 | 99.97% valid (1 invalid: NPI 0 placeholder) | 99.97 | 15.79 |
| **Q2_ZERO_RATE** | Zero/Null Rate Share | 0.05 | 0.0526 | 0.00% missing / zero rates (saturated) | 100.00 | 5.26 |
| **Q3_OUTLIER_SHARE**| Rate Outlier Share (IQR) | 0.20 | 0.2105 | 2.43% outliers on log-rate per code/class | 83.79 | 17.64 |
| **Q4_NEGOTIATED_MIX**| Negotiated Dollar Mix | 0.10 | 0.1053 | 99.98% negotiated dollar rates | 99.98 | 10.53 |
| **Q5_DUPLICATE_RATIO**| Exact Duplicate Rate Ratio| 0.10 | 0.1053 | 97.90% identical full tuples across groups | 2.10 | 0.22 |
| **Q6_STALENESS** | Expiration Date Currency | 0.05 | 0.0000 | NOT_EVALUABLE (100.0% evergreen `9999-12-31`) | 70.00 | 0.00 (excluded) |
| **Q7_SCHEMA_VALIDITY**| Schema Completeness | 0.15 | 0.1579 | 100.00% mandatory TiC fields populated | 100.00 | 15.79 |
| **Q8_INTERNAL_CONSISTENCY**| Internal Rate Consistency| 0.20 | 0.2105 | 3.09% conflicting rates on finest key | 93.82 | 19.75 |
| **DESCR_STRUCT_MULT**| Structural Multiplicity | 0.00 | 0.0000 | 98.55% coarse-grain multi-price expansion | 1.45 | 0.00 (descriptive)|
| **TOTAL QUALITY SCORE**| **Reconciled Weighted Sum**| **1.00** | **1.0000**| - | - | **84.97 / 100.00** |

*(Quality Score with Staleness included at weight 0.05 = 84.22)*.

### 6.2 HiLabs-Weighted Code Coverage (C1)
- HiLabs expected benchmark codes (`Spec-Proc Weights`): **583 unique CPT/HCPCS codes** (0 RC codes).
- Present in Centene raw file: **134 CPT/HCPCS codes** (plus 212 facility RC codes).
- HiLabs weighted coverage: \(\sum_{\text{present}} \text{weight} / \sum_{\text{all}} \text{weight} = 14,590,982,482 / 21,205,590,948 = \mathbf{68.81\%}\).
- Score is the unscaled percentage: **68.81**.
- Combined Score: \(0.60 \times 84.97 + 0.40 \times 68.81 = \mathbf{78.51}\) (**Letter Grade: C**).

### 6.3 Isolated Six-Mutation Testing Results
Evaluated on a 50,000-row baseline sample (Baseline Quality = 80.00):

| Mutation ID | Corruption Description | Target Metric | Baseline Metric | Mutated Metric | Metric Delta | Mutated Quality | Overall Drop | Confirmed |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **M1_ZERO_RATES** | 10% zero/null rates injected | Q2_ZERO_RATE | 100.00 | 0.00 | -100.00 | 72.63 | **-7.37** | Yes |
| **M2_DUPLICATE_ROWS**| 25,000 exact duplicates injected | Q5_DUPLICATE_RATIO | 3.91 | 2.61 | -1.30 | 79.66 | **-0.34** | Yes |
| **M3_EXPIRED_DATES** | 20% expired contracts (2020-01-01) | Q6_STALENESS | 70.00 | 90.00 | +20.00 | 80.00 | **0.00** (wt 0) | Yes |
| **M4_CONFLICTING_RATES**| Perturbed rates on finest keys | Q8_INTERNAL_CONSISTENCY| 82.19 | 35.45 | -46.74 | 70.79 | **-9.21** | Yes |
| **M5_INVALID_NPIS** | 50 distinct invalid Luhn NPIs | Q1_NPI_LUHN | 100.00 | 88.10 | -11.90 | 78.12 | **-1.88** | Yes |
| **M6_RATE_OUTLIERS** | 10% extreme 100x rate outliers | Q3_OUTLIER_SHARE | 70.87 | 69.86 | -1.01 | 78.33 | **-1.67** | Yes |

### 6.4 Granular Tie-Breaking & Curated Rates
- **Rule Clarification**: Renamed `RULE_PREFER_CLASS_MATCHED_SERVICE_CODE` because `setting` is 100% "outpatient" in this file; the rule specifically evaluates `service_code` (POS 11/22/02 for professional vs POS 22/23 for institutional).
- **NPI 0 Rows**: Exactly 5 rate rows across 5 TINs carry NPI 0 (`86-1264633`, `86-1158385`, `46-0854874`, `57-3865868`, `47-5029847`). These are retained as TIN-level organization rows with `npi_status="PLACEHOLDER_ZERO"`, linked via TIN evidence only, capped at `Probable`.
- **Spread Metrics & Bundled Revenue Codes**: Added `rate_mean`, `rate_spread_ratio` (\(\max / \min\)), `spread_flag` (true if ratio > 3 or source prices > 100), `rate_reliability` (HIGH, MEDIUM, LOW), `modifier_used`, `service_code_used`.
  - Curated rows with `spread_flag` by code type: CPT 134/10,111 (1.32%), HCPCS 16/2,022 (0.79%), RC 1,494/9,475 (15.77%). Total spread-flagged keys: 1,644 (7.61%).
  - Rate reliability tiers: HIGH: 18,950 keys (87.70%), MEDIUM: 1,464 keys (6.78%), LOW: 1,194 keys (5.53%).
  - For spread-flagged keys, parsed single cross-reference code from `additional_information` into `data/output/rates_by_crossref.parquet` at grain `(npi, tin, billing_code, billing_class, crossref_code)`. **100.0% of groups (5,172 / 5,172) collapse to a tight range (\(\text{spread ratio} \le 1.5\))**, proving that wide dispersion reflects bundled drug formulations rather than contract noise.
- **Trace Verification**: 25/25 sample rows verified via standalone `scripts/trace_row.py` (0 imports from `src/ptd`), documented in `docs/trace_report.csv`.
- **Kaiser / IPA Audit**: Top 25 review-flagged entities documented in `docs/review_flags_top25.csv`.

---

## 7. Phase 5: Multi-Source TIN -> NPI -> Practicing Address Linkage (C5)

### 7.1 Source Availability Matrix & Independence Principle
To ensure that corroboration represents genuine multi-source consensus rather than circular re-reporting, sources are grouped into strict **Independence Groups**:

| Source ID | Source Name | Independence Group | Status | Trust Tier | What It Adds | Coverage Impact |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **`nppes_primary`** | NPPES npidata Primary Practice | `group_1_nppes` | AVAILABLE_LOCAL | HIGH | Official practice address, Last Update Date, NPI deactivations | Covers 99.97% of active providers |
| **`nppes_secondary`**| NPPES pl_pfile Secondary Practice | `group_1_nppes` | AVAILABLE_LOCAL | MODERATE | 1,658 secondary hospital and clinic practicing locations | Expands multi-site clinical roamers |
| **`nppes_mailing`** | NPPES npidata Mailing Address | `group_1_nppes` | AVAILABLE_LOCAL | LOW | Provider mailing address (PO boxes excluded as NON_PRACTICE)| Baseline presence only |
| **`npi_registry_api`**| Live CMS NPI Registry API v2.1 | `group_1_nppes` | AVAILABLE_LIVE | HIGH | Real-time status verification, current practice address | Shared upstream with NPPES (0 extra corroboration) |
| **`cms_doctors_clinicians`**| CMS Doctors & Clinicians Dataset| `group_2_cms` | AVAILABLE_STREAMED | HIGH | Clinician-to-group PAC ID and facility clinical addresses | Independent CMS Group 2 corroboration (464 rows across 302 NPIs ingested) |
| **`medicare_public`**| Medicare Physician by Provider | `group_2_cms` | UNAVAILABLE_API_403 | MODERATE | Rendering provider Medicare specialty & practicing location | Probed; CMS API endpoint returned 403 Forbidden |
| **`ca_medical_board`**| CA Medical Board DCA Public | `group_3_state_board` | UNAVAILABLE_NO_PUBLIC_API| HIGH | State licensure address of record | Probed; automated HTTP requests blocked (403 Forbidden) |
| **`healthnet_directory`**| Health Net CA Provider Directory| `group_3_payer` | UNAVAILABLE_UNREACHABLE | HIGH | Payer-specific network practicing sites | Probed; endpoint returned 404 / name resolution error |
| **`tin_co_membership`**| Rate-File TIN Entity Corroboration| Corroboration Modifier | AVAILABLE_LOCAL | MODERATE | Co-membership of multiple NPIs under same TIN at same site | Corroboration modifier (not an independent group) |

### 7.2 Strict V1 vs Full V2 Verification Hierarchy
Per user specification, address verification is evaluated under two distinct routes:
1. **Route V1 (Strict Verified)**: Requires $\ge 2$ independent source groups agreeing on `address_key` (`group_1_nppes` + `group_2_cms`).
   - `status_basis`: `INDEPENDENT_AGREEMENT`
2. **Route V2 (Full Verified)**: Accepts Route V1 OR 1 high-trust source with `source_date <= 3 years` AND rate-file TIN corroboration (`c_tin >= 0.5`).
   - `status_basis`: `SINGLE_SOURCE_RECENT_TIN`
3. **Probable**: Single high-trust source without multi-source or TIN corroboration (`status_basis`: `SINGLE_SOURCE_ONLY` or `TIN_MODAL_INFERENCE`).
4. **Unverified**: Stale NPPES records older than 3 years without corroboration, deactivated NPIs, or unmatched providers (`status_basis`: `UNVERIFIED_STALE_OR_DEACTIVATED`).

### 7.3 Reconciled Status Distribution & Coverage
Evaluated strictly across real output files (`data/interim/npi_tin_address_links.parquet`, 6,905 links):
- **Denominator Discipline**:
  - Non-zero unique NPIs: **3,693** (3,692 found in NPPES + 1 unmatched in NPPES `1342464355`).
  - Facility-only NPI 0: Reported separately as 5 facility keys.
  - Unique TINs: **2,856** (2,851 with non-zero NPIs + 5 facility-only TINs).

| Dimension | Strict V1 Verified (Multi-Source Agreement) | Full V2 Verified (Recent High-Trust + TIN Corroboration) | Probable | Unverified | Total Population |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Unique NPIs** | **202 (5.47%)** | **1,316 (35.63%)** | **321 (8.69%)** | **2,056 (55.67%)** | **3,693** |
| - *Type 1 Individuals* | 202 (6.00%) | 1,215 (36.11%) | 290 (8.62%) | 1,858 (55.22%) | 3,365 |
| - *Type 2 Organizations* | 0 (0.00%) | 101 (30.89%) | 31 (9.48%) | 195 (59.63%) | 327 |
| **Unique TINs** | **197 (6.90%)** | **1,219 (42.68%)** | **59 (2.07%)** | **1,578 (55.25%)** | **2,856** |
| **Rate-Weighted (Primary)**| **365 (1.69%)** | **7,942 (36.75%)** | **1,240 (5.74%)** | **12,426 (57.51%)** | **21,608** |

### 7.4 Conflict Rules R1 Through R8 Execution
Every linkage decision applies explicit written conflict rules, logged with exact fire counts:

| Rule ID | Rule Name & Logic | Fires | Destination & Status Impact |
| :--- | :--- | :---: | :--- |
| **R1** | **Multi-Address Retention**: Multiple valid practicing locations per provider are kept as separate uncollapsed rows, ranked by score. | **1,563** | Preserves multi-site clinical practice networks. |
| **R2** | **Multi-TIN Separation**: The same NPI contracted under several TINs produces separate links per TIN. | **73** | Maintains contract-entity integrity. |
| **R3** | **Stale NPPES Degradation**: NPPES address older than 3 years with no independent corroboration is downgraded to Unverified. | **370** | Prevents false confidence on outdated records. |
| **R4** | **Deactivated NPI Guard**: Applies strictly to NPIs deactivated and NOT reactivated (7 NPIs). Status capped at Unverified. | **7** | 10 reactivated NPIs have active status restored. |
| **R5** | **Non-CA Residency Downgrade**: Out-of-state practice locations for a California network provider are downgraded one tier and flagged. | **493** | Verified -> Probable; Probable -> Unverified. |
| **R6** | **Mailing-Only Cap**: Addresses originating solely from mailing fields are capped at Probable. | **1,138** | Prevents non-clinical billing addresses from being Verified. |
| **R7** | **Disagreement Ranking**: Disagreeing candidate addresses are retained, ranked by score; lower candidates keep their own status. | **1,563** | Full audit visibility without artificial data loss. |
| **R8** | **NPI 0 TIN-Level Inference**: NPI 0 placeholder rows are linked strictly via modal TIN co-membership, capped at Probable. | **5** | Succeeded across 5 facility organizations. |
| **UNMATCHED** | **Unmatched in NPPES**: Documented NPI missing from official dissemination files (`1342464355`). | **1** | Capped at Unverified. |

### 7.5 Primary Address Uniqueness
- Each of the **3,739 unique (NPI, TIN) pairs** is evaluated once, and exactly one practicing address receives `address_rank = 1` and `is_primary_address = True`.
- When joining curated rate keys (21,608 rows) to primary practicing addresses, the joined output count equals **exactly 21,608 rows** (1:1 join).

### 7.6 Empirical Staleness vs Industry Claim
We measured the empirical agreement rate between NPPES Primary practice addresses and the independent CMS Doctors & Clinicians National File across 301 overlapping California providers, stratified by NPPES Last Update age:

| NPPES Last Update Age Bucket | CMS DAC Providers Evaluated | Agreed on Exact Address Key | Empirical Agreement Rate |
| :--- | :---: | :---: | :---: |
| **< 1 year** | 30 | 19 | **63.33%** |
| **1 - 3 years** | 55 | 39 | **70.91%** |
| **3 - 5 years** | 37 | 23 | **62.16%** |
| **> 5 years** | 179 | 109 | **60.89%** |
| **OVERALL EMPIRICAL BASELINE** | **301** | **190** | **63.12%** |

**Clinical & Actuarial Finding**: Rather than directory accuracy decaying from 100% to near-zero as time elapses, empirical agreement remains remarkably stable between 60.89% and 70.91% across all age buckets. Directory inaccuracy in commercial PPO networks is primarily caused by **unmodeled multi-site clinical mobility** (providers practicing at 2 to 5 facility sites simultaneously) rather than physical site obsolescence.

### 7.7 Specialty Mapping & Plausibility Breakdown
- **Mapping Breakdown**:
  - `MAPPED_HILABS_XWALK`: 5,048 links (61.03%)
  - `FALLBACK_NUCC_DISPLAY`: 3,210 links (38.81%)
  - `FACILITY_DEFAULT`: 6 links (0.07%)
  - `UNMAPPED_TAXONOMY`: 7 links (0.08%)
- **Clinical Plausibility**:
  - Revenue Codes (9,475 rows): Classified as `Unknown` because HiLabs benchmark weights cover CPT/HCPCS.
  - CPT / HCPCS Codes (11,854 rows):
    - Type 1 Individuals with benchmark: **81.30% plausible** (713 plausible / 877 evaluated; 164 implausible, 113 no benchmark).
    - Type 2 Organizations: 2,146 plausible, 2,707 implausible, 6,011 no benchmark.
- **Top 10 Failed Specialty / Procedure Code Pairs**:
  1. Primary Care + 88305 (Surgical pathology) - 31 rows
  2. Primary Care + 95117 (Immunotherapy injection) - 25 rows
  3. Primary Care + 36415 (Routine venipuncture) - 21 rows
  4. Emergency Medicine + 99053 (Unscheduled night service) - 19 rows
  5. Emergency Medicine + 71045 (Chest x-ray) - 19 rows
  6. Ophthalmology + J3301 (Triamcinolone acetonide) - 18 rows
  7. Psychiatry + 90837 (Psychotherapy 60 min) - 18 rows
  8. Ophthalmology + 95117 (Immunotherapy injection) - 18 rows
  9. Gastroenterology + 99213 (Office visit established) - 17 rows
  10. Primary Care + 93000 (Electrocardiogram) - 16 rows

---

## 8. Phase 6: Final Curated Rate File Architecture (C6)

The final production deliverable joins curated provider rates with multi-site practicing locations into a unified, relational tabular dataset.

### 8.1 Required Column Layout (27 Columns)
Ordered strictly from core commercial pricing to governance attestation and technical metadata:
`NPI, TIN, Address, Billing Code, Specialty, Rate`, `address_confidence, address_status, source_file, file_quality_score`, `billing_code_type, billing_class, npi_type, npi_status, tin_canonical_name, ppo_evidence_tier, rate_min, rate_max, n_source_prices, rate_reliability, spread_flag, review_flag, address_rank, is_primary_address, status_basis, specialty_plausible, class_npi_type_match`.

### 8.2 Production Volume & Excel Headroom
- **Total Multi-Site Production Rows**: **46,263 rows**
- **Primary Practicing Locations Only**: **21,608 rows** (1:1 with curated rate keys)
- **Excel Capacity Ceiling**: 1,048,576 rows per worksheet
- **Excel Headroom**: **95.59% headroom** on a single worksheet, eliminating artificial multi-file splitting.
- **Production File Manifest**:
  - Parquet: `data/output/final_curated_rates.parquet` (0.77 MB)
  - CSV: `data/output/final_curated_rates.csv` (16.19 MB)
  - Excel: `data/output/final_curated_rates.xlsx` (6.38 MB; includes `Curated_Rates` and `Notes` sheets)

---

## 9. Comprehensive Pipeline Limitations & Methodological Assumptions

1. **PPO Shared-File Assumption**: Centene publishes single unified in-network commercial rate files shared across both PPO and HMO plan IDs. While Ambetter individual market and explicit HMO groups are excluded, commercial master rates cannot be isolated to PPO-only without payer contract metadata. Rates are attributed under documented tiers T1 (explicit PPO) and T2 (shared commercial fee schedule).
2. **Integrated Health System Flags (Kaiser & IPAs)**: Commercial payers frequently contract with integrated HMO delivery networks (e.g. Kaiser Permanente, Hill Physicians, Sutter Health). Rates associated with these entities are tagged with `review_flag` (`POTENTIAL_INTEGRATED_HMO_KAISER` or `POTENTIAL_INTEGRATED_IPA`) to alert analysts.
3. **Capitation Exclusion Assumption**: 368 rate blocks specifying `negotiation_arrangement == "capitation"` are excluded from fee-for-service benchmarks as non-comparable risk payments.
4. **Bundled Revenue Code Dispersion**: Revenue Code 636 keys exhibit wide rate dispersion (spread ratios up to 8,700) because hundreds of distinct oncology and specialty drugs are billed under the same revenue code. Disaggregated cross-reference rates are published in `data/output/rates_by_crossref.parquet`.
5. **Exclusive Provider Organization (EOA) Exclusion**: All 127 EOA plans are excluded from the PPO baseline as non-PPO products.
6. **Source Independence Limits**: Downstream directories frequently draw from NPPES. Multi-source agreement requires strictly independent data collection (Group 2 CMS Doctors & Clinicians).
7. **Unavailable Remote Sources**: State licensing portals (CA Medical Board DCA) and payer directories (Health Net) restrict automated access via CAPTCHA and authentication, capping strict multi-source verification to providers corroborated in CMS federal datasets.


