# Practical Pilot Plan for Agentic AI–Driven Knowledge-Graph Discovery in Battery Electrolyte Design

## Executive summary

This pilot aims to demonstrate—within six months—a credible “knowledge-graph (KG) discovery loop” for electrolyte design in which an agentic AI system (i) builds and maintains a provenance-rich KG of electrolyte formulations, properties, and interphase-relevant concepts, (ii) proposes a small set of non-trivial, typed KG augmentations (candidate missing edges) that are *actionable hypotheses*, and (iii) validates or falsifies them via low-cost evidence pathways (retrospective time-slice, simulation/DFT surrogates, and—if available—small wet-lab measurements such as ionic conductivity via EIS). The pilot is considered successful if it produces at least a few validated KG augmentations that measurably improve a predictive task (e.g., conductivity model accuracy or uncertainty reduction) and are recorded with complete provenance and reproducible evaluation protocols. citeturn7view1turn7view2turn7view0turn5search1

A pragmatic scope choice for a first pilot (because open, machine-readable datasets already exist) is **non-aqueous liquid Li-ion electrolytes** focused on carbonate solvents and LiPF₆, with an initial target property of **ionic conductivity** and a secondary target of **SEI-relevant molecular decomposition/interphase species** through computed datasets like LIBE. This scope aligns tightly with existing machine-readable conductivity/EIS datasets (composition → conductivity across temperatures), autonomous electrolyte optimization literature (robotics + Bayesian optimization), and first-principles electrolyte/interphase datasets. citeturn7view1turn7view0turn7view2

Key go/no-go gates are: (a) can you ingest at least two high-value structured datasets into a consistent formulation schema; (b) can link-prediction or rule/abduction propose candidate edges that pass novelty/time-slice filters; (c) can at least one candidate edge be validated with an independently measurable effect (model lift or experiment/simulation confirmation) while maintaining full provenance and auditability. citeturn7view1turn5search1turn7view0

## Pilot objective and first-scope selection

### Concise objective

Build an end-to-end “agentic KG discovery” prototype for electrolyte design that:

- Constructs an electrolyte-centric KG from at least two structured sources and a scoped literature/patent corpus.
- Generates candidate KG augmentations (typed edges) using a combination of KG completion (embeddings/GNNs), rule mining, and constrained abductive hypothesis generation.
- Evaluates these candidate edges using predictive-task deltas and (where feasible) simulation and/or minimal wet-lab measurements.
- Curates validated edges into the KG with explicit provenance (source, method, confidence, scope), and keeps failed hypotheses as negative evidence. citeturn5search1turn7view1turn7view0

### Success criteria for a first pilot

Success criteria should be explicit and measurable (example thresholds are intentionally adjustable; the exact dataset size is **unspecified** and depends on corpus scope):

- **KG substrate**: A queryable KG with a stable formulation schema and provenance fields, containing at minimum:
  - ≥1,000 distinct “electrolyte formulation” nodes (or formulation measurements) from structured datasets and extracted corpus (range: 10³–10⁵ is plausible; exact count unspecified). citeturn7view1turn8view1
- **Discovery loop output**: ≥10 candidate augmentation edges proposed; ≥3 survive novelty/time-slice filters; ≥1–3 validated via model delta and/or experiment/simulation; all with complete provenance. citeturn5search1turn7view0
- **Model lift** (pilot-level): statistically defensible improvement on a pre-registered task (e.g., conductivity regression RMSE reduction, better-calibrated uncertainty, or improved generalization to withheld formulation region), attributable to the added edge(s) via ablations. citeturn7view1turn7view0
- **Provenance completeness**: ≥95% of new KG assertions have machine-readable provenance fields (source DOI/patent ID or dataset ID, extraction method, timestamp, agent/tool version), aligned to PROV-O concepts. citeturn5search1turn7view1

### Scope selection rationale

**Subdomain selection (since the user did not specify a single subdomain):** This plan scopes the pilot primarily to **liquid electrolytes** (carbonate solvent mixtures + LiPF₆ + a small additive set) and secondarily to **SEI formation knowledge** as encoded in computed interphase datasets. Solid electrolytes can be a later extension; including them in the first pilot increases ontology heterogeneity and measurement complexity. citeturn7view0turn7view2turn7view1

Rationale for choosing carbonate/LiPF₆ first:

