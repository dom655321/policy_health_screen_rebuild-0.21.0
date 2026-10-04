"""Offline deterministic stand-in for condition fact extraction.

It answers the Schedule B v2 prompt by pattern-matching inside the supplied windows, and it
exists for the same reason as the Schedule A heuristic adapter: CI and golden cases need a
deterministic path through prompting, verification and evaluation with no network.

It is not review-grade. It reads figures, ratings, agency counts and rating basis with
regular expressions and decides REQUIRED conditions by keyword overlap. It does not map
SUBSET vocabularies: where a SUBSET condition's subject appears it omits the fact (UNKNOWN)
rather than guess; where it does not appear it answers silence. ANY_OF conditions are
answered only from cue phrases carried in the catalogue.
"""
from __future__ import annotations

import json
import re
from typing import Any

SENTENCE = re.compile(r"(?<=[.;])\s+|\n\s*\n")
NUM_UNIT = re.compile(r"(\d{1,4}(?:,\d{3})?(?:\.\d+)?)\s*(?:\(\d+\)\s*)?(days?|months?|years?|%|percent)\b", re.I)
LESS_THAN = re.compile(r"less than\s*$", re.I)
AGENCIES = re.compile(r"\b(?:at least|by)\s+(one|two|three|1|2|3)\s+(?:nationally recognized|rating|credit)", re.I)
RATING = {
    "SHORT_TERM": re.compile(r"\b(A-1\+|A-1|A1\+|A1|P-1|P1|F1\+|F1|A-2|P-2|F2)\b"),
    "LONG_TERM": re.compile(r"\b(AAA|AA\+|AA-|AA|A\+|A-|Aaa|Aa1|Aa2|Aa3|A1|A2|A3|BBB\+|BBB-|BBB|Baa1|Baa2|Baa3)(?![-\w])"),
    "POOL": re.compile(r"\b(AAA-?m(?:mf)?|AAAm|AAAf|AAA|AA-?m|AAf)\b"),
}
WORD_NUM = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3}
FRAME = {"policy", "requires", "requirement", "authorized", "investment", "investments",
         "statute", "conditions", "condition", "including", "limited"}
UNIT = {"day": "days", "days": "days", "month": "months", "months": "months",
        "year": "years", "years": "years", "%": "pct", "percent": "pct"}


