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
    "Filter by category",
    ["solvent", "salt", "molecule", "interphase"],
    default=["solvent", "salt", "molecule", "interphase"],
    help="All items are molecules; these categories help filter by function"
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

# Create ID mapping to avoid agraph treating names as file paths
id_to_display = {}
display_to_id = {}

for mol in filtered_molecules:
    # Use a safe node ID format (prefix with 'n_' to avoid path interpretation)
    safe_id = f"n_{hash(mol['id']) % 100000}"
    id_to_display[mol["id"]] = safe_id
    display_to_id[safe_id] = mol["id"]

    # Note: Don't use 'title' as it causes double-click navigation errors
    nodes.append(Node(
        id=safe_id,
        label=mol["name"] if mol.get("name") else mol["id"],
        size=25,
        color=colors.get(mol["type"], "#888888"),
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
            source=id_to_display[rel["source"]],
            target=id_to_display[rel["target"]],
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
        "highlightStrokeColor": "#F7A7A6",
    },
    link={
        "labelProperty": "label",
        "renderLabel": True,
    },
    # Use staticGraphWithDragAndDrop to prevent double-click navigation issues
    staticGraph=False,
    staticGraphWithDragAndDrop=True,
)

# Main layout
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("Graph Visualization")
    st.caption("Single-click a node to select it. Drag nodes to rearrange. Use the dropdown on the right to explore relationships.")

    if nodes:
        return_value = agraph(nodes=nodes, edges=edges, config=config)

        # Handle node selection from graph click (map back from safe ID)
        if return_value and return_value in display_to_id:
            st.session_state['selected_node'] = display_to_id[return_value]
    else:
        st.info("No molecules match the current filters.")

    st.markdown(f"""
    **Showing {len(filtered_molecules)} molecules, {len(relations)} relations**

    **Legend:**
    🔵 Solvent | 🟢 Salt | 🟣 Molecule | 🟠 Interphase
    """, unsafe_allow_html=True)

with col2:
    # Show selected node info prominently
    st.subheader("📋 Node Details")

    selected_node_id = st.session_state.get('selected_node')
    selected_mol_data = None

    if selected_node_id:
        selected_mol_data = next((m for m in molecules if m["id"] == selected_node_id), None)

    if selected_mol_data:
        st.markdown(f"### {selected_mol_data['name']}")
        st.markdown(f"**Type:** {selected_mol_data['type'].title()}")
        if selected_mol_data.get('smiles'):
            st.code(selected_mol_data['smiles'], language=None)

        # Show curated properties if available
        props = load_curated_properties()
        solvent_props = next(
            (s for s in props.get("solvents", [])
             if s.get("abbreviation") == selected_mol_data.get("name") or
                s.get("name") == selected_mol_data.get("name")),
            None
        )
        salt_props = next(
            (s for s in props.get("salts", [])
             if s.get("abbreviation") == selected_mol_data.get("name") or
                s.get("name") == selected_mol_data.get("name")),
            None
        )

        entity_props = solvent_props or salt_props
        if entity_props:
            st.markdown("**Properties:**")
            prop_data = entity_props.get("properties", {})
            for prop_name, prop_val in prop_data.items():
                if isinstance(prop_val, dict) and "value" in prop_val:
                    unit = prop_val.get("unit", "")
                    st.markdown(f"- {prop_name}: {prop_val['value']} {unit}")

        # Show connections with explanations
        st.markdown("---")
        st.markdown("**Relationships** (click to see explanation):")
        node_relations = []
        for rel in relations:
            if rel["source"] == selected_node_id:
                target_mol = next((m for m in molecules if m["id"] == rel["target"]), None)
                target_name = target_mol["name"] if target_mol else rel["target"][:12]
                node_relations.append({
                    "label": f"→ **{rel['type']}** → {target_name}",
                    "type": rel["type"],
                    "other": target_name
                })
            elif rel["target"] == selected_node_id:
                source_mol = next((m for m in molecules if m["id"] == rel["source"]), None)
                source_name = source_mol["name"] if source_mol else rel["source"][:12]
                node_relations.append({
                    "label": f"← **{rel['type']}** ← {source_name}",
                    "type": rel["type"],
                    "other": source_name
                })

        if node_relations:
            for r in node_relations[:10]:
                with st.expander(r["label"]):
                    explanation = RELATION_EXPLANATIONS.get(r["type"], {})
                    if explanation:
                        st.markdown(f"**Method:** {explanation.get('method', 'Unknown')}")
                        st.markdown(explanation.get('description', ''))
                        st.caption(f"Basis: {explanation.get('basis', 'N/A')}")
                    else:
                        st.caption("No detailed explanation available")
            if len(node_relations) > 10:
                st.caption(f"...and {len(node_relations) - 10} more relationships")
        else:
            st.caption("No relationships in current view")
    else:
        st.info("Click a node in the graph to see its details")

    # Relationship explainer in expander
    with st.expander("🔍 Explain a Relationship"):
        rel_options = []
        for rel in relations:
            if rel["source"] in visible_ids and rel["target"] in visible_ids:
                source_mol = next((m for m in molecules if m["id"] == rel["source"]), None)
                target_mol = next((m for m in molecules if m["id"] == rel["target"]), None)
                source_name = source_mol["name"] if source_mol else rel["source"][:12]
                target_name = target_mol["name"] if target_mol else rel["target"][:12]
                label = f"{source_name} ↔ {target_name} ({rel['type']})"
                rel_options.append((label, rel))

        if rel_options:
            selected_label = st.selectbox(
                "Select relationship",
                [r[0] for r in rel_options],
                index=0
            )

            selected_rel = next((r[1] for r in rel_options if r[0] == selected_label), None)

            if selected_rel:
                rel_type = selected_rel["type"]
                explanation = RELATION_EXPLANATIONS.get(rel_type, {})

                if explanation:
                    st.info(f"**Method:** {explanation.get('method', 'Unknown')}")
                    st.markdown(explanation.get('description', ''))
                    st.caption(f"**Basis:** {explanation.get('basis', 'N/A')}")
        else:
            st.caption("No relationships in current view")

# Molecule details section
st.divider()
col1, col2 = st.columns(2)

with col1:
    st.subheader("Molecule Details")

    # Build options with display names
    mol_options = [(m["id"], m.get("name", m["id"])) for m in filtered_molecules]
    mol_id_to_name = {m[0]: m[1] for m in mol_options}
    mol_ids = [m[0] for m in mol_options]

    if mol_ids:
        # Use clicked node if available
        default_idx = 0
        if 'selected_node' in st.session_state and st.session_state['selected_node'] in mol_ids:
            default_idx = mol_ids.index(st.session_state['selected_node'])

        selected_mol = st.selectbox(
            "Select molecule",
            mol_ids,
            index=default_idx,
            format_func=lambda x: mol_id_to_name.get(x, x),
            key="mol_select"
        )

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

    if mol_ids and selected_mol:
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