- A machine-readable conductivity/EIS dataset exists for EC/PC/EMC + LiPF₆ with controlled variation of solvent ratios and salt mass, plus temperature series and derived activation energies—ideal for grounding a pilot KG and evaluation tasks. citeturn7view1
- Autonomous/robotic electrolyte optimization work demonstrates that conductivity optimization can be done efficiently over carbonate/LiPF₆ spaces using a robotic platform (“Clio”) coupled to Bayesian optimization (“Dragonfly”), providing an existence proof and design template for closed-loop workflows (even if your pilot uses lower-cost validation initially). citeturn7view0
- LIBE provides first-principles molecular and interphase species data (∼17,000 unique species, DFT-level properties), supporting simulation-only validation paths for mechanistic edges tied to SEI chemistry. citeturn7view2

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["lithium-ion battery electrolyte solvents ethylene carbonate dimethyl carbonate diagram","solid electrolyte interphase SEI schematic lithium ion battery","electrochemical impedance spectroscopy Nyquist plot electrolyte conductivity"],"num_per_query":1}

## Minimal KG schema and provenance model for electrolyte discovery

### Minimal schema design principles

A first pilot should prioritize **a small number of high-utility entity types and relations** that can be populated reliably and queried for discovery tasks. The schema must represent *formulations as first-class objects* rather than just bags of molecules, because composition is the primary control variable in electrolyte design. The battery semantics literature explicitly shows how a plain-text recipe like “1 M LiPF₆ in DMC:EC:EMC 1:1:1 + 2 wt% VC” can be converted into typed triples (e.g., electrolyte hasSolute LiPF₆; numerical value + unit attached as a property), enabling consistent machine interpretation and query. citeturn8view1

A pragmatic strategy is:

- Represent formulation as a node with structured component edges (solvents, salts, additives), each with concentration/amount and unit.
- Attach property measurements (conductivity, viscosity, electrochemical stability window proxies, impedance-derived resistance) as nodes with method metadata.
- Maintain explicit links to evidence sources: dataset row IDs, DOIs, and patent IDs. citeturn8view1turn7view1turn13view4

### Entity types

Minimum entity classes (pilot):

- **ElectrolyteFormulation**
- **Component**
  - **Solvent** (e.g., EC, PC, EMC, DMC)
  - **Salt** (e.g., LiPF₆)
  - **Additive** (e.g., VC, FEC; additive scope initially limited; exact list unspecified)
- **Molecule** (canonical chemical identity for each component; linkable to external identifiers such as PubChem CID or ontology IRIs)
- **PropertyMeasurement**
  - conductivity (S/cm), activation energy, resistance, etc.
- **MeasurementMethod**
  - EIS; temperature series; Arrhenius fit
- **CellContext** (optional in pilot; required if you move beyond bulk properties)
  - electrode materials, separator, cell format
- **InterphaseSpecies / SEISpecies** (for LIBE-driven extension)
- **EvidenceSource**
  - dataset (e.g., LIBE, conductivity dataset), paper DOI, patent document
- **ProvenanceActivity / Agent** (for extraction, transformation, inference)

The goal is not an exhaustive ontology; it is a **minimally adequate schema** to make hypotheses and validations explicit. citeturn7view1turn7view2turn5search1

### Relation types

A minimal relation set that supports discovery queries:

Formulation composition
- `hasSolvent(formulation, solvent)`
- `hasSalt(formulation, salt)`
- `hasAdditive(formulation, additive)`
- `hasComponent(formulation, component)` (generic)
- `hasAmount(component_in_formulation, value+unit)`
  - amount type: molarity, molality, mass fraction, volume fraction, wt%  
  (start with what the structured datasets provide: masses and derived concentrations; more types can be added later) citeturn7view1turn8view1

Property measurement
- `hasMeasurement(formulation, propertyMeasurement)`
- `measuresProperty(propertyMeasurement, propertyType)`
- `measuredBy(propertyMeasurement, method)`
- `measuredAt(propertyMeasurement, temperature)`
- `derivedFrom(propertyMeasurement, rawEISData)` (optional; but useful when raw spectra exist) citeturn7view1turn2search18

Interphase/SEI (LIBE-driven pilot extension)
- `decomposesTo(molecule, interphaseSpecies)` (hypothesized/validated)
- `participatesInReaction(species, reaction)` (optional; later)
- `associatedWithSEI(species, SEIConcept)` (coarse, if chem mechanisms not represented) citeturn7view2

Discovery edges (explicit hypothesis objects)
- `hypothesizedRelation(hypothesis, relationType)`
- `evidenceFor(hypothesis, evidenceSource)`
- `validatedBy(hypothesis, validationActivity)`
- `status(hypothesis, {proposed, rejected, validated})` citeturn5search1

### Provenance fields

