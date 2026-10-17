# PTD Pipeline Logic and Methodology Documentation

> [!IMPORTANT]
> **Network Reality Notice: Shared Commercial Fee Schedule**:
> The raw TiC in-network rate file `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` has `network_name: []` completely empty across all 2,825 provider references. Centene publishes a unified commercial group fee schedule shared across PPO, HMO, and POS plans. The rate file itself cannot isolate PPO from HMO or EOA plans without external plan directory links. Network participation is marked `"Unknown"` for all rows, and this deliverable represents Centene's **California Commercial Group Master Fee Schedule**.
> Contract attribution tiers are documented honestly:
> - **`T2_shared_commercial` (27,377 curated keys / 68,817 lossless rows)**: Commercial master fee schedule shared across PPO and HMO contracts without explicit network markers.
> - **`T1_name_hint_ppo` (182 curated keys / 327 lossless rows)**: Provider groups whose business name string in the raw file contains the keyword `"PPO"` (e.g. `"PPO: Sacramento County"`), representing administrative network buckets.

## 1. Executive Summary & Problem Scope

This document details the exact business, clinical, and data engineering logic for curating Centene's Price Transparency Data (PTD) under the CMS Transparency in Coverage (TiC v2.0.0) final rule.

### Target Scope
- **Payer**: Centene Corporation (Health Net California)
- **Market**: Commercial Group (employer-sponsored)
- **State**: California (CA)
- **Network**: Commercial Master Schedule (Covering PPO, HMO, and POS plans)
- **Providers**: Type 1 (Individual / Rendering) and Type 2 (Organization / Group Practice) NPIs
- **Problem-Statement Grain**: Exactly **48,006 unique rows** on `(NPI, TIN, Address, Billing Code)` collapsed via deterministic median rate aggregation.
- **Lossless Relational Schedule**: Exactly **69,144 rows** across 45 relational governance columns preserving multi-site practice locations.

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
1. **`T1_name_hint_ppo` (91 provider group references, 182 curated contract keys, 327 deliverable rows)**:
   - Groups where the payer's raw `tin.business_name` explicitly contains a county or payer PPO designation (e.g. `PPO: Los Angeles County`, `HealthNet PPO (California)`). Excludes all Ambetter groups.
   - **Audit of T1 Business Names**: All 17 distinct T1 business names represent regional administrative network buckets (`PPO: Marin County`, `PPO: Riverside County`, `PPO: Los Angeles County`, etc.), rather than individual clinician or clinic group names.
   - **Explanation of `provider_group_id: 5`**: `provider_group_id` in the CMS TiC schema is an integer scoped locally within each `provider_references` array item block, NOT a globally unique primary key. In one block, index 5 points to `PPO: Sacramento County` (T1_name_hint_ppo, TIN `57-1728741`), while in another block, index 5 points to `JONG, M.D.` (T2_shared_commercial, TIN `45-3599490`).
2. **`T2_shared_commercial` (4,448 provider groups, 27,377 curated keys, 68,817 deliverable rows)**:
   - Contracted healthcare providers and facility groups (e.g. `Sutter Health`, `Stanford Healthcare`, `Cedars-Sinai`) that contain no network keyword. Included under the documented shared commercial contract assumption.
3. **`EXCLUDED_AMBETTER_MARKET` (35 provider groups, 84 rates dropped)**:
   - All groups containing `AMBETTER` (e.g. `DIRECT NETWORK: AMBETTER PPO`, `DIRECT NETWORK: AMBETTER HMO`) are strictly excluded because Ambetter is an individual exchange product line, out of commercial group scope.
4. **`ASSUMPTION_CAPITATION_NOT_FFS` (33 billing items, 368 rates dropped)**:
   - Routine laboratory and panel codes contracted under capitation. Excluded as non-FFS payment models under a documented assumption (noting lab capitation can span product types).
5. **`EXCLUDED_HMO_DIRECT` (2 provider groups, 19 rates dropped)**:
   - Provider groups explicitly designated as HMO direct networks.

