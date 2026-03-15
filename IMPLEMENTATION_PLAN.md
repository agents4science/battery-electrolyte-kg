# Implementation Plan: Agentic AI-Driven Knowledge-Graph Discovery for Battery Electrolyte Design

Based on the pilot plan document, this is a detailed implementation roadmap.

---

## Overview

**Goal**: Build an end-to-end KG discovery prototype that:
- Constructs a provenance-rich electrolyte KG from 2+ structured sources
- Proposes typed KG augmentations (hypothesis edges)
- Validates hypotheses via time-slice, simulation, and optional wet-lab methods
- Maintains complete provenance throughout

**Success Criteria**:
- ≥1,000 electrolyte formulation nodes
- ≥10 candidate edges proposed → ≥3 pass novelty filters → ≥1-3 validated
- Measurable model lift (e.g., conductivity RMSE reduction)
- ≥95% provenance completeness (PROV-O aligned)

---

## Phase 1: Schema Design & Pilot Scoping (Month 0-1)

### 1.1 Define Minimal KG Schema

**Entity Types**:
```
ElectrolyteFormulation
├── Component
│   ├── Solvent (EC, PC, EMC, DMC)
│   ├── Salt (LiPF₆)
│   └── Additive (VC, FEC)
├── Molecule (canonical identity: PubChem CID, SMILES)
├── PropertyMeasurement
│   └── conductivity, activation energy, resistance
├── MeasurementMethod (EIS, Arrhenius fit)
├── InterphaseSpecies / SEISpecies (LIBE-driven)
└── EvidenceSource (dataset ID, DOI, patent ID)
```

**Relation Types**:
```yaml
Formulation Composition:
  - hasSolvent(formulation, solvent)
  - hasSalt(formulation, salt)
  - hasAdditive(formulation, additive)
  - hasAmount(component_in_formulation, value+unit)

Property Measurement:
  - hasMeasurement(formulation, propertyMeasurement)
  - measuresProperty(propertyMeasurement, propertyType)
  - measuredBy(propertyMeasurement, method)
  - measuredAt(propertyMeasurement, temperature)

Interphase/SEI:
  - decomposesTo(molecule, interphaseSpecies)
  - participatesInReaction(species, reaction)

Discovery Edges:
  - hypothesizedRelation(hypothesis, relationType)
  - evidenceFor(hypothesis, evidenceSource)
  - validatedBy(hypothesis, validationActivity)
  - status(hypothesis, {proposed, rejected, validated})
```

**Provenance Fields** (PROV-O aligned):
- `prov:wasDerivedFrom` (dataset DOI/row ID, paper DOI, patent ID)
- `prov:wasGeneratedBy` (extraction activity, ETL job ID)
- `prov:wasAttributedTo` (agent: software component or curator)
- Timestamp, KG version, confidence score
- Evidence snippet pointer

### 1.2 Define Competency Questions

Example queries the KG must support:
1. "Find all formulations with EC fraction in [x,y] and LiPF₆ mass in [a,b], return conductivity at 25°C"
2. "Which additives appear in formulations with conductivity > threshold?"
3. "What SEI species are associated with solvent X decomposition?"

### 1.3 Pre-register Evaluation Tasks

- Conductivity regression (RMSE/MAE)
- Link prediction (MRR, Hits@k)
- Time-slice novelty hit rate

### Deliverables
- [ ] Pilot specification document
- [ ] Frozen minimal schema (OWL/RDF)
- [ ] Competency question list
- [ ] Evaluation task pre-registration

---

## Phase 2: Structured Data Ingestion Baseline (Month 1-2)

### 2.1 Primary Data Sources

| Dataset | Content | Format | Priority |
|---------|---------|--------|----------|
| **Conductivity/EIS Dataset** (Scientific Data 2023) | EC/PC/EMC/LiPF₆ compositions, EIS-derived conductivity, temperature series | CSV/JSON | HIGH |
| **LIBE Dataset** (Scientific Data 2021) | ~17,000 interphase species, DFT properties | CSV/JSON | HIGH |
| **Materials Project** (Electrolyte Genome) | Computed redox/electrochemical properties | API | MEDIUM |
| **NFDI4Chem** (RADAR4Chem) | Dataset metadata, SPARQL endpoint | RDF/Turtle | MEDIUM |

### 2.2 Implementation Tasks