For each asserted triple (especially inferred/hypothesized), store:

- `prov:wasDerivedFrom` (dataset DOI/row ID; paper DOI; patent ID) citeturn5search1turn7view1turn13view4
- `prov:wasGeneratedBy` (extraction activity: OCR/NLP model version; parser; ETL job ID)
- `prov:wasAttributedTo` (agent: which software component or human curator)
- Timestamp, KG version, confidence score
- Evidence snippet pointer (e.g., sentence span in paper/patent) where available
- License/usage constraints if known (important for patents and proprietary sources)

PROV-O provides a W3C-recommended vocabulary for representing provenance as entities/activities/agents, intended to support assessment of quality and trustworthiness. citeturn5search1turn5search25

## Data sources and initial corpus collection strategy

### High-value structured datasets to ingest first

These sources are ideal because they are already machine-oriented and can be converted into KG nodes/edges with minimal NLP risk.

- **Conductivity/EIS formulation dataset** (Scientific Data 2023): includes electrolyte composition in mass terms for EC/PC/EMC/LiPF₆, EIS-derived conductivity across temperatures, and metadata fields such as batch numbers, CAS numbers, SMILES, supplier, measurement settings, and derived quantities like resistance and chi-square goodness-of-fit. citeturn7view1
- **LIBE dataset** (Scientific Data 2021): ∼17,000 unique species relevant to electrolyte and interphase chemistry; DFT-level structural/thermodynamic/vibrational information; intended to improve understanding of SEI species and associated reactions. citeturn7view2turn1search4
- **Materials Project molecular “legacy” electrolyte data**: documents that early molecular properties on the platform came from the Electrolyte Genome Project through JCESR, providing computed electrochemical/redox properties (methodology notes include functional/basis choices). This can provide additional computed molecular nodes/attributes for solvents/additives when relevant. citeturn9view3
- **NFDI4Chem ecosystem (metadata KGs)**:
  - A daily-updated RADAR4Chem knowledge graph is publicly available as Turtle, and RADAR supports a SPARQL endpoint. citeturn7view4turn12view2
  - NFDI4Chem’s search service exposes a SPARQL endpoint and sample queries (e.g., dataset lookup by InChIKey), which is directly useful for connecting your electrolyte KG to chemistry datasets in the NFDI ecosystem. citeturn12view0
  - The CHEMOTION KG construction pipeline describes harvesting experimental metadata via API in JSON-LD, converting to RDF, and aligning schema.org metadata to upper ontologies using SPARQL CONSTRUCT queries; it explicitly reuses NFDICore and ChEBI, a useful pattern library for your KG builder. citeturn8view0
- **MatKG** (Scientific Data 2024): a large literature-derived materials science KG (serialized in CSV/RDF) that can serve as a broader context for materials entities and methods if you decide to connect electrolyte and electrode materials concepts later. citeturn3search2
- **OntoKin** (JCIM 2019/2020): a domain ontology for chemical kinetic reaction mechanisms; not electrolyte-specific, but relevant if you later represent decomposition/SEI reactions as a mechanistic KG rather than coarse “decomposesTo” edges. citeturn3search3turn3search6
- **OntoChem** (commercial): relevant primarily as a benchmark for “industrial-strength” chemical text mining and normalization; note this is not necessarily open, but its scale and semantic indexing claims illustrate what a mature chemistry text-mining stack looks like. citeturn5search4turn5search19

### Patents and literature (scoped corpus)

For the pilot, the corpus should be constrained and reproducible.

**Patents**
- US patents: PatentsView PatentSearch API provides a JSON query language with date filters and full-text query operators (`_text_all`, `_text_any`, `_text_phrase`). Constraints: API keys are required and (per documentation) new API key grants may be temporarily suspended, which is a practical risk; plan alternative access if needed. citeturn13view4turn2search21
- International patents: WIPO PATENTSCOPE provides access to PCT applications and national/regional collections via web search; it is a primary route for broad patent retrieval if an API path is unavailable. citeturn2search5turn2search13

**Literature**
- Start with review-heavy and method-heavy papers (to stabilize terminology) and then expand into primary articles.
- For electrolyte automation/closed-loop context, anchor on robotic/BO electrolyte papers (e.g., non-aqueous conductivity optimization and full-cell autonomous electrolyte exploration). citeturn7view0turn13view0
- For semantic representation of electrolyte recipes and controlled vocabularies, use battery semantics/ontology work showing explicit electrolyte formulation graphs and JSON-LD implementations. citeturn8view1turn4search8

### Suggested initial corpus queries and filters

