"""Wire Schedule B v2 into a review: detect instruments, extract one fact per condition,
verify every quoted fact against the document, and evaluate deterministically.

The run is additive. It reads the same document and profile as the 0.18.0 schedule, uses a
merged detection lexicon without modifying the base file, and writes its own ledger block
(`instrument_conditions`). Until the catalogue is adopted it never changes a section status.

    model / stand-in  ->  raw facts (value, unit, stated, contradicted, quote, ...)
    verify_facts      ->  facts whose affirmative claims are located in the document
    evaluate_instrument (evaluate.py)  ->  condition states and instrument status

A fact that asserts something (stated, contradicted, outside, authorized, excluded,
by_reference) without a quote that can be found in the document is discarded, so its
condition reads UNKNOWN. Silence ("stated": false) needs no quote.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..adapter.base import AdapterError
from ..adapter.retrieval import find_all
from .catalogue import Catalogue, Condition
from .evaluate import (CONTRADICTED, InstrumentResult, NOT_APPLICABLE, UNKNOWN, UNRESOLVED,
                       evaluate_instrument)

PROMPT_VERSION = "b2-conditions-1"
WINDOW_BEFORE, WINDOW_AFTER, MAX_WINDOWS = 500, 900, 4
AFFIRMATIVE = ("stated", "contradicted", "outside", "authorized", "excluded", "by_reference")

FACT_SHAPES = {
    "CAP": '{"stated": bool, "value": number, "unit": "days|months|years|pct_of_<base>", "inclusive": bool, "quote": str}',
    "FLOOR": '{"stated": bool, "value": number, "unit": str, "quote": str}',
    "RATING_FLOOR": '{"stated": bool, "value": "rating as written", "agencies": int, "basis": "AT_PURCHASE|CONTINUOUS", "quote": str}',
    "SUBSET": '{"stated": bool, "value": [vocabulary codes, or "OTHER:<text>" for anything outside], "quote": str}',
    "ANY_OF": '{"stated": bool, "value": [alternative ids], "outside": bool, "quote": str}',
    "REQUIRED": '{"stated": bool, "contradicted": bool, "quote": str}',
    "PROHIBITED": '{"authorized": bool, "excluded": bool, "quote": str}',
}


@dataclass
class V2Run:
    catalogue_version: str
    detector_state: str
    authorized: list[str] = field(default_factory=list)
    results: list[InstrumentResult] = field(default_factory=list)
    discarded: list[dict[str, Any]] = field(default_factory=list)
    adapter: str = ""
    calls: int = 0
    cache_hits: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    # Quality counters for the bake-off (never used to decide a state).
    affirmative_claims: int = 0
    unquoted_discards: int = 0
    disagreements: int = 0
    second_adapter: str = ""
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------- detection

def load_supplement(registers_dir: str | Path) -> dict[str, Any]:
    path = Path(registers_dir) / "instrument-conditions" / "lexicon_supplement.json"
    return json.loads(path.read_text(encoding="utf-8"))


def merged_lexicon(registers_dir: str | Path) -> dict[str, Any]:
    from ..instruments import load_lexicon

    base = load_lexicon(registers_dir)
    sup = load_supplement(registers_dir)
    merged = dict(base)
    merged["instruments"] = dict(base["instruments"])
    for code, terms in sup["supplement_terms"].items():
        merged["instruments"][code] = {"terms": list(terms)}
    return merged


def v2_codes(authorized: list[str], catalogue: Catalogue, supplement: Mapping[str, Any],
             entity_classes: list[str]) -> list[str]:
    """Map detected codes onto catalogue codes: aliases, class-dependent splits, class gates."""
    reverse = {old: new for new, old in supplement.get("aliases", {}).items()}
    out: set[str] = set()
    for code in authorized:
        split = supplement.get("by_entity_class", {}).get(code)
        if split:
            out.update(v for cls, v in split.items() if cls in entity_classes)
            continue
        out.add(reverse.get(code, code))
    kept = []
    for code in sorted(out):
        inst = catalogue.instruments.get(code)
        if inst is None:
            continue
        if "*" in inst.entity_classes or set(inst.entity_classes) & set(entity_classes):
            kept.append(code)
    return kept


def windows_for(code: str, resolution: Any, document: str,
                supplement: Mapping[str, Any]) -> list[tuple[int, str]]:
    """Passages around this instrument's mentions (including its pre-alias code)."""
    names = {code} | {old for new, old in supplement.get("aliases", {}).items() if new == code}
    names |= {src for src, split in supplement.get("by_entity_class", {}).items() if code in split.values()}
    spans = []
    for m in resolution.mentions:
        if m.code in names:
            spans.append((max(0, m.start - WINDOW_BEFORE), min(len(document), m.end + WINDOW_AFTER)))
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, document[s:e]) for s, e in merged[:MAX_WINDOWS]]