```python
# Suggested project structure
kg_discovery/
├── data/
│   ├── raw/                    # Downloaded datasets
│   ├── processed/              # Normalized data
│   └── kg/                     # KG exports (RDF, JSON-LD)
├── ingestion/
│   ├── conductivity_ingest.py  # Scientific Data 2023 dataset
│   ├── libe_ingest.py          # LIBE dataset
│   ├── mp_ingest.py            # Materials Project API
│   └── nfdi_sparql.py          # NFDI4Chem SPARQL queries
├── schema/
│   ├── electrolyte_schema.owl  # OWL ontology
│   └── prov_model.py           # PROV-O provenance model
├── kg_store/
│   ├── graph_db.py             # Graph database interface
│   └── versioning.py           # KG versioning
└── tests/
```

### 2.3 KG Store Setup

**Options**:
- Neo4j (property graph, good for exploration)
- Apache Jena/Fuseki (RDF triple store, SPARQL native)
- RDFLib (Python-native, good for prototyping)

### Deliverables
- [ ] Data download scripts
- [ ] Ingestion pipelines for each source
- [ ] KG store with versioning
- [ ] Provenance tracking (≥95% coverage)
- [ ] Consistency validation tests

---

## Phase 3: Corpus Extraction & NFDI Integration (Month 2-3)

### 3.1 Literature/Patent Corpus Collection

**Literature Query Templates** (2015-2025):
```
A. Liquid electrolyte formulations:
   ("electrolyte" AND (solvent OR "salt" OR additive)
    AND ("LiPF6" OR "LiTFSI" OR "LiFSI")
    AND ("ethylene carbonate" OR "dimethyl carbonate")
    AND ("ionic conductivity" OR impedance OR EIS))

B. Additives and SEI:
   (("electrolyte additive" OR additive)
    AND ("SEI" OR "solid electrolyte interphase")
    AND ("vinylene carbonate" OR VC OR "fluoroethylene carbonate" OR FEC))
```

**Patent Query** (PatentsView API):
```json
{
  "_and": [
    {"_gte": {"patent_date": "2015-01-01"}},
    {"_lte": {"patent_date": "2025-12-31"}},
    {"_text_any": {"patent_title": "battery electrolyte solvent salt additive SEI"}},
    {"_not": {"patent_type": "design"}}
  ]
}
```

### 3.2 Extraction Pipeline

**Conservative approach for pilot**:
1. Start with structured recipe extraction (solvents/salts/additives/ratios)
2. Extract property values with units
3. Link to canonical chemical identifiers
4. Defer deep mechanistic relation extraction

**Tools**:
- ChemDataExtractor / OSCAR4 for chemical NER
- Grobid for PDF parsing
- Custom regex for formulation patterns

### 3.3 NFDI4Chem Integration

- Connect to RADAR4Chem SPARQL endpoint
- Integrate dataset metadata nodes
- Align to schema.org/BFO/NFDICore patterns

### Deliverables
- [ ] Corpus collection scripts
- [ ] NER/extraction pipeline
- [ ] Entity resolution system
- [ ] NFDI SPARQL integration
- [ ] Extraction precision/recall on seed set

---

## Phase 4: Hypothesis Generation MVP (Month 3-4)

### 4.1 KG Completion Models

**Embedding-based approaches**:
- TransE, RotatE, ComplEx for link prediction
- Train on existing KG edges
- Score candidate missing edges

**GNN-based approaches**:
- R-GCN for relational data
- Node classification + link prediction

### 4.2 Rule Mining

**Pattern discovery**:
```
IF formulation contains X AND Y at Z range
THEN conductivity_class = high
```

**Tools**:
- AMIE+ for rule mining on KGs
- Association rule mining on structured data

### 4.3 Hypothesis Types

1. **Property prediction**: "Additive X increases conductivity in formulation family Y"
2. **Mechanistic**: "Molecule A decomposes preferentially to SEI species class B"
3. **Composition patterns**: "Solvent ratio regime R correlates with property P"

### 4.4 Candidate Filtering

- **Novelty filter**: Not in pre-cutoff KG
- **Time-slice filter**: Does not appear in training window
- **Plausibility filter**: Consistent with chemical constraints

### Deliverables
- [ ] KG embedding models
- [ ] Rule mining pipeline
- [ ] Hypothesis generation module
- [ ] ≥10 candidate edges proposed
- [ ] ≥3 edges pass novelty/time-slice filters

---

## Phase 5: Evaluation & Time-Slice Experiments (Month 4-5)

### 5.1 Retrospective Time-Slice Validation

1. Build KG from data up to cutoff year T (e.g., 2019)
2. Propose hypothesis edges
3. Check if edges appear in T+1...T+k literature/patents
4. Score: novelty hit rate, ranking quality

### 5.2 Predictive Task Evaluation