class ConditionStandIn:
    name = "conditions-standin-offline"

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        request = json.loads(prompt.split("<request>", 1)[1].split("</request>", 1)[0])
        text = prompt.split("Document windows:\n", 1)[-1].split("\n\n<request>", 1)[0]
        sentences = [" ".join(s.split()) for s in SENTENCE.split(text)
                     if s.strip() and not s.strip().startswith("[window offset")]
        # Keep sentences about this instrument and their neighbours (lists run on);
        # a figure in a neighbouring clause about another instrument is not this one's term.
        terms = [t.lower() for t in request.get("instrument_terms", [])]
        if terms:
            keep: set[int] = set()
            for i, s in enumerate(sentences):
                if any(t in s.lower() for t in terms):
                    keep.update({i - 1, i, i + 1})
            sentences = [s for i, s in enumerate(sentences) if i in keep]
        out: dict[str, Any] = {"conditions": {}, "activation": {}}
        for cond in request["conditions"]:
            fact = self._fact(cond, sentences)
            if fact is not None:
                out["conditions"][cond["id"]] = fact
        cues = request.get("activation_cues", {})
        for key in request.get("activation", []):
            out["activation"][key] = self._activation(cues.get(key, []), sentences)
        return out

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _keywords(requirement: str) -> list[str]:
        words = [w.strip(".,;:()'\"").lower() for w in requirement.split()]
        return [w for w in words if len(w) > 5 and w not in FRAME][:8]

    def _topic(self, cond: dict[str, Any], sentences: list[str], need: int = 2) -> str | None:
        keys = self._keywords(cond["requirement"])
        best, score = None, 0
        for s in sentences:
            low = s.lower()
            hits = sum(1 for k in keys if k in low)
            if hits > score:
                best, score = s, hits
        return best if score >= min(need, len(keys)) else None

    # -------------------------------------------------------------- per mode

    @staticmethod
    def _contradiction(cond: dict[str, Any], sentences: list[str]) -> tuple[Any, str] | None:
        for raw in cond.get("contradiction_cues", []):
            cue, value = (raw["cue"], raw.get("value")) if isinstance(raw, dict) else (raw, None)
            if any(cue.lower() in s.lower() for s in sentences):
                return value, cue
        return None

    def _fact(self, cond: dict[str, Any], sentences: list[str]) -> dict[str, Any] | None:
        mode = cond["mode"]
        hit = self._contradiction(cond, sentences)
        if hit is not None:
            value, cue = hit
            if mode == "REQUIRED":
                return {"stated": True, "contradicted": True, "quote": cue}
            if mode == "SUBSET":
                return {"stated": True, "value": [f"OTHER:{cue}"], "quote": cue}
            if mode == "PROHIBITED":
                return {"authorized": True, "quote": cue}
            if mode == "ANY_OF":
                return {"stated": True, "outside": True, "quote": cue}
            if mode == "RATING_FLOOR":
                return {"stated": True, "value": value, "quote": cue} if value else None
        if mode in ("CAP", "FLOOR"):
            return self._figure(cond, sentences)
        if mode == "RATING_FLOOR":
            return self._rating(cond, sentences)
        if mode == "ANY_OF":
            return self._any_of(cond, sentences)
        if mode == "SUBSET":
            return None if self._topic(cond, sentences) else {"stated": False}
        if mode == "REQUIRED":
            s = self._topic(cond, sentences, need=3)
            return {"stated": True, "contradicted": False, "quote": s} if s else {"stated": False}
        if mode == "PROHIBITED":
            return {}
        return None

    def _figure(self, cond: dict[str, Any], sentences: list[str]) -> dict[str, Any] | None:
        want_pct = str(cond.get("unit", "")).startswith("pct")
        topic = self._topic(cond, sentences, need=1)
        if topic is None:
            return {"stated": False}
        for m in NUM_UNIT.finditer(topic):
            unit = UNIT[m.group(2).lower()]
            if (unit == "pct") != want_pct:
                continue
            inclusive = not LESS_THAN.search(topic[: m.start()])
            return {"stated": True, "value": float(m.group(1).replace(",", "")), "unit": unit,
                    "inclusive": inclusive, "quote": m.group(0)}
        return None  # the subject is present but no comparable figure was read: UNKNOWN

    def _rating(self, cond: dict[str, Any], sentences: list[str]) -> dict[str, Any] | None:
        pattern = RATING[cond["scale"]] if cond["scale"] in RATING else None
        topic = self._topic(cond, sentences, need=1)
        if topic is None or pattern is None:
            return {"stated": False}
        m = pattern.search(topic)
        if not m:
            return None
        fact: dict[str, Any] = {"stated": True, "value": m.group(1), "quote": m.group(0)}
        a = AGENCIES.search(topic)
        if a:
            fact["agencies"] = WORD_NUM[a.group(1).lower()]
        low = topic.lower()
        if "continuously" in low:
            fact["basis"] = "CONTINUOUS"
        elif "at the time of" in low:
            fact["basis"] = "AT_PURCHASE"
        return fact

    def _any_of(self, cond: dict[str, Any], sentences: list[str]) -> dict[str, Any] | None:
        stated, quote = [], ""
        for alt in cond.get("alternatives", []):
            for cue in alt.get("cues", []):
                hit = next((s for s in sentences if cue in s.lower()), None)
                if hit:
                    stated.append(alt["id"])
                    quote = quote or cue
                    break
        if stated:
            return {"stated": True, "value": stated, "quote": quote}
        for cue in cond.get("outside_cues", []):
            hit = next((s for s in sentences if cue in s.lower()), None)
            if hit:
                return {"stated": True, "outside": True, "quote": cue}
        return None if self._topic(cond, sentences) else {"stated": False}

    @staticmethod
    def _activation(cues: list[str], sentences: list[str]) -> dict[str, Any]:
        for cue in cues:
            hit = next((s for s in sentences if cue in s.lower()), None)
            if hit:
                return {"value": True, "quote": cue}
        return {"value": False}