Below are concrete, reproducible query templates (adapt these to your retrieval tool; exact database endpoints are unspecified).

```text
Literature keyword query templates (2015–2025, English, batteries context):

A. Liquid electrolyte formulations:
("electrolyte" AND (solvent OR "salt" OR additive) AND ("LiPF6" OR "LiTFSI" OR "LiFSI") AND
("ethylene carbonate" OR "dimethyl carbonate" OR "ethyl methyl carbonate" OR "propylene carbonate") AND
("ionic conductivity" OR impedance OR EIS))

B. Additives and SEI:
(("electrolyte additive" OR additive) AND ("SEI" OR "solid electrolyte interphase") AND
("vinylene carbonate" OR VC OR "fluoroethylene carbonate" OR FEC OR "lithium difluoro(oxalato)borate" OR LiDFOB))

C. High-concentration / localized high concentration electrolytes:
(("high concentration electrolyte" OR "localized high concentration") AND (LiFSI OR LiTFSI) AND (battery OR "Li-ion"))

D. Safety/compatibility:
(("electrolyte" AND flammable) OR ("HF" AND LiPF6) OR ("gas evolution" AND electrolyte))

Patent query templates:

1) PatentsView date window (granted patents):
q={
  "_and":[
    {"_gte":{"patent_date":"2015-01-01"}},
    {"_lte":{"patent_date":"2025-12-31"}},
    {"_text_any":{"patent_title":"battery electrolyte solvent salt additive SEI"}},
    {"_not":{"patent_type":"design"}}
  ]
}
f=["patent_id","patent_date","patent_title","patent_num_claims","patent_num_times_cited_by_us_patents"]

2) PATENTSCOPE advanced-search template (conceptual):
(electrolyte AND (solvent OR salt OR additive OR "solid electrolyte interphase" OR SEI))
AND (lithium OR "Li-ion" OR "lithium ion")
AND PD:[2015-01-01 TO 2025-12-31]
```

PatentsView’s documentation provides the operators used above (`_gte/_lte` on `patent_date`, and `_text_any` on text fields like `patent_title`) and emphasizes using `_text*` operators for text fields. citeturn13view4turn15view1turn15view2  
PATENTSCOPE is an official portal for searching international and national patent collections, including PCT applications. citeturn2search5turn2search13

## Agent pipeline, tools, and prototype architecture

### Prototype architecture diagram

```mermaid
flowchart LR
  subgraph Sources
    D1[Structured datasets\n- Conductivity/EIS dataset\n- LIBE\n- MP legacy molecules]
    L1[Literature corpus\n(2015–2025)]
    P1[Patents corpus\n(2015–2025)]
    N1[NFDI4Chem endpoints\n(RADAR4Chem KG, SPARQL)]
  end

  subgraph Substrate
    KG[(Electrolyte KG\nRDF + embeddings + versioning)]
    PV[(Provenance store\nPROV-O aligned)]
    ART[(Artifacts\nprompts, configs, models)]
  end

  subgraph Agents
    A1[KG Builder\nETL + extraction + entity linking]
    A2[Explorer\nqueries + subgraph mining]
    A3[Hypothesis Agent\nKGE/GNN + rules + abduction]
    A4[Evaluator\npredictive tasks + simulation]
    A5[Experiment Planner\nAL/BO + constraints]
    A6[Executor\nlab/workflow APIs]
    A7[Curator\nalignment + review + merge]
  end

  subgraph Validation Backends
    SIM[Simulation\nDFT/MD surrogates\ntrained on LIBE/MP]
    LAB[Wet-lab (optional)\nEIS conductivity, CV\nresources unspecified]
  end

  D1 --> A1
  L1 --> A1
  P1 --> A1
  N1 --> A1

  A1 --> KG
  A1 --> PV
  A1 --> ART

  KG --> A2 --> A3 --> A4
  A4 -->|needs compute| SIM --> A4
  A4 -->|needs data| A5 --> A6 --> LAB --> A1

  A7 <--> KG
  A7 <--> PV
  A7 <--> ART
```

This architecture explicitly mirrors the structure of successful autonomous electrolyte workflows (robotics + Bayesian optimization) while adding a KG substrate that encodes hypotheses as graph updates and preserves provenance through the loop. citeturn7view0turn13view0turn5search1

### Agent roles, minimal implementations, and success criteria