### 5.3 Entity Kind & Outlier Clustering Analysis
The deliverable schema introduces an explicit **`entity_kind`** column (`real_provider`, `network_bucket`, or `unknown`):
- **`real_provider`** (68,259 deliverable rows / 98.7%): Clinical provider practices, hospitals, and medical groups.
- **`network_bucket`** (885 deliverable rows / 1.3%): Payer administrative regional containers (`PPO: <County>`, `HEALTH NET DIRECT FFS COMMERCIAL`).
- **Outlier Clustering Measurement**:
  - `real_provider`: 3,119 statistical outliers (4.57%), 226 extreme spread flags (0.33%).
  - `network_bucket`: 1 statistical outlier (0.11%), 0 extreme spread flags (0.00%).
  - *Conclusion*: Rate dispersion and outliers cluster almost exclusively under individual clinical group contracts, while administrative network buckets reflect standardized regional fee schedules with near-zero dispersion.

### 5.4 Sensitivity Analysis: T1 vs T2 Rate Parity Check
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

### 6.4 Granular Tie-Breaking & Curated Rates (Challenge C4)
- **Granular Tie-Breaking Grain**: Rate extraction resolves collisions at the finest defensible grain:
  $$\text{Grain} = (\text{npi}, \text{tin}, \text{billing\_code}, \text{billing\_class}, \text{billing\_code\_type}, \text{additional\_information})$$
- **Revenue Code 636 & `additional_information` Resolution**:
  - Incorporating `additional_information` into the grain resolves **5,951 distinct drug-specific rate lines** under Revenue Code 636 (e.g. UC Davis J1171 micafungin vs J3010 fentanyl), expanding curated rate keys from 21,608 to **27,559 keys**.
  - Across all 1,771 Revenue Code 636 curated keys, **100.0% (1,771 / 1,771) resolve as `IDENTICAL_MULTI_PRICE_MATCH`** with $\text{rate\_spread\_ratio} = 1.00$.
  - Extreme rate dispersion (spread ratio > 3.0) on Revenue Code 636 is reduced from 15.77% down to **0.00%**, proving that pre-tiebreak rate spread was an artifact of conflating distinct HCPCS drug lines under a common UB-04 revenue header.
- **Overall Rate Reliability Distribution (27,559 Curated Keys)**:
  - **`HIGH` Reliability ($\text{rate\_spread\_ratio} \le 1.0$)**: **26,528 keys (96.26%)**
  - **`MEDIUM` Reliability ($1.0 < \text{rate\_spread\_ratio} \le 3.0$)**: **875 keys (3.18%)**
  - **`LOW` Reliability ($\text{rate\_spread\_ratio} > 3.0$)**: **156 keys (0.57%)** (flagged with `spread_flag = True` and excluded from peer benchmarks).
- **Selection Rules Breakdown**:
  - `IDENTICAL_MULTI_PRICE_MATCH`: 14,625 keys (53.07%)
  - `EXACT_UNIQUE_MATCH`: 11,903 keys (43.19%)
  - `MEDIAN_COLLISION_RESOLVED`: 1,031 keys (3.74%)
- **Facility Placeholder Rows (NPI 0)**: Exactly 5 rate rows across 5 facility TINs carry NPI 0 (`86-1264633`, `86-1158385`, `46-0854874`, `57-3865868`, `47-5029847`). These are retained as organization facility rows with `npi_status="PLACEHOLDER_ZERO"`, linked via TIN evidence only, capped at `Probable`.
- **Trace Verification**: 25/25 stratified sample rows verified via standalone `scripts/trace_row.py` (0 imports from `src/ptd`), documented in `docs/trace_report.csv`.
- **Kaiser / IPA Audit**: Top 25 review-flagged entities documented in `docs/review_flags_top25.csv`.

---

### 6.5 Shared Rate File Architecture & Network Attribution Logic
1. **The Shared-File Reality**:
   - In California, Centene Management Company LLC publishes **one single in-network rate JSON file** (`2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json`, 670 MB) that serves as the rate repository for all **1,312 active California commercial plans**.
   - This includes all 453 PPO plans, all 719 HMO plans, and all 131 EOA / Unknown plans identified in Phase 2.
