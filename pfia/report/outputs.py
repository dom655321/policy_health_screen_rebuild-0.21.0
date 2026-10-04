"""Two outputs built from a finding ledger: the redline and mandate fit.

Both read the ledger only (plus the register for wording), never the policy document,
so they show exactly what the review found and nothing more.

    redline_context      proposed amendments for Core provisions and authorized-investment
                         terms, a hold list for readings to verify, and a draft resolution
    mandate_fit_context  an internal onboarding view: can a strategy run under the policy?

Neither decides anything the evaluator did not. The redline proposes statute-derived
language for items the review marked as conflicting or not addressed; mandate fit compares
a strategy's parameters with the binding terms the review recorded, using the same
deterministic comparators as the evaluator.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import phrasing

ACTION_STATUSES = ("CONFLICTS", "NOT_ADDRESSED", "PARTIALLY_ADDRESSED")
# Placeholders that name a person or body rather than ask for a decision.
NAME_PLACEHOLDERS = ("[Governing Body]", "[Officer]", "[Governing Body or designated investment committee]")
VOCAB = {
    "US_TREASURY": "Treasuries", "US_AGENCY_INSTRUMENTALITY": "agencies and instrumentalities",
    "FHLB": "FHLB", "US_LETTER_OF_CREDIT": "U.S. letters of credit", "TX_DIRECT": "Texas direct obligations",
    "TX_AGENCY_DIRECT": "Texas agency obligations", "CASH": "cash",
    "OBLIGATIONS_2256_009A1": "Sec. 2256.009(a)(1) obligations", "OBLIGATIONS_2256_009A": "Sec. 2256.009(a) obligations",
    "COMMERCIAL_PAPER_2256_013": "Sec. 2256.013 commercial paper",
    "ISD_CORPORATE_BOND_2256_0204": "Sec. 2256.0204 corporate bonds (ISDs)", "AGENCY_MBS": "agency MBS",
    "PRIMARY_DEALER_FRB": "primary dealers (FRB)", "PRIMARY_DEALER_5CFR": "primary dealers",
    "TX_FINANCIAL_INSTITUTION": "Texas financial institutions", "TX_OFFICE_BROKER": "Texas-office brokers",
    "TX_OFFICE_DEPOSITORY": "Texas-office depositories", "SELECTED_DEPOSITORY": "the selected depository",
    "ENTITY_2257_041_D": "Sec. 2257.041(d) custodians", "SEC_15C3_3_CLEARING_BD": "SEC 15c3-3 clearing broker-dealers",
    "TWO_AGENCIES": "two agencies", "ONE_AGENCY_PLUS_LOC": "one agency + bank letter of credit",
    "INSURED": "insured", "SECURED_009A": "secured by Sec. 2256.009(a) obligations", "SECURED_2257": "secured under ch. 2257",
    "FDIC": "FDIC", "NCUSIF": "NCUSIF", "PLEDGED_2256_009_SECURITIES": "pledged Sec. 2256.009 securities",
    "PLEDGED_IRREVOCABLE_LOC": "pledged bank letters of credit",
}


def _label(code: Any) -> str:
    text = str(code)
    if text.startswith("OTHER:"):
        return text[6:].strip()
    return VOCAB.get(text, text.replace("_", " ").lower())
MODE_ORDER = {"Revision": 0, "Addition": 1}


# ---------------------------------------------------------------- shared

def _header(ledger: Mapping[str, Any], entity: str) -> dict[str, Any]:
    doc = ledger.get("document") or {}
    return {
        "entity": entity,
        "policy_file": doc.get("source_name") or doc.get("label") or "policy",
        "pages": doc.get("pages"),
        "ledger_id": str(ledger.get("ledger_sha256", ""))[:16].upper(),
        "package_version": ledger.get("package_version", ""),
        "reader": ledger.get("extractor", ""),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reviewed_on": str(ledger.get("generated_at", ""))[:10],
    }


def _v2(ledger: Mapping[str, Any]) -> Mapping[str, Any] | None:
    block = ledger.get("instrument_conditions")
    return block if isinstance(block, Mapping) and block.get("instruments") else None


def _spans(finding: Mapping[str, Any], satisfied: bool | None = None) -> list[dict[str, Any]]:
    """Quoted policy text, deduplicated; fragments too short to orient a reader are dropped."""
    out, seen = [], set()
    for e in finding.get("elements", []):
        if satisfied is not None and bool(e.get("satisfied")) != satisfied:
            continue
        for s in e.get("spans", []) or []:
            text = " ".join(str(s.get("text", "")).split())
            if len(text) >= 25 and text not in seen:
                seen.add(text)
                out.append({"text": text, "page": s.get("page")})
    return out


# ---------------------------------------------------------------- redline

def redline_context(ledger: Mapping[str, Any], registers_root: str | Path, entity: str,
                    statutory_only: bool = False, example: bool = False) -> dict[str, Any]:
    """Proposed amendments from a ledger.

    Included: Core Schedule A findings that conflict, are not addressed or are addressed in
    part, and authorized-investment terms that conflict. Advisory Core items are optional
    restatements (excluded with statutory_only). Held, not proposed: findings whose reading
    needs verification, and authorized-investment conditions the reader could not settle.
    Context provisions and out-of-scope instruments are never amended here.
    """
    from .. import loader

    rs = loader.load(Path(registers_root))
    # An offline or unlabelled reading is never review-grade, whatever it found.
    reader_ok = not str(ledger.get("extractor", "")).startswith(("heuristic", "keyword", "unlabelled"))
    amendments: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []

    for f in ledger.get("findings", []):
        if f.get("schedule") != "A" or f.get("relevance") != "CORE" or not f.get("in_scope"):
            continue
        if f.get("status") not in ACTION_STATUSES:
            continue
        control = rs.control(f["control_id"])
        raw = control.raw if hasattr(control, "raw") else {}
        proposed = (raw.get("proposed_text") or f.get("remediation_language") or "").replace("[Entity]", entity)
        entry = {
            "ids": [f["control_id"]],
            "cite": f["citation"],
            "title": f["title"],
            "kind": "Revision" if f["status"] == "CONFLICTS" else "Addition",
            "status": phrasing.status(f["status"]),
            "delete": [{"text": h.get("text", ""), "page": h.get("page")}
                       for h in f.get("anti_pattern_hits", []) if h.get("text")],
            "context": _spans(f, satisfied=True)[:2],
            "missing": [e["assertion"] for e in f.get("elements", []) if not e.get("satisfied")],
            "proposed": proposed,
            "proposed_is_text": bool(raw.get("proposed_text")),
            "basis": "Tex. Gov't Code " + f["citation"],
            "source": "Schedule A",
            "detail": "",
        }
        literal_conflict = f["status"] == "CONFLICTS" and bool(entry["delete"]) and reader_ok
        if f.get("review_action") == "VERIFY_EXTRACTION" and not literal_conflict:
            entry["hold_reason"] = "A supporting quotation was discarded or the reading is weak; verify the passage before proposing language."
            held.append(entry)
        elif f.get("review_action") == "VERIFY_EXTRACTION" and f.get("band") != "ADVISORY":
            # The conflicting text is a literal match, verified by construction; only the
            # other elements' reading is weak. Propose the revision, and say so.
            entry["detail"] = "the conflicting language is a verified literal match; confirm the other elements"
            amendments.append(entry)
        elif f.get("band") == "ADVISORY":
            if not statutory_only:
                optional.append(entry)
        else:
            amendments.append(entry)

    block = _v2(ledger)
    source_note = ""
    if block:
        source_note = ("Authorized-investment amendments come from the Schedule B v2 condition "
                       f"catalogue (status: {block.get('status')}), which names the specific term.")
        for inst in block["instruments"]:
            if inst.get("status") == "NOT_REVIEWED":
                continue
            for c in inst.get("conditions", []):
                if c.get("state") == "CONTRADICTED":
                    amendments.append({
                        "ids": [c["id"]],
                        "cite": "Sec. " + c["cite"],
                        "title": f"{inst['label']}: {c['component'].replace('_', ' ').lower()}",
                        "kind": "Revision",
                        "status": "Stated terms differ from the Act",
                        "delete": [{"text": c["quote"], "page": None}] if c.get("quote") else [],
                        "context": [],
                        "missing": [],
                        "proposed": c.get("requirement", ""),
                        "proposed_is_text": True,
                        "basis": "Tex. Gov't Code Sec. " + c["cite"],
                        "source": "Schedule B v2",
                        "detail": c.get("detail", ""),
                    })
            unknown = [c["id"] for c in inst.get("conditions", []) if c.get("state") == "UNKNOWN"]
            if unknown:
                held.append({"ids": unknown, "cite": inst["label"], "title": inst["label"],
                             "kind": "Hold", "status": "Reading not settled", "proposed": "",
                             "hold_reason": f"{len(unknown)} condition(s) could not be read with certainty: {', '.join(unknown)}."})
    else:
        source_note = ("Authorized-investment amendments come from the 0.18.0 instrument schedule. "
                       "Re-run `pfia review ... --schedule-b-v2` for amendments that name the specific term.")
        for f in ledger.get("findings", []):
            if (f.get("schedule") == "B" and f.get("in_scope") and f.get("band") == "STATUTORY"
                    and f.get("status") == "CONFLICTS"):
                amendments.append({
                    "ids": [f["control_id"]], "cite": f["citation"], "title": f["title"],
                    "kind": "Revision", "status": phrasing.status("CONFLICTS"),
                    "delete": [{"text": h.get("text", ""), "page": h.get("page")}
                               for h in f.get("anti_pattern_hits", []) if h.get("text")],
                    "context": [], "missing": [],
                    "proposed": f.get("remediation_language", ""), "proposed_is_text": False,
                    "basis": "Tex. Gov't Code " + f["citation"], "source": "0.18.0 schedule",
                    "detail": "",
                })

    amendments.sort(key=lambda a: (MODE_ORDER[a["kind"]], a["source"] != "Schedule B v2", a["cite"]))
    for n, a in enumerate(amendments + optional, 1):
        a["no"] = n
        a["decisions"] = _decisions(a["proposed"])
    sections = ledger.get("sections", {})
    return {
        **_header(ledger, entity),
        "amendments": amendments,
        "optional": optional,
        "held": held,
        "counts": {
            "revisions": sum(1 for a in amendments if a["kind"] == "Revision"),
            "additions": sum(1 for a in amendments if a["kind"] == "Addition"),
            "optional": len(optional),
            "held": len(held),
            "blanks": sum(_decisions(a["proposed"]) for a in amendments + optional),
        },
        "sections": [{"label": phrasing.SECTION_LABELS.get(k, k), "status": phrasing.section(v["status"])}
                     for k, v in sections.items()],
        "source_note": source_note,
        "reliability": authorization_reliability(ledger),
        "statutory_only": statutory_only,
        "example": example,
    }


def _decisions(text: str) -> int:
    import re
    return sum(1 for m in re.findall(r"\[[^\]]*\]", text) if m not in NAME_PLACEHOLDERS)


# ---------------------------------------------------------------- mandate fit

FITS, CONSTRAINS, BLOCKS, UNDETERMINED, NOT_USED, NOT_REVIEWED = (
    "Fits", "Constrains", "Blocks", "Cannot determine", "Not used", "Not reviewed")


class StrategyError(ValueError):
    """The strategy file names an instrument or condition the catalogue does not have."""


def load_strategy(path: str | Path, catalogue: Any) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = []
    for code, spec in (doc.get("instruments") or {}).items():
        if code not in catalogue.instruments:
            problems.append(f"unknown instrument {code}")
            continue
        known = {c.id for c in catalogue.conditions_for(code)}
        for cid in (spec.get("terms") or {}):
            if cid not in known:
                problems.append(f"{code}: unknown or retired condition {cid}")
    if problems:
        raise StrategyError("strategy file: " + "; ".join(problems))
    return doc


def _fmt(mode: str, value: Any) -> str:
    if value is None:
        return "-"
    if mode in ("CAP", "FLOOR") and isinstance(value, Mapping):
        sign = "<" if value.get("strict") else ("≤" if mode == "CAP" else "≥")
        unit = str(value.get("unit", "")).replace("pct_of_", "% of ").replace("_", " ")
        return f"{sign} {value.get('limit', value.get('value')):g}{'' if unit.startswith('%') else ' '}{unit}".strip()
    if mode == "RATING_FLOOR" and isinstance(value, Mapping):
        extra = []
        if value.get("min_agencies", 1) > 1 or value.get("agencies", 1) > 1:
            extra.append(f"{value.get('min_agencies', value.get('agencies'))} agencies")
        if value.get("basis") == "CONTINUOUS":
            extra.append("continuous")
        return f"≥ {value.get('floor', value.get('value'))}" + (f" ({', '.join(extra)})" if extra else "")
    if isinstance(value, list):
        return ", ".join(_label(v) for v in value)
    if isinstance(value, Mapping) and "value" in value:
        return _fmt(mode, value["value"]) if not isinstance(value["value"], (int, float)) else \
            (f"{value['value']:g}" + ("" if str(value.get('unit', '')).startswith('pct') else " ")
             + str(value.get('unit', '')).replace('pct_of_', '% of ').replace('_', ' '))
    return str(value)


DAYS = {"day": 1, "days": 1, "month": 30.4375, "months": 30.4375, "year": 365.25, "years": 365.25}


def _to_days(value: Any, unit: Any) -> float | None:
    """A duration in days, for comparing maturity limits written in different units."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    factor = DAYS.get(str(unit or "").strip().lower())
    return None if factor is None else float(value) * factor


