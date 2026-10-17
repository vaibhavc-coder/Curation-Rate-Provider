# Challenge C7: Cost-Effectiveness & Price Competitiveness Provider Frontier

## 1. Executive Summary & Objective
The Transparency in Coverage (TiC) mandate yields unprecedented volumes of in-network negotiated rates across healthcare commercial markets. However, raw rates cannot be directly compared across providers without controlling for clinical procedure, site of service, provider taxonomy/credentialing, and geographic market variations. 

This module constructs an **explainable, statistically defensible price competitiveness frontier** across the Centene California Commercial Group PPO network, enabling health plans, self-insured employers, and actuarial researchers to quantify provider efficiency without introducing parametric bias or conflating contractual price with clinical quality.

---

## 2. Statistical Defenses: Metric Selection Rationale

### 2.1 The Skewness Problem in Healthcare Rates
Negotiated rates in commercial payer rate files are severely non-normal:
- Rates exhibit extreme right skewness due to high-cost tertiary referral centers and specialized academic hospital systems.
- Rate files feature artificial clusters around master fee schedule benchmarks (e.g., 120% of Medicare RBRVS).
- Classical parametric statistics—mean ($\mu$) and standard deviation ($\sigma$)—are distorted by outlier prices and bi-modal contracting tiers. A single $25,000 negotiated rate for an outpatient procedure pulls the arithmetic mean away from the typical market contract.

### 2.2 Median and Median Absolute Deviation (MAD)
To ensure mathematical robustness against outlier rates, all peer distributions are characterized using:
1. **Peer Median**:
   $$\text{Median}(R) = \text{Med}_{i=1\dots N}(r_i)$$
2. **Median Absolute Deviation (MAD)**:
   $$\text{MAD} = \text{Med}_{i=1\dots N} \left| r_i - \text{Median}(R) \right|$$
3. **Logarithmic Scaling for Multiplicative Price Dynamics**:
   Contract negotiations are fundamentally multiplicative (e.g., $1.25 \times$ baseline vs $0.85 \times$ baseline). Thus, the robust z-score is computed on the natural logarithm of the negotiated rate:
   $$\text{Robust } Z = \frac{\ln(r) - \text{Median}(\ln(R))}{1.4826 \times \text{MAD}(\ln(R))}$$
   where the scaling factor $1.4826 \approx 1 / \Phi^{-1}(0.75)$ provides an asymptotically unbiased estimator of the population standard deviation for normally transformed log-prices.

### 2.3 Additional Price Competitiveness Metrics
For every evaluated rate key:
- **Rate-to-Peer Median Ratio**:
  $$\text{Ratio} = \frac{\text{Rate}}{\text{Peer Median}}$$
  - $\text{Ratio} < 1.0$: Lower than peer median (price-competitive).
  - $\text{Ratio} = 1.0$: Exactly at the peer market median.
  - $\text{Ratio} > 1.0$: Higher than peer median.
- **Percentile Rank**:
  $$\text{Percentile} = \frac{\# \{r_j \le r\}}{N} \times 100$$
  Empirical cumulative rank within the qualified peer group.

---

## 3. Peer Grouping Methodology & Hierarchical Widening

### 3.1 Strict Peer Group Definition
A valid clinical peer group requires homogeneity across 5 fundamental dimensions:
$$\text{Peer Group} = (\text{Billing Code}, \text{Billing Class}, \text{NPI Entity Type}, \text{Specialty}, \text{Geographic Market})$$
- **Billing Code**: Exact procedure (CPT/HCPCS) or institutional revenue code.
- **Billing Class**: `professional` vs `institutional` (never mixed, as facility fees and professional fees represent distinct balance-sheet cost structures).
- **NPI Entity Type**: Type 1 (individual clinician) vs Type 2 (organizational group practice).
- **Specialty**: Resolved clinical specialty (e.g., `INTERNAL MEDICINE`, `DERMATOLOGY`, `CARDIOLOGY`).
- **Geographic Market**: 3-digit California ZIP code healthcare market prefix (e.g., `900`-`918` Los Angeles Metro, `940`-`944` SF Peninsula).

### 3.2 Minimum Peer Threshold & Hierarchical Widening
To protect against small-sample variance:
- **Minimum Peer Threshold**: $N \ge 10$ unique providers required to establish a peer baseline.
- **Hierarchical Fallback (Statewide Widening)**:
  - If a 3-digit regional market contains $< 10$ peer providers for a given code/class/specialty, the algorithm falls back to the California statewide pool:
    $$\text{Fallback Group} = (\text{Billing Code}, \text{Billing Class}, \text{NPI Entity Type}, \text{Specialty}, \text{CA\_STATEWIDE})$$
    The row is tagged with `peer_level: STATEWIDE`.
  - If fewer than 10 providers bill the code statewide, the row is marked `is_scoreable: False` and `peer_level: INSUFFICIENT_PEERS`, preventing arbitrary ranking against inadequate cohorts.

### 3.3 Data Hygiene & Baseline Qualification
To prevent contaminated baselines:
- **Exclusion of LOW Reliability Rates**: Rates with excessive multi-plan spreads ($\max/\min > 3$) or erratic collision tiers are excluded from peer median calculation.
- **Exclusion of Integrated HMO Captive Rates**: Kaiser Permanente and other staff-model integrated HMO rates flagged during Phase 4 are excluded from the commercial PPO peer baseline.
- **Zero-Dollar Rates**: Filtered out prior to peer distribution modeling.

---

## 4. Multi-Code Provider Efficiency Index

### 4.1 Clinician-Level Aggregation
Because individual clinicians and practices bill dozens of distinct procedure codes, single-code ratios do not convey holistic practice efficiency. 

The **Provider Efficiency Index** aggregates code-level ratios into a single composite practice index:
1. Filters for providers with at least **3 qualified procedure codes**.
2. Applies procedure frequency benchmarking weights derived from the HiLabs `Spec-Proc Weights` schedule ($w_c$).
3. Calculates the **Weighted Median** of code-level ratios:
   $$\text{Provider Index} = \text{WeightedMedian}_{c \in \text{Codes}} \left( \frac{\text{Rate}_c}{\text{PeerMedian}_c}, w_c \right)$$

---

## 5. Price Competitiveness Disclaimer
> [!IMPORTANT]
> **Regulatory and Actuarial Disclaimer**: 
> A lower price ratio indicates contract cost-efficiency relative to regional peers, **NOT** clinical efficacy, diagnostic accuracy, or superior patient outcomes. Conversely, higher negotiated rates reflect hospital market concentration, academic research subsidies, specialized facility overhead, or payer-provider bargaining leverage, rather than intrinsic clinical quality. 
> These metrics are intended solely for actuarial network design, benefit modeling, and transparency compliance.
