# TiC v2.0.0 Rate File Quality Grading Framework (Challenge C3)

## 1. Grading Philosophy & Evaluation Framework

In accordance with CMS Transparency in Coverage (TiC v2.0.0), data pipeline quality evaluation must evaluate the **raw expanded price stream** prior to curation, filtering, or deduplication. This ensures that the scorecard measures true file integrity rather than post-pipeline cleanup.

Quality and coverage dimensions are strictly separated:
- **Data Quality Score (60% weight)**: Validity, duplicates, internal consistency, statistical outliers, contract mix, expiration currency, and schema completeness.
- **Data Coverage Score (40% weight)**: Official procedure code breadth weighted against the HiLabs benchmark workbook (`Rate_Benchmarking_Individual_Weights_Hackathon.xlsx`).

---

## 2. Reconciled Raw Stream Quality Scorecard (91.14 Quality Points)

Evaluated across all **1,511,720 raw expanded price records** in `raw_price_audit.parquet` across 8 canonical TiC quality metrics summing to weight $1.0000$.

| Metric ID | Metric Name | Weight | Measured Raw Value | Metric Score | Weighted Points | Relational Significance & Formula |
| :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| **Q1_NPI_LUHN** | NPI Luhn Checksum Validity | 0.15 | 99.97% valid (1 invalid: NPI 0 placeholder) | 99.97 | 15.00 | Modulo-10 check digit verification over `80840 + NPI` |
| **Q2_ZERO_RATE** | Zero / Null Rate Share | 0.05 | 0.00% zero or missing rates (saturated) | 100.00 | 5.00 | Saturated contractual baseline: $\max(0, 100 - \text{zero\_pct} \times 10)$ |
| **Q3_OUTLIER_SHARE**| Rate Outlier Ratio (Robust MAD) | 0.20 | 4.90% log-rate outliers per code/class | 67.30 | 13.46 | Outliers exceeding $2.5 \times \text{MAD}$ on $\log(\text{rate})$ per code and class |
| **Q4_NEGOTIATED_MIX**| Negotiated Dollar Rate Mix | 0.10 | 99.98% explicit negotiated dollar rates | 99.98 | 10.00 | Share of explicit dollar rates over percentage fee schedules |
| **Q5_DUPLICATE_RATIO**| Exact Duplicate Rate Ratio | 0.10 | 0.76% true within-block duplicates (11,432 rows) | 99.24 | 9.92 | True duplicate price records within item blocks; structural cross-reference fan-out (97.90%) reported as informational |
| **Q6_STALENESS** | Expiration Date Currency | 0.05 | 80.00 pts (11d publication age, 30pt evergreen penalty) | 80.00 | 4.00 | Published 2026-10-06 vs 2026-10-17 run date (11d old <= 30d -> 100 pts) with documented 30pt evergreen contract penalty |
| **Q7_SCHEMA_VALIDITY**| Schema Completeness | 0.15 | 100.00% mandatory TiC fields populated | 100.00 | 15.00 | Mandatory presence of `tin`, `billing_code`, `negotiated_rate`, `class` |
| **Q8_INTERNAL_CONSISTENCY**| Internal Rate Consistency | 0.20 | 3.09% multi-rate finest keys | 93.82 | 18.76 | Conflict rate on finest key: $\max(0, 100 - \text{conflict\_pct} \times 2)$ |
| **DESCR_STRUCT_MULT**| Structural Multiplicity | 0.00 | 97.90% structural cross-reference fan-out | 2.10 | 0.00 | Descriptive volume of contract prices collapsed during tie-breaking (1,480,048 duplicates) |
| **METHOD_V1_BASELINE** | Method v1 Score (Checkpoints D/E) | 1.0000 | Structural fan-out scored in Q5 | 81.50 | 81.50 | Historical baseline before within-block duplicate isolation |
| **TOTALS (METHOD V2)** | | **1.0000** | Within-block duplicate isolation | | **91.14** | **Quality Score = 91.14 (Grade A)** |

### +9.64 Point Score Bridge & Mathematical Decomposition (Method v1 $\to$ Method v2)

The raw quality score moved from **81.50** (Grade B) to **91.14** (Grade A). The bridge contains zero unexplained plugs and decomposes into three verifiable components:
1. **Q5 Within-Block Duplicate Isolation**: **+9.70 points** ($(99.24 \times 0.10) - (2.10 \times 0.1053) = 9.924 - 0.221 \approx +9.70$).
2. **Q6 Staleness & Currency Activation**: **+4.00 points** ($80.00 \times 0.05$, previously uncredited / 0 pts).
3. **Weight Budget Renormalization**: **-4.06 points** (re-scaling across the remaining 6 metrics from the non-staleness $1/0.95$ divisor back to standard 1.00 weight budget).