# ---------------------------------------------------------------- prompt

def activation_keys(conditions: list[Condition]) -> list[str]:
    return sorted({c.activation["fact"] for c in conditions if c.activation})


def build_prompt(code: str, label: str, conditions: list[Condition],
                 windows: list[tuple[int, str]],
                 activation_cues: Mapping[str, list[str]] | None = None,
                 instrument_terms: list[str] | None = None) -> str:
    """Extraction prompt. The model reports what the text says; it never judges conformity.

    A machine-readable copy of the request sits between <request> tags so a replayed or
    stand-in answer is tied to exactly what was asked.
    """
    request = {
        "prompt_version": PROMPT_VERSION, "instrument": code,
        "conditions": [{"id": c.id, "mode": c.mode, "fact_key": c.test["fact"],
                        "requirement": c.requirement,
                        **({"vocabulary": c.test["allowed"]} if c.mode == "SUBSET" else {}),
                        **({"alternatives": c.test["alternatives"]} if c.mode == "ANY_OF" else {}),
                        **({"outside_cues": c.test.get("outside_cues", [])} if c.mode == "ANY_OF" else {}),
                        **({"unit": c.test["unit"]} if c.mode in ("CAP", "FLOOR") else {}),
                        **({"scale": c.test["scale"]} if c.mode == "RATING_FLOOR" else {}),
                        **({"contradiction_cues": c.test["contradiction_cues"]} if c.test.get("contradiction_cues") else {})}
                       for c in conditions],
        "activation": activation_keys(conditions),
        "activation_cues": {k: list((activation_cues or {}).get(k, [])) for k in activation_keys(conditions)},
        "instrument_terms": list(instrument_terms or []),
    }
    lines = [
        f"CONDITION FACT EXTRACTION - {label} ({code})",
        "",
        "Report what the policy text states about each condition. Do not decide whether a",
        "term conforms to the statute; comparisons are made elsewhere. Quote the exact",
        "passage for every affirmative answer. If the text does not address a condition,",
        'answer {"stated": false}. If you cannot tell, omit the condition.',
        "",
        "Fact shapes by mode:",
        *[f"  {mode}: {shape}" for mode, shape in FACT_SHAPES.items()],
        "",
        "Conditions:",
    ]
    for c in conditions:
        lines.append(f"  {c.id} [{c.mode}] {c.requirement}")
        cues = [x["cue"] if isinstance(x, dict) else x for x in c.test.get("contradiction_cues", [])]
        if cues:
            lines.append(f"      language that would contradict it, for example: {'; '.join(cues)}")
    if request["activation"]:
        lines += ["", "Also answer true or false for each activation question, quoting the passage:"]
        lines += [f"  {k}" for k in request["activation"]]
    lines += ["", "Document windows:"]
    for start, text in windows:
        lines.append(f"[window offset {start}]\n{text}")
    lines += ["", "<request>", json.dumps(request), "</request>", "",
              'Return JSON: {"conditions": {"<id>": {fact}}, "activation": {"<key>": {"value": bool, "quote": str}}}']
    return "\n".join(lines)


def response_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {
        "conditions": {"type": "object"}, "activation": {"type": "object"}}}