def _compare(cond: Any, binding: Any, term: Any) -> tuple[str, str]:
    """Strategy term against the binding term, with the evaluator's own comparators."""
    from ..conditions import evaluate as ev

    if binding is None:
        return UNDETERMINED, "the policy's term could not be read"
    mode = cond.mode
    if mode in ("SUBSET", "ANY_OF"):
        wanted = set(term if isinstance(term, list) else [term])
        allowed = set(binding if isinstance(binding, list) else [])
        extra = sorted(wanted - allowed)
        return (CONSTRAINS, "the policy does not permit " + ", ".join(extra)) if extra else (FITS, "")
    test = dict(cond.test)
    if mode == "CAP":
        test.update(limit=binding["limit"], unit=binding["unit"], strict=binding.get("strict", False))
        fact = {"stated": True, "value": term["value"], "unit": term.get("unit", binding["unit"]), "inclusive": True}
    elif mode == "FLOOR":
        test.update(limit=binding["limit"], unit=binding["unit"])
        fact = {"stated": True, "value": term["value"], "unit": term.get("unit", binding["unit"])}
    elif mode == "RATING_FLOOR":
        test.update(floor=binding["floor"], granularity=binding.get("granularity", "NOTCH"),
                    min_agencies=binding.get("min_agencies", 1), basis=binding.get("basis", "AT_PURCHASE"))
        fact = {"stated": True, **({"value": term} if isinstance(term, str) else term)}
    else:
        return FITS, ""
    probe = dataclasses.replace(cond, test=test, activation=None)
    result = ev.evaluate_condition(probe, fact)
    if result.state == ev.CONTRADICTED:
        return CONSTRAINS, "the strategy goes beyond the policy: " + result.detail.replace("policy", "strategy", 1)
    if result.state == ev.UNKNOWN:
        return UNDETERMINED, result.detail
    return FITS, ""