| Metric Component | Old Method v1 Weight | Old Raw Score | Old Contribution | New Method v2 Weight | New Raw Score | New Contribution | Net Score Impact |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q1: NPI Luhn** | 0.1579 | 99.97 | 15.79 | 0.1500 | 99.97 | 15.00 | -0.79 |
| **Q2: Zero Rate** | 0.0526 | 100.00 | 5.26 | 0.0500 | 100.00 | 5.00 | -0.26 |
| **Q3: Outlier Share** | 0.2105 | 67.30 | 14.17 | 0.2000 | 67.30 | 13.46 | -0.71 |
| **Q4: Negotiated Mix**| 0.1053 | 99.98 | 10.53 | 0.1000 | 99.98 | 10.00 | -0.53 |
| **Q5: Duplicate Ratio**| 0.1053 | 2.10 | 0.22 | 0.1000 | 99.24 | 9.92 | **+9.70** |
| **Q6: Staleness** | 0.0000 | 0.00 | 0.00 | 0.0500 | 80.00 | 4.00 | **+4.00** |
| **Q7: Schema Validity**| 0.1579 | 100.00 | 15.79 | 0.1500 | 100.00 | 15.00 | -0.79 |
| **Q8: Internal Consistency**| 0.2105 | 93.82 | 19.74 | 0.2000 | 93.82 | 18.76 | -0.98 |
| **TOTAL SCORE** | **1.0000** | — | **81.50** | **1.0000** | — | **91.14** | **+9.64** |

$$\mathbf{81.50 + 9.70 + 4.00 - 4.06 = 91.14}$$

**Sensitivity of Final Score to Q6 Blend Assumption**:
- *100% Publication Freshness (100 pts)*: Quality = 92.14 (+1.00 pt), Combined = 82.74 (Grade B).
- *50/50 Documented Blend (80 pts)*: Quality = 91.14, Combined = 82.21 (Grade B).
- *100% Evergreen Penalty (70 pts)*: Quality = 90.64 (-0.50 pt), Combined = 81.84 (Grade B).
The file remains solidly Grade B across all blend assumptions.

---

## 3. Data Coverage Scorecard (HiLabs Benchmark)

- **Official HiLabs Benchmark Coverage (C1)**: Evaluated against official procedure code weights in HiLabs Sheet 3 (`Spec-Proc Weights`).
  - Total procedure codes in HiLabs benchmark workbook: 583 distinct procedure codes (946 specialty-procedure pairs; total weight 21,205,590,948).
  - Matching distinct procedure codes in Centene file: **134 distinct codes** (sum of matched weights: 14,590,967,314).
  - Weighted code coverage score: **68.81%** ($\frac{14,590,967,314}{21,205,590,948}$)
  - Unweighted distinct code coverage: **22.98%** ($\frac{134}{583}$)
- **Combined File Score & Final Grade**:
  $$\text{Combined Score} = 0.60 \times 91.14 + 0.40 \times 68.81 = 54.684 + 27.524 = \mathbf{82.21} \quad (\mathbf{Grade\ B})$$


---

## 3.1 Rate Reliability Formula & Classification
Rate reliability evaluates contractual rate stability across the curated grain `(npi, tin, billing_code, billing_class, billing_code_type, additional_information)`:
$$\text{rate\_spread\_ratio} = \frac{\text{rate\_max}}{\text{rate\_min}} \quad (\text{for } \text{rate\_min} > 0)$$

- **`HIGH` Reliability ($\text{rate\_spread\_ratio} \le 1.0$)**: Single observed contract price ($N=1$) or identical multi-contract rate matches where maximum rate equals minimum rate ($\text{rate\_spread\_ratio} = 1.00$). Represents **26,528 keys (96.26%)** of all curated contract keys.
- **`MEDIUM` Reliability ($1.0 < \text{rate\_spread\_ratio} \le 3.0$)**: Narrow contractual dispersion within a factor of 3.0. Represents **875 keys (3.18%)**.
- **`LOW` Reliability ($\text{rate\_spread\_ratio} > 3.0$)**: Extreme rate variation across bundled contracts. Flagged with `spread_flag = True` and excluded from peer competitiveness frontiers. Represents only **156 keys (0.57%)**.

---

## 4. Exact Duplicate Analysis & File Defects

The measured exact duplicate ratio on the raw stream is **97.90%** (1,480,048 duplicates out of 1,511,720 rows; 31,672 unique tuples).
This duplication includes `additional_information` in the exact-duplicate hash.

### Empirical Repetition Examples from Raw Rate Stream:
1. **Dominican Santa Cruz Hospital (TIN: 72-1561119, NPI: 1427181007)**:
   - Billing Code 636, institutional, outpatient, POS 22, Modifier NONE, Rate **$6,984.85**, Additional Information: `NONE`.
   - Repeats **1,161 times** across item 895 and provider reference IDs `[116, 174, 194, 299, 370, 492, ...]`.