| Agent role | Inputs | Outputs | Minimal algorithms/tools | Immediate success criteria |
|---|---|---|---|---|
| KG Builder | Structured datasets; PDFs/HTML; patents metadata/full text; NFDI SPARQL datasets | Normalized entities (molecules/formulations); typed triples; provenance attachments | Start with structured ingestion (CSV/JSON) for the conductivity dataset and LIBE; represent formulations using typed triples as in ontology-based battery semantics; adopt PROV-O fields for all assertions. citeturn7view1turn7view2turn8view1turn5search1 | ≥2 datasets ingested; consistency checks pass; ≥95% triples have provenance fields |
| Explorer | KG snapshot + embeddings | Candidate “gaps”: missing relations, low-coverage regions, contradictory nodes | SPARQL queries for competency questions; embedding-neighborhood analysis; “distant node” discovery along formulation→property→interphase paths | Produces a ranked list of candidate hypothesis areas with traceable rationale |
| Hypothesis Agent | Candidate gaps; relation schemas; constraints | Proposed KG augmentations (typed edges) with confidence and explanations | KG completion models (embeddings/GNN) + rule mining + constrained abduction (keep hypothesis space small and typed) | ≥10 candidate edges; ≥3 pass novelty/time-slice filters |
| Evaluator | Proposed edges; predictive tasks; holdout sets; simulation resources | Predictive delta; robustness/ablation evidence; simulation plausibility | (1) Conductivity regression/classification using formulation features from KG; (2) simulation-only checks using LIBE/MP computed properties; (3) ablation to attribute lift to the new edge | Demonstrates measurable lift on a pre-registered metric and stability across splits citeturn7view1turn7view2turn9view3 |
| Experiment Planner | Top candidate edges; model uncertainty; budget; constraints | Minimal experimental plan (batch) + stopping rules | Bayesian optimization / active learning inspired by closed-loop electrolyte studies; constrain to safe, feasible compositions. citeturn7view0turn13view0 | Plan selects ≤N experiments (N small; resources unspecified) with high expected information gain |
| Executor | Protocol plan + instrument interfaces | Raw EIS/CV data + metadata + execution logs | If lab automation exists: SiLA 2 for instrument connectivity and/or PyLabRobot for liquid-handling orchestration; protocol abstraction via Autoprotocol and/or AnIML-like outputs as metadata containers. citeturn8view4turn1search18turn1search7turn6search2turn6search1 | Runs complete with audit trails; data captured in machine-readable form |
| Curator | New evidence; conflicting assertions; ontology mappings | Accepted/rejected edges; KG version update; provenance/citation integrity | Human-in-the-loop review checkpoints; reconcile units/identifiers; enforce schema constraints | ≥1 validated edge merged; rejected edges retained with negative evidence |

Notes on tool choices:
- SiLA 2 is explicitly designed as an open connectivity standard for lab automation built atop open communication protocols and a thin domain-specific layer (concepts/vocabulary/taxonomy), making it a reasonable integration target if you have heterogeneous instruments. citeturn8view4turn6search0
- PyLabRobot provides an open-source, hardware-agnostic Python interface for liquid-handling robots and related equipment, supporting shared, programmable workflows. citeturn1search18turn1search7
- Autoprotocol is a formalizable protocol language intended to reduce ambiguity in experimental procedures (initially life-science-centric but useful as a protocol abstraction concept). citeturn6search2turn1search2
- AnIML is positioned as an ASTM E13.15–sanctioned XML standard effort for analytical chemistry data interchange/archiving; it can inform how you store analytical outputs and metadata even if you do not implement full AnIML in the pilot. citeturn6search1turn6search17turn6search9

## Low-cost validation strategies and pilot evaluation metrics

### Validation strategy stack

A credible six-month pilot should not rely solely on wet-lab availability (which is **unspecified**). Instead, plan three tiers that can be executed independently.

**Retrospective time-slice validation (lowest cost; high credibility early)**
- Build KG from literature/patents up to cutoff year T (e.g., 2019 or 2020; exact choice unspecified).
- Ask the Hypothesis Agent to propose edges that would “predict” relationships appearing in T+1…T+k papers/patents.
- Score: novelty hit rate and ranking quality for edges that later became explicit in the literature/patents.  
This is a standard way to evaluate discovery-like systems without new experiments and is compatible with your “KG augmentation” framing. citeturn13view4turn15view1

**Simulation-only validation (moderate cost; mechanistic anchoring)**
- Use LIBE for SEI-related molecular plausibility checks, since it was designed to provide first-principles data for electrolyte/interphase species and reactions. citeturn7view2
- Use Materials Project legacy molecular data (Electrolyte Genome) for redox/electrochemical property priors of candidate solvents/additives where relevant. citeturn9view3
- Validation notion: a hypothesized edge (e.g., additive→favorable decomposition motif, or formulation→reduced reactive propensity) should be consistent with computed property constraints (e.g., redox stability proxies, reaction energetics proxies; exact proxies unspecified because they depend on your modeling choice). citeturn7view2turn9view3

