# Rate Competitiveness & Peer Benchmarking (C7)

## 1. Overview & Objective
Raw in-network negotiated rates cannot be compared apples-to-apples without accounting for the procedure, whether it's facility or professional, the provider's specialty, and where they practice. 

This module benchmarks each provider's rates against comparable peers across California. The goal is to give health plans and employers a straightforward, statistically sound way to see which providers have competitive rates compared to market medians, without confusing price with clinical quality.

---

## 2. Methodology & Metrics

### 2.1 Why Medians and MAD Instead of Means
Healthcare prices are rarely normally distributed:
- Academic medical centers and specialized surgical centers charge significantly higher rates that pull up the simple arithmetic average.
- Many rates bunch up around standard fee-schedule multipliers (like 120% of Medicare).
- A handful of $20,000+ outliers can distort the mean and standard deviation.

To keep the metrics stable and resistant to outliers, we use medians and median absolute deviations (MAD) rather than means and standard deviations.

### 2.2 Core Benchmarking Metrics

For each valid rate, we compute:

1. **Peer Median Rate**:
   $$\text{Median}(R) = \text{Med}(r_i)$$
   The midpoint rate among qualified peer providers.

2. **Rate-to-Peer Median Ratio**:
   $$\text{Ratio} = \frac{\text{Rate}}{\text{Peer Median}}$$
   - Below `1.0`: Lower than market median (more cost-competitive).
   - Equal to `1.0`: Exactly at the peer market median.
   - Above `1.0`: Higher than market median.

3. **Percentile Rank**:
   $$\text{Percentile} = \frac{\# \{r_j \le r\}}{N} \times 100$$
   Where this rate falls within the peer group (0% to 100%).

4. **Log-Scaled Robust Z-Score**:
   Because rate negotiations scale multiplicatively (e.g. $1.25\times$ or $0.85\times$ base), we compute the robust z-score on the log of the rate using Median Absolute Deviation:
   $$\text{Robust } Z = \frac{\ln(r) - \text{Median}(\ln(R))}{1.4826 \times \text{MAD}(\ln(R))}$$
   *(The $1.4826$ factor scales the MAD to match a standard normal distribution).*

---

## 3. Peer Groups & Regional Fallbacks

### 3.1 Peer Group Definition
Providers are compared against peers matching on 5 attributes:
$$\text{Peer Group} = (\text{Billing Code}, \text{Billing Class}, \text{Entity Type}, \text{Specialty}, \text{Region})$$

- **Billing Code**: CPT/HCPCS code or revenue code.
- **Billing Class**: `professional` vs `institutional` (kept separate because facility overhead costs are fundamentally different).
- **Entity Type**: Individual physician (Type 1) vs group practice/facility (Type 2).
- **Specialty**: Clinical specialty (e.g., Internal Medicine, Dermatology, Cardiology).
- **Region**: 3-digit California ZIP code prefix grouped into metro regions (e.g. `900–918` for Los Angeles, `940–944` for SF Peninsula).

### 3.2 Minimum Cohort Size & Statewide Fallback
To avoid unreliable rankings based on tiny sample sizes:
- **Minimum 10 Peers**: A group must have at least 10 providers to establish a regional baseline.
- **Statewide Fallback**: If a local 3-digit region has fewer than 10 peers for a code/specialty combination, the system falls back to the statewide California pool (`peer_level: STATEWIDE`).
- **Insufficient Peers**: If fewer than 10 providers bill that code statewide, the row is marked `is_scoreable: False` and `peer_level: INSUFFICIENT_PEERS`, rather than guessing from an unrepresentative sample.

### 3.3 Data Cleaning Rules
To keep peer baselines clean:
- **Exclude Low-Reliability Rates**: Rates with extreme multi-plan spreads or collision issues are excluded from calculating peer medians.
- **Exclude Integrated HMO Contracts**: Closed staff-model HMO rates (such as Kaiser Permanente) are excluded so they do not distort open commercial PPO medians.
- **Exclude Zero/Negative Rates**: Filtered out before computing stats.

---

## 4. Overall Provider Efficiency Index

Individual clinicians bill many different codes, so evaluating a single code does not give the whole picture.

To measure a practice's overall rate profile:
1. We filter for providers with at least **3 qualified procedure codes**.
2. We weight codes by clinical volume using standard procedure weights from the reference table ($w_c$).
3. We take the **weighted median** of all code ratios for that provider:
   $$\text{Provider Index} = \text{WeightedMedian}_{c \in \text{Codes}} \left( \frac{\text{Rate}_c}{\text{PeerMedian}_c}, w_c \right)$$

A provider index of `0.92` means that, on typical volume-weighted care, their negotiated rates sit about 8% below the peer median.

---

## 5. Note on Price vs. Quality
> [!NOTE]
> A lower rate ratio simply means a provider's contract is more cost-effective relative to local peers. It does not measure clinical quality, diagnostic skill, or patient outcomes. Higher rates often reflect academic medical centers, tertiary trauma capabilities, or local market bargaining power.
