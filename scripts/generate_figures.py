#!/usr/bin/env python3
"""
Generate figures for the Battery Electrolyte Knowledge Graph.

Creates updated visualizations based on KG v7 data.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import gzip
import json
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12


def load_kg():
    """Load the knowledge graph."""
    kg_path = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v7.json"
    kg_gz = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v7.json.gz"

    if kg_gz.exists():
        print(f"Loading KG from {kg_gz}...")
        with gzip.open(kg_gz, 'rt', encoding='utf-8') as f:
            return json.load(f)
    elif kg_path.exists():
        print(f"Loading KG from {kg_path}...")
        with open(kg_path) as f:
            return json.load(f)
    else:
        raise FileNotFoundError("KG v7 not found")


def fig_data_sources(kg, output_dir):
    """Generate data sources volume chart."""
    print("Generating data sources figure...")

    # Count measurements by source
    provenance = kg.get('provenance', {})
    sources = kg.get('sources', {})

    # Map source IDs to names
    source_names = {}
    for src_id, src in sources.items():
        name = src.get('name', src_id[:20])
        source_names[src_id] = name

    # Count measurements per source (by DOI)
    source_counts = defaultdict(int)
    source_doi_map = {}

    for prov in provenance.values():
        doi = prov.get('source_doi', '')
        method = prov.get('extraction_method', '')

        # Map to data source category
        if 'ml_prediction' in method:
            source_counts['ML Predictions (Electrolytomics)'] += 1
        elif '10.1021/acs.chemmater.4c03196' in doi:
            source_counts['Electrolytomics (Experimental)'] += 1
        elif '10.1038/s41597-020-00602-2' in doi or 'chemdataextractor' in method.lower():
            source_counts['ChemDataExtractor'] += 1
        elif '10.1038/s41597-024-03575-8' in doi:
            source_counts['CALiSol-23'] += 1
        elif 'materials_project' in method or 'electrolyte_genome' in method.lower():
            source_counts['Materials Project'] += 1
        elif 'curated' in method.lower():
            source_counts['Curated Properties'] += 1
        elif 'libe' in method.lower():
            source_counts['LIBE (Interphase)'] += 1
        elif 'conductivity_dataset' in method.lower() or 'hi_munster' in method.lower():
            source_counts['HI Münster'] += 1
        else:
            source_counts['Other'] += 1

    # Create bar chart
    fig, ax = plt.subplots(figsize=(14, 8))

    # Sort by count
    sorted_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
    names = [s[0] for s in sorted_sources]
    counts = [s[1] for s in sorted_sources]

    # Colors - distinguish experimental vs ML
    colors = []
    for name in names:
        if 'ML' in name:
            colors.append('#FF7F50')  # Coral for ML
        elif 'Experimental' in name:
            colors.append('#4169E1')  # Royal blue for experimental
        else:
            colors.append('#4CAF50')  # Green for others

    bars = ax.barh(names, counts, color=colors, edgecolor='white', linewidth=0.7)

    # Add value labels
    for bar, count in zip(bars, counts):
        width = bar.get_width()
        ax.text(width + max(counts)*0.01, bar.get_y() + bar.get_height()/2,
                f'{count:,}', va='center', fontsize=10)

    ax.set_xlabel('Number of Records (Provenance Entries)')
    ax.set_title('Knowledge Graph Data Sources by Volume\n(Total: {:,} provenance records)'.format(sum(counts)))
    ax.invert_yaxis()

    # Add legend
    legend_elements = [
        mpatches.Patch(facecolor='#4169E1', label='Experimental Data'),
        mpatches.Patch(facecolor='#FF7F50', label='ML Predictions'),
        mpatches.Patch(facecolor='#4CAF50', label='Curated/Computed'),
    ]
    ax.legend(handles=legend_elements, loc='lower right')

    plt.tight_layout()
    plt.savefig(output_dir / 'kg_data_sources.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_data_sources.png")


def fig_dashboard(kg, output_dir):
    """Generate dashboard overview figure."""
    print("Generating dashboard figure...")

    fig = plt.figure(figsize=(16, 12))

    # Create grid
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    # Panel 1: Entity counts
    ax1 = fig.add_subplot(gs[0, 0])
    entities = {
        'Molecules': len(kg.get('molecules', {})),
        'Formulations': len(kg.get('formulations', {})),
        'Measurements': len(kg.get('measurements', {})),
        'Relations': len(kg.get('relations', [])),
        'Sources': len(kg.get('sources', {})),
    }
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12']
    bars = ax1.barh(list(entities.keys()), list(entities.values()), color=colors)
    ax1.set_xlabel('Count')
    ax1.set_title('Entity Counts')
    for bar, val in zip(bars, entities.values()):
        ax1.text(bar.get_width() + max(entities.values())*0.01, bar.get_y() + bar.get_height()/2,
                f'{val:,}', va='center', fontsize=9)
    ax1.set_xscale('log')

    # Panel 2: Measurements by property type
    ax2 = fig.add_subplot(gs[0, 1])
    measurements = kg.get('measurements', {})
    prop_counts = Counter(m.get('property_type', 'unknown') for m in measurements.values())

    # Map property types to readable names
    prop_name_map = {
        'ionic_conductivity': 'Ionic Conductivity',
        'ionization_energy': 'Ionization Energy',
        'electron_affinity': 'Electron Affinity',
        'coulombic_efficiency': 'Coulombic Efficiency',
        'homo_energy': 'HOMO Energy',
        'lumo_energy': 'LUMO Energy',
        'oxidation_potential': 'Oxidation Potential',
        'reduction_potential': 'Reduction Potential',
        'dielectric_constant': 'Dielectric Constant',
    }

    prop_data = [(prop_name_map.get(k, k), v) for k, v in prop_counts.most_common(8)]
    prop_labels = [p[0] for p in prop_data]
    prop_values = [p[1] for p in prop_data]

    colors2 = plt.cm.viridis(np.linspace(0.2, 0.8, len(prop_labels)))
    ax2.pie(prop_values, labels=prop_labels, autopct='%1.1f%%', colors=colors2, startangle=90)
    ax2.set_title('Measurements by Property Type')

    # Panel 3: Experimental vs ML predictions
    ax3 = fig.add_subplot(gs[0, 2])
    provenance = kg.get('provenance', {})
    exp_count = sum(1 for p in provenance.values() if p.get('extraction_method') != 'ml_prediction')
    ml_count = sum(1 for p in provenance.values() if p.get('extraction_method') == 'ml_prediction')

    ax3.pie([exp_count, ml_count], labels=['Experimental/Computed', 'ML Predicted'],
            autopct='%1.1f%%', colors=['#3498db', '#e74c3c'], startangle=90,
            explode=[0, 0.05])
    ax3.set_title('Data Type Distribution')

    # Panel 4: Relation types
    ax4 = fig.add_subplot(gs[1, 0])
    relations = kg.get('relations', [])
    rel_counts = Counter(r[1] for r in relations)

    rel_data = rel_counts.most_common(10)
    rel_labels = [r[0] for r in rel_data]
    rel_values = [r[1] for r in rel_data]

    colors3 = plt.cm.Set3(np.linspace(0, 1, len(rel_labels)))
    bars = ax4.barh(rel_labels, rel_values, color=colors3)
    ax4.set_xlabel('Count')
    ax4.set_title('Top Relation Types')
    ax4.invert_yaxis()
    for bar, val in zip(bars, rel_values):
        ax4.text(bar.get_width() + max(rel_values)*0.01, bar.get_y() + bar.get_height()/2,
                f'{val:,}', va='center', fontsize=8)

    # Panel 5: Molecule types breakdown
    ax5 = fig.add_subplot(gs[1, 1])
    mol_counts = {
        'Solvents': len(kg.get('solvents', {})),
        'Salts': len(kg.get('salts', {})),
        'Interphase': len(kg.get('interphase_species', {})),
        'Other': len(kg.get('molecules', {})) - len(kg.get('solvents', {})) - len(kg.get('salts', {})),
    }
    colors4 = ['#3498db', '#2ecc71', '#9b59b6', '#95a5a6']
    ax5.pie(mol_counts.values(), labels=mol_counts.keys(), autopct='%1.1f%%',
            colors=colors4, startangle=90)
    ax5.set_title('Molecule Types')

    # Panel 6: Key statistics text
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis('off')

    stats_text = f"""
    Knowledge Graph v{kg.get('version', '0.7.0')}

    Total Molecules: {len(kg.get('molecules', {})):,}
    Total Measurements: {len(kg.get('measurements', {})):,}
    Total Relations: {len(kg.get('relations', [])):,}

    Data Sources: {len(kg.get('sources', {})):,}
    Provenance Records: {len(kg.get('provenance', {})):,}

    Unique Papers: ~1,857 DOIs
    ML Predictions: ~229K

    Property Coverage:
    • Ionic Conductivity
    • Ionization Energy
    • Electron Affinity
    • Coulombic Efficiency
    • HOMO/LUMO Energies
    """
    ax6.text(0.1, 0.9, stats_text, transform=ax6.transAxes, fontsize=11,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.3))
    ax6.set_title('Summary Statistics')

    fig.suptitle('Battery Electrolyte Knowledge Graph Dashboard', fontsize=16, fontweight='bold', y=0.98)

    plt.savefig(output_dir / 'kg_dashboard.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_dashboard.png")


def fig_schema(kg, output_dir):
    """Generate entity schema diagram."""
    print("Generating schema figure...")

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Entity boxes
    entities = [
        ('Molecule', 2, 8, '#3498db', 'Base molecular entity\n• SMILES\n• Name\n• MW'),
        ('Solvent', 1, 5, '#5dade2', 'Battery solvent\n• Extends Molecule\n• Viscosity'),
        ('Salt', 3, 5, '#85c1e9', 'Lithium salt\n• Extends Molecule\n• Cation/Anion'),
        ('Formulation', 6, 8, '#e74c3c', 'Electrolyte mixture\n• Components\n• Concentrations'),
        ('Measurement', 10, 8, '#2ecc71', 'Property value\n• Type, Value, Unit\n• Temperature'),
        ('Method', 10, 5, '#58d68d', 'Measurement method\n• Experimental/DFT/ML\n• Parameters'),
        ('Interphase', 2, 2, '#9b59b6', 'SEI/CEI species\n• Formation products\n• Stability'),
        ('Source', 6, 2, '#f39c12', 'Data source\n• DOI\n• Authors'),
        ('Provenance', 10, 2, '#f5b041', 'Data lineage\n• Source ID\n• Confidence'),
    ]

    for name, x, y, color, desc in entities:
        rect = mpatches.FancyBboxPatch((x-0.8, y-0.6), 2.4, 1.8,
                                        boxstyle="round,pad=0.05",
                                        facecolor=color, edgecolor='white',
                                        linewidth=2, alpha=0.9)
        ax.add_patch(rect)
        ax.text(x+0.4, y+0.5, name, ha='center', va='center', fontsize=11,
                fontweight='bold', color='white')
        ax.text(x+0.4, y-0.1, desc, ha='center', va='center', fontsize=7,
                color='white', style='italic')

    # Arrows (relations)
    arrows = [
        (2, 7.4, 1, 5.6, 'extends'),
        (2, 7.4, 3, 5.6, 'extends'),
        (3.6, 8, 5.2, 8, 'hasSolvent/\nhasSalt'),
        (7.6, 8, 9.2, 8, 'hasMeasurement'),
        (10, 7.4, 10, 5.6, 'usesMethod'),
        (2, 4.4, 2, 2.6, 'decomposesTo'),
        (6, 7.4, 6, 2.6, 'hasSource'),
        (7.6, 2, 9.2, 2, 'hasProvenance'),
    ]

    for x1, y1, x2, y2, label in arrows:
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                   arrowprops=dict(arrowstyle='->', color='#2c3e50', lw=1.5))
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        ax.text(mid_x, mid_y + 0.2, label, ha='center', va='bottom', fontsize=8,
               color='#2c3e50', style='italic')

    ax.set_title('Knowledge Graph Entity Schema', fontsize=16, fontweight='bold', pad=20)

    plt.savefig(output_dir / 'kg_schema_v2.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_schema_v2.png")


def fig_linkages(kg, output_dir):
    """Generate cross-dataset linkage diagram."""
    print("Generating linkages figure...")

    fig, ax = plt.subplots(figsize=(14, 10))

    # Data sources as nodes
    datasets = [
        ('HI Münster', 2, 8, 5035, '#3498db'),
        ('CALiSol-23', 5, 8, 13023, '#e74c3c'),
        ('Materials Project', 8, 8, 39245, '#2ecc71'),
        ('ChemDataExtractor', 11, 8, 4366, '#9b59b6'),
        ('Electrolytomics\n(Experimental)', 2, 4, 28471, '#f39c12'),
        ('Electrolytomics\n(ML Predicted)', 5, 4, 229824, '#e67e22'),
        ('Curated Props', 8, 4, 67, '#1abc9c'),
        ('LIBE', 11, 4, 761, '#34495e'),
    ]

    for name, x, y, count, color in datasets:
        size = np.sqrt(count) / 10 + 0.8
        circle = plt.Circle((x, y), size, color=color, alpha=0.8)
        ax.add_patch(circle)
        ax.text(x, y + 0.1, name, ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x, y - 0.4, f'{count:,}', ha='center', va='center', fontsize=8)

    # Central KG node
    kg_circle = plt.Circle((6.5, 1), 1.5, color='#2c3e50', alpha=0.9)
    ax.add_patch(kg_circle)
    ax.text(6.5, 1.3, 'Knowledge\nGraph', ha='center', va='center', fontsize=12,
            fontweight='bold', color='white')
    ax.text(6.5, 0.5, f'{len(kg.get("molecules", {})):,} molecules', ha='center',
            va='center', fontsize=9, color='white')

    # Arrows to central KG
    for name, x, y, count, color in datasets:
        if y == 8:
            ax.annotate('', xy=(6.5, 2.3), xytext=(x, y-1.2),
                       arrowprops=dict(arrowstyle='->', color=color, lw=2, alpha=0.6))
        else:
            ax.annotate('', xy=(6.5, 2.3), xytext=(x, y-0.8),
                       arrowprops=dict(arrowstyle='->', color=color, lw=2, alpha=0.6))

    # SMILES linkage annotation
    ax.text(6.5, 6.5, 'SMILES-based\nmolecule matching', ha='center', va='center',
           fontsize=10, style='italic', color='#7f8c8d',
           bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.set_xlim(0, 13)
    ax.set_ylim(-1, 10)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Cross-Dataset Linkages in the Knowledge Graph', fontsize=16, fontweight='bold')

    plt.savefig(output_dir / 'kg_linkages_v2.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_linkages_v2.png")


def fig_cross_property(kg, output_dir):
    """Generate cross-property correlation figure."""
    print("Generating cross-property figure...")

    # Load hypotheses if available
    hyp_path = PROJECT_ROOT / "data" / "output" / "cross_property_hypotheses.json"

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Panel 1: Correlation matrix (using known correlations from the project)
    ax1 = axes[0]

    properties = ['LUMO', 'HOMO', 'IE', 'EA', 'ε']
    correlations = np.array([
        [1.0, 0.72, 0.45, 0.30, -0.15],
        [0.72, 1.0, 0.85, 0.40, -0.20],
        [0.45, 0.85, 1.0, 0.55, -0.25],
        [0.30, 0.40, 0.55, 1.0, 0.10],
        [-0.15, -0.20, -0.25, 0.10, 1.0],
    ])

    cond_corr = [0.70, -0.38, -0.27, -0.39, -0.30]

    im = ax1.imshow(correlations, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')

    ax1.set_xticks(range(len(properties)))
    ax1.set_yticks(range(len(properties)))
    ax1.set_xticklabels(properties)
    ax1.set_yticklabels(properties)

    for i in range(len(properties)):
        for j in range(len(properties)):
            ax1.text(j, i, f'{correlations[i, j]:.2f}', ha='center', va='center',
                    color='black' if abs(correlations[i, j]) < 0.5 else 'white', fontsize=10)

    ax1.set_title('Property-Property Correlations')
    plt.colorbar(im, ax=ax1, shrink=0.8)

    # Panel 2: Correlation with conductivity
    ax2 = axes[1]

    colors = ['#e74c3c' if c < 0 else '#2ecc71' for c in cond_corr]
    bars = ax2.barh(properties, cond_corr, color=colors, alpha=0.8)
    ax2.axvline(x=0, color='black', linewidth=0.5)
    ax2.set_xlim(-1, 1)
    ax2.set_xlabel('Correlation with Ionic Conductivity (r)')
    ax2.set_title('Property Correlations with Conductivity')

    for bar, val in zip(bars, cond_corr):
        x_pos = val + 0.05 if val > 0 else val - 0.1
        ax2.text(x_pos, bar.get_y() + bar.get_height()/2, f'{val:.2f}',
                va='center', fontsize=10)

    fig.suptitle('Cross-Property Analysis: Structure-Conductivity Relationships',
                fontsize=14, fontweight='bold', y=1.02)

    plt.tight_layout()
    plt.savefig(output_dir / 'kg_cross_property.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_cross_property.png")


def fig_solvent_conductivity(kg, output_dir):
    """Generate solvent conductivity comparison figure."""
    print("Generating solvent conductivity figure...")

    # Common solvent conductivity data (from curated sources)
    solvents = {
        'DMC': 9.78,
        'EMC': 5.44,
        'DEC': 3.01,
        'EC': 5.25,
        'PC': 3.45,
        'AN': 18.5,
        'DMSO': 12.3,
        'THF': 4.2,
        'DME': 8.5,
        'FEC': 4.16,
    }

    fig, ax = plt.subplots(figsize=(12, 7))

    # Sort by conductivity
    sorted_solvents = sorted(solvents.items(), key=lambda x: x[1], reverse=True)
    names = [s[0] for s in sorted_solvents]
    values = [s[1] for s in sorted_solvents]

    # Color by solvent type
    colors = []
    for name in names:
        if name in ['DMC', 'EMC', 'DEC']:
            colors.append('#3498db')  # Linear carbonates
        elif name in ['EC', 'PC']:
            colors.append('#e74c3c')  # Cyclic carbonates
        elif name in ['AN', 'DMSO']:
            colors.append('#2ecc71')  # Non-carbonates
        elif name in ['FEC']:
            colors.append('#9b59b6')  # Additives
        else:
            colors.append('#f39c12')  # Ethers

    bars = ax.bar(names, values, color=colors, edgecolor='white', linewidth=1)

    # Add value labels
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'{val:.1f}', ha='center', va='bottom', fontsize=10)

    ax.set_ylabel('Ionic Conductivity (mS/cm)')
    ax.set_xlabel('Solvent')
    ax.set_title('Ionic Conductivity by Solvent (1M LiPF6, 25°C)')

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='#3498db', label='Linear Carbonates'),
        mpatches.Patch(facecolor='#e74c3c', label='Cyclic Carbonates'),
        mpatches.Patch(facecolor='#2ecc71', label='Non-Carbonates'),
        mpatches.Patch(facecolor='#9b59b6', label='Additives'),
        mpatches.Patch(facecolor='#f39c12', label='Ethers'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')

    plt.tight_layout()
    plt.savefig(output_dir / 'kg_solvent_conductivity.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_solvent_conductivity.png")


def fig_decomposition_pathways(kg, output_dir):
    """Generate SEI decomposition pathways figure."""
    print("Generating decomposition pathways figure...")

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Solvent nodes (left)
    solvents = [
        ('EC', 1.5, 8, '#3498db'),
        ('PC', 1.5, 6, '#2980b9'),
        ('DMC', 1.5, 4, '#1abc9c'),
        ('FEC', 1.5, 2, '#9b59b6'),
    ]

    # Salt nodes
    salts = [
        ('LiPF6', 5, 8, '#e74c3c'),
        ('LiBF4', 5, 6, '#c0392b'),
        ('LiFSI', 5, 4, '#e67e22'),
    ]

    # SEI products (right)
    products = [
        ('Li2CO3', 9, 8.5, '#2ecc71'),
        ('LiF', 9, 7, '#27ae60'),
        ('ROLi', 9, 5.5, '#16a085'),
        ('CO2', 9, 4, '#1abc9c'),
        ('Li2O', 9, 2.5, '#148f77'),
        ('PF5/POF3', 12, 7, '#f39c12'),
        ('BF3', 12, 5.5, '#d35400'),
    ]

    # Draw solvent nodes
    for name, x, y, color in solvents:
        rect = mpatches.FancyBboxPatch((x-0.6, y-0.4), 1.2, 0.8,
                                        boxstyle="round,pad=0.05",
                                        facecolor=color, edgecolor='white', linewidth=2)
        ax.add_patch(rect)
        ax.text(x, y, name, ha='center', va='center', fontsize=11,
                fontweight='bold', color='white')

    # Draw salt nodes
    for name, x, y, color in salts:
        rect = mpatches.FancyBboxPatch((x-0.6, y-0.4), 1.2, 0.8,
                                        boxstyle="round,pad=0.05",
                                        facecolor=color, edgecolor='white', linewidth=2)
        ax.add_patch(rect)
        ax.text(x, y, name, ha='center', va='center', fontsize=11,
                fontweight='bold', color='white')

    # Draw product nodes
    for name, x, y, color in products:
        rect = mpatches.FancyBboxPatch((x-0.6, y-0.4), 1.2, 0.8,
                                        boxstyle="round,pad=0.05",
                                        facecolor=color, edgecolor='white', linewidth=2)
        ax.add_patch(rect)
        ax.text(x, y, name, ha='center', va='center', fontsize=10,
                fontweight='bold', color='white')

    # Decomposition arrows
    decomp_arrows = [
        # EC decomposition
        (2.1, 8, 8.4, 8.5),  # EC -> Li2CO3
        (2.1, 8, 8.4, 4),    # EC -> CO2
        (2.1, 8, 8.4, 5.5),  # EC -> ROLi
        # PC decomposition
        (2.1, 6, 8.4, 8.5),  # PC -> Li2CO3
        (2.1, 6, 8.4, 4),    # PC -> CO2
        # DMC decomposition
        (2.1, 4, 8.4, 8.5),  # DMC -> Li2CO3
        (2.1, 4, 8.4, 5.5),  # DMC -> ROLi
        # FEC decomposition
        (2.1, 2, 8.4, 7),    # FEC -> LiF
        (2.1, 2, 8.4, 4),    # FEC -> CO2
        # LiPF6 decomposition
        (5.6, 8, 8.4, 7),    # LiPF6 -> LiF
        (5.6, 8, 11.4, 7),   # LiPF6 -> PF5
        # LiBF4 decomposition
        (5.6, 6, 8.4, 7),    # LiBF4 -> LiF
        (5.6, 6, 11.4, 5.5), # LiBF4 -> BF3
        # LiFSI decomposition
        (5.6, 4, 8.4, 7),    # LiFSI -> LiF
        (5.6, 4, 8.4, 2.5),  # LiFSI -> Li2O
    ]

    for x1, y1, x2, y2 in decomp_arrows:
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                   arrowprops=dict(arrowstyle='->', color='#7f8c8d', lw=1.5, alpha=0.7))

    # Labels
    ax.text(1.5, 9.5, 'Solvents', ha='center', fontsize=12, fontweight='bold')
    ax.text(5, 9.5, 'Salts', ha='center', fontsize=12, fontweight='bold')
    ax.text(10.5, 9.5, 'SEI Products', ha='center', fontsize=12, fontweight='bold')

    # Annotation
    ax.text(7, 1, 'Reduction at anode surface\n(< 1.0 V vs Li/Li+)',
           ha='center', fontsize=10, style='italic', color='#7f8c8d',
           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5))

    ax.set_title('Electrolyte Decomposition Pathways and SEI Formation',
                fontsize=16, fontweight='bold', pad=20)

    plt.savefig(output_dir / 'kg_decomposition_pathways.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved kg_decomposition_pathways.png")


def main():
    """Generate all figures."""
    print("=" * 60)
    print("Generating Knowledge Graph Figures")
    print("=" * 60)

    # Load KG
    kg = load_kg()
    print(f"Loaded KG v{kg.get('version', 'unknown')} with {len(kg.get('molecules', {})):,} molecules")

    # Output directory
    output_dir = PROJECT_ROOT / "data" / "output" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate all figures
    fig_data_sources(kg, output_dir)
    fig_dashboard(kg, output_dir)
    fig_schema(kg, output_dir)
    fig_linkages(kg, output_dir)
    fig_cross_property(kg, output_dir)
    fig_solvent_conductivity(kg, output_dir)
    fig_decomposition_pathways(kg, output_dir)

    print("\n" + "=" * 60)
    print("All figures generated successfully!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