**Small wet-lab validation (optional; highest evidential weight)**
If minimal lab resources exist (unspecified), run a small campaign to validate *a small number of hypotheses* (not to “optimize the electrolyte” yet). Use methods that map cleanly to the existing dataset formats:

- **Ionic conductivity via EIS**: the Scientific Data dataset already uses EIS across temperature series and derives conductivity, resistance, and Arrhenius activation energy in machine-readable form. Design your pilot protocol so your data can be ingested into the same schema. citeturn7view1turn2search18
- **Cyclic voltammetry (CV)** as a low-cost screen for electrochemical stability trends (pilot-level, not definitive; exact electrode choices and voltage ranges unspecified).
- **EIS on symmetric cells** for electrolyte resistance and interface-related semicircles if relevant; EIS is widely used and tutorials/reviews summarize fundamentals and interpretation frameworks. citeturn2search18turn2search12

### Recommended pilot metrics

Use a layered metric set so that “discovery” does not collapse into “accuracy improvement only.”

**KG/task metrics**
- Link prediction: MRR / Hits@k on held-out triples for relations like hasComponent/hasAmount/hasMeasurement and for hypothesized scientific relations (where ground truth exists).
- Extraction quality: precision/recall on a hand-labeled seed set of electrolyte recipes (seed size unspecified). citeturn8view1

**Downstream predictive metrics**
- ΔRMSE / ΔMAE for conductivity regression on the machine-readable composition dataset, with strict held-out splits (e.g., hold out regions of solvent ratio space; exact split protocol pre-registered). citeturn7view1turn7view0
- Calibration metrics for uncertainty estimates (if you implement uncertainty-aware models; details unspecified).

**Discovery-specific metrics**
- **Novelty/time-slice hit rate**: fraction of top-N proposed edges that appear in post-cutoff literature/patents.
- **Attribution via ablation**: demonstrate that adding the hypothesized edge is responsible for model improvement (remove the edge and show improvement disappears).
- **Provenance completeness** (target ≥95%): fraction of assertions with PROV-O–style provenance fields. citeturn5search1

**Compression proxy (pilot-friendly)**
True MDL evaluation may be heavy; a pilot proxy is:
- “Explanation compression” = performance gain per new edge (or per byte of added schema complexity), with penalties for adding many weak edges. This aligns with your “discovery as minimal KG augmentation” framing and discourages trivial augmentation. (Exact formalism unspecified; treat as a pre-registered heuristic in pilot.)

### Operational criterion: when a KG augmentation counts as “discovery” in this pilot

A KG augmentation (edge or relation refinement) qualifies as pilot “discovery” if all are satisfied:

1) **Typed, falsifiable hypothesis edge** (not just a similarity link): e.g., “Additive X increases conductivity in formulation family Y under constraint Z,” or “Molecule A decomposes preferentially to SEI species class B.” citeturn8view1turn7view2  
2) **Novelty**: edge is not present in pre-cutoff KG and is not a synonym duplication (checked by time-slice filtration and entity resolution). citeturn13view4turn15view1  
3) **Predictive consequence**: adding the edge changes a pre-registered model outcome (improved prediction or reduced uncertainty) with ablation evidence. citeturn7view1turn7view0  
4) **Independent corroboration**: either (a) appears in post-cutoff literature/patent set (retrospective), or (b) passes simulation-based plausibility (LIBE/MP consistency), or (c) is directly validated by a small experiment. citeturn7view2turn9view3turn7view1  
5) **Provenanced integration**: merged into KG with a complete provenance record using PROV-O concepts. citeturn5search1

## Six-month milestone plan with resource ranges

### Prioritized milestones (0–6 months)

**Month 0–1: Pilot scoping and schema lock**
- Write a short “pilot spec” with: chosen subdomain (liquid carbonate + LiPF₆; additives limited; SEI extension via LIBE), pre-registered evaluation tasks, and a frozen minimal schema (entities/relations + provenance). Ground formulation modeling in the ontology-based recipe graph approach described in battery semantics work. citeturn8view1
- Define competency questions (example): “Find all formulations with solvent EC fraction in [x,y] and LiPF₆ mass in [a,b] and return conductivity at 25°C.” (Exact CQ list unspecified.) citeturn7view1