# ---------------------------------------------------------------- verification

def _locate(quote: str, document: str) -> list[int] | None:
    if not quote or len(quote.strip()) < 3:
        return None
    hits = find_all(quote.strip(), document)
    return [hits[0][0], hits[0][1]] if hits else None


def verify_facts(raw: Mapping[str, Any], document: str, code: str
                 ) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Keep facts whose affirmative claims are located verbatim; discard the rest."""
    facts: dict[str, dict[str, Any]] = {}
    discarded: list[dict[str, Any]] = []
    for cid, fact in (raw.get("conditions") or {}).items():
        if not isinstance(fact, Mapping):
            continue
        fact = dict(fact)
        if any(fact.get(k) for k in AFFIRMATIVE):
            span = _locate(str(fact.get("quote", "")), document)
            if span is None:
                discarded.append({"instrument": code, "condition": cid,
                                  "reason": "affirmative answer without a quote found in the document",
                                  "quote": str(fact.get("quote", ""))[:200]})
                continue
            fact["span"] = span
        facts[cid] = fact
    activation: dict[str, Any] = {}
    for key, ans in (raw.get("activation") or {}).items():
        if not isinstance(ans, Mapping) or not isinstance(ans.get("value"), bool):
            continue
        if ans["value"] and _locate(str(ans.get("quote", "")), document) is None:
            discarded.append({"instrument": code, "activation": key,
                              "reason": "activation claimed without a located quote"})
            continue
        activation[key] = ans["value"]
    return facts, activation, discarded


# ---------------------------------------------------------------- two readers

def _norm_value(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(sorted(str(x).strip().upper() for x in v))
    if isinstance(v, str):
        return "".join(v.split()).upper()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 6)
    return v


def signature(fact: Mapping[str, Any] | None, mode: str) -> tuple:
    """The decision-relevant content of a fact. Spans and quotes are excluded: two readers
    may quote different sentences that say the same thing."""
    if fact is None:
        return ("NO_ANSWER",)
    f = dict(fact)
    common = (bool(f.get("stated")), bool(f.get("by_reference")))
    if mode in ("CAP", "FLOOR"):
        return common + (_norm_value(f.get("value")), f.get("unit"), f.get("inclusive", True))
    if mode == "RATING_FLOOR":
        return common + (_norm_value(f.get("value")), f.get("agencies"), f.get("basis"))
    if mode in ("SUBSET", "ANY_OF"):
        return common + (_norm_value(f.get("value")), bool(f.get("outside")))
    if mode == "REQUIRED":
        return common + (bool(f.get("contradicted")),)
    if mode == "PROHIBITED":
        return (bool(f.get("authorized")), bool(f.get("excluded")))
    return common


def reconcile(conditions: list[Condition], a: tuple, b: tuple, code: str
              ) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Keep only what both readers agree on. Any disagreement is UNKNOWN, never a pick.

    `a` and `b` are (facts, activation) after quote verification. A condition one reader
    answered and the other omitted is a disagreement too: silence from one reader is not
    corroboration.
    """
    (fa, aa), (fb, ab) = a, b
    facts: dict[str, dict[str, Any]] = {}
    notes: list[dict[str, Any]] = []
    for c in conditions:
        x, y = fa.get(c.id), fb.get(c.id)
        if x is None and y is None:
            continue
        if signature(x, c.mode) == signature(y, c.mode):
            facts[c.id] = dict(x)
        else:
            notes.append({"instrument": code, "condition": c.id, "reason": "readers disagree",
                          "first": list(signature(x, c.mode)), "second": list(signature(y, c.mode))})
    activation: dict[str, Any] = {}
    for key in set(aa) | set(ab):
        if key in aa and key in ab and aa[key] == ab[key]:
            activation[key] = aa[key]
        else:
            notes.append({"instrument": code, "activation": key, "reason": "readers disagree",
                          "first": aa.get(key), "second": ab.get(key)})
    return facts, activation, notes


# ---------------------------------------------------------------- run

