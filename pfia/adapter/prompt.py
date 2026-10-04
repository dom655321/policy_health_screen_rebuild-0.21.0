"""Prompt construction, derived from the register rather than hand-written.

A control edit propagates into the prompt automatically. No prompt text is maintained
separately from the control it serves, so the register stays the single source of truth
and there is no second artifact to drift.

Three things are deliberately withheld from the model:

  * the verdict vocabulary, so it cannot skip to a conclusion;
  * severity and weight, so its answer cannot be biased by consequence;
  * the anti-pattern list, because anti-patterns are literal searches the runner performs
    deterministically. Asking a model to find them invites paraphrase matching, which is
    exactly the failure the anti-pattern library exists to prevent.
"""

from __future__ import annotations

import json
from typing import Any

from ..model import Control

SYSTEM_RULES = """You are extracting evidence from a public entity investment policy.

Rules:
1. Answer only from the document text provided. Never rely on outside knowledge of the law.
2. For each element, decide whether the document text supports the assertion.
3. When supported, quote the exact supporting text verbatim from the document. Do not
   paraphrase, correct or normalize it. Quote the shortest contiguous passage that carries
   the support - a clause or a sentence, never a whole section or several paragraphs.
4. If the text is silent, ambiguous, or only partially addresses the assertion, answer
   supported = false. A partial match is not support.
5. Do not judge whether the policy is compliant, adequate or lawful. That is not your task.
6. Return only a JSON object matching the schema. No prose outside the JSON, and no
   explanation before or after it.
7. Keep any note under 25 words. Notes are for why an assertion is unsupported, not for
   restating the document.
8. Where the policy states different limits for different rating tiers, fund types or
   circumstances, report the most permissive figure the policy allows for this instrument -
   the longest maturity, the largest percentage. Tiering always narrows, so the loosest
   stated term is the one that has to be checked against the statute."""


def asked_elements(control: Control) -> list:
    """Elements a model is asked about: the affirmative ones only.

    A negative element is a search for language that would defeat it, which the runner
    performs literally. Putting it to a model invites a fabricated quote for a proposition
    that has no supporting passage by construction.
    """
    return [e for e in control.elements if not e.tested_by_absence]


def response_schema(control: Control) -> dict[str, Any]:
    """JSON shape the provider is asked to return."""
    schema: dict[str, Any] = {
        "type": "object",
        "required": ["elements"],
        "properties": {
            "elements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "supported"],
                    "properties": {
                        "id": {"type": "string", "enum": [e.id for e in asked_elements(control)]},
                        "supported": {"type": "boolean"},
                        "quote": {"type": "string"},
                        "note": {"type": "string"},
                    },
                },
            }
        },
    }
    extract = control.test.get("extract_schema")
    if extract:
        schema["properties"]["facts"] = {"type": "object", "description": json.dumps(extract)}
    return schema


def build(control: Control, windows: list[tuple[int, str]]) -> str:
    """Render the extraction prompt for one control over the selected windows."""
    elements = "\n".join(
        f"  {e.id}: {e.assertion}" for e in asked_elements(control)
    )
    extract = control.test.get("extract_schema")
    facts_block = (
        "\nAlso extract these values where the text states them. Omit any key the text does "
        "not state; never infer or supply a default. Where several figures apply to the "
        "same key, report the most permissive one:\n"
        f"  {json.dumps(extract)}\n"
        if extract
        else ""
    )
    body = "\n\n".join(f"[window offset {offset}]\n{text}" for offset, text in windows)
    return f"""{SYSTEM_RULES}

Statutory subject under review (for context only, do not quote it back):
{control.cite_label} - {control.title}

Elements to assess:
{elements}
{facts_block}
Document windows:
{body}

Return JSON with one entry per element id listed above."""