**Month 1–2: Structured ingestion baseline**
- Ingest the conductivity/EIS dataset as the backbone (formulation nodes + measurement nodes + metadata fields). citeturn7view1
- Ingest LIBE into a “molecule/interphase species” subgraph with computed properties and identifiers. citeturn7view2
- Optional: ingest Materials Project legacy molecular electrolyte data fields relevant to your solvents/additives list. citeturn9view3
- Stand up KG store + versioning + provenance store (PROV-O aligned). citeturn5search1

**Month 2–3: Extraction from a small corpus + NFDI connections**
- Connect to NFDI endpoints (RADAR4Chem KG ttl + SPARQL) and integrate dataset metadata nodes relevant to electrolytes; optionally link to Chemotion-KG patterns for schema.org→BFO/NFDICore alignment. citeturn12view2turn8view0turn7view4
- Collect a small, reproducible literature/patent corpus using the queries above; implement a conservative extraction pipeline (start with structured recipe extraction: solvents/salts/additives/ratios; avoid deep mechanistic relation extraction early). citeturn8view1turn13view4

**Month 3–4: Hypothesis generation MVP**
- Train baseline KG embeddings / GNN completion models on the KG snapshot; produce candidate missing edges in a small set of relation types (e.g., additive→property impact; solvent ratio regime→conductivity trend; molecule→SEI species class). (Exact model choice unspecified; keep it simple and well-instrumented.)
- Add a rule-mining layer for interpretable candidate edges (“if formulation contains X and Y at Z range, then conductivity high”) using the structured conductivity dataset as training signal. citeturn7view1turn7view0

**Month 4–5: Evaluation and time-slice experiment**
- Run retrospective time-slice evaluation against later papers/patents; quantify novelty hit rate and ranking quality.
- Run predictive-task evaluation (conductivity) with strict ablations (with/without augmented edges). citeturn7view1turn13view4turn15view1

**Month 5–6: Optional wet-lab mini-validation**
- If lab access exists (unspecified), run 5–15 carefully selected electrolyte formulations to validate 1–3 top hypotheses using EIS conductivity and optionally CV screening.
- Ensure protocol and metadata are captured in a machine-readable structure; consider protocol abstraction via Autoprotocol concepts and analytical data containers inspired by AnIML. citeturn6search2turn6search1turn7view1turn2search18

### Resource estimates (open-ended ranges)

Because dataset scale, lab availability, and compute constraints are unspecified, ranges are intentionally broad but realistic for a six-month pilot:

- **Personnel**: 4–8 FTE total
  - 1 KG/data engineer (schema, RDF/SPARQL, provenance/versioning)
  - 1 ML engineer/scientist (embeddings, GNNs, predictive models, evaluation)
  - 1 NLP/IE engineer (recipe extraction + entity resolution)
  - 0.5–1 domain scientist (electrolytes/SEI)
  - 0–2 lab automation/experimentalists (only if wet-lab is in scope) citeturn7view0turn7view1
- **Compute**: 1,000–20,000 GPU-hours total
  - Lower end if you rely mainly on classical ML + small embeddings
  - Higher end if you train multiple ablations and uncertainty models (exact compute depends on model choices; unspecified)  
- **Dataset size**: unspecified; expect
  - 10³–10⁵ formulation-measurement records (depending on corpus expansion beyond the base dataset)
  - 10⁴–10⁵ molecular/species nodes if LIBE and additional molecular sources are integrated citeturn7view2turn7view1

### Suggested “chart” artifacts to produce during the pilot

- Discovery funnel chart: candidate edges → novelty-passing edges → validated edges → merged edges.
- Lift vs. edges-added chart: predictive improvement per validated augmentation (compression proxy).
- Provenance completeness dashboard: % triples with complete PROV-O records per data source. citeturn5search1

## Risks, mitigations, quick wins, and go/no-go criteria

### Key risks and mitigations

**False positives from KG completion**
- Risk: embedding/GNN link prediction proposes plausible-but-wrong edges, especially when the KG is incomplete or biased.
- Mitigation: constrain relation types; require typed hypotheses; enforce novelty filters; demand ablation-based attribution; maintain rejected hypotheses as negative evidence. citeturn7view0turn15view1

**Ontology mismatch / entity resolution failures**
- Risk: the same chemical appears under many names; formulations differ in how ratios and units are reported.
- Mitigation: treat formulation as a node with normalized unit-bearing attributes; adopt controlled-vocabulary recipe modeling (as shown in the battery semantics graph examples); link chemicals to canonical identifiers and store synonyms as metadata. citeturn8view1turn7view1