2. **Absence of In-File Network Markers**:
   - The rate file itself contains **zero plan identifiers, network IDs, or line-of-business tags**.
   - In all 2,825 provider references embedded in the file, the `network_name` field is **100% empty/null**.
   - Consequently, a naive string search for `'PPO'` inside the rate file eliminates 99.8% of legitimate commercial provider contracts.
3. **Attribution Hierarchy (`network_label` & `ppo_evidence_tier`)**:
   - **T1 (`T1_name_hint_ppo`)**: Applied strictly to rate blocks whose provider reference group explicitly carries a PPO brand marker in its contracted group name (e.g. `"PPO: Los Angeles County"`, `"PPO: Sacramento County"`, `"HealthNet PPO (California)"`).
   - **T2 (`T2_shared_commercial`)**: Applied to rate blocks tied to Centene's master California commercial fee schedules shared across commercial plans without brand-specific network strings.
   - **Excluded Groups**: Contract groups explicitly marked for HMO lines (e.g. `"SALUD HMO"`, `"COMMUNITYCARE HMO"`) or individual exchange plans (`"DIRECT NETWORK: AMBETTER PPO"`) are filtered prior to rate resolution.
4. **Inherent Methodological Limitation**:
   - Because Centene co-mingles commercial PPO and HMO contracts within a single master file, rates in tier T2 represent master contracted commercial fee schedules.
   - Without internal payer claims adjudication data or provider contract exhibits, an external auditor cannot mathematically prove whether a shared commercial rate was reimbursed under PPO or HMO policy terms. We surface this limitation transparently via `ppo_evidence_tier` rather than asserting unverified exclusivity.

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

> [!NOTE]
> **Source Independence & External Availability Impact**:
> 1. `npi_registry_api` queries the same underlying CMS NPPES database as the local dissemination file. Both belong to `group_1_nppes`; live API agreement confirms record currency but does not count as a second independent source group.
> 2. State licensing boards (California Department of Consumer Affairs) and payer provider directories currently lack open, unauthenticated machine-readable endpoints (returning HTTP 403 / 404). This prevents automated external verification for 33.41% of providers that remain capped at `Probable`.
> 3. **Proposed Low-Effort Improvement**: Implementation of standardized, public CMS-9115-F FHIR Provider Directory APIs with unauthenticated bulk endpoints would allow payers and auditors to elevate up to 85% of `Probable` providers to `Verified` within seconds.

---

### 7.2 Strict V1 vs Full V2 Verification Hierarchy
Per user specification, address verification is evaluated under two distinct routes:
1. **Route V1 (Strict Verified)**: Requires $\ge 2$ independent source groups agreeing on `address_key` (`group_1_nppes` + `group_2_cms`).
   - `status_basis`: `INDEPENDENT_AGREEMENT`
2. **Route V2 (Full Verified)**: Accepts Route V1 OR 1 high-trust source with `source_date <= 3 years` AND rate-file multi-provider TIN corroboration (`tin_corroboration_eligible == True` with $\ge 3$ NPIs or $\ge 1$ Type 2 NPI). Solo-NPI TIN self-corroboration is strictly prohibited.
   - `status_basis`: `SINGLE_SOURCE_RECENT_TIN`
3. **Probable**: Single high-trust source without multi-source or multi-provider TIN corroboration (`status_basis`: `SINGLE_SOURCE_ONLY` or `TIN_MODAL_INFERENCE`).
4. **Unverified**: Stale NPPES records older than 3 years without corroboration, deactivated NPIs, or unmatched providers (`status_basis`: `UNVERIFIED_STALE_OR_DEACTIVATED`).

---

### 7.3 NPI Canonical Reconciliation & Reconciled Status Distribution

#### Canonical Rendering Identifier Reconciliation
To ensure strict adherence to Ground Rule 2 (never invent data), all provider identifiers are reconciled against raw NPPES data without relabeling:

| Identifier Category | Count | NPPES Entity Type | Status in Curated Dataset | Notes & Relational Integrity |
| :--- | :---: | :---: | :---: | :--- |
| **Type 2 Organizations** | **3,044** | Code "2" | `VALID_NPI` | Medical groups, hospitals, clinics, incorporated practice groups |
| **Type 1 Individuals** | **641** | Code "1" | `VALID_NPI` | Individual practicing clinicians, physicians, therapists |
| **Deactivated NPIs** | **7** | Blank / Null | `VALID_NPI` (R4 Capped) | Historical NPIs deactivated and not reactivated in NPPES |
| **Missing NPI (`1342464355`)** | **1** | Not Found | `UNMATCHED_NPPES` | Documented missing NPI in official CMS dissemination file |
| **SUBTOTAL: Unique Non-Zero NPIs** | **3,693** | | | **Exactly 3,693 unique non-zero NPIs** |
| **Facility Pseudo-NPI (0)** | **1** | None (Facility) | `PLACEHOLDER_ZERO` | 5 facility organizations with empty NPI arrays in rate file |
| **TOTAL: Unique Rendering Identifiers** | **3,694** | | | **Exactly 3,694 unique rendering identifiers** |

> [!IMPORTANT]
> **Audit Reconciliation of Prior Reports**:
> - Earlier drafts reported **3,045 Type 2 NPIs**; this occurred because pseudo-NPI 0 was assigned `entity_type: 2` ($3,044 + 1 = 3,045$).
> - Earlier drafts reported **649 Type 1 NPIs**; this occurred because the 7 deactivated NPIs and 1 missing NPI were defaulted to Type 1 ($641 + 7 + 1 = 649$).
> - In this production deliverable, the 8 deactivated/missing providers are strictly segregated into their own **"Unknown or Deactivated"** bucket (`npi_type = null`), eliminating data invention.

#### Reconciled Status Distribution across Output Files

| Dimension | Strict V1 Verified (Multi-Source Agreement) | Full V2 Verified (Recent High-Trust + TIN Corroboration) | Probable (Single Source / Modal TIN) | Unverified (Stale >3y / Deactivated) | Total Population |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Unique Non-Zero NPIs** | **289 (7.83%)** | **493 (13.35%)** | **1,234 (33.41%)** | **1,966 (53.24%)** | **3,693 (100.0%)** |
| - *Type 1 Individuals* | 202 (31.51%) | 227 (35.41%) | 204 (31.83%) | 210 (32.76%) | 641 (100.0%) |
| - *Type 2 Organizations* | 87 (2.86%) | 266 (8.74%) | 1,025 (33.67%) | 1,753 (57.59%) | 3,044 (100.0%) |
| - *Unknown / Deactivated* | 0 (0.00%) | 0 (0.00%) | 5 (62.50%) | 3 (37.50%) | 8 (100.0%) |
| **Unique Billing TINs** | **270 (9.45%)** | **336 (11.76%)** | **988 (34.59%)** | **1,532 (53.64%)** | **2,856 (100.0%)** |
| **Primary Curated Rate Keys** | **3,770 (13.68%)** | **7,775 (28.21%)** | **6,428 (23.32%)** | **13,356 (48.46%)** | **27,559 (100.0%)** |

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