def _cache_key(code: str, document_sha: str, catalogue_version: str, adapter: str) -> str:
    raw = f"{PROMPT_VERSION}|{catalogue_version}|{adapter}|{code}|{document_sha}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def run(catalogue: Catalogue, rs: Any, document: str, entity_classes: list[str], adapter: Any,
        registers_dir: str | Path, cache_dir: str | Path | None = None,
        authorized_override: list[str] | None = None, second_adapter: Any | None = None) -> V2Run:
    """Run Schedule B v2 over one document.

    `authorized_override` is the authorized set the 0.18.0 review used (a facts file), so a
    parallel run compares like with like. Codes only the v2 lexicon knows (Texas, guaranteed
    and CMO obligations; Israel bonds) are still read from the document.
    """
    from ..instruments import detect

    supplement = load_supplement(registers_dir)
    lexicon = merged_lexicon(registers_dir)
    resolution = detect(rs, document, registers_dir, lexicon=lexicon)
    detected = list(resolution.authorized)
    if authorized_override is not None:
        extra = set(supplement["supplement_terms"]) & set(detected)
        detected = list(authorized_override) + sorted(extra)
    codes = v2_codes(detected, catalogue, supplement, entity_classes)
    # Prohibitions are always evaluated: silence is fine, an authorization is not.
    if "CMO_IO_PO_INVERSE" in catalogue.instruments and "CMO_IO_PO_INVERSE" not in codes:
        codes.append("CMO_IO_PO_INVERSE")
    out = V2Run(catalogue_version=catalogue.meta.get("version", ""), detector_state=resolution.state,
                authorized=codes, adapter=getattr(adapter, "name", "unknown"),
                second_adapter=getattr(second_adapter, "name", "") if second_adapter else "")
    doc_sha = hashlib.sha256(document.encode("utf-8")).hexdigest()
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    for code in codes:
        inst = catalogue.instruments[code]
        conditions = catalogue.conditions_for(code)
        if inst.not_reviewed:
            out.results.append(evaluate_instrument(catalogue, code, {}, {}))
            continue
        if code == "CMO_IO_PO_INVERSE":
            # Answered from detection, not from the model: the lexicon's polarity already
            # read whether the prohibited structures are authorized or excluded.
            facts = _prohibition_facts(conditions, resolution, document)
            out.results.append(evaluate_instrument(catalogue, code, facts, {}))
            continue
        windows = windows_for(code, resolution, document, supplement)
        prompt = build_prompt(code, inst.label, conditions, windows,
                              supplement.get("activation_cues"), _terms(code, lexicon, supplement))
        answers = []
        for reader in [adapter] + ([second_adapter] if second_adapter else []):
            raw = _ask(reader, prompt, code, doc_sha, out, cache)
            out.affirmative_claims += sum(
                1 for f in (raw.get("conditions") or {}).values()
                if isinstance(f, Mapping) and any(f.get(k) for k in AFFIRMATIVE))
            facts, activation, discarded = verify_facts(raw, document, code)
            out.unquoted_discards += len(discarded)
            out.discarded.extend(discarded)
            answers.append((facts, activation))
        if second_adapter:
            facts, activation, notes = reconcile(conditions, answers[0], answers[1], code)
            out.disagreements += len(notes)
            out.discarded.extend(notes)
        else:
            facts, activation = answers[0]
        out.facts[code] = facts
        out.results.append(evaluate_instrument(catalogue, code, facts, activation))
    return out


def _ask(reader: Any, prompt: str, code: str, doc_sha: str, out: V2Run, cache: Path | None) -> Mapping[str, Any]:
    name = getattr(reader, "name", "unknown")
    cached = cache / f"{_cache_key(code, doc_sha, out.catalogue_version, name)}.json" if cache else None
    if cached and cached.exists():
        out.cache_hits += 1
        return json.loads(cached.read_text(encoding="utf-8"))
    try:
        raw = reader.ask(prompt, f"B2:{code}", response_schema())
        out.calls += 1
    except AdapterError as exc:
        out.failures[f"{name}:{code}"] = str(exc)
        return {}
    if cached:
        cached.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    return raw


