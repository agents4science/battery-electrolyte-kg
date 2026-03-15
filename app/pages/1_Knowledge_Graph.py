"""
Knowledge Graph Explorer Page

Interactive visualization of the electrolyte knowledge graph.
Click on nodes to see details and relationships.
"""

import streamlit as st
import plotly.graph_objects as go
import networkx as nx
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import (
    get_molecules_for_graph,
    get_relations_for_graph,
    get_relations_for_molecule,
    get_measurements_for_molecule,
    get_provenance_for_molecule,
    load_curated_properties,
    COMPOUND_NAMES,
    COMPOUND_SMILES,
)

st.set_page_config(page_title="KG Explorer", page_icon="🔗", layout="wide")

PROJECT_ROOT = Path(__file__).parent.parent.parent


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
st.markdown("Explore molecules, salts, and their relationships.")

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

show_neighbors = st.sidebar.checkbox(
    "Show connected molecules",
    value=True,
    help="When searching, also show molecules connected to the search results"
)

st.sidebar.markdown("---")
st.sidebar.caption("KG contains 23,421 molecules total. Use search and filters to explore.")

# Get data
molecules = get_molecules_for_graph(
    search_query=search_query,
    entity_types=entity_types,
    max_nodes=max_nodes
)

molecule_ids = {m["id"] for m in molecules}

# If searching and show_neighbors is enabled, expand to include connected molecules
if search_query and show_neighbors and len(molecules) > 0:
    from utils.data_loader import get_relations_for_molecule, get_all_molecules_from_kg, COMPOUND_NAMES, COMPOUND_SMILES

    # Get neighbors for each searched molecule
    neighbor_ids = set()
    for mol in molecules:
        mol_relations = get_relations_for_molecule(mol["id"], mol.get("name"))
        for rel in mol_relations:
            neighbor_ids.add(rel["other_id"])

    # Load neighbor molecule data
    all_mols = get_all_molecules_from_kg()
    mol_by_id = {m["id"]: m for m in all_mols}

    # Also check hardcoded compounds
    for abbrev, smiles in COMPOUND_SMILES.items():
        if abbrev not in mol_by_id:
            mol_by_id[abbrev] = {
                "id": abbrev,
                "name": COMPOUND_NAMES.get(abbrev, abbrev),
                "smiles": smiles,
                "type": "salt" if abbrev.startswith(("Li", "Na")) else "solvent"
            }

    # Add neighbors to molecules list (up to max_nodes total)
    existing_ids = {m["id"] for m in molecules}
    for nid in neighbor_ids:
        if len(molecules) >= max_nodes:
            break
        if nid not in existing_ids:
            if nid in mol_by_id:
                molecules.append(mol_by_id[nid])
                existing_ids.add(nid)

    molecule_ids = {m["id"] for m in molecules}

relations = get_relations_for_graph(molecule_ids=molecule_ids)
filtered_molecules = molecules

# Create name lookup
mol_name_lookup = {m["id"]: m.get("name", m["id"][:12]) for m in molecules}
mol_type_lookup = {m["id"]: m.get("type", "molecule") for m in molecules}

# Colors by type
colors = {
    "solvent": "#4A90D9",   # Blue
    "salt": "#50C878",      # Green
    "molecule": "#9B59B6",  # Purple
    "interphase": "#E67E22", # Orange
}

# Build networkx graph for layout
G = nx.Graph()
for mol in filtered_molecules:
    G.add_node(mol["id"], name=mol.get("name", mol["id"]), type=mol.get("type", "molecule"))

for rel in relations:
    if rel["source"] in molecule_ids and rel["target"] in molecule_ids:
        G.add_edge(rel["source"], rel["target"], relation=rel["type"])

# Get layout
if len(G.nodes()) > 0:
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
else:
    pos = {}

# Build Plotly figure
edge_x = []
edge_y = []
edge_mid_x = []
edge_mid_y = []
edge_labels = []
edge_info = []  # Store edge data for click handling