def mandate_fit_context(ledger: Mapping[str, Any], strategy: Mapping[str, Any], registers_root: str | Path,
                        entity: str, policy_limits: Mapping[str, Any] | None = None,
                        example: bool = False) -> dict[str, Any]:
    """Compare a strategy with the policy's binding terms, instrument by instrument."""
    from ..conditions import load_catalogue

    root = Path(registers_root)
    cat = load_catalogue(root / "instrument-conditions" / "register.json")
    block = _v2(ledger)
    authorized = set(block.get("authorized", [])) if block else set(
        (ledger.get("policy_facts") or {}).get("authorized_instruments", []))
    by_code = {i["code"]: i for i in block["instruments"]} if block else {}
    rows, notes, fit_not_compliance = [], [], []
    # If the policy's authorized list may have been misread, "not authorized" is unproven:
    # report it as undetermined rather than as a block.
    reliability = authorization_reliability(ledger)

    for code, spec in (strategy.get("instruments") or {}).items():
        inst = cat.instruments[code]
        conds = {c.id: c for c in cat.conditions_for(code)}
        recorded = {c["id"]: c for c in (by_code.get(code, {}).get("conditions", []))}
        v2 = by_code.get(code)
        strategy_desc = spec.get("summary") or "; ".join(
            f"{_fmt(conds[k].mode, v)}" for k, v in (spec.get("terms") or {}).items())
        row = {"code": code, "label": inst.label, "cite": ", ".join(inst.authority),
               "strategy": strategy_desc, "policy": [], "act": [], "fit": FITS, "details": [],
               "vs_act": ""}
        if inst.not_reviewed or (v2 and v2.get("status") == "NOT_REVIEWED"):
            row.update(fit=NOT_REVIEWED, policy=["Outside the review's scope"])
        elif code not in authorized and reliability:
            row.update(fit=UNDETERMINED, policy=["Not found in the list as read"])
            row["details"].append("authorized list not read reliably")
        elif code not in authorized:
            row.update(fit=BLOCKS, policy=["Not authorized"])
            notes.append(f"{inst.label} is not authorized by the policy; the strategy uses it"
                         + (f" ({spec['target']})" if spec.get("target") else "") + ".")
        else:
            policy_bits, act_bits = [], []
            for cid, term in (spec.get("terms") or {}).items():
                c = recorded.get(cid)
                cond = conds[cid]
                if c is None or c.get("state") in ("NOT_APPLICABLE", "APPLICABILITY_UNRESOLVED"):
                    row["details"].append(f"{cid}: not evaluated for this policy")
                    continue
                binding = None if c.get("state") == "UNKNOWN" else c.get("binding")
                fit, why = _compare(cond, binding, term)
                source = "policy" if c.get("state") == "STRICTER" else "Act"
                policy_bits.append(f"{_fmt(cond.mode, binding)}" + (" (policy)" if source == "policy" else ""))
                act_bits.append(_fmt(cond.mode, c.get("statutory_value")))
                if fit != FITS:
                    row["details"].append(f"{cid}: {why}")
                    if fit == CONSTRAINS or row["fit"] == FITS:
                        row["fit"] = fit if row["fit"] != CONSTRAINS else CONSTRAINS
            row["policy"] = policy_bits or ["Authorized"]
            row["act"] = list(dict.fromkeys(act_bits)) or ["-"]
            if v2 and v2.get("contradicted"):
                row["vs_act"] = "Conflicts: " + ", ".join(v2["contradicted"])
                if row["fit"] == FITS:
                    fit_not_compliance.append(f"{inst.label.lower()} ({', '.join(v2['contradicted'])})")
            elif v2:
                row["vs_act"] = phrasing.section("ADDRESSES_PROVISIONS_REVIEWED") if v2.get("status") == "ALIGNED" \
                    else "Reading not settled"
            if row["fit"] == CONSTRAINS:
                notes.append(f"{inst.label}: " + "; ".join(d.split(": ", 1)[1] for d in row["details"] if "beyond" in d or "permit" in d))
            elif row["fit"] == UNDETERMINED:
                notes.append(f"{inst.label}: confirm the policy's terms by reading the clause ({', '.join(d.split(':')[0] for d in row['details'])}).")
        rows.append(row)

    if fit_not_compliance:
        notes.append("Fit is not compliance: the policy's terms for " + "; ".join(fit_not_compliance)
                     + " conflict with the Act. The strategy meets the Act's term, so trading is unaffected, "
                     "but these clauses belong in the redline.")

    for code in sorted(authorized - set(strategy.get("instruments") or {})):
        if code in cat.instruments and code != "CMO_IO_PO_INVERSE" and not cat.instruments[code].not_reviewed:
            rows.append({"code": code, "label": cat.instruments[code].label, "cite": ", ".join(cat.instruments[code].authority),
                         "strategy": "-", "policy": ["Authorized"], "act": [], "fit": NOT_USED, "details": [], "vs_act": ""})

    portfolio = []
    for key, spec in (strategy.get("portfolio") or {}).items():
        entered = (policy_limits or {}).get(key)
        row = {"key": key, "label": spec.get("label", key.replace("_", " ").capitalize()), "cite": spec.get("cite", ""),
               "strategy": f"{spec['value']:g} {spec.get('unit', '')}".strip() if isinstance(spec.get("value"), (int, float)) else str(spec.get("value", "")),
               "policy": "", "fit": UNDETERMINED, "note": ""}
        if entered is None:
            row.update(policy="Not extracted", note="Add to the policy limits file to compare")
        else:
            row["policy"] = (f"{entered['value']:g} {entered.get('unit', '')}".strip()
                             if isinstance(entered.get("value"), (int, float)) else str(entered.get("value")))
            row["note"] = "Entered by reviewer" + (f" ({entered['source']})" if entered.get("source") else "")
            a, b = _to_days(spec.get("value"), spec.get("unit")), _to_days(entered.get("value"), entered.get("unit"))
            if a is None and isinstance(spec.get("value"), (int, float)) and spec.get("unit") == entered.get("unit"):
                a, b = spec["value"], entered["value"]
            if a is not None and b is not None:
                if spec.get("kind", "cap") == "cap":
                    row["fit"] = FITS if a <= b else CONSTRAINS
                else:
                    row["fit"] = FITS if a >= b else CONSTRAINS
                if row["fit"] == CONSTRAINS:
                    notes.append(f"{row['label']}: the policy sets {row['policy']}; the strategy uses {row['strategy']}.")
            elif str(spec.get("value")).lower() == str(entered.get("value")).lower():
                row["fit"] = FITS
        portfolio.append(row)

    if reliability:
        notes.insert(0, "The policy's list of authorized investments may not have been read correctly, so "
                        "instruments not found in it are shown as Cannot determine, not Blocks. "
                        + " ".join(reliability))
    tally = {k: sum(1 for r in rows if r["fit"] == k) for k in (BLOCKS, CONSTRAINS, FITS, UNDETERMINED, NOT_USED, NOT_REVIEWED)}
    tally["portfolio_constrains"] = sum(1 for r in portfolio if r["fit"] == CONSTRAINS)
    conflicts = [r for r in rows if r["vs_act"].startswith("Conflicts")]
    return {
        **_header(ledger, entity),
        "strategy_name": strategy.get("strategy", "Strategy"),
        "strategy_version": strategy.get("version", ""),
        "strategy_approved": strategy.get("approved", ""),
        "rows": rows, "portfolio": portfolio, "notes": notes, "tally": tally,
        "act_conflicts": len(conflicts),
        "has_v2": bool(block),
        "example": example,
        "reliability": reliability,
        "can_run_as_designed": tally[BLOCKS] == 0 and tally[CONSTRAINS] == 0 and tally["portfolio_constrains"] == 0
                               and tally[UNDETERMINED] == 0,
    }


