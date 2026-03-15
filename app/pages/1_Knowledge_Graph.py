"""
Knowledge Graph Explorer Page

Interactive visualization of the electrolyte knowledge graph.
Click on nodes or select relationships to see provenance.
"""

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config
from pathlib import Path
import json
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import (
    get_molecules_for_graph,
    get_relations_for_graph,
    load_curated_properties,
    COMPOUND_NAMES,
    COMPOUND_SMILES,
)

st.set_page_config(page_title="KG Explorer", page_icon="🔗", layout="wide")

PROJECT_ROOT = Path(__file__).parent.parent.parent


@st.cache_data
def load_kg_provenance():
    """Load provenance data from KG."""
    kg_path = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v3.json"
    if kg_path.exists():
        with open(kg_path) as f:
            kg = json.load(f)
        return {
            "sources": kg.get("sources", {}),
            "provenance": kg.get("provenance", {}),
            "molecules": kg.get("molecules", {}),
            "solvents": kg.get("solvents", {}),
            "salts": kg.get("salts", {}),
        }
    return None


# Relation explanations
RELATION_EXPLANATIONS = {
    "usedWith": {
        "method": "Dataset Co-occurrence",
        "description": "These components appear together in electrolyte formulations in the source datasets.",
        "basis": "Direct observation from CALiSol-23 and HI Münster datasets",
    },
    "coOccursWith": {
        "method": "Association Rule Mining",
        "description": "These solvents frequently appear together in high-performance electrolyte formulations.",
        "basis": "Statistical analysis: co-occurrence frequency > 50% in formulations",
    },
    "sameAs": {
        "method": "SMILES Matching",
        "description": "These entities represent the same molecule in different datasets, linked by identical SMILES strings.",
        "basis": "Exact structural match via canonical SMILES comparison",
    },
    "decomposesTo": {
        "method": "Literature Knowledge",
        "description": "Electrochemical decomposition pathway from electrolyte chemistry literature.",
        "basis": "Published reaction mechanisms for SEI formation",
    },
    "increases": {
        "method": "Correlation Analysis",
        "description": "This component is correlated with increased values of the target property.",
        "basis": "Pearson correlation coefficient from cross-property analysis",
    },
    "decreases": {
        "method": "Correlation Analysis",
        "description": "This component is correlated with decreased values of the target property.",
        "basis": "Pearson correlation coefficient from cross-property analysis",
    },
}


st.title("🔗 Knowledge Graph Explorer")
st.markdown("Explore molecules, salts, and their relationships. **Click on a relationship to see its provenance.**")

# Sidebar filters
st.sidebar.header("Filters")

entity_types = st.sidebar.multiselect(
    "Entity Types",
    ["solvent", "salt", "molecule", "interphase"],
    default=["solvent", "salt"]
)

search_query = st.sidebar.text_input(
    "Search molecules",
    placeholder="e.g., carbonate, lithium, EC"
)

max_nodes = st.sidebar.slider(
    "Max nodes to display",
    min_value=10,
    max_value=200,
    value=50,
    step=10,
    help="Limit nodes for performance. Use search to find specific molecules."
)

st.sidebar.markdown("---")
st.sidebar.caption(f"KG contains 23,421 molecules total. Use search and filters to explore.")

# Get data from actual KG
molecules = get_molecules_for_graph(
    search_query=search_query,
    entity_types=entity_types,
    max_nodes=max_nodes
)
kg_data = load_kg_provenance()

# Get relations for the displayed molecules
molecule_ids = {m["id"] for m in molecules}
relations = get_relations_for_graph(molecule_ids=molecule_ids)

filtered_molecules = molecules  # Already filtered by get_molecules_for_graph

# Build graph
nodes = []
edges = []

colors = {
    "solvent": "#4A90D9",   # Blue
    "salt": "#50C878",       # Green
    "molecule": "#9B59B6",   # Purple
    "interphase": "#E67E22", # Orange
}

for mol in filtered_molecules:
    nodes.append(Node(
        id=mol["id"],
        label=mol["id"],
        size=25,
        color=colors.get(mol["type"], "#888888"),
        title=f"{mol['name']} | {mol['smiles']}",
        symbolType="circle",
    ))

visible_ids = {m["id"] for m in filtered_molecules}

# Build edges with IDs for selection
edge_lookup = {}
for rel in relations:
    if rel["source"] in visible_ids and rel["target"] in visible_ids:
        edge_id = f"{rel['source']}--{rel['type']}--{rel['target']}"
        edge_color = "#FF6B6B" if rel["type"] == "usedWith" else "#888888"
        edges.append(Edge(
            source=rel["source"],
            target=rel["target"],
            label=rel["type"],
            color=edge_color,
        ))
        edge_lookup[edge_id] = rel

config = Config(
    width=800,
    height=450,
    directed=False,
    physics=True,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#F7A7A6",
    collapsible=False,
    node={
        "labelProperty": "label",
        "renderLabel": True,
    },
    link={
        "labelProperty": "label",
        "renderLabel": True,
    },
    # Disable navigation on double-click
    staticGraph=False,
    staticGraphWithDragAndDrop=False,
)

# Main layout
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("Graph Visualization")
    st.caption("Click a node to select it. Use the dropdown on the right to explore relationships.")

    if nodes:
        return_value = agraph(nodes=nodes, edges=edges, config=config)

        # Handle node selection from graph click
        if return_value:
            st.session_state['selected_node'] = return_value
    else:
        st.info("No molecules match the current filters.")

    st.markdown(f"""
    **Showing {len(filtered_molecules)} molecules, {len(relations)} relations**

    **Legend:**
    🔵 Solvent | 🟢 Salt | 🟣 Molecule | 🟠 Interphase
    """, unsafe_allow_html=True)