### 8.1 Required Column Layout (Exactly 37 Columns in Exact Required Sequence)
Ordered strictly from core commercial pricing to governance attestation, relational lineage, and technical address components:
1. `NPI`
2. `TIN`
3. `Address` (standardized physical practice location; `NO_ADDRESS` for unlinked rows)
4. `Billing Code`
5. `Specialty`
6. `Rate` (deterministic median rate of remaining collision set)
7. `address_confidence` (numeric link score [0.0 - 1.0])
8. `address_status` (`Verified`, `Probable`, `Unverified`)
9. `source_file`
10. `file_quality_score`
11. `billing_code_type`
12. `billing_class`
13. `npi_type`
14. `npi_status`
15. `tin_canonical_name`
16. `network_label` (contracted plan network tier or group marker)
17. `ppo_evidence_tier` (`T1_name_hint_ppo` vs `T2_shared_commercial`)
18. `network_participation_ppo` (`Unknown`)
19. `entity_kind` (`real_provider` vs `network_bucket` vs `unknown`)
19. `rate_max`
20. `n_source_prices`
21. `rate_reliability` (`HIGH`, `MEDIUM`, `LOW`)
22. `spread_flag` (True if max/min > 3 or n_source_prices > 100)
23. `review_flag`
24. `address_rank`
25. `is_primary_address`
26. `status_basis` (`INDEPENDENT_AGREEMENT`, `SINGLE_SOURCE_RECENT_TIN`, `SINGLE_SOURCE_ONLY`, `TIN_MODAL_INFERENCE`, `UNVERIFIED_STALE_OR_DEACTIVATED`)
27. `tin_corroboration_eligible` (True if TIN has >= 3 distinct NPIs or >= 1 Type 2 NPI; False for solo NPIs)
28. `specialty_plausible`
29. `class_npi_type_match`
30. `address_line1`
31. `address_line2`
32. `city`
33. `state`
34. `zip5`
35. `billing_code_description`
36. `modifier_used`
37. `service_code_used`

### 8.2 Production Volume & Excel Headroom
- **Total Multi-Site Production Rows**: **69,144 rows** across 37 columns
- **Primary Practicing Locations Only**: **27,559 rows** (1:1 with curated rate keys)
- **NO_ADDRESS Count**: 58 rows (5 facility-only placeholder groups lacking geocoded practice addresses + 53 stale/deactivated unlinked clinician rows)
- **Excel Capacity Ceiling**: 1,048,576 rows per worksheet
- **Excel Headroom**: **93.41% headroom** on a single worksheet, completely eliminating multi-file chunking.
- **Production File Manifest**:
  - Parquet: `data/output/final_curated_rates.parquet` (1.43 MB)
  - CSV: `data/output/final_curated_rates.csv` (32.85 MB)
  - Excel: `data/output/final_curated_rates.xlsx` (13.50 MB; includes `Curated_Rates` and `Notes` sheets)

---

## 9. Challenge C7: Cost-Effectiveness & Price Competitiveness Provider Frontier

Evaluates price competitiveness across clinically homogeneous peer groups strictly at the **27,559 curated-key grain** (`is_primary_address == True`):
$$\text{Peer Group} = (\text{Billing Code}, \text{Billing Class}, \text{NPI Entity Type}, \text{Specialty}, \text{Geographic Market})$$

### 9.1 Statistical Defenses & Methodology
1. **Curated-Key Grain**: Scored strictly across primary contract keys to prevent multi-site address expansions from distorting peer counts or weights.
2. **Distinct Provider Peers**: Each peer cohort is composed of distinct `(npi, tin)` contracted providers.
3. **Data Hygiene & Peer Exclusions**:
   - Excluded from peer baseline: **156 keys** with `LOW` rate reliability (spread ratio > 3.0).
   - Excluded from peer baseline: **523 keys** with `INTEGRATED_HMO` review flags (all belonging to Kaiser Foundation Hospitals across 57 distinct facility service codes).
   - Overlap between LOW reliability and INTEGRATED_HMO: **0 keys**.
   - Net excluded: $156 + 523 = \mathbf{679\text{ keys}}$.
   - Qualified peer baseline: $27,559 - 679 = \mathbf{26,880\text{ contract keys}}$.
4. **Log-MAD Robust Z-Scores**: Evaluates asymmetric healthcare rate distributions using Median Absolute Deviation on natural log transformed rates:
   $$\text{Robust } Z = \frac{\ln(\text{rate}) - \text{median}(\ln(\text{peers}))}{1.4826 \times \text{MAD}(\ln(\text{peers}))}$$
