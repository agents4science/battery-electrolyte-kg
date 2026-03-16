"""
Discovery Dashboard Page

View and curate AI-generated hypotheses from the discovery pipeline.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Discovery", page_icon="🔬", layout="wide")

PROJECT_ROOT = Path(__file__).parent.parent.parent
DISCOVERY_DIR = PROJECT_ROOT / "data" / "output" / "discovery"


@st.cache_data
def load_latest_discovery_run():
    """Load the most recent discovery run."""
    if not DISCOVERY_DIR.exists():
        return None

    # Find latest run file
    run_files = list(DISCOVERY_DIR.glob("discovery-*.json"))
    if not run_files:
        return None

    # Sort by modification time
    latest = max(run_files, key=lambda p: p.stat().st_mtime)

    with open(latest) as f:
        return json.load(f)


def render_funnel_chart(run_data):
    """Render discovery funnel visualization."""
    funnel = run_data.get("funnel", {})

    stages = ["Gaps Found", "Hypotheses Generated", "Validated", "Ready for Curation"]
    values = [
        funnel.get("gaps_found", 0),
        funnel.get("hypotheses_generated", 0),
        funnel.get("validated", 0),
        run_data.get("metrics", {}).get("ready_for_curation", 0),
    ]

    fig = go.Figure(go.Funnel(
        y=stages,
        x=values,
        textposition="inside",
        textinfo="value+percent initial",
        marker=dict(color=["#3498db", "#9b59b6", "#2ecc71", "#f39c12"]),
    ))

    fig.update_layout(
        title="Discovery Funnel",
        height=350,
        margin=dict(l=20, r=20, t=50, b=20),
    )

    return fig


def render_hypothesis_table(hypotheses):
    """Render hypotheses as a table."""
    if not hypotheses:
        return pd.DataFrame()

    rows = []
    for h in hypotheses:
        rows.append({
            "ID": h.get("hypothesis_id", "")[:16] + "...",
            "Type": h.get("hypothesis_type", ""),
            "Subject": h.get("subject", {}).get("name", "")[:30],
            "Object": h.get("object", {}).get("name", "")[:30],
            "Confidence": f"{h.get('confidence', 0):.3f}",
            "Status": h.get("status", "validated"),
        })

    return pd.DataFrame(rows)


st.title("🔬 Discovery Dashboard")
st.markdown("AI-generated hypotheses from the knowledge graph discovery pipeline.")

# Load data
run_data = load_latest_discovery_run()

if run_data is None:
    st.warning("No discovery runs found. Run the discovery pipeline first:")
    st.code("python scripts/run_discovery.py", language="bash")
    st.stop()

# Header metrics
col1, col2, col3, col4 = st.columns(4)

funnel = run_data.get("funnel", {})
metrics = run_data.get("metrics", {})

with col1:
    st.metric("Gaps Found", funnel.get("gaps_found", 0))
with col2:
    st.metric("Hypotheses", funnel.get("hypotheses_generated", 0))
with col3:
    st.metric("Validated", funnel.get("validated", 0))
with col4:
    st.metric("Validation Rate", f"{metrics.get('validation_rate', 0):.1%}")

st.markdown("---")

# Main content
tab1, tab2, tab3 = st.tabs(["📊 Overview", "🔍 Hypotheses", "✅ Curation"])

with tab1:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Discovery Funnel")
        fig = render_funnel_chart(run_data)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Run Details")
        st.markdown(f"**Run ID:** `{run_data.get('run_id', 'N/A')}`")
        st.markdown(f"**Timestamp:** {run_data.get('timestamp', 'N/A')}")
        st.markdown(f"**KG Version:** {run_data.get('kg_version', 'N/A')}")

        st.markdown("---")
        st.markdown("**Metrics:**")
        st.json(metrics)

    # Hypothesis types breakdown
    st.subheader("Hypotheses by Type")
    validated = run_data.get("validated_hypotheses", [])
    if validated:
        type_counts = {}
        for h in validated:
            t = h.get("hypothesis_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        fig = px.pie(
            values=list(type_counts.values()),
            names=list(type_counts.keys()),
            title="Validated Hypotheses by Type"
        )
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Validated Hypotheses")

    validated = run_data.get("validated_hypotheses", [])

    if not validated:
        st.info("No validated hypotheses in this run.")
    else:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            type_filter = st.multiselect(
                "Filter by type",
                options=list(set(h.get("hypothesis_type", "") for h in validated)),
                default=None
            )
        with col2:
            min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)

        # Apply filters
        filtered = validated
        if type_filter:
            filtered = [h for h in filtered if h.get("hypothesis_type") in type_filter]
        filtered = [h for h in filtered if h.get("confidence", 0) >= min_conf]

        st.markdown(f"Showing **{len(filtered)}** of {len(validated)} hypotheses")

        # Display as table
        df = render_hypothesis_table(filtered)
        if not df.empty:
            st.dataframe(df, use_container_width=True)

        # Detail view
        st.markdown("---")
        st.subheader("Hypothesis Details")

        if filtered:
            hyp_options = {
                f"{h.get('subject', {}).get('name', '')} → {h.get('hypothesis_type', '')} → {h.get('object', {}).get('name', '')}": i
                for i, h in enumerate(filtered)
            }

            selected_label = st.selectbox("Select hypothesis", list(hyp_options.keys()))
            selected_idx = hyp_options[selected_label]
            selected_hyp = filtered[selected_idx]

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Subject:**")
                st.json(selected_hyp.get("subject", {}))

                st.markdown("**Object:**")
                st.json(selected_hyp.get("object", {}))

            with col2:
                st.markdown("**Hypothesis Type:**")
                st.code(selected_hyp.get("hypothesis_type", ""))

                st.markdown("**Confidence:**")
                st.progress(selected_hyp.get("confidence", 0))
                st.caption(f"{selected_hyp.get('confidence', 0):.3f}")

                st.markdown("**Explanation:**")
                st.info(selected_hyp.get("explanation", "N/A"))

            st.markdown("**Evidence:**")
            st.json(selected_hyp.get("evidence", {}))

with tab3:
    st.subheader("Hypothesis Curation")
    st.markdown("Review and approve/reject hypotheses for integration into the knowledge graph.")

    validated = run_data.get("validated_hypotheses", [])
    ready = run_data.get("ready_for_curation", [])

    if not validated:
        st.info("No hypotheses to curate.")
    else:
        # Initialize session state for curation decisions
        if "curation_decisions" not in st.session_state:
            st.session_state.curation_decisions = {}

        # Stats
        approved = sum(1 for d in st.session_state.curation_decisions.values() if d == "approved")
        rejected = sum(1 for d in st.session_state.curation_decisions.values() if d == "rejected")
        pending = len(validated) - len(st.session_state.curation_decisions)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Approved", approved, delta=None)
        with col2:
            st.metric("Rejected", rejected, delta=None)
        with col3:
            st.metric("Pending", pending, delta=None)

        st.markdown("---")

        # Curation interface
        for i, hyp in enumerate(validated):
            hyp_id = hyp.get("hypothesis_id", f"hyp-{i}")
            current_decision = st.session_state.curation_decisions.get(hyp_id)

            # Show decision status
            if current_decision == "approved":
                status_icon = "✅"
            elif current_decision == "rejected":
                status_icon = "❌"
            else:
                status_icon = "⏳"

            with st.expander(
                f"{status_icon} {hyp.get('subject', {}).get('name', '?')} → "
                f"{hyp.get('hypothesis_type', '?')} → "
                f"{hyp.get('object', {}).get('name', '?')} "
                f"(conf: {hyp.get('confidence', 0):.2f})"
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"**Explanation:** {hyp.get('explanation', 'N/A')}")

                    evidence = hyp.get("evidence", {})
                    if evidence:
                        st.markdown("**Evidence:**")
                        for k, v in list(evidence.items())[:5]:
                            st.caption(f"• {k}: {v}")

                with col2:
                    st.markdown("**Decision:**")

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("✅ Approve", key=f"approve_{hyp_id}"):
                            st.session_state.curation_decisions[hyp_id] = "approved"
                            st.rerun()
                    with btn_col2:
                        if st.button("❌ Reject", key=f"reject_{hyp_id}"):
                            st.session_state.curation_decisions[hyp_id] = "rejected"
                            st.rerun()

                    if current_decision:
                        st.success(f"Decision: {current_decision.upper()}")

        # Export decisions
        st.markdown("---")
        if st.session_state.curation_decisions:
            st.subheader("Export Curation Decisions")

            decisions_json = json.dumps({
                "timestamp": datetime.now().isoformat(),
                "run_id": run_data.get("run_id"),
                "decisions": st.session_state.curation_decisions,
            }, indent=2)

            st.download_button(
                label="Download Decisions (JSON)",
                data=decisions_json,
                file_name=f"curation_decisions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

            if st.button("Clear All Decisions"):
                st.session_state.curation_decisions = {}
                st.rerun()

# Footer
st.markdown("---")
st.caption(
    "Discovery pipeline implements the multi-agent architecture from the "
    "[Practical Pilot Plan](https://github.com/agents4science/battery-electrolyte-kg) "
    "for agentic AI-driven KG discovery."
)