for edge in G.edges(data=True):
    src, tgt, data = edge
    x0, y0 = pos[src]
    x1, y1 = pos[tgt]
    edge_x.extend([x0, x1, None])
    edge_y.extend([y0, y1, None])

    # Midpoint for label and click target
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    edge_mid_x.append(mid_x)
    edge_mid_y.append(mid_y)
    edge_labels.append(data.get('relation', ''))
    edge_info.append({
        'source': src,
        'target': tgt,
        'type': data.get('relation', ''),
        'source_name': mol_name_lookup.get(src, src[:12]),
        'target_name': mol_name_lookup.get(tgt, tgt[:12])
    })

# Edge lines
edge_trace = go.Scatter(
    x=edge_x, y=edge_y,
    line=dict(width=1.5, color='#888'),
    hoverinfo='none',
    mode='lines'
)

# Edge labels (clickable)
edge_label_trace = go.Scatter(
    x=edge_mid_x, y=edge_mid_y,
    mode='markers+text',
    text=edge_labels,
    textposition="middle center",
    textfont=dict(size=8, color='#555'),
    hoverinfo='text',
    hovertext=[f"{e['source_name']} ↔ {e['target_name']}\n({e['type']})" for e in edge_info],
    marker=dict(size=15, color='rgba(255,255,255,0.8)', symbol='square'),
    customdata=[f"edge:{i}" for i in range(len(edge_info))],
)

node_x = []
node_y = []
node_text = []
node_colors = []
node_ids = []

for node in G.nodes():
    x, y = pos[node]
    node_x.append(x)
    node_y.append(y)
    node_text.append(mol_name_lookup.get(node, node[:12]))
    node_type = mol_type_lookup.get(node, "molecule")
    node_colors.append(colors.get(node_type, "#888888"))
    node_ids.append(node)

node_trace = go.Scatter(
    x=node_x, y=node_y,
    mode='markers+text',
    hoverinfo='text',
    hovertext=node_text,
    text=node_text,
    textposition="top center",
    textfont=dict(size=10),
    marker=dict(
        size=25,
        color=node_colors,
        line=dict(width=2, color='white')
    ),
    customdata=[f"node:{nid}" for nid in node_ids],
)

fig = go.Figure(data=[edge_trace, edge_label_trace, node_trace],
                layout=go.Layout(
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=20, l=5, r=5, t=40),
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    height=500,
                    clickmode='event+select',
                ))

# Main layout
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("Graph Visualization")

    if len(G.nodes()) > 0:
        # Display the graph (hover to see names, use dropdown to select)
        st.plotly_chart(fig, key="kg_graph")
    else:
        st.info("No molecules match the current filters.")

    st.markdown(f"""
    **Showing {len(filtered_molecules)} molecules, {len(relations)} relations**

    **Legend:** 🔵 Solvent | 🟢 Salt | 🟣 Molecule | 🟠 Interphase

    *Hover over nodes to see names. Use the dropdown on the right to view details.*
    """)