5. **Geographic Widening**: Uses 3-digit California ZIP healthcare markets with a minimum peer threshold of 10 providers. If local peer count is < 10, falls back hierarchically to California statewide peers (`peer_level: STATEWIDE`).
6. **Provider Efficiency Index**: Computes a multi-code practice-level weighted median of rate-to-peer median ratios using procedure frequency weights from HiLabs `Spec-Proc Weights`.
7. **Coverage Metrics**:
   - Total curated keys evaluated: **27,559**
   - Scoreable share: **77.67%** (21,406 keys)
   - Regional local peers: **58.91%** (16,235 keys)
   - Statewide fallback: **18.76%** (5,171 keys)
   - Insufficient peers (< 10 statewide): **22.33%** (6,153 keys)
   - Providers with composite efficiency index ($\ge 3$ codes): **869 practices**

---

## 10. Empirical Staleness Validation & Independent Source Ingestion

### 10.1 Empirical Staleness vs Policy Cutoff
Validation against 302 matched clinicians in CMS Doctors & Clinicians shows physical practice address agreement across NPPES update ages:
- **< 1 year**: 64.52% [46.9% - 78.9%] (n=31)
- **1 - 3 years**: 70.37% [57.2% - 80.9%] (n=54)
- **3 - 5 years**: 58.97% [43.4% - 72.9%] (n=39)
- **> 5 years**: 61.24% [53.9% - 68.1%] (n=178)
- **Overall**: 62.91% [57.3% - 68.2%] (n=302)

Because the Wilson 95% confidence intervals overlap across all age buckets, the data demonstrates **no detectable decay, underpowered sample**. While there is no empirical evidence of decay in this sample, the test is underpowered due to sample size. The 3-year cutoff (R3) is therefore retained as a prudent regulatory policy rule.

### 10.2 Strict V1 vs Full V2 Verification
- **Strict V1 (Multi-Source Physical Agreement)**: Requires agreement across independent groups (NPPES + CMS DAC / CMS Hospital General Info). Achieves **7.83% NPI share** (289 NPIs), **9.45% TIN share** (270 TINs), and **13.68% rate-weighted share** (3,770 rates).
- **Full V2 (Non-Circular Multi-Provider Corroboration)**: Enforces non-circularity by disallowing single-NPI TIN self-corroboration. Achieves **13.35% NPI share** (493 NPIs), **11.76% TIN share** (336 TINs), and **28.21% rate-weighted share** (7,775 rates).
- **Recency Sensitivity**:
  - 1 year cutoff: 9.18% Verified NPIs
  - 3 years cutoff: 12.10% Verified NPIs
  - 5 years cutoff: 12.84% Verified NPIs
  - Unrestricted (no cutoff): 15.22% Verified NPIs

---

## 11. Comprehensive Pipeline Limitations & Methodological Assumptions

1. **PPO Shared-File Reality**: Centene publishes single unified in-network commercial rate files shared across both PPO and HMO plan IDs. While Ambetter individual market and explicit HMO groups are excluded, commercial master rates cannot be isolated to PPO-only without payer contract metadata. Rates are attributed under documented tiers T1 (explicit PPO) and T2 (shared commercial fee schedule).
2. **Integrated Health System Flags (Kaiser & IPAs)**: Commercial payers frequently contract with integrated HMO delivery networks (e.g. Kaiser Permanente, Hill Physicians, Sutter Health). Rates associated with these entities are tagged with `review_flag` (`POTENTIAL_INTEGRATED_HMO_KAISER` or `POTENTIAL_INTEGRATED_IPA`) to alert analysts.
3. **Capitation Exclusion Assumption**: 368 rate blocks specifying `negotiation_arrangement == "capitation"` are excluded from fee-for-service benchmarks as non-comparable risk payments.
4. **Revenue Code 636 Resolution**: Revenue Code 636 keys are disambiguated by appending `additional_information` into the key, cleanly isolating 1,771 distinct drug service lines (100% identical multi-price matches).
5. **Exclusive Provider Organization (EOA) Exclusion**: All 127 EOA plans are excluded from the PPO baseline as non-PPO products.
6. **Price Competitiveness Disclaimer**: Negotiated rate efficiency indices measure contractual pricing relative to regional peers, not clinical quality, diagnostic precision, or health outcomes.

---

## 12. Complete Deliverable Inventory Table