**Provenance debt**
- Risk: without rigorous provenance and versioning, “continuous KG augmentation” becomes untrustworthy and hard to audit.
- Mitigation: PROV-O-aligned provenance is mandatory for each assertion; automate provenance completeness checks in CI; snapshot KG versions for every evaluation run. citeturn5search1turn5search25

**Patents access constraints**
- Risk: PatentsView Search API requires an API key and documentation notes temporary suspension of new API key grants; that can block programmatic patent retrieval in the pilot window.
- Mitigation: (a) start with already-accessible patent corpora; (b) use PATENTSCOPE web retrieval for a smaller patent set; (c) treat patents as optional in the earliest pilot stage. citeturn13view4turn2search5

**Safety/ethics (electrolyte handling)**
- Risk: non-aqueous electrolytes involve flammability and reactive salts; autonomous execution without safeguards is inappropriate in early pilots.
- Mitigation: explicitly gate any wet-lab execution behind human approval; constrain formulation space to known-safe handling envelopes; log all actions; treat lab automation support (SiLA/PyLabRobot) as optional, later-stage integration. citeturn8view4turn1search18turn7view0

### Recommended quick wins

- **Quick win**: reproduce and extend a conductivity predictive model using the machine-readable conductivity/EIS dataset, then show a measurable improvement when the KG explicitly encodes formulation semantics rather than treating compositions as flat feature vectors. citeturn7view1turn8view1
- **Quick win**: integrate LIBE molecules into the KG and demonstrate that the Hypothesis Agent can propose new “decomposesTo / SEI-species-class” edges, validated by checking consistency with computed properties and (retrospectively) later literature mentions. citeturn7view2
- **Quick win**: connect to NFDI endpoints (RADAR4Chem KG and SPARQL) and demonstrate cross-resource querying (e.g., find datasets by InChIKey and link to electrolyte components). citeturn12view0turn12view2

### Go/no-go criteria at month 3 and month 6

**Month 3 go/no-go**
- GO if: structured ingestion works (conductivity dataset + LIBE) and you can query formulations/properties reliably; provenance completeness ≥90%. citeturn7view1turn7view2turn5search1
- NO-GO if: entity resolution fails systematically (e.g., you cannot reliably normalize solvent/salt identities and units), or provenance is too incomplete to trust evaluation outcomes. citeturn8view1turn5search1

**Month 6 go/no-go**
- GO if: ≥1 KG augmentation meets the operational “discovery” criteria (novel, typed, predictive consequence + independent corroboration), and the evaluation is reproducible with frozen KG snapshots and ablation proofs.
- NO-GO if: all proposed edges collapse into trivial synonymy/duplication, or predictive lifts are not attributable to KG augmentation (i.e., gains come only from generic retraining without structurally meaningful edges). citeturn7view0turn15view1

### Key resource links (convenience list)

```text
Chemotion-KG pipeline (arXiv HTML): https://arxiv.org/html/2509.01536v1
RADAR4Chem KG + SPARQL: https://radar.products.fiz-karlsruhe.de/en/radarabout/radar4chem
NFDI4Chem SPARQL editor: https://search.nfdi4chem.de/sparql

LIBE dataset (Scientific Data): https://www.nature.com/articles/s41597-021-00986-9
LIBE dataset files (Figshare): https://figshare.com/articles/dataset/Lithium-Ion_Battery_Electrolyte_LIBE_dataset/14226464

Conductivity/EIS dataset (Scientific Data): https://www.nature.com/articles/s41597-023-01936-3

Materials Project API docs: https://docs.materialsproject.org/downloading-data/using-the-api
Materials Project molecules legacy (Electrolyte Genome context): https://docs.materialsproject.org/methodology/molecules-methodology/legacy-data

MatKG (Scientific Data): https://www.nature.com/articles/s41597-024-03039-z

OntoKin (ACS JCIM): https://pubs.acs.org/doi/10.1021/acs.jcim.9b00960
OntoChem (company scale claim context): https://www.digital-science.com/blog/2023/06/digital-science-boosts-pharma-industry-support-following-ontochem-acquisition/

PatentsView Search API reference: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
WIPO PATENTSCOPE: https://www.wipo.int/en/web/patentscope

Autoprotocol spec: https://autoprotocol.org/specification/
SiLA 2 standard overview: https://sila-standard.com/standards/
PyLabRobot (paper + docs): https://www.sciencedirect.com/science/article/pii/S2666998623001709 ; https://docs.pylabrobot.org/

PROV-O (W3C): https://www.w3.org/TR/prov-o/
AnIML overview (official): https://www.animl.org/overview
```

