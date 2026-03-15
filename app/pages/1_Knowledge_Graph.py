"""
Knowledge Graph Explorer Page

Interactive visualization of the electrolyte knowledge graph.
"""

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config
from pathlib import Path
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

st.title("🔗 Knowledge Graph Explorer")
st.markdown("Explore molecules, salts, and their relationships in the electrolyte knowledge graph.")

# Sidebar filters
st.sidebar.header("Filters")

# Entity type filter
entity_types = st.sidebar.multiselect(
    "Entity Types",
    ["solvent", "salt"],
    default=["solvent", "salt"]
)

# Search box
search_query = st.sidebar.text_input("Search molecules", placeholder="e.g., EC, LiPF6")

# Get data
molecules = get_molecules_for_graph()
relations = get_relations_for_graph()

# Filter molecules
filtered_molecules = [
    m for m in molecules
    if m["type"] in entity_types
    and (not search_query or search_query.upper() in m["id"].upper() or
         search_query.lower() in m["name"].lower())
]

# Build graph
nodes = []
edges = []

# Color scheme
colors = {
    "solvent": "#4A90D9",  # Blue
    "salt": "#50C878",     # Green
}

for mol in filtered_molecules:
    nodes.append(Node(
        id=mol["id"],
        label=mol["id"],
        size=25,
        color=colors.get(mol["type"], "#888888"),
        title=f"{mol['name']}\n{mol['smiles']}",
    ))

# Get IDs of visible nodes
visible_ids = {m["id"] for m in filtered_molecules}

# Add edges for visible nodes
for rel in relations:
    if rel["source"] in visible_ids and rel["target"] in visible_ids:
        edge_color = "#FF6B6B" if rel["type"] == "usedWith" else "#888888"
        edges.append(Edge(
            source=rel["source"],
            target=rel["target"],
            label=rel["type"],
            color=edge_color,
        ))

# Graph configuration
config = Config(
    width=900,
    height=500,
    directed=False,
    physics=True,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#F7A7A6",
    collapsible=False,
    node={"labelProperty": "label"},
    link={"labelProperty": "label", "renderLabel": True},
)

# Display graph
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Graph Visualization")

    if nodes:
        selected = agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("No molecules match the current filters.")

    # Legend
    st.markdown("""
    **Legend:**
    🔵 Solvent | 🟢 Salt |
    <span style="color: #FF6B6B">—</span> usedWith |
    <span style="color: #888888">—</span> coOccursWith
    """, unsafe_allow_html=True)

with col2:
    st.subheader("Molecule Details")

    # Selection dropdown
    mol_options = [m["id"] for m in filtered_molecules]
    if mol_options:
        selected_mol = st.selectbox("Select molecule", mol_options)

        if selected_mol:
            mol_data = next((m for m in molecules if m["id"] == selected_mol), None)
            if mol_data:
                st.markdown(f"**Name:** {mol_data['name']}")
                st.markdown(f"**Type:** {mol_data['type'].title()}")
                st.code(mol_data['smiles'], language=None)

                # Load properties if available
                props = load_curated_properties()
                solvent_props = next(
                    (s for s in props.get("solvents", [])
                     if s.get("abbreviation") == selected_mol),
                    None
                )

                if solvent_props:
                    st.subheader("Properties")
                    prop_data = solvent_props.get("properties", {})

                    if "homo_energy" in prop_data:
                        st.metric("HOMO Energy",
                                  f"{prop_data['homo_energy']['value']:.2f} eV")
                    if "lumo_energy" in prop_data:
                        st.metric("LUMO Energy",
                                  f"{prop_data['lumo_energy']['value']:.2f} eV")
                    if "dielectric_constant" in prop_data:
                        st.metric("Dielectric Constant",
                                  f"{prop_data['dielectric_constant']['value']:.1f}")
                    if "ionization_energy" in prop_data:
                        st.metric("Ionization Energy",
                                  f"{prop_data['ionization_energy']['value']:.2f} eV")

                # Show related molecules
                st.subheader("Related Molecules")
                related = []
                for rel in relations:
                    if rel["source"] == selected_mol:
                        related.append(f"{rel['target']} ({rel['type']})")
                    elif rel["target"] == selected_mol:
                        related.append(f"{rel['source']} ({rel['type']})")

                if related:
                    for r in related[:10]:
                        st.markdown(f"- {r}")
                else:
                    st.caption("No direct relations found")

# Schema diagram
st.divider()
st.subheader("Entity Schema")

PROJECT_ROOT = Path(__file__).parent.parent.parent
schema_path = PROJECT_ROOT / "data" / "output" / "figures" / "kg_schema_v2.png"
if schema_path.exists():
    st.image(str(schema_path), use_container_width=True)
else:
    st.info("Schema diagram not available")
