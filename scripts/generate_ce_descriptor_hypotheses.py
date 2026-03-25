#!/usr/bin/env python3
"""
Generate descriptor-based hypotheses for coulombic efficiency (CE).

This script focuses on experimental CE only and mines hypotheses of the form:
    descriptor X increases/decreases CE

Descriptor families:
1) Composition descriptors (counts of solvents/salts/additives, etc.)
2) Computable structure descriptors from SMILES (lightweight, no RDKit needed)
3) Formulation-level property descriptors (e.g., ionic_conductivity mean when present)
4) Component-presence descriptors (contains specific component)
"""

import argparse
import gzip
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


TARGET_PROPERTY = "coulombic_efficiency"
COMPONENT_RELS = {"hasSolvent", "hasSalt", "hasAdditive"}


@dataclass
class DescriptorHypothesis:
    hypothesis_id: str
    descriptor_key: str
    descriptor_name: str
    descriptor_type: str
    direction: str
    confidence: float
    score: float
    evidence: dict
    explanation: str


def _load_kg(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    with open(path) as f:
        return json.load(f)


def _is_ml_ce_method(method: Optional[dict]) -> bool:
    if not method:
        return False
    name = str(method.get("name", "")).lower()
    description = str(method.get("description", "")).lower()
    params = method.get("parameters") or {}
    pred_type = str(params.get("prediction_type", "")).lower()
    model = str(params.get("model", "")).lower()
    return (
        "ml-predicted-ce" in name
        or pred_type == "virtual_screening"
        or "predicted" in name
        or "predicted" in description
        or "chemprop" in model
        or "lightgbm" in model
    )


def _experimental_ce_measurement_ids(kg: dict) -> set:
    methods = kg.get("methods", {})
    measurements = kg.get("measurements", {})
    ml_ce_method_ids = {
        method_id for method_id, method in methods.items() if _is_ml_ce_method(method)
    }
    return {
        meas_id
        for meas_id, meas in measurements.items()
        if meas.get("property_type") == TARGET_PROPERTY and meas.get("method_id") not in ml_ce_method_ids
    }


def _safe_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _smiles_features(smiles: Optional[str]) -> dict:
    if not smiles:
        return {}

    s = smiles
    length = len(s)
    aromatic_chars = sum(1 for ch in s if ch in "cnosp")
    ring_digits = sum(1 for ch in s if ch.isdigit())
    branch_tokens = s.count("(") + s.count(")")
    dbl = s.count("=")
    triple = s.count("#")

    halogens = s.count("F") + s.count("Cl") + s.count("Br") + s.count("I")
    oxy = s.count("O")
    nit = s.count("N")
    sulfur = s.count("S")
    phosphorus = s.count("P")

    return {
        "smiles_len": float(length),
        "smiles_aromatic_ratio": aromatic_chars / length if length > 0 else 0.0,
        "smiles_ring_digit_count": float(ring_digits),
        "smiles_branch_token_count": float(branch_tokens),
        "smiles_double_bond_count": float(dbl),
        "smiles_triple_bond_count": float(triple),
        "smiles_halogen_count": float(halogens),
        "smiles_o_count": float(oxy),
        "smiles_n_count": float(nit),
        "smiles_s_count": float(sulfur),
        "smiles_p_count": float(phosphorus),
    }


def _label_for_descriptor_key(key: str) -> tuple:
    """
    Map internal descriptor keys to chemistry-facing labels.
    Returns: (label, interpretation)
    """
    descriptor_map = {
        "desc:all:n_components": (
            "Number of formulation components",
            "Compositional complexity (count of distinct components).",
        ),
        "desc:all:n_solvents": (
            "Number of solvent components",
            "Diversity of solvent species in the formulation.",
        ),
        "desc:all:n_salts": (
            "Number of salt components",
            "Diversity of salt species in the formulation.",
        ),
        "desc:all:n_additives": (
            "Number of additive components",
            "Additive richness in the formulation.",
        ),
        "desc:all:has_additive": (
            "Additive presence",
            "Binary indicator of whether any additive is present.",
        ),
        "desc:all:mw_mean": (
            "Mean molecular weight (all components)",
            "Average molecular weight (g/mol) across all components in the formulation.",
        ),
        "desc:all:mw_max": (
            "Maximum molecular weight (all components)",
            "Largest molecular weight (g/mol) among all components in the formulation.",
        ),
        "desc:all:smiles_len_mean": (
            "Average molecular graph string length (all components)",
            "Proxy for molecular size/complexity from SMILES length.",
        ),
        "desc:all:smiles_aromatic_ratio_mean": (
            "Average aromatic character index (all components)",
            "Fraction of aromatic tokens in SMILES; proxy for aromaticity.",
        ),
        "desc:all:smiles_ring_digit_count_mean": (
            "Average ring topology index (all components)",
            "Count of ring-closure markers in SMILES; proxy for ring-rich structures.",
        ),
        "desc:all:smiles_branch_token_count_mean": (
            "Average molecular branching index (all components)",
            "Count of SMILES branch markers '()'; proxy for structural branching.",
        ),
        "desc:all:smiles_double_bond_count_mean": (
            "Average unsaturation (double-bond) index (all components)",
            "Number of '=' tokens in SMILES; proxy for pi-bond unsaturation.",
        ),
        "desc:all:smiles_triple_bond_count_mean": (
            "Average triple-bond index (all components)",
            "Number of '#' tokens in SMILES; proxy for strong unsaturation motifs.",
        ),
        "desc:all:smiles_halogen_count_mean": (
            "Average halogen substitution index (all components)",
            "Count of F/Cl/Br/I tokens; proxy for halogenation level.",
        ),
        "desc:all:smiles_o_count_mean": (
            "Average oxygen atom count index (all components)",
            "Count of O tokens; proxy for oxygenated functional groups.",
        ),
        "desc:all:smiles_n_count_mean": (
            "Average nitrogen atom count index (all components)",
            "Count of N tokens; proxy for nitrogen-containing motifs.",
        ),
        "desc:all:smiles_s_count_mean": (
            "Average sulfur atom count index (all components)",
            "Count of S tokens; proxy for sulfur-containing motifs.",
        ),
        "desc:all:smiles_p_count_mean": (
            "Average phosphorus atom count index (all components)",
            "Count of P tokens; proxy for phosphorus-containing motifs.",
        ),
    }

    if key in descriptor_map:
        return descriptor_map[key]

    if key.startswith("prop:"):
        prop = key.replace("prop:", "").replace("_mean", "")
        label = "Formulation-average %s" % prop.replace("_", " ")
        interp = "Average measured %s for the same formulation." % prop.replace("_", " ")
        return label, interp

    # Generic parser for scoped descriptors: desc:<scope>:<feature>
    if key.startswith("desc:"):
        parts = key.split(":")
        if len(parts) == 3:
            _, scope, feature = parts
            scope_label_map = {
                "all": "all components",
                "solvent": "solvent components",
                "salt": "salt components",
                "additive": "additive components",
            }
            feature_label_map = {
                "mw_mean": "mean molecular weight",
                "mw_max": "maximum molecular weight",
                "smiles_len_mean": "average molecular graph string length",
                "smiles_aromatic_ratio_mean": "average aromatic character index",
                "smiles_ring_digit_count_mean": "average ring topology index",
                "smiles_branch_token_count_mean": "average molecular branching index",
                "smiles_double_bond_count_mean": "average unsaturation (double-bond) index",
                "smiles_triple_bond_count_mean": "average triple-bond index",
                "smiles_halogen_count_mean": "average halogen substitution index",
                "smiles_o_count_mean": "average oxygen atom count index",
                "smiles_n_count_mean": "average nitrogen atom count index",
                "smiles_s_count_mean": "average sulfur atom count index",
                "smiles_p_count_mean": "average phosphorus atom count index",
                "n_components": "number of components",
                "n_solvents": "number of solvent components",
                "n_salts": "number of salt components",
                "n_additives": "number of additive components",
                "has_additive": "additive presence",
            }
            scope_label = scope_label_map.get(scope, scope)
            feat_label = feature_label_map.get(feature, feature.replace("_", " "))
            label = "%s (%s)" % (feat_label[:1].upper() + feat_label[1:], scope_label)
            interp = "Descriptor computed using %s within each formulation." % scope_label
            return label, interp

    return key, "Descriptor derived from KG features."


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks for ties, 1-based ranks."""
    sorter = np.argsort(a, kind="mergesort")
    inv = np.empty_like(sorter)
    inv[sorter] = np.arange(len(a))
    arr_sorted = a[sorter]

    ranks = np.zeros(len(a), dtype=float)
    i = 0
    while i < len(a):
        j = i + 1
        while j < len(a) and arr_sorted[j] == arr_sorted[i]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        ranks[i:j] = avg_rank
        i = j

    return ranks[inv]


def _corr_spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    rx = _rankdata(x)
    ry = _rankdata(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def _bootstrap_sign_confidence(
    x: np.ndarray,
    y: np.ndarray,
    n_boot: int,
    rng: np.random.Generator,
) -> tuple:
    n = len(x)
    corr = _corr_spearman(x, y)
    if n < 3:
        return 0.0, corr, 0.0, 0.0

    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = _corr_spearman(x[idx], y[idx])

    if corr >= 0:
        conf = float(np.mean(boots > 0.0))
    else:
        conf = float(np.mean(boots < 0.0))
    ci_low, ci_high = np.percentile(boots, [2.5, 97.5])
    return conf, corr, float(ci_low), float(ci_high)


def _build_dataset(kg: dict) -> tuple:
    """
    Returns:
        rows: list[dict], one per formulation with experimental CE
        component_presence: dict[component_id, list[int]]
    """
    relations = kg.get("relations", [])
    measurements = kg.get("measurements", {})
    molecules = kg.get("molecules", {})
    exp_ce_ids = _experimental_ce_measurement_ids(kg)

    form_components = {}
    form_components_by_type = {}
    form_measurements = {}
    for subj, rel, obj in relations:
        if rel in COMPONENT_RELS:
            form_components.setdefault(subj, set()).add(obj)
            form_components_by_type.setdefault(
                subj,
                {"solvent": set(), "salt": set(), "additive": set()},
            )
            if rel == "hasSolvent":
                form_components_by_type[subj]["solvent"].add(obj)
            elif rel == "hasSalt":
                form_components_by_type[subj]["salt"].add(obj)
            elif rel == "hasAdditive":
                form_components_by_type[subj]["additive"].add(obj)
        elif rel == "hasMeasurement" and obj in measurements:
            form_measurements.setdefault(subj, []).append(obj)

    rows = []
    for form_id, meas_ids in form_measurements.items():
        ce_vals = []
        non_ce_vals = {}
        for mid in meas_ids:
            m = measurements.get(mid, {})
            pt = m.get("property_type")
            val = _safe_float(m.get("value"))
            if pt is None or val is None:
                continue
            if mid in exp_ce_ids and pt == TARGET_PROPERTY:
                ce_vals.append(val)
            elif pt != TARGET_PROPERTY:
                non_ce_vals.setdefault(pt, []).append(val)

        if not ce_vals:
            continue

        comps = form_components.get(form_id, set())
        if not comps:
            continue

        row = {
            "formulation_id": form_id,
            "ce_value": float(np.mean(ce_vals)),
            "components": sorted(comps),
        }

        typed = form_components_by_type.get(
            form_id, {"solvent": set(), "salt": set(), "additive": set()}
        )
        scopes = {
            "all": set(comps),
            "solvent": set(typed.get("solvent", set())),
            "salt": set(typed.get("salt", set())),
            "additive": set(typed.get("additive", set())),
        }

        row["desc:all:n_components"] = float(len(scopes["all"]))
        row["desc:all:n_solvents"] = float(len(scopes["solvent"]))
        row["desc:all:n_salts"] = float(len(scopes["salt"]))
        row["desc:all:n_additives"] = float(len(scopes["additive"]))
        row["desc:all:has_additive"] = 1.0 if len(scopes["additive"]) > 0 else 0.0

        for scope_name, scope_components in scopes.items():
            if not scope_components:
                continue
            mw_values = []
            smiles_feat_acc = {}
            smiles_feat_n = {}
            for cid in scope_components:
                mol = molecules.get(cid, {})
                mw = _safe_float(mol.get("molecular_weight"))
                if mw is not None:
                    mw_values.append(mw)

                feats = _smiles_features(mol.get("smiles"))
                for k, v in feats.items():
                    smiles_feat_acc[k] = smiles_feat_acc.get(k, 0.0) + float(v)
                    smiles_feat_n[k] = smiles_feat_n.get(k, 0) + 1

            if mw_values:
                row["desc:%s:mw_mean" % scope_name] = float(np.mean(mw_values))
                row["desc:%s:mw_max" % scope_name] = float(np.max(mw_values))

            for k, total in smiles_feat_acc.items():
                n = smiles_feat_n.get(k, 1)
                row["desc:%s:%s_mean" % (scope_name, k)] = float(total / n)

        # Property descriptors attached to the same formulation (if present)
        for prop, vals in non_ce_vals.items():
            if vals:
                row["prop:%s_mean" % prop] = float(np.mean(vals))

        rows.append(row)

    # Component-presence descriptors (binary)
    component_presence = {}
    if rows:
        all_components = sorted({c for r in rows for c in r["components"]})
        for cid in all_components:
            component_presence[cid] = [1 if cid in r["components"] else 0 for r in rows]

    return rows, component_presence


def _mine_hypotheses(
    kg: dict,
    rows: list,
    component_presence: dict,
    min_samples: int,
    min_abs_corr: float,
    min_confidence: float,
    min_component_support: int,
    n_boot: int,
    top_k: int,
    seed: int,
) -> list:
    if not rows:
        return []

    rng = np.random.default_rng(seed)
    y = np.array([r["ce_value"] for r in rows], dtype=float)
    molecules = kg.get("molecules", {})

    descriptor_keys = sorted({
        k
        for r in rows
        for k in r.keys()
        if k.startswith("desc:") or k.startswith("prop:")
    })

    hypotheses = []

    # Numeric descriptors
    for key in descriptor_keys:
        vals = []
        ys = []
        for r in rows:
            if key in r:
                vals.append(r[key])
                ys.append(r["ce_value"])
        if len(vals) < min_samples:
            continue

        x = np.array(vals, dtype=float)
        y_sub = np.array(ys, dtype=float)
        if np.std(x) == 0 or np.std(y_sub) == 0:
            continue

        conf, corr, ci_low, ci_high = _bootstrap_sign_confidence(
            x=x, y=y_sub, n_boot=n_boot, rng=rng
        )
        if abs(corr) < min_abs_corr or conf < min_confidence:
            continue

        direction = "increases" if corr >= 0 else "decreases"
        score = float(abs(corr) * conf * np.log1p(len(x)))
        hyp_id = "desc-%012d" % (abs(hash((key, direction, TARGET_PROPERTY))) % 10**12)
        descriptor_type = "property" if key.startswith("prop:") else "computed_descriptor"

        hypotheses.append(
            DescriptorHypothesis(
                hypothesis_id=hyp_id,
                descriptor_key=key,
                descriptor_name=_label_for_descriptor_key(key)[0],
                descriptor_type=descriptor_type,
                direction=direction,
                confidence=conf,
                score=score,
                evidence={
                    "spearman_r": corr,
                    "ci95": [ci_low, ci_high],
                    "sample_size": int(len(x)),
                    "x_mean": float(np.mean(x)),
                    "x_std": float(np.std(x)),
                    "ce_mean": float(np.mean(y_sub)),
                    "descriptor_interpretation": _label_for_descriptor_key(key)[1],
                    "method": "bootstrap_spearman",
                },
                explanation=(
                    "%s %s %s (rho=%.3f, conf=%.2f, n=%d)"
                    % (_label_for_descriptor_key(key)[0], direction, TARGET_PROPERTY, corr, conf, len(x))
                ),
            )
        )

    # Component-presence descriptors
    for comp_id, mask in component_presence.items():
        mask_arr = np.array(mask, dtype=float)
        support = int(np.sum(mask_arr))
        if support < min_component_support:
            continue
        if support >= len(mask_arr):
            continue

        conf, corr, ci_low, ci_high = _bootstrap_sign_confidence(
            x=mask_arr, y=y, n_boot=n_boot, rng=rng
        )
        if abs(corr) < min_abs_corr or conf < min_confidence:
            continue

        name = molecules.get(comp_id, {}).get("name", comp_id[:12])
        direction = "increases" if corr >= 0 else "decreases"
        score = float(abs(corr) * conf * np.log1p(support))
        hyp_id = "comp-%012d" % (abs(hash((comp_id, direction, TARGET_PROPERTY))) % 10**12)

        component_role = "component"
        if comp_id in kg.get("solvents", {}):
            component_role = "solvent"
        elif comp_id in kg.get("salts", {}):
            component_role = "salt"
        elif comp_id in kg.get("additives", {}):
            component_role = "additive"

        hypotheses.append(
            DescriptorHypothesis(
                hypothesis_id=hyp_id,
                descriptor_key="contains:%s" % comp_id,
                descriptor_name="Presence of %s (%s)" % (name, component_role),
                descriptor_type="component_presence",
                direction=direction,
                confidence=conf,
                score=score,
                evidence={
                    "component_id": comp_id,
                    "spearman_r": corr,
                    "ci95": [ci_low, ci_high],
                    "sample_size": int(len(y)),
                    "support": support,
                    "component_role": component_role,
                    "descriptor_interpretation": "Binary presence/absence of this component in a formulation.",
                    "method": "bootstrap_spearman_binary",
                },
                explanation=(
                    "Presence of %s (%s) %s %s (rho=%.3f, conf=%.2f, support=%d)"
                    % (name, component_role, direction, TARGET_PROPERTY, corr, conf, support)
                ),
            )
        )

    hypotheses.sort(key=lambda h: h.score, reverse=True)
    return hypotheses[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate descriptor-based hypotheses affecting experimental CE"
    )
    parser.add_argument(
        "--kg",
        type=Path,
        default=Path("data/output/knowledge_graph_v7.json.gz"),
        help="Path to KG JSON(.gz)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/discovery"),
        help="Output directory",
    )
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--min-abs-corr", type=float, default=0.15)
    parser.add_argument("--min-confidence", type=float, default=0.70)
    parser.add_argument("--min-component-support", type=int, default=5)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.kg.exists():
        raise SystemExit("KG not found: %s" % args.kg)

    kg = _load_kg(args.kg)
    rows, component_presence = _build_dataset(kg)

    hypotheses = _mine_hypotheses(
        kg=kg,
        rows=rows,
        component_presence=component_presence,
        min_samples=args.min_samples,
        min_abs_corr=args.min_abs_corr,
        min_confidence=args.min_confidence,
        min_component_support=args.min_component_support,
        n_boot=args.n_boot,
        top_k=args.top_k,
        seed=args.seed,
    )

    out = {
        "run_id": "ce-descriptor-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "kg_version": kg.get("version", "unknown"),
        "target_property": TARGET_PROPERTY,
        "settings": {
            "top_k": args.top_k,
            "min_samples": args.min_samples,
            "min_abs_corr": args.min_abs_corr,
            "min_confidence": args.min_confidence,
            "min_component_support": args.min_component_support,
            "n_boot": args.n_boot,
            "seed": args.seed,
        },
        "stats": {
            "formulations_with_experimental_ce": len(rows),
            "total_hypotheses": len(hypotheses),
            "by_type": {
                "component_presence": sum(1 for h in hypotheses if h.descriptor_type == "component_presence"),
                "property": sum(1 for h in hypotheses if h.descriptor_type == "property"),
                "computed_descriptor": sum(1 for h in hypotheses if h.descriptor_type == "computed_descriptor"),
            },
            "by_direction": {
                "increases": sum(1 for h in hypotheses if h.direction == "increases"),
                "decreases": sum(1 for h in hypotheses if h.direction == "decreases"),
            },
        },
        "hypotheses": [asdict(h) for h in hypotheses],
    }

    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / ("%s.json" % out["run_id"])
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print("=" * 70)
    print("CE DESCRIPTOR HYPOTHESIS GENERATION")
    print("=" * 70)
    print("Output:", out_path)
    print("Formulations with exp CE:", out["stats"]["formulations_with_experimental_ce"])
    print("Total hypotheses:", out["stats"]["total_hypotheses"])
    print("By type:", out["stats"]["by_type"])
    print("By direction:", out["stats"]["by_direction"])
    print("\nTop 10:")
    for i, h in enumerate(hypotheses[:10], 1):
        print(
            "%2d. %s --[%s]--> %s | conf=%.2f score=%.3f"
            % (i, h.descriptor_name, h.direction, TARGET_PROPERTY, h.confidence, h.score)
        )


if __name__ == "__main__":
    main()
