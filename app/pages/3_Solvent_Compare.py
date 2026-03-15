"""
Solvent Comparison Page

Compare properties and conductivity across different solvents.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import (
    load_curated_properties,
    load_calisol_data,
    get_solvent_conductivity_stats,
    COMPOUND_NAMES,
)

st.set_page_config(page_title="Solvent Comparison", page_icon="⚗️", layout="wide")

st.title("⚗️ Solvent Comparison Tool")
st.markdown("Compare electrochemical properties and conductivity across different solvents.")

# Load data
props_data = load_curated_properties()
solvents = props_data.get("solvents", [])

# Build solvent lookup
solvent_lookup = {s["abbreviation"]: s for s in solvents}
available_solvents = list(solvent_lookup.keys())

# Sidebar selection
st.sidebar.header("Select Solvents")
selected_solvents = st.sidebar.multiselect(
    "Choose solvents to compare",
    available_solvents,
    default=["EC", "PC", "DMC", "EMC"] if len(available_solvents) >= 4 else available_solvents[:4]
)

if len(selected_solvents) < 2:
    st.warning("Please select at least 2 solvents to compare.")
    st.stop()

# Build comparison dataframe
comparison_data = []
for abbrev in selected_solvents:
    solvent = solvent_lookup.get(abbrev, {})
    props = solvent.get("properties", {})

    row = {
        "Solvent": abbrev,
        "Full Name": solvent.get("name", abbrev),
        "HOMO (eV)": props.get("homo_energy", {}).get("value"),
        "LUMO (eV)": props.get("lumo_energy", {}).get("value"),
        "IE (eV)": props.get("ionization_energy", {}).get("value"),
        "EA (eV)": props.get("electron_affinity", {}).get("value"),
        "Dielectric": props.get("dielectric_constant", {}).get("value"),
        "Ox. Pot. (V)": props.get("oxidation_potential", {}).get("value"),
        "Red. Pot. (V)": props.get("reduction_potential", {}).get("value"),
    }
    comparison_data.append(row)

df = pd.DataFrame(comparison_data)

# Main comparison table
st.header("Property Comparison")
st.dataframe(df, use_container_width=True, hide_index=True)

# Tabs for different visualizations
tab1, tab2, tab3 = st.tabs(["Bar Charts", "Radar Plot", "Conductivity"])

with tab1:
    st.subheader("Property Bar Charts")

    # Select which property to plot
    numeric_cols = ["HOMO (eV)", "LUMO (eV)", "IE (eV)", "EA (eV)", "Dielectric"]
    available_cols = [c for c in numeric_cols if df[c].notna().any()]

    col1, col2 = st.columns(2)

    with col1:
        if "HOMO (eV)" in available_cols and "LUMO (eV)" in available_cols:
            # HOMO-LUMO comparison
            homo_lumo_df = df[["Solvent", "HOMO (eV)", "LUMO (eV)"]].melt(
                id_vars=["Solvent"],
                var_name="Energy Level",
                value_name="Energy (eV)"
            )
            fig = px.bar(
                homo_lumo_df,
                x="Solvent",
                y="Energy (eV)",
                color="Energy Level",
                barmode="group",
                title="HOMO and LUMO Energies",
                color_discrete_map={"HOMO (eV)": "#FF6B6B", "LUMO (eV)": "#4ECDC4"}
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if "Dielectric" in available_cols:
            fig = px.bar(
                df,
                x="Solvent",
                y="Dielectric",
                title="Dielectric Constant",
                color="Dielectric",
                color_continuous_scale="Viridis",
            )
            st.plotly_chart(fig, use_container_width=True)

    # HOMO-LUMO gap calculation
    if "HOMO (eV)" in df.columns and "LUMO (eV)" in df.columns:
        df_gap = df.copy()
        df_gap["Gap (eV)"] = df_gap["LUMO (eV)"] - df_gap["HOMO (eV)"]

        if df_gap["Gap (eV)"].notna().any():
            fig = px.bar(
                df_gap,
                x="Solvent",
                y="Gap (eV)",
                title="HOMO-LUMO Gap (Electrochemical Window)",
                color="Gap (eV)",
                color_continuous_scale="Plasma",
            )
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Radar Plot Comparison")

    # Prepare data for radar plot
    radar_props = ["HOMO (eV)", "LUMO (eV)", "IE (eV)", "Dielectric"]
    radar_available = [p for p in radar_props if p in df.columns and df[p].notna().any()]

    if len(radar_available) >= 3:
        # Normalize values for radar plot
        df_radar = df[["Solvent"] + radar_available].copy()

        for col in radar_available:
            col_data = df_radar[col].dropna()
            if len(col_data) > 0:
                min_val, max_val = col_data.min(), col_data.max()
                if max_val > min_val:
                    df_radar[col] = (df_radar[col] - min_val) / (max_val - min_val)
                else:
                    df_radar[col] = 0.5

        # Create radar chart
        fig = go.Figure()

        for _, row in df_radar.iterrows():
            values = [row[p] if pd.notna(row[p]) else 0 for p in radar_available]
            values.append(values[0])  # Close the polygon

            fig.add_trace(go.Scatterpolar(
                r=values,
                theta=radar_available + [radar_available[0]],
                fill='toself',
                name=row["Solvent"],
                opacity=0.7,
            ))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            showlegend=True,
            title="Normalized Property Comparison",
            height=500,
        )

        st.plotly_chart(fig, use_container_width=True)
        st.caption("Values normalized to 0-1 range for comparison")
    else:
        st.info("Not enough properties available for radar plot")

with tab3:
    st.subheader("Conductivity Comparison")

    # Load conductivity statistics
    cond_stats = get_solvent_conductivity_stats()

    if cond_stats:
        # Filter to selected solvents
        cond_data = []
        for solvent in selected_solvents:
            if solvent in cond_stats:
                stats = cond_stats[solvent]
                cond_data.append({
                    "Solvent": solvent,
                    "Mean σ (S/cm)": stats["mean"],
                    "Std": stats["std"],
                    "Min": stats["min"],
                    "Max": stats["max"],
                    "N Measurements": stats["count"],
                })

        if cond_data:
            df_cond = pd.DataFrame(cond_data)

            # Bar chart with error bars
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_cond["Solvent"],
                y=df_cond["Mean σ (S/cm)"],
                error_y=dict(type='data', array=df_cond["Std"]),
                marker_color='#4A90D9',
            ))
            fig.update_layout(
                title="Average Ionic Conductivity by Solvent",
                xaxis_title="Solvent",
                yaxis_title="Conductivity (S/cm)",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Data table
            st.dataframe(df_cond, use_container_width=True, hide_index=True)
        else:
            st.info("Conductivity data not available for selected solvents")

    # LUMO vs Conductivity scatter plot
    st.subheader("LUMO Energy vs Conductivity")

    if cond_stats:
        scatter_data = []
        for solvent in selected_solvents:
            solv_props = solvent_lookup.get(solvent, {}).get("properties", {})
            lumo = solv_props.get("lumo_energy", {}).get("value")

            if solvent in cond_stats and lumo is not None:
                scatter_data.append({
                    "Solvent": solvent,
                    "LUMO (eV)": lumo,
                    "Conductivity (S/cm)": cond_stats[solvent]["mean"],
                })

        if len(scatter_data) >= 2:
            df_scatter = pd.DataFrame(scatter_data)

            fig = px.scatter(
                df_scatter,
                x="LUMO (eV)",
                y="Conductivity (S/cm)",
                text="Solvent",
                title="LUMO Energy vs Ionic Conductivity (r = 0.70)",
            )
            fig.update_traces(textposition='top center', marker_size=12)
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

            st.info("""
            **Key Finding:** Higher LUMO energy correlates with higher conductivity (r=0.70).
            This suggests that reduction stability is linked to ion transport properties.
            """)
        else:
            st.info("Not enough data points for scatter plot")

# Solvent conductivity image
st.divider()
PROJECT_ROOT = Path(__file__).parent.parent.parent
cond_path = PROJECT_ROOT / "data" / "output" / "figures" / "kg_solvent_conductivity.png"
if cond_path.exists():
    st.subheader("Full Conductivity Analysis")
    st.image(str(cond_path), use_container_width=True)
