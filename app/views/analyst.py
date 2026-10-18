"""Analyst View (Page 2) for PTD Streamlit application.

Interactive Contracting Analyst workspace providing:
- Multi-dimensional filters (Billing Code, Specialty, TIN, NPI, Address Status, Network Tier, Outliers).
- Paginated & searchable results table (6 core columns + governance metadata).
- Rate distribution histograms, box plots, and peer median benchmarks.
- Deep Provider Drill-Down (Practicing sites, NPIs, TINs, and rate lineage).
- Cost-Effectiveness Frontier (C7) with percentile rankings.
- Zero-cost California regional ZIP3 map.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.data_access import (
    load_cost_effectiveness_df,
    load_distinct_filter_options,
    query_curated_rates_polars,
    render_missing_file_warning,
)

# Zero-cost California 3-digit postal centroid lookup (no paid external APIs)
CA_ZIP3_CENTROIDS = {
    "900": (34.05, -118.25, "Los Angeles"),
    "901": (34.05, -118.25, "Los Angeles"),
    "902": (33.97, -118.40, "Inglewood / Culver City"),
    "903": (33.95, -118.35, "Inglewood"),
    "904": (34.02, -118.49, "Santa Monica"),
    "905": (33.83, -118.34, "Torrance"),
    "906": (33.92, -118.04, "Whittier"),
    "907": (33.80, -118.20, "Long Beach"),
    "908": (33.78, -118.18, "Long Beach"),
    "910": (34.19, -118.15, "Pasadena"),
    "911": (34.15, -118.14, "Pasadena"),
    "912": (34.15, -118.25, "Glendale"),
    "913": (34.20, -118.55, "San Fernando Valley"),
    "914": (34.18, -118.44, "Van Nuys"),
    "915": (34.18, -118.32, "Burbank"),
    "916": (34.17, -118.38, "North Hollywood"),
    "917": (34.06, -117.97, "San Gabriel Valley"),
    "918": (34.08, -118.13, "Alhambra"),
    "919": (32.65, -117.00, "Chula Vista / South Bay"),
    "920": (33.05, -117.15, "North County San Diego"),
    "921": (32.75, -117.15, "San Diego Central"),
    "922": (33.75, -116.30, "Palm Springs / Coachella"),
    "923": (34.10, -117.20, "San Bernardino / Inland Empire"),
    "924": (34.12, -117.28, "San Bernardino"),
    "925": (33.80, -117.20, "Riverside / Corona"),
    "926": (33.65, -117.80, "Irvine / Newport Beach"),
    "927": (33.75, -117.87, "Santa Ana"),
    "928": (33.85, -117.85, "Anaheim / Fullerton"),
    "930": (34.28, -119.25, "Ventura / Oxnard"),
    "931": (34.43, -119.72, "Santa Barbara"),
    "932": (35.80, -119.20, "Tulare / Porterville"),
    "933": (35.37, -119.02, "Bakersfield"),
    "934": (35.28, -120.66, "San Luis Obispo / Santa Maria"),
    "935": (34.70, -118.15, "Lancaster / Palmdale / Mojave"),
    "936": (36.70, -119.70, "Fresno Rural / Madera"),
    "937": (36.78, -119.79, "Fresno City"),
    "938": (36.75, -119.77, "Fresno"),
    "939": (36.68, -121.66, "Salinas / Monterey"),
    "940": (37.45, -122.18, "San Mateo / Palo Alto"),
    "941": (37.77, -122.42, "San Francisco"),
    "942": (38.58, -121.49, "Sacramento"),
    "943": (37.44, -122.16, "Palo Alto"),
    "944": (37.56, -122.32, "San Mateo"),
    "945": (37.90, -122.05, "Walnut Creek / Concord"),
    "946": (37.80, -122.27, "Oakland"),
    "947": (37.87, -122.27, "Berkeley"),
    "948": (37.93, -122.35, "Richmond"),
    "949": (37.97, -122.53, "Marin / San Rafael"),
    "950": (36.97, -122.03, "Santa Cruz / Los Gatos"),
    "951": (37.34, -121.89, "San Jose"),
    "952": (37.96, -121.29, "Stockton"),
    "953": (37.64, -120.99, "Modesto"),
    "954": (38.44, -122.71, "Santa Rosa / Sonoma"),
    "955": (40.80, -124.16, "Eureka / Humboldt"),
    "956": (38.65, -121.35, "Sacramento Suburbs / Davis"),
    "957": (38.75, -121.28, "Roseville / Folsom"),
    "958": (38.58, -121.49, "Sacramento Downtown"),
    "959": (39.73, -121.84, "Chico / Yuba City"),
    "960": (40.59, -122.39, "Redding / Shasta"),
    "961": (39.33, -120.18, "Truckee / Lake Tahoe / Modoc"),
}


def render_analyst_view(source_mode: str = "Production outputs", global_filters: Dict[str, Any] | None = None) -> None:
    """Render the detailed contracting analyst exploration page."""
    st.title("🔍 Analyst View: Rate Inspection & Contracting Drill-Down")
    st.caption("Investigate procedure pricing distributions, contract terms, provider address footprints, and peer benchmarks.")

    opts = load_distinct_filter_options(source_mode)

    # -------------------------------------------------------------------------
    # 1. Interactive Analyst Filter Toolbar
    # -------------------------------------------------------------------------
    with st.expander("🛠️ Advanced Query & Filtering Controls", expanded=True):
        f_row1_col1, f_row1_col2, f_row1_col3, f_row1_col4 = st.columns(4)

        with f_row1_col1:
            q_code = st.text_input("Billing Code Search", value="", placeholder="e.g. 99213, 90837, 636, 250").strip()
        with f_row1_col2:
            spec_opts = ["ALL"] + opts.get("specialties", [])
            q_spec = st.selectbox("Specialty", options=spec_opts, index=0)
        with f_row1_col3:
            q_tin = st.text_input("TIN Filter", value="", placeholder="e.g. 94-0382330").strip()
        with f_row1_col4:
            q_npi_str = st.text_input("NPI Filter", value="", placeholder="e.g. 1003961251").strip()
            q_npi = int(q_npi_str) if q_npi_str.isdigit() else None

        f_row2_col1, f_row2_col2, f_row2_col3, f_row2_col4 = st.columns(4)
        with f_row2_col1:
            q_tier = st.selectbox("PPO Evidence Tier", options=["ALL", "T1_name_hint_ppo", "T2_shared_commercial"], index=0)
        with f_row2_col2:
            q_addr_status = st.selectbox("Address Status", options=["ALL", "Verified", "Probable", "Unverified", "Facility/TIN-level"], index=0)
        with f_row2_col3:
            q_outlier = st.selectbox("Outlier Flag", options=["ALL", "Outliers only", "Standard only"], index=0)
        with f_row2_col4:
            max_rows = st.number_input("Max Query Limit", min_value=100, max_value=5000, value=1000, step=100)

    # Execute memory-bounded polars query
    with st.spinner("Fetching matching rates..."):
        df_rates = query_curated_rates_polars(
            source_mode=source_mode,
            billing_code=q_code if q_code else None,
            specialty=q_spec,
            tin=q_tin if q_tin else None,
            npi=q_npi,
            address_status=q_addr_status,
            network_tier=q_tier,
            outlier_filter=q_outlier,
            limit=int(max_rows)
        )

    if df_rates is None or df_rates.empty:
        st.info("No curated rate records matched your query filters. Try loosening your criteria.")
        return

    # -------------------------------------------------------------------------
    # 2. Results Table with Export
    # -------------------------------------------------------------------------
    st.subheader(f"1. Curated Contract Rates Table ({len(df_rates):,} matching rows)")

    # Core 6 columns + essential governance columns
    cols_to_show = [
        "NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate",
        "address_status", "address_confidence", "rate_reliability", "ppo_evidence_tier", "outlier_flag"
    ]
    display_df = df_rates[[c for c in cols_to_show if c in df_rates.columns]].copy()

    # Format Rate
    if "Rate" in display_df.columns:
        display_df["Rate_Formatted"] = display_df["Rate"].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "")

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        height=320
    )

    # Download filtered CSV
    csv_bytes = df_rates.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Filtered Results (CSV)",
        data=csv_bytes,
        file_name="ptd_filtered_rates.csv",
        mime="text/csv"
    )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 3. Rate Distribution & Statistical Benchmarks
    # -------------------------------------------------------------------------
    st.subheader("2. Price Distribution & Benchmark Analysis")
    dist_col1, dist_col2 = st.columns(2)

    with dist_col1:
        st.markdown("**Rate Distribution Histogram**")
        fig_hist = px.histogram(
            df_rates,
            x="Rate",
            nbins=35,
            color="ppo_evidence_tier" if "ppo_evidence_tier" in df_rates.columns else None,
            color_discrete_map={"T1_name_hint_ppo": "#2E7D32", "T2_shared_commercial": "#1E88E5"},
            labels={"Rate": "Negotiated Rate ($)", "count": "Frequency"},
        )
        med_val = df_rates["Rate"].median()
        fig_hist.add_vline(x=med_val, line_dash="dash", line_color="#D32F2F", annotation_text=f"Median: ${med_val:,.2f}")
        fig_hist.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_hist, width="stretch")

    with dist_col2:
        st.markdown("**Rate Box Plot by Specialty / Tier**")
        group_col = "Specialty" if df_rates["Specialty"].nunique() <= 10 else "ppo_evidence_tier"
        fig_box = px.box(
            df_rates,
            x=group_col,
            y="Rate",
            color=group_col,
            labels={"Rate": "Negotiated Rate ($)"},
        )
        fig_box.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig_box, width="stretch")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 4. Provider Footprint & Lineage Drill-Down
    # -------------------------------------------------------------------------
    st.subheader("3. Provider Multi-Address Footprint & Lineage Drill-Down")

    unique_tins = df_rates["TIN"].dropna().unique().tolist()
    unique_npis = df_rates["NPI"].dropna().astype(str).unique().tolist()

    drill_col1, drill_col2 = st.columns(2)
    with drill_col1:
        selected_tin = st.selectbox("Select Provider TIN to Inspect:", options=unique_tins[:100], index=0)
    with drill_col2:
        tin_filtered = df_rates[df_rates["TIN"] == selected_tin]
        available_npis = tin_filtered["NPI"].dropna().astype(str).unique().tolist()
        selected_npi = st.selectbox("Select NPI associated with TIN:", options=["ALL"] + available_npis, index=0)

    p_data = tin_filtered if selected_npi == "ALL" else tin_filtered[tin_filtered["NPI"].astype(str) == selected_npi]

    d_col1, d_col2 = st.columns([3, 2])
    with d_col1:
        st.markdown(f"**Practicing Physical Addresses for TIN `{selected_tin}`**")
        addr_df = p_data[["Address", "address_status", "address_confidence", "rate_reliability"]].drop_duplicates()
        st.dataframe(addr_df, width="stretch", hide_index=True)

    with d_col2:
        st.markdown("**Contract Lineage & Terms**")
        canonical_name = p_data["tin_canonical_name"].iloc[0] if "tin_canonical_name" in p_data.columns and not p_data.empty else "N/A"
        st.markdown(
            f"""
            - **Canonical Entity Name**: `{canonical_name}`
            - **Network Tier**: `{p_data['ppo_evidence_tier'].iloc[0] if 'ppo_evidence_tier' in p_data.columns else 'N/A'}`
            - **Modifiers Retained**: `{', '.join(p_data['modifier_used'].dropna().unique()) if 'modifier_used' in p_data.columns else 'NONE'}`
            - **POS Setting Used**: `{', '.join(p_data['service_code_used'].dropna().unique()) if 'service_code_used' in p_data.columns else 'N/A'}`
            - **Total Contract Codes Billed**: `{p_data['Billing Code'].nunique()}`
            """
        )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 5. Cost-Effectiveness Frontier (C7)
    # -------------------------------------------------------------------------
    st.subheader("4. Cost-Effectiveness Frontier (C7 Rubric Dimension)")
    df_ce = load_cost_effectiveness_df(source_mode, limit=1000)

    if df_ce is not None and not df_ce.empty:
        c7_col1, c7_col2 = st.columns([3, 2])
        with c7_col1:
            st.markdown("**Provider Price Competitiveness by Regional Peer Cohort**")
            ce_sub = df_ce[["NPI", "TIN", "Billing Code", "Specialty", "Rate", "peer_median_rate", "rate_to_peer_median", "percentile_rank", "is_scoreable"]].head(25)
            st.dataframe(ce_sub, width="stretch", hide_index=True)

        with c7_col2:
            st.markdown("**Rate vs Percentile Rank**")
            valid_ce = df_ce.dropna(subset=["percentile_rank", "rate_to_peer_median"])
            if not valid_ce.empty:
                fig_scatter = px.scatter(
                    valid_ce.head(200),
                    x="percentile_rank",
                    y="Rate",
                    color="rate_to_peer_median",
                    color_continuous_scale="Viridis",
                    labels={"percentile_rank": "Peer Percentile Rank", "Rate": "Negotiated Rate ($)"},
                    hover_data=["Billing Code", "Specialty"]
                )
                fig_scatter.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_scatter, width="stretch")
    else:
        st.caption("ℹ️ Cost effectiveness dataset loading.")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 6. California Regional ZIP3 Map (Zero API cost)
    # -------------------------------------------------------------------------
    st.subheader("5. Geographic Distribution: California Regional ZIP3 Footprint")
    st.caption("📍 Aggregated by California ZIP3 Regional Centroids (no external paid geocoding APIs called; zero network latency).")

    # Extract ZIP3 from Address
    map_records = []
    for _, row in df_rates.iterrows():
        addr = str(row.get("Address", ""))
        status = row.get("address_status", "Unverified")
        rate = row.get("Rate", 0.0)

        # Look for 5-digit zip in address string
        tokens = addr.replace(",", " ").split()
        zip5 = next((t for t in tokens if len(t) == 5 and t.isdigit() and t.startswith("9")), None)
        if zip5:
            zip3 = zip5[:3]
            if zip3 in CA_ZIP3_CENTROIDS:
                lat, lon, region_name = CA_ZIP3_CENTROIDS[zip3]
                map_records.append({
                    "zip3": zip3,
                    "region": region_name,
                    "lat": lat,
                    "lon": lon,
                    "address_status": status,
                    "rate": rate,
                })

    if map_records:
        df_map = pd.DataFrame(map_records)
        df_map_agg = df_map.groupby(["zip3", "region", "lat", "lon", "address_status"]).agg(
            provider_count=("rate", "count"),
            median_rate=("rate", "median")
        ).reset_index()

        fig_map = px.scatter_geo(
            df_map_agg,
            lat="lat",
            lon="lon",
            size="provider_count",
            color="address_status",
            color_discrete_map={"Verified": "#2E7D32", "Probable": "#1E88E5", "Unverified": "#FF9800", "Facility/TIN-level": "#9C27B0"},
            hover_name="region",
            hover_data={"zip3": True, "provider_count": True, "median_rate": ":$.2f", "lat": False, "lon": False},
            scope="usa",
        )
        fig_map.update_geos(
            fitbounds="locations",
            visible=False,
            showsubunits=True,
            subunitcolor="Black",
            showcoastlines=True,
            showland=True,
            landcolor="#F5F5F5",
            lataxis_range=[32, 42],
            lonaxis_range=[-125, -114]
        )
        fig_map.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_map, width="stretch")
    else:
        st.info("No California 5-digit postal codes parsed from current filtered results.")