with col2:
    # Molecule selector - always show this
    st.subheader("📋 Node Details")

    mol_options = [(m["id"], m.get("name", m["id"])) for m in filtered_molecules]
    mol_ids = [m[0] for m in mol_options]
    mol_id_to_name = {m[0]: m[1] for m in mol_options}

    if mol_ids:
        # Get default from session state (graph click) or use first
        selected_node_id = st.session_state.get('selected_node')
        default_idx = 0
        if selected_node_id and selected_node_id in mol_ids:
            default_idx = mol_ids.index(selected_node_id)

        selected_mol_id = st.selectbox(
            "Select molecule",
            mol_ids,
            index=default_idx,
            format_func=lambda x: mol_id_to_name.get(x, x),
            key="mol_select"
        )

        selected_mol_data = next((m for m in molecules if m["id"] == selected_mol_id), None)

        if selected_mol_data:
            st.markdown(f"### {selected_mol_data['name']}")
            st.markdown(f"**Type:** {selected_mol_data['type'].title()}")
            if selected_mol_data.get('smiles'):
                st.code(selected_mol_data['smiles'], language=None)

            # Show curated properties
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
                st.markdown("**Curated Properties:**")
                prop_data = entity_props.get("properties", {})
                for prop_name, prop_val in prop_data.items():
                    if isinstance(prop_val, dict) and "value" in prop_val:
                        unit = prop_val.get("unit", "")
                        st.markdown(f"- {prop_name}: {prop_val['value']} {unit}")

            # Show KG measurements (from datasets)
            measurements = get_measurements_for_molecule(selected_mol_id)
            if measurements:
                with st.expander(f"**Dataset Measurements** ({len(measurements)} values)"):
                    # Group by property type
                    by_prop = {}
                    for m in measurements:
                        prop = m["property"]
                        if prop not in by_prop:
                            by_prop[prop] = []
                        by_prop[prop].append(m)

                    for prop, mlist in by_prop.items():
                        values = [f"{m['value']} {m['unit']}" for m in mlist if m['value'] is not None]
                        if values:
                            st.markdown(f"**{prop.replace('_', ' ').title()}:** {', '.join(values[:5])}")
                            if len(values) > 5:
                                st.caption(f"...and {len(values) - 5} more")

            # Show ALL relationships from full KG (not just visible ones)
            st.markdown("---")
            st.markdown("**All Connections in KG:**")

            # Get all relations for this molecule from the full KG
            # Pass both ID and name to handle both KG data and hardcoded compounds
            all_mol_relations = get_relations_for_molecule(
                selected_mol_id,
                molecule_name=selected_mol_data.get('name')
            )

            if all_mol_relations:
                # Group by relation type
                by_type = {}
                for rel in all_mol_relations:
                    rel_type = rel["type"]
                    if rel_type not in by_type:
                        by_type[rel_type] = []
                    by_type[rel_type].append(rel)

                for rel_type, rels in by_type.items():
                    explanation = RELATION_EXPLANATIONS.get(rel_type, {})
                    with st.expander(f"**{rel_type}** ({len(rels)} connections)"):
                        if explanation:
                            st.caption(f"Method: {explanation.get('method', 'Unknown')}")
                            st.markdown(explanation.get('description', ''))

                        st.markdown("**Connected to:**")
                        for rel in rels[:15]:
                            arrow = "→" if rel["direction"] == "outgoing" else "←"
                            st.markdown(f"- {arrow} {rel['other_name']} ({rel['other_type']})")
                        if len(rels) > 15:
                            st.caption(f"...and {len(rels) - 15} more")

                st.caption(f"Total: {len(all_mol_relations)} connections")
            else:
                st.caption("No connections found in knowledge graph")

            # Show provenance information
            st.markdown("---")
            st.markdown("**Data Sources:**")

            provenance = get_provenance_for_molecule(selected_mol_id)
            if provenance:
                # Group by source
                by_source = {}
                for p in provenance:
                    src_name = p["source_name"]
                    if src_name not in by_source:
                        by_source[src_name] = {
                            "doi": p["source_doi"],
                            "rows": [],
                            "types": set(),
                        }
                    if p["source_row"]:
                        by_source[src_name]["rows"].append(p["source_row"])
                    by_source[src_name]["types"].add(p["entity_type"])

                for src_name, info in by_source.items():
                    doi = info["doi"]
                    rows = info["rows"]
                    types = ", ".join(info["types"])

                    if doi:
                        st.markdown(f"**[{src_name}](https://doi.org/{doi})**")
                    else:
                        st.markdown(f"**{src_name}**")

                    if rows:
                        row_str = ", ".join(rows[:5])
                        if len(rows) > 5:
                            row_str += f" (+{len(rows)-5} more)"
                        st.caption(f"Rows: {row_str} | Data: {types}")
                    else:
                        st.caption(f"Data: {types}")
            else:
                st.caption("No provenance information available")
    else:
        st.info("No molecules to display with current filters")
