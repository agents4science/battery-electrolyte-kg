"""
Hypothesis Dashboard Page

Browse and explore generated hypotheses from the knowledge graph.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import load_hypotheses

st.set_page_config(page_title="Hypotheses", page_icon="💡", layout="wide")

st.title("💡 Hypothesis Dashboard")
st.markdown("Explore hypotheses generated through cross-property correlation analysis and association rule mining.")

# Load data
hypotheses_data = load_hypotheses()

# Tabs for different views
tab1, tab2, tab3 = st.tabs(["Cross-Property Hypotheses", "Correlations", "Rule Mining"])

with tab1:
    st.header("Cross-Property Hypotheses")

    # Sidebar filters for this section
    confidence_min = st.slider("Minimum Confidence", 0.0, 1.0, 0.5, 0.05)

    # Get hypotheses
    cross_hyps = hypotheses_data.get("cross_property_hypotheses", [])

    # Filter by confidence
    filtered_hyps = [h for h in cross_hyps if h.get("confidence", 0) >= confidence_min]

    st.markdown(f"Showing **{len(filtered_hyps)}** of {len(cross_hyps)} hypotheses")

    # Display each hypothesis
    for hyp in filtered_hyps:
        confidence = hyp.get("confidence", 0)
        color = "green" if confidence >= 0.8 else ("orange" if confidence >= 0.6 else "red")

        with st.expander(f"**{hyp['id']}**: {hyp['hypothesis']}", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**Hypothesis:** {hyp['hypothesis']}")
                st.markdown(f"**Evidence:** {hyp['evidence']}")
                st.markdown(f"**Mechanism:** {hyp['mechanism']}")

                if "correlation" in hyp:
                    st.markdown(f"**Correlation:** r = {hyp['correlation']:.3f}")

            with col2:
                st.metric("Confidence", f"{confidence:.0%}")

                # Visual confidence bar
                st.progress(confidence)

with tab2:
    st.header("Cross-Property Correlations")
    st.markdown("Correlations between molecular properties and ionic conductivity.")

    correlations = hypotheses_data.get("cross_property_correlations", {})

    if correlations:
        # Create correlation dataframe
        corr_data = []
        for prop, data in correlations.items():
            corr_data.append({
                "Property": prop.replace("_", " ").title(),
                "Correlation": data["correlation"],
                "Confidence": data["confidence"],
                "N Solvents": data["n_solvents"],
                "Interpretation": data["interpretation"],
            })

        df_corr = pd.DataFrame(corr_data)

        # Bar chart of correlations
        fig = px.bar(
            df_corr,
            x="Property",
            y="Correlation",
            color="Correlation",
            color_continuous_scale="RdBu",
            range_color=[-1, 1],
            title="Property Correlations with Ionic Conductivity",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

        # Details table
        st.subheader("Correlation Details")
        st.dataframe(
            df_corr[["Property", "Correlation", "Confidence", "N Solvents", "Interpretation"]],
            use_container_width=True,
            hide_index=True
        )

        # Key insight
        st.info("""
        **Key Finding:** LUMO energy shows the strongest correlation (r=0.70) with ionic conductivity.
        Solvents with higher LUMO energies (indicating greater reduction stability) tend to enable
        higher conductivity.
        """)

    # Correlation heatmap image
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    corr_path = PROJECT_ROOT / "data" / "output" / "figures" / "kg_cross_property.png"
    if corr_path.exists():
        st.subheader("Full Correlation Analysis")
        st.image(str(corr_path), use_container_width=True)

with tab3:
    st.header("Association Rule Mining")
    st.markdown("Patterns discovered through mining electrolyte formulation compositions.")

    rules = hypotheses_data.get("rule_mining_hypotheses", {})

    if rules:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Rules Discovered", rules.get("total", 0))

        with col2:
            by_type = rules.get("by_type", {})
            st.metric("Co-occurrence Patterns", by_type.get("coOccursWith", 0))

        with col3:
            causal = by_type.get("increases", 0) + by_type.get("decreases", 0)
            st.metric("Causal Rules", causal)

        # Rule type breakdown
        if by_type:
            fig = px.pie(
                values=list(by_type.values()),
                names=list(by_type.keys()),
                title="Rule Types Distribution",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

        # Top patterns
        st.subheader("Top Discovered Patterns")
        patterns = rules.get("top_patterns", [])

        for i, pattern in enumerate(patterns, 1):
            st.markdown(f"**{i}.** {pattern}")

        # Explanation
        st.info("""
        **How it works:** Association rule mining finds frequent patterns in electrolyte
        formulations. For example, if EC and EMC often appear together in high-conductivity
        electrolytes, this suggests a synergistic effect worth investigating.
        """)

# Data source info
st.divider()
st.subheader("About Hypothesis Generation")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **Cross-Property Analysis:**
    - Links electrochemical properties (HOMO, LUMO, IE, EA) to conductivity
    - Uses SMILES-based matching across datasets
    - Identifies structure-property relationships
    """)

with col2:
    st.markdown("""
    **Association Rule Mining:**
    - Discovers frequent component combinations
    - Identifies causal relationships (increases/decreases)
    - Generates testable hypotheses
    """)