# ---------------------------------------------------------------- screen report

SECTION_RANK = {"REVIEW_IN_PROGRESS": 0, "REVISIONS_RECOMMENDED": 1, "ADDITIONS_RECOMMENDED": 2,
                "ADDRESSES_PROVISIONS_REVIEWED": 3, "NOT_ASSESSED": 4}
PRIORITY = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "MODERATE": 3, "ADVISORY": 4, "LOW": 4}
ACTION_LABEL = {
    "READ_THE_PASSAGE": ("Read the passage", "Language known to defeat the requirement was located; confirm it says what the review read."),
    "VERIFY_EXTRACTION": ("Verify the reading", "A supporting quotation was discarded or the reader is not review-grade; check the policy before treating this as a gap."),
    "CONFIRM_ABSENCE": ("Confirm the policy is silent", "Nothing on this subject was found anywhere in the document; confirm it is not phrased in other words."),
    "INTERPRETIVE": ("Judgment call", "The controlling text is contested or the requirement rests on a reading."),
    "REVIEW_FINDING": ("Ordinary review", "Elements not addressed on located evidence."),
}
CONDITION_LABEL = {
    "CONFORMING": "Addressed", "STRICTER": "More restrictive than the Act",
    "BY_REFERENCE": "Addressed by reference to the Act", "SILENT": "Not restated (the Act applies)",
    "CONTRADICTED": "Stated terms differ from the Act", "UNKNOWN": "Not read with certainty",
    "APPLICABILITY_UNRESOLVED": "Confirmation required",
}
INSTRUMENT_LABEL = {
    "ALIGNED": "Addresses the provisions reviewed", "CONFLICTS": "Stated terms differ from the Act",
    "REVIEW_REQUIRED": "Review required", "NOT_REVIEWED": "Not reviewed (outside the client base)",
}
AUTH_LIST_CONTROL = "TX-PFIA-2256.005-b-4-A-001"


