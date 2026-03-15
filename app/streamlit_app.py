"""
Battery Electrolyte Knowledge Graph - Web Demo

A Streamlit application for exploring the integrated knowledge graph
of battery electrolyte data.
"""

import streamlit as st
from pathlib import Path

# Must be the first Streamlit command
st.set_page_config(
    page_title="Battery Electrolyte KG",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import utilities
from utils.data_loader import get_kg_statistics, get_data_sources, load_hypotheses

# Get project root for images
PROJECT_ROOT = Path(__file__).parent.parent


def main():
    # Header
    st.title("🔋 Battery Electrolyte Knowledge Graph")
    st.markdown("""
    An AI-driven knowledge graph integrating heterogeneous data sources for
    lithium-ion battery electrolyte research, enabling automated hypothesis
    generation and cross-property discovery.
    """)

    # Key Statistics
    st.header("Knowledge Graph Statistics")
    stats = get_kg_statistics()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Molecules", f"{stats['molecules']:,}")
    with col2:
        st.metric("Formulations", f"{stats['formulations']:,}")
    with col3:
        st.metric("Measurements", f"{stats['measurements']:,}")
    with col4:
        st.metric("Relations", f"{stats['relations']:,}")

    col5, col6 = st.columns(2)
    with col5:
        st.metric("Interphase Species", stats['interphase_species'])
    with col6:
        st.metric("Generated Hypotheses", stats['hypotheses'])

    # Data Sources
    st.header("Integrated Data Sources")
    sources = get_data_sources()

    # Create a nice table
    source_data = {
        "Dataset": [s["name"] for s in sources],
        "Measurements": [f"{s['measurements']:,}" for s in sources],
        "Type": [s["type"] for s in sources],
        "Properties": [s["properties"] for s in sources],
    }
    st.dataframe(source_data, width='stretch', hide_index=True)

    # Key Findings
    st.header("Key Discoveries")

    hypotheses = load_hypotheses()
    correlations = hypotheses.get("cross_property_correlations", {})

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cross-Property Correlations")
        for prop, data in correlations.items():
            corr = data["correlation"]
            conf = data["confidence"]
            icon = "🟢" if conf == "strong" else ("🟡" if conf == "moderate" else "⚪")
            st.markdown(f"{icon} **{prop.replace('_', ' ').title()}**: r = {corr:.3f}")
            st.caption(data["interpretation"])

    with col2:
        st.subheader("Top Hypotheses")
        for hyp in hypotheses.get("cross_property_hypotheses", [])[:3]:
            with st.expander(f"**{hyp['id']}**: {hyp['hypothesis'][:60]}..."):
                st.markdown(f"**Hypothesis:** {hyp['hypothesis']}")
                st.markdown(f"**Evidence:** {hyp['evidence']}")
                st.markdown(f"**Mechanism:** {hyp['mechanism']}")
                st.progress(hyp['confidence'], text=f"Confidence: {hyp['confidence']:.0%}")

    # Rule Mining Summary
    st.subheader("Association Rule Mining")
    rules = hypotheses.get("rule_mining_hypotheses", {})
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Rules", rules.get("total", 0))
    with col2:
        st.metric("Co-occurrence Patterns", rules.get("by_type", {}).get("coOccursWith", 0))
    with col3:
        st.metric("Causal Rules", rules.get("by_type", {}).get("increases", 0) +
                  rules.get("by_type", {}).get("decreases", 0))

    # Top patterns
    patterns = rules.get("top_patterns", [])
    if patterns:
        st.markdown("**Top Discovered Patterns:**")
        for pattern in patterns:
            st.markdown(f"- {pattern}")

    # Dashboard image
    st.header("Knowledge Graph Overview")
    dashboard_path = PROJECT_ROOT / "data" / "output" / "figures" / "kg_dashboard.png"
    if dashboard_path.exists():
        st.image(str(dashboard_path), width='stretch')
    else:
        st.info("Dashboard image not available")

    # Navigation hints
    st.divider()
    st.markdown("""
    ### Explore the Knowledge Graph

    Use the sidebar to navigate to:
    - **Knowledge Graph**: Interactive graph exploration with search and filtering
    - **Hypotheses**: Browse and filter generated hypotheses
    - **Solvent Comparison**: Compare solvent properties and conductivity
    """)

    # Footer
    st.divider()
    st.caption("""
    Built with Streamlit | Data from CALiSol-23, Materials Project, LIBE, and curated literature |
    [GitHub Repository](https://github.com/agents4science/battery-electrolyte-kg)
    """)


if __name__ == "__main__":
    main()