2. **UC Davis Medical Center (TIN: 94-6036494, NPI: 1710918545)**:
   - Billing Code 636, institutional, outpatient, POS 22, Modifier NONE, Rate **$786.59**, Additional Information: `J2704`.
   - Repeats **1,032 times** across item 895 and provider reference IDs `[139, 200, 221, 56, 380, 45, ...]`.
3. **UC Davis Medical Center (TIN: 94-6036494, NPI: 1710918545)**:
   - Billing Code 636, institutional, outpatient, POS 22, Modifier NONE, Rate **$8,443.05**, Additional Information: `J3010`.
   - Repeats **1,032 times** across item 895 and provider reference IDs `[139, 200, 221, 56, 380, 45, ...]`.

**Root Cause**: Centene's rate file associates dozens of distinct provider references representing various clinic divisions and provider sub-groups with the exact same underlying contractual rate blocks. This represents a genuine structural file defect in the raw publication.

---

## 5. Automated Mutation Testing & Sensitivity Verification

Each mutation was executed across a 50,000-row sample to prove that metrics respond sensitively and monotonically to data corruption:

| Mutation ID | Targeted Metric | Metric Score Before | Metric Score After | Metric Score $\Delta$ | Metric Weight | Weighted Delta ($\Delta \times w_i$) | Measured Value Before | Measured Value After | Overall Quality Score Movement |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| **M1_ZERO_RATES** | Q2_ZERO_RATE | 100.00 | 0.00 | -100.00 | 0.0500 | -5.00 | 0.00% zeros | 10.00% zeros | 83.86 $\to$ 78.83 (-5.03 pts) |
| **M2_DUPLICATE_ROWS** | Q5_DUPLICATE_RATIO | 20.47 | 13.65 | -6.82 | 0.1000 | -0.68 | 79.53% dups | 86.35% dups | 83.86 $\to$ 83.14 (-0.72 pts) |
| **M3_EXPIRED_DATES** | Q6_STALENESS | 70.00 | 60.00 | -10.00 | 0.0500 | -0.50 | `NOT_EVALUABLE` | 20.00% expired | 83.86 $\to$ 83.36 (-0.50 pts) |
| **M4_CONFLICTING_RATES**| Q8_INTERNAL_CONSISTENCY | 98.29 | 88.61 | -9.68 | 0.2000 | -1.94 | 0.86% conflicts | 5.70% conflicts | 83.86 $\to$ 82.03 (-1.83 pts) |
| **M5_INVALID_NPIS** | Q1_NPI_LUHN | 100.00 | 80.03 | -19.97 | 0.1500 | -3.00 | 100.00% valid | 80.03% valid | 83.86 $\to$ 80.87 (-2.99 pts) |
| **M6_RATE_OUTLIERS** | Q3_OUTLIER_SHARE | 68.31 | 49.15 | -19.16 | 0.2000 | -3.83 | 4.75% outliers | 7.63% outliers | 83.86 $\to$ 80.03 (-3.83 pts) |

### Key Findings from Mutation Testing:
1. **Decoupled Outlier vs Conflict Mutations (M4 & M6)**: In M6, scaling 10% of finest keys uniformly by 10x drops Q3 outlier score by -19.16 points with **zero cross-metric movement on Q8** (weighted delta ties out exactly to overall drop of -3.83 pts). In M4, perturbing rates by +1.0% on multi-row finest keys drops Q8 by -9.68 points without triggering the MAD outlier detector (Q3 delta is 0.00).
2. **Monotonic Staleness (M3)**: Injecting 20% expired contracts drops Q6 from 70.0 to 60.0 ($100 - 20 \times 2 = 60.0$). At fixed canonical weight 0.05, weighted delta ties out exactly to overall drop of -0.50 pts with zero movement across all other 7 metrics.
3. **Exact Luhn Tracking (M5)**: Corrupting exactly 20% of unique NPI check digits drops Q1 from 100.00% to 80.03% (delta -19.97 pts), producing a weighted delta of $-19.97 \times 0.15 = -3.00$ pts (overall drop -2.99 pts), verifying perfect identifier checksum isolation.
4. **Reconciliation Integrity**: All metrics before and after are recorded in `data/output/mutation_test_report.csv`. Baseline sample score (83.86) reflects 50,000-row sample baseline with canonical weights ($0.15, 0.05, 0.20, 0.10, 0.10, 0.05, 0.15, 0.20$). Full-file production score with audited within-block duplicates (0.76%) and currency (80.0 pts) is 91.14 (Quality Grade A) across all 8 canonical metrics, yielding an 82.21 Combined Score (Grade B).