def authorization_reliability(ledger: Mapping[str, Any]) -> list[str]:
    """Reasons the policy's list of authorized investments may not have been read correctly.

    Every authorized-investment result gates on that list, so a misread list silently turns
    into "not authorized". Shared by the screen report and mandate fit.
    """
    reasons = []
    quality = ((ledger.get("document") or {}).get("quality") or {})
    if quality.get("verdict") not in (None, "OK"):
        reasons.append(f"Text extraction quality is {quality.get('verdict')}: " + "; ".join(quality.get("reasons", [])))
    finding = next((f for f in ledger.get("findings", []) if f.get("control_id") == AUTH_LIST_CONTROL), None)
    if finding and finding.get("in_scope"):
        e1 = next((e for e in finding.get("elements", []) if e.get("element_id") == "e1"), None)
        if e1 is not None and not e1.get("satisfied"):
            reasons.append("The review did not locate an enumerated list of authorized investments, so the "
                           "authorized set may be incomplete.")
    return reasons


def _card(f: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    action = f.get("review_action") or "NONE"
    return {
        "id": f["control_id"], "cite": f["citation"], "title": f["title"],
        "status": phrasing.status(f["status"]), "status_code": f["status"],
        "band": "Required in the policy" if f.get("band") == "STATUTORY" else "Binds regardless (restatement optional)",
        "priority": PRIORITY.get(f.get("severity", ""), 4),
        "action": ACTION_LABEL.get(action, ("", ""))[0],
        "evidence": _spans(f, satisfied=True)[:2] or _spans(f)[:1],
        "elements": [{"text": e["assertion"], "addressed": bool(e.get("satisfied")),
                      "optional": e.get("band") == "ADVISORY" and f.get("band") == "STATUTORY"}
                     for e in f.get("elements", [])],
        "flagged": [{"text": h.get("text", ""), "page": h.get("page")} for h in f.get("anti_pattern_hits", []) if h.get("text")],
        "limitations": [f"A supporting quotation for element {d.get('element_id', d) if isinstance(d, Mapping) else d} could not be found in the document and was discarded."
                        for d in (f.get("discarded_claims") or [])],
        "proposed": raw.get("proposed_text") or "",
    }


def screen_context(ledger: Mapping[str, Any], registers_root: str | Path, entity: str,
                   entity_class: str | None = None, policy_version: str | None = None,
                   distribution: str = "internal") -> dict[str, Any]:
    """The policy screen, rebuilt on the current model (ADRs 0009-0013).

    Page one: the result by section, the scope statement, and the leading items. Then the
    internal working paper: the work queue, authorized investments (condition by condition
    when the Schedule B v2 block is present), investment management provisions (Core, element
    by element), the governance summary (Context, one line each), restatement items, evidence
    requests and run provenance. No score, and no audit vocabulary anywhere in the document.
    """
    from .. import loader

    rs = loader.load(Path(registers_root))
    findings = [f for f in ledger.get("findings", []) if f.get("in_scope")]
    sections = ledger.get("sections", {})
    open_statuses = ("CONFLICTS", "NOT_ADDRESSED", "PARTIALLY_ADDRESSED")

    core = [f for f in findings if f.get("schedule") == "A" and f.get("relevance") == "CORE"]
    context_items = [f for f in ledger.get("findings", []) if f.get("relevance") == "CONTEXT"]
    inst_findings = [f for f in findings if f.get("schedule") == "B"]

    def raw_of(f):
        c = rs.control(f["control_id"])
        return c.raw if hasattr(c, "raw") else {}

    open_core = sorted((f for f in core if f["status"] in open_statuses),
                       key=lambda f: (f["status"] != "CONFLICTS", f.get("band") != "STATUTORY",
                                      PRIORITY.get(f.get("severity", ""), 4), f["citation"]))
    aligned_core = [f for f in core if f["status"] not in open_statuses]

    block = _v2(ledger)
    v2_rows, v2_conflicts = [], []
    if block:
        for inst in block["instruments"]:
            conds = [{"id": c["id"], "cite": c["cite"], "requirement": c.get("requirement", ""),
                      "state": CONDITION_LABEL.get(c["state"], c["state"]), "state_code": c["state"],
                      "quote": c.get("quote") or "", "detail": c.get("detail", "")}
                     for c in inst.get("conditions", []) if c.get("state") != "NOT_APPLICABLE"]
            v2_rows.append({"code": inst["code"], "label": inst["label"], "status": INSTRUMENT_LABEL.get(inst["status"], inst["status"]),
                            "status_code": inst["status"], "conditions": conds})
            for c in conds:
                if c["state_code"] == "CONTRADICTED":
                    v2_conflicts.append({"cite": "Sec. " + c["cite"], "title": f"{inst['label']}: {c['requirement']}",
                                         "status": "Stated terms differ from the Act", "verify": False, "ids": c["id"]})

    leading = v2_conflicts + [{"cite": f["citation"], "title": f["title"], "status": phrasing.status(f["status"]),
                               "verify": f.get("review_action") == "VERIFY_EXTRACTION", "ids": f["control_id"]}
                              for f in open_core if f.get("band") == "STATUTORY"]
    queue: dict[str, list[dict[str, Any]]] = {}
    for f in core + [f for f in inst_findings if f.get("band") == "STATUTORY"]:
        if f["status"] in ("ALIGNED", "ALIGNED_BY_REFERENCE", "NOT_APPLICABLE") or f.get("review_action") in (None, "NONE"):
            continue
        label, why = ACTION_LABEL.get(f["review_action"], (f["review_action"], ""))
        queue.setdefault(label, {"why": why, "items": []})["items"].append({
            "id": f["control_id"], "cite": f["citation"], "title": f["title"],
            "priority": PRIORITY.get(f.get("severity", ""), 4), "status": phrasing.status(f["status"])})
    for g in queue.values():
        g["items"].sort(key=lambda i: (i["priority"], i["cite"]))

    worst = min((sections.get(s, {}).get("status", "NOT_ASSESSED")
                 for s in ("AUTHORIZED_INVESTMENTS", "PFIA_REQUIREMENTS")), key=lambda s: SECTION_RANK.get(s, 9))
    headline, sub = phrasing.verdict(worst, False)
    gov_in = [f for f in context_items if f.get("in_scope")]
    tiles = []
    for key in ("AUTHORIZED_INVESTMENTS", "PFIA_REQUIREMENTS", "POLICY_GOVERNANCE"):
        if key not in sections:
            continue
        if key == "AUTHORIZED_INVESTMENTS":
            n = len(v2_conflicts) if block else sum(1 for f in inst_findings if f.get("band") == "STATUTORY" and f["status"] in open_statuses)
            foot = f"{n} term(s) differ from the Act" if n else "No stated term differs from the Act"
        elif key == "PFIA_REQUIREMENTS":
            n = sum(1 for f in open_core if f.get("band") == "STATUTORY")
            foot = f"{n} required provision(s) to add or revise; {sum(1 for f in core if f['status'] in ('ALIGNED', 'ALIGNED_BY_REFERENCE'))} of {len(core)} addressed"
        else:
            foot = f"{sum(1 for f in gov_in if f['status'] == 'ALIGNED')} of {len(gov_in)} addressed"
        tiles.append({"label": phrasing.SECTION_LABELS[key], "status": phrasing.section(sections[key]["status"]),
                      "flag": sections[key]["status"] in ("REVISIONS_RECOMMENDED", "REVIEW_IN_PROGRESS"), "foot": foot})

    authorized = (block or {}).get("authorized") or (ledger.get("policy_facts") or {}).get("authorized_instruments") \
        or ((ledger.get("instruments") or {}).get("authorized") or [])
    evidence = _evidence_requests(Path(registers_root), set(authorized))
    doc = ledger.get("document") or {}
    discarded = [f"{f['control_id']}:{d.get('element_id', d) if isinstance(d, Mapping) else d}"
                 for f in findings for d in (f.get("discarded_claims") or [])]
    return {
        **_header(ledger, entity),
        "entity_class": entity_class, "policy_version": policy_version,
        "distribution": distribution,
        "headline": headline, "headline_sub": sub,
        "tiles": tiles,
        "reliability": authorization_reliability(ledger),
        "leading": leading[:6], "leading_more": max(0, len(leading) - 6),
        "queue": queue,
        "authorized": sorted(authorized),
        "v2": v2_rows, "v2_status": (block or {}).get("status"), "v2_version": (block or {}).get("catalogue_version"),
        "not_reviewed": (block or {}).get("not_reviewed", []),
        "instrument_findings": [{"cite": f["citation"], "title": f["title"], "status": phrasing.status(f["status"])}
                                for f in inst_findings if f.get("band") == "STATUTORY" and f["status"] != "NOT_APPLICABLE"],
        "core_cards": [_card(f, raw_of(f)) for f in open_core],
        "core_aligned": [{"cite": f["citation"], "title": f["title"], "status": phrasing.status(f["status"])} for f in aligned_core],
        "governance": [{"cite": f["citation"], "title": f["title"],
                        "status": "Not applicable" if not f.get("in_scope") else phrasing.status(f["status"])}
                       for f in context_items],
        "restatements": [{"cite": f["citation"], "title": f["title"], "status": phrasing.status(f["status"])}
                         for f in inst_findings if f.get("band") == "ADVISORY" and f["status"] in open_statuses],
        "evidence": evidence,
        "provenance": {
            "source": doc.get("source_name") or doc.get("label"), "sha256": doc.get("source_sha256") or doc.get("sha256"),
            "backend": doc.get("backend"), "quality": (doc.get("quality") or {}).get("verdict"),
            "reader": ledger.get("extractor"), "registers": ", ".join(f"{r['id'].split('/')[-1]} {r['version']}" for r in ledger.get("registers", [])),
            "catalogue": f"{(block or {}).get('catalogue_version', '-')} ({(block or {}).get('status', 'not run')})",
            "discarded": discarded, "generated": ledger.get("generated_at"),
        },
        "scope_statement": "Governance and administrative provisions are summarized, not reviewed in detail.",
    }


def _evidence_requests(root: Path, authorized: set[str]) -> list[dict[str, Any]]:
    try:
        doc = json.loads((root / "evidence-requests" / "register.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    out = []
    for q in doc.get("requests", []):
        if q.get("status") == "paused":
            continue
        scopes = [s.get("instrument_authorized") for s in q.get("scope", [])]
        if any(s is None for s in scopes) or not scopes or set(scopes) & authorized:
            out.append({"id": q["id"], "request": q["request"], "cite": q.get("cite", ""), "cadence": q.get("cadence", "")})
    return out
