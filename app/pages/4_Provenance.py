"""
Provenance Tracing Page

Explore the sources and basis for links in the knowledge graph.
"""

import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="Provenance", page_icon="🔍", layout="wide")

st.title("🔍 Provenance Tracing")
st.markdown("Trace any entity or relationship back to its original data source.")

# Load KG data
PROJECT_ROOT = Path(__file__).parent.parent.parent


@st.cache_data
def load_kg_data():
    """Load the knowledge graph JSON."""
    kg_path = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v7.json"
    if kg_path.exists():
        with open(kg_path) as f:
            return json.load(f)
    return None


kg = load_kg_data()

if kg is None:
    st.error("Knowledge graph data not found. Please ensure knowledge_graph_v7.json exists.")
    st.stop()

# Get data
sources = kg.get("sources", {})
provenance = kg.get("provenance", {})
molecules = kg.get("molecules", {})
solvents = kg.get("solvents", {})
salts = kg.get("salts", {})
measurements = kg.get("measurements", {})
formulations = kg.get("formulations", {})
interphase = kg.get("interphase_species", {})
relations = kg.get("relations", [])

# Tabs
tab1, tab2, tab3 = st.tabs(["Data Sources", "Entity Lookup", "Relation Explainer"])

with tab1:
    st.header("Integrated Data Sources")
    st.markdown("All data in the knowledge graph comes from these sources:")

    for src_id, src in sources.items():
        with st.expander(f"**{src.get('name', 'Unknown')}**", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Type:** {src.get('source_type', 'N/A')}")
                doi = src.get('doi')
                if doi:
                    st.markdown(f"**DOI:** [{doi}](https://doi.org/{doi})")
                else:
                    st.markdown("**DOI:** Not available")
            with col2:
                url = src.get('url')
                if url:
                    st.markdown(f"**URL:** [{url}]({url})")
                authors = src.get('authors', [])
                if authors:
                    st.markdown(f"**Authors:** {', '.join(authors[:3])}{'...' if len(authors) > 3 else ''}")

    # Provenance statistics
    st.subheader("Provenance Coverage")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Provenance Records", f"{len(provenance):,}")
    with col2:
        with_doi = sum(1 for p in provenance.values() if p.get('source_doi'))
        st.metric("With DOI", f"{with_doi:,}")
    with col3:
        validated = sum(1 for p in provenance.values() if p.get('validated'))
        st.metric("Validated", f"{validated:,}")

with tab2:
    st.header("Entity Provenance Lookup")

    # Build entity index for search
    all_entities = {}

    for mol_id, mol in molecules.items():
        name = mol.get('name', mol_id[:8])
        all_entities[f"{name} (Molecule)"] = {"id": mol_id, "type": "Molecule", "data": mol}

    for sol_id, sol in solvents.items():
        name = sol.get('name', sol_id[:8])
        all_entities[f"{name} (Solvent)"] = {"id": sol_id, "type": "Solvent", "data": sol}

    for salt_id, salt in salts.items():
        name = salt.get('name', salt_id[:8])
        all_entities[f"{name} (Salt)"] = {"id": salt_id, "type": "Salt", "data": salt}

    for sp_id, sp in interphase.items():
        name = sp.get('name', sp_id[:8])
        all_entities[f"{name} (Interphase)"] = {"id": sp_id, "type": "InterphaseSpecies", "data": sp}

    # Search box
    search = st.text_input("Search for an entity", placeholder="e.g., Ethylene carbonate, LiPF6, Li2CO3")

    if search:
        # Filter matches
        matches = [k for k in all_entities.keys() if search.lower() in k.lower()]

        if matches:
            selected = st.selectbox("Select entity", matches[:20])

            if selected:
                entity = all_entities[selected]
                entity_id = entity["id"]
                entity_data = entity["data"]

                st.subheader(f"Entity: {entity_data.get('name', 'Unknown')}")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Type:** {entity['type']}")
                    st.markdown(f"**ID:** `{entity_id[:16]}...`")
                    if entity_data.get('smiles'):
                        st.code(entity_data['smiles'], language=None)

                with col2:
                    # Find provenance
                    entity_prov = [p for p in provenance.values() if p.get('entity_id') == entity_id]

                    if entity_prov:
                        p = entity_prov[0]
                        st.markdown("**Provenance:**")
                        if p.get('source_doi'):
                            doi = p['source_doi']
                            st.markdown(f"- DOI: [{doi}](https://doi.org/{doi})")
                        if p.get('source_row_id'):
                            st.markdown(f"- Dataset Row: {p['source_row_id']}")
                        st.markdown(f"- Method: {p.get('extraction_method', 'N/A')}")
                        st.markdown(f"- Confidence: {p.get('confidence', 'N/A')}")
                    else:
                        st.info("No direct provenance record found")

                # Show related entities
                st.subheader("Related Entities")
                related = []
                for rel in relations:
                    if rel[0] == entity_id:
                        related.append({"relation": rel[1], "target": rel[2], "direction": "outgoing"})
                    elif rel[2] == entity_id:
                        related.append({"relation": rel[1], "target": rel[0], "direction": "incoming"})

                if related[:10]:
                    for r in related[:10]:
                        target_id = r["target"]
                        target_name = target_id[:12] + "..."

                        # Try to find name
                        for entity_dict in [molecules, solvents, salts, interphase]:
                            if target_id in entity_dict:
                                target_name = entity_dict[target_id].get('name', target_name)
                                break

                        arrow = "→" if r["direction"] == "outgoing" else "←"
                        st.markdown(f"- {arrow} **{r['relation']}** → {target_name}")
                else:
                    st.caption("No relations found")
        else:
            st.warning("No entities found matching your search")

with tab3:
    st.header("Relation Explainer")
    st.markdown("Understand why a relationship exists between two entities.")

    # Relation type selector
    relation_types = list(set(r[1] for r in relations))
    selected_rel = st.selectbox("Select relation type", sorted(relation_types))

    # Filter relations by type
    filtered_rels = [r for r in relations if r[1] == selected_rel][:100]

    st.markdown(f"Found **{len([r for r in relations if r[1] == selected_rel]):,}** `{selected_rel}` relations")

    # Explain the relation type
    st.subheader("Relation Basis")

    explanations = {
        "sameAs": {
            "method": "SMILES String Matching",
            "description": "Entities from different datasets are linked when they have identical SMILES representations. This enables cross-dataset property queries.",
            "confidence": "High - based on exact structural match",
        },
        "hasMeasurement": {
            "method": "Direct Dataset Import",
            "description": "Links formulations to their measured properties. Each measurement is traced to a specific row in the source dataset.",
            "confidence": "High - direct from experimental data",
        },
        "decomposesTo": {
            "method": "Literature Knowledge",
            "description": "Decomposition pathways from electrolyte chemistry literature. Maps solvents/salts to their SEI decomposition products.",
            "confidence": "Moderate - based on published mechanisms",
        },
        "coOccursWith": {
            "method": "Association Rule Mining",
            "description": "Discovered through mining co-occurrence patterns in electrolyte formulations. Components that frequently appear together are linked.",
            "confidence": "Statistical - based on frequency analysis",
        },
        "increases": {
            "method": "Correlation Analysis",
            "description": "Generated by analyzing property correlations. Links components to properties they tend to increase.",
            "confidence": "Statistical - based on correlation coefficients",
        },
        "decreases": {
            "method": "Correlation Analysis",
            "description": "Generated by analyzing property correlations. Links components to properties they tend to decrease.",
            "confidence": "Statistical - based on correlation coefficients",
        },
        "hasSolvent": {
            "method": "Direct Dataset Import",
            "description": "Links formulations to their solvent components with amounts/ratios.",
            "confidence": "High - direct from source data",
        },
        "hasSalt": {
            "method": "Direct Dataset Import",
            "description": "Links formulations to their salt components with concentrations.",
            "confidence": "High - direct from source data",
        },
    }

    if selected_rel in explanations:
        exp = explanations[selected_rel]
        st.info(f"**Method:** {exp['method']}")
        st.markdown(exp['description'])
        st.markdown(f"**Confidence Level:** {exp['confidence']}")
    else:
        st.caption("No detailed explanation available for this relation type")

    # Show sample relations
    st.subheader("Sample Relations")

    for rel in filtered_rels[:5]:
        subj_id, rel_type, obj_id = rel

        # Get names
        subj_name = subj_id[:12] + "..."
        obj_name = obj_id[:12] + "..."

        for entity_dict in [molecules, solvents, salts, interphase, formulations]:
            if subj_id in entity_dict:
                subj_name = entity_dict[subj_id].get('name', subj_name)
            if obj_id in entity_dict:
                obj_name = entity_dict[obj_id].get('name', obj_name)

        with st.expander(f"{subj_name} → {rel_type} → {obj_name}"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Subject:**")
                st.markdown(f"- Name: {subj_name}")
                st.markdown(f"- ID: `{subj_id[:20]}...`")

                # Get subject provenance
                subj_prov = next((p for p in provenance.values() if p.get('entity_id') == subj_id), None)
                if subj_prov and subj_prov.get('source_doi'):
                    st.markdown(f"- Source: [{subj_prov['source_doi']}](https://doi.org/{subj_prov['source_doi']})")

            with col2:
                st.markdown("**Object:**")
                st.markdown(f"- Name: {obj_name}")
                st.markdown(f"- ID: `{obj_id[:20]}...`")

                # Get object provenance
                obj_prov = next((p for p in provenance.values() if p.get('entity_id') == obj_id), None)
                if obj_prov and obj_prov.get('source_doi'):
                    st.markdown(f"- Source: [{obj_prov['source_doi']}](https://doi.org/{obj_prov['source_doi']})")

            # Show SMILES match for sameAs
            if rel_type == "sameAs":
                for entity_dict in [molecules, solvents, salts]:
                    if subj_id in entity_dict and obj_id in entity_dict:
                        subj_smiles = entity_dict[subj_id].get('smiles', '')
                        obj_smiles = entity_dict.get(obj_id, {}).get('smiles', '')
                        if subj_smiles:
                            st.success(f"**Matching SMILES:** `{subj_smiles}`")
                        break