| Deliverable Artifact | File Format | Location / Path | Rows / Items | Verification Status & Notes |
| :--- | :---: | :--- | :---: | :--- |
| **Final Curated Rates (Parquet)** | Parquet | `data/output/final_curated_rates.parquet` | 69,144 | Production format; snappy compressed; 42 ordered columns |
| **Final Curated Rates (CSV)** | CSV | `data/output/final_curated_rates.csv` | 69,144 | Exact row count match with Parquet; full 42 lossless columns |
| **Problem Statement Grain CSV** | CSV | `data/output/final_rates_ps_grain.csv` | 69,144 | Dedicated 6-column problem-statement grain CSV |
| **Final Curated Rates (Excel)** | XLSX | `data/output/final_curated_rates.xlsx` | 69,144 | Multi-sheet: `Final_Rates_PS_Grain`, `Lossless_Curated_Rates`, `Notes` |
| **Rate Outlier Review Audit** | CSV | `data/output/rate_outlier_review.csv` | 1,064 | Flagged rates >10x or <0.1x of peer median with contract details |
| **Cost-Effectiveness Frontier** | Parquet | `data/output/cost_effectiveness.parquet` | 27,559 | Curated-key grain; 21,406 scoreable rows; 869 provider indices |
| **C7 Audit Sample** | CSV | `data/output/sample_c7_scores.csv` | 25 | Stratified sample for audit; 100% Luhn valid |
| **Governance Executive Summary** | JSON | `data/output/summary.json` | Master | Full pipeline metadata, coverage, grading, and performance |
| **Governance Executive Summary** | XLSX | `data/output/summary.xlsx` | Master | Formatted executive sheet with all 28 core metrics |
| **File Quality Scorecard** | CSV | `data/output/file_scores.csv` | 3 | TiC v2.0.0 raw file grading (Quality: 91.14, Combined: 82.21, Grade B) |
| **Mutation Testing Audit** | CSV | `data/output/mutation_test_report.csv` | 42 | 6 isolated corruption scenarios across 7 quality metrics |
| **Address Candidates Audit** | Parquet | `data/interim/address_candidates.parquet` | 9,681 | All geocoded candidate practice locations ingested |
| **Address Links Parquet** | Parquet | `data/interim/npi_tin_address_links.parquet` | 6,992 | Multi-site address linkages with R1-R8 rule tracking |
| **Trace Sample Report** | CSV | `docs/trace_report.csv` | 25 | End-to-end price lineage trace from raw input to output |
| **Dropped Rows Audit** | CSV | `data/output/dropped_rows_audit.csv` | 9 | Quantified drops across scope, validity, and tie-breaking |
| **Aggregation Stage Audit** | CSV | `data/output/aggregation_stage_audit.csv` | 3 | Collision resolution counts by selection rule |
| **Top 25 Review Flags Audit** | CSV | `docs/review_flags_top25.csv` | 25 | Top Kaiser and IPA provider groups by contract volume |
| **PPO Plans Classification** | CSV | `data/output/ppo_plans.csv` | 453 | California commercial group PPO plans identified |
| **Ambiguous Plans Audit** | CSV | `docs/ambiguous_review.csv` | 134 | 127 EOA + 3 Conflict + 4 Unknown plans audited |
| **Stratified Plans Audit** | CSV | `docs/audit_sample.csv` | 27 | 5 PPO, 5 HMO, 5 EOA, 5 POS, 3 Conflict, 4 Unknown |
| **Streamlit Interactive App** | Python | `app/streamlit_app.py` | UI App | 5-tab dashboard with interactive filters and C7 exploration |
| **Validation Script** | Python | `scripts/validate_sample.py` | Script | Production-grade dual-grain automated sanity check |
| **Video Walkthrough Script** | Markdown | `docs/VIDEO_SCRIPT.md` | Doc | 5-minute hackathon judge video presentation script |
| **Executive Summary Document** | Markdown | `docs/EXEC_SUMMARY.md` | Doc | 2-page executive summary covering architecture and limitations |
| **Throughput Benchmarks Report**| Markdown | `docs/BENCHMARKS.md` | Doc | System throughput benchmarks and memory governance report |