with col2:
    # Relationship selector
    st.subheader("🔍 Explain Relationship")

    # Build list of relationships for dropdown
    rel_options = []
    for rel in relations:
        if rel["source"] in visible_ids and rel["target"] in visible_ids:
            label = f"{rel['source']} ↔ {rel['target']} ({rel['type']})"
            rel_options.append((label, rel))

    if rel_options:
        selected_label = st.selectbox(
            "Select a relationship to explain",
            [r[0] for r in rel_options],
            index=0
        )

        # Find the selected relation
        selected_rel = next((r[1] for r in rel_options if r[0] == selected_label), None)

        if selected_rel:
            rel_type = selected_rel["type"]
            source = selected_rel["source"]
            target = selected_rel["target"]

            # Show relationship details
            st.markdown(f"### {source} ↔ {target}")
            st.markdown(f"**Relation:** `{rel_type}`")

            # Get explanation
            explanation = RELATION_EXPLANATIONS.get(rel_type, {})

            if explanation:
                st.info(f"**Method:** {explanation.get('method', 'Unknown')}")
                st.markdown(explanation.get('description', ''))
                st.caption(f"**Basis:** {explanation.get('basis', 'N/A')}")

            # Show SMILES for both entities
            st.markdown("---")
            st.markdown("**Entities:**")

            source_mol = next((m for m in molecules if m["id"] == source), None)
            target_mol = next((m for m in molecules if m["id"] == target), None)

            if source_mol:
                st.markdown(f"**{source}** ({source_mol['type']})")
                st.code(source_mol['smiles'], language=None)

            if target_mol:
                st.markdown(f"**{target}** ({target_mol['type']})")
                st.code(target_mol['smiles'], language=None)

            # For sameAs, highlight the matching SMILES
            if rel_type == "sameAs" and source_mol and target_mol:
                if source_mol['smiles'] == target_mol['smiles']:
                    st.success("✓ SMILES match confirmed - these are the same molecule")

            # Show data sources
            if rel_type == "usedWith":
                st.markdown("---")
                st.markdown("**Data Sources:**")
                st.markdown("- [CALiSol-23](https://doi.org/10.1038/s41597-024-03575-8)")
                st.markdown("- [HI Münster Dataset](https://doi.org/10.1038/s41597-023-01936-3)")

            elif rel_type == "coOccursWith":
                st.markdown("---")
                st.markdown("**Data Sources:**")
                st.markdown("- Association rule mining on 6,134 formulations")
                st.markdown("- Minimum support: 3 occurrences")
                st.markdown("- Minimum confidence: 50%")

    else:
        st.info("No relationships visible with current filters")

# Molecule details section
st.divider()
col1, col2 = st.columns(2)

with col1:
    st.subheader("Molecule Details")

    mol_options = [m["id"] for m in filtered_molecules]
    if mol_options:
        # Use clicked node if available
        default_idx = 0
        if 'selected_node' in st.session_state and st.session_state['selected_node'] in mol_options:
            default_idx = mol_options.index(st.session_state['selected_node'])

        selected_mol = st.selectbox("Select molecule", mol_options, index=default_idx, key="mol_select")

        if selected_mol:
            mol_data = next((m for m in molecules if m["id"] == selected_mol), None)
            if mol_data:
                st.markdown(f"**Name:** {mol_data['name']}")
                st.markdown(f"**Type:** {mol_data['type'].title()}")
                st.code(mol_data['smiles'], language=None)

                props = load_curated_properties()
                solvent_props = next(
                    (s for s in props.get("solvents", [])
                     if s.get("abbreviation") == selected_mol),
                    None
                )

                if solvent_props:
                    st.markdown("**Properties:**")
                    prop_data = solvent_props.get("properties", {})

                    props_col1, props_col2 = st.columns(2)
                    with props_col1:
                        if "homo_energy" in prop_data:
                            st.metric("HOMO", f"{prop_data['homo_energy']['value']:.2f} eV")
                        if "dielectric_constant" in prop_data:
                            st.metric("ε", f"{prop_data['dielectric_constant']['value']:.1f}")
                    with props_col2:
                        if "lumo_energy" in prop_data:
                            st.metric("LUMO", f"{prop_data['lumo_energy']['value']:.2f} eV")
                        if "ionization_energy" in prop_data:
                            st.metric("IE", f"{prop_data['ionization_energy']['value']:.2f} eV")

with col2:
    st.subheader("Connections")

    if mol_options and selected_mol:
        related = []
        for rel in relations:
            if rel["source"] == selected_mol:
                related.append({"entity": rel["target"], "relation": rel["type"], "direction": "→"})
            elif rel["target"] == selected_mol:
                related.append({"entity": rel["source"], "relation": rel["type"], "direction": "←"})

        if related:
            for r in related[:10]:
                with st.expander(f"{r['direction']} {r['entity']} ({r['relation']})"):
                    exp = RELATION_EXPLANATIONS.get(r['relation'], {})
                    st.markdown(f"**Why this link exists:**")
                    st.markdown(exp.get('description', 'No explanation available'))
                    st.caption(f"Method: {exp.get('method', 'Unknown')}")
        else:
            st.caption("No connections found")