**Conductivity Regression**:
- Train model with/without augmented edges
- Compare RMSE/MAE on held-out formulation regions
- Ablation studies to attribute improvement to specific edges

**Metrics**:
| Metric | Target |
|--------|--------|
| ΔRMSE (conductivity) | Statistically significant reduction |
| Link prediction MRR | Improvement over baseline |
| Time-slice hit rate | >0 novel edges validated |
| Provenance completeness | ≥95% |

### 5.3 Simulation-Based Validation

- Check consistency with LIBE computed properties
- Verify redox stability via Materials Project data
- Flag chemically implausible hypotheses

### Deliverables
- [ ] Time-slice experiment results
- [ ] Predictive model with ablations
- [ ] Simulation validation pipeline
- [ ] Evaluation report with metrics

---

## Phase 6: Wet-Lab Validation (Month 5-6, Optional)

### 6.1 Experiment Selection

**Criteria**:
- High expected information gain
- Safe, feasible compositions
- Maps to existing dataset format (EIS conductivity)

**Target**: 5-15 formulations to validate 1-3 top hypotheses

### 6.2 Protocol Design

**Measurements**:
- Ionic conductivity via EIS (temperature series)
- Optional: CV for electrochemical stability screening

**Lab Automation Integration** (if available):
- SiLA 2 for instrument connectivity
- PyLabRobot for liquid handling
- Autoprotocol for protocol abstraction

### 6.3 Data Capture

- Machine-readable format matching existing schema
- Complete metadata (batch, equipment, conditions)
- AnIML-inspired analytical data containers

### Deliverables
- [ ] Experiment plan
- [ ] Lab protocols
- [ ] Raw data + metadata
- [ ] Validated hypothesis edges (≥1)

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENTIC KG DISCOVERY LOOP                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  KG Builder  │───▶│   Explorer   │───▶│  Hypothesis  │      │
│  │              │    │              │    │    Agent     │      │
│  │ - Ingest     │    │ - SPARQL     │    │              │      │
│  │ - Normalize  │    │ - Embeddings │    │ - KG Compl.  │      │
│  │ - Provenance │    │ - Gap detect │    │ - Rule mine  │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                                       │               │
│         │                                       ▼               │
│         │            ┌──────────────┐    ┌──────────────┐      │
│         │            │   Curator    │◀───│  Evaluator   │      │
│         │            │              │    │              │      │
│         │◀───────────│ - Merge edge │    │ - Pred. task │      │
│                      │ - Reject+log │    │ - Ablation   │      │
│                      │ - Version KG │    │ - Simulation │      │
│                      └──────────────┘    └──────────────┘      │
│                             ▲                   │               │
│                             │                   ▼               │
│                      ┌──────────────┐    ┌──────────────┐      │
│                      │   Executor   │◀───│  Experiment  │      │
│                      │              │    │   Planner    │      │
│                      │ - Lab auto   │    │              │      │
│                      │ - EIS/CV     │    │ - BO/AL      │      │
│                      │ - Audit logs │    │ - Batch sel. │      │
│                      └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Resource Estimates

| Resource | Range | Notes |
|----------|-------|-------|
| Personnel | 4-8 FTE | KG engineer, ML engineer, NLP engineer, domain scientist |
| Compute | 1,000-20,000 GPU-hours | Depends on model complexity |
| Dataset size | 10³-10⁵ formulations | Scales with corpus |

---

## Go/No-Go Gates

| Gate | Criterion | Check Point |
|------|-----------|-------------|
| **G1** | Ingest ≥2 structured datasets into consistent schema | End of Month 2 |
| **G2** | Link prediction proposes candidates passing novelty filters | End of Month 4 |
| **G3** | ≥1 validated edge with measurable effect + full provenance | End of Month 6 |

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| False positives from KG completion | Typed hypotheses, novelty filters, ablation attribution |
| Entity resolution failures | Canonical identifiers (PubChem CID), controlled vocabulary |
| Provenance debt | Mandatory PROV-O fields, automated completeness checks |
| Patent API access constraints | Alternative: PATENTSCOPE web interface |
| Wet-lab unavailability | Time-slice + simulation validation paths |

---

## Quick Wins for Early Traction

1. **Week 1**: Ingest conductivity dataset → queryable formulation KG
2. **Week 2**: Basic link prediction on formulation→property edges
3. **Week 3**: Connect to NFDI SPARQL endpoint
4. **Week 4**: First competency question demo

---

## Next Steps

1. Set up project repository structure
2. Download and explore primary datasets (Conductivity/EIS, LIBE)
3. Implement minimal schema in RDF/OWL
4. Build first ingestion pipeline
5. Stand up graph database with provenance support