def _terms(code: str, lexicon: Mapping[str, Any], supplement: Mapping[str, Any]) -> list[str]:
    names = {code} | {old for new, old in supplement.get("aliases", {}).items() if new == code}
    names |= {src for src, split in supplement.get("by_entity_class", {}).items() if code in split.values()}
    return sorted({t for n in names for t in lexicon["instruments"].get(n, {}).get("terms", [])})


def _prohibition_facts(conditions: list[Condition], resolution: Any, document: str) -> dict[str, dict]:
    authorized = "CMO_IO_PO_INVERSE" in resolution.authorized
    excluded = "CMO_IO_PO_INVERSE" in resolution.excluded
    mention = next((m for m in resolution.mentions if m.code == "CMO_IO_PO_INVERSE"), None)
    span = [mention.start, mention.end] if mention else None
    if authorized:
        return {c.id: {"authorized": True, "span": span} for c in conditions}
    if excluded:
        return {c.id: {"excluded": True, "span": span} for c in conditions}
    return {c.id: {} for c in conditions}


# ---------------------------------------------------------------- ledger

def section_status(run_: V2Run) -> str:
    # NOT_REVIEWED instruments are listed in the ledger and never set the section status.
    statuses = {r.status for r in run_.results if r.status != "NOT_REVIEWED"}
    if "CONFLICTS" in statuses:
        return "REVISIONS_RECOMMENDED"
    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_IN_PROGRESS"
    return "ADDRESSES_PROVISIONS_REVIEWED" if statuses else "NOT_ASSESSED"


def ledger_block(catalogue: Catalogue, run_: V2Run) -> dict[str, Any]:
    """The `instrument_conditions` ledger block. Proposed: never sets a section status."""
    index = {c.id: c for c in catalogue.conditions}
    return {
        "status": catalogue.meta.get("status"),
        "catalogue_version": run_.catalogue_version,
        "prompt_version": PROMPT_VERSION,
        "adapter": run_.adapter,
        "detector_state": run_.detector_state,
        "authorized": run_.authorized,
        "section_status_if_adopted": section_status(run_),
        "not_reviewed": [{"code": r.code, "reason": catalogue.instruments[r.code].scope["reason"]}
                         for r in run_.results if r.status == "NOT_REVIEWED"],
        "calls": run_.calls, "cache_hits": run_.cache_hits, "failures": run_.failures,
        "second_adapter": run_.second_adapter or None,
        "quality": {"affirmative_claims": run_.affirmative_claims,
                    "unquoted_discards": run_.unquoted_discards,
                    "disagreements": run_.disagreements},
        "discarded": run_.discarded,
        "instruments": [{
            "code": r.code,
            "label": catalogue.instruments[r.code].label,
            "status": r.status,
            "contradicted": r.contradicted, "unknown": r.unknown,
            "unresolved": r.unresolved, "not_restated": r.not_restated,
            "conditions": [{
                "id": c.condition_id, "cite": index[c.condition_id].cite,
                "component": index[c.condition_id].component, "binds": index[c.condition_id].binds,
                "state": c.state, "detail": c.detail,
                "policy_value": c.policy_value, "statutory_value": c.statutory_value,
                # The binding term once policy and statute both apply (stricter of the two;
                # the statute where the policy is silent or conflicts). Read by mandate fit.
                "binding": c.effective_value,
                "requirement": index[c.condition_id].requirement,
                "quote": (run_.facts.get(r.code, {}).get(c.condition_id) or {}).get("quote"),
                "span": c.span,
            } for c in r.results if c.state != NOT_APPLICABLE],
        } for r in run_.results],
    }


__all__ = ["run", "ledger_block", "section_status", "build_prompt", "verify_facts",
           "v2_codes", "merged_lexicon", "V2Run", "CONTRADICTED", "UNKNOWN", "UNRESOLVED"]
