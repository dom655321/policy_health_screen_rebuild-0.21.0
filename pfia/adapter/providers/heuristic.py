"""Offline deterministic stand-in adapter.

It answers the extraction prompt by literal search inside the supplied windows, quoting
the sentence around the match. It exercises the entire pipeline - retrieval, prompting,
response normalization, span verification, caching - without a network call, which is what
makes the golden harness runnable in CI.

It is not review-grade and must never be used for client work. It cannot tell whether a
matched phrase actually supports an element assertion, which is precisely the judgment a
real model is there to make. Its value is that it is deterministic: when a golden fixture
moves, the register or the evaluator changed, not the weather.
"""

from __future__ import annotations

import re
from typing import Any

SENTENCE_END = re.compile(r"(?<=[.;:])\s")

# Words the register's policy-text convention puts in every assertion ("The policy requires
# ...", "Each strategy addresses ..."). As keywords they would match nearly any sentence.
FRAME_WORDS = frozenset({"requires", "addresses"})


class HeuristicAdapter:
    name = "heuristic-offline"

    def _elements(self, prompt: str) -> list[str]:
        block = prompt.split("Elements to assess:\n", 1)[-1].split("\n\n", 1)[0]
        return [line.strip().split(":", 1)[0] for line in block.splitlines() if line.strip()]

    def _windows(self, prompt: str) -> str:
        return prompt.split("Document windows:\n", 1)[-1].rsplit("\n\nReturn JSON", 1)[0]

    def _keywords(self, assertion: str) -> list[str]:
        words = [w.strip(".,;:()").lower() for w in assertion.split()]
        return [w for w in words if len(w) > 6 and w not in FRAME_WORDS][:6]

    def _assertions(self, prompt: str) -> dict[str, str]:
        block = prompt.split("Elements to assess:\n", 1)[-1].split("\n\n", 1)[0]
        out: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.strip().split(":", 1)
                out[key.strip()] = value.strip()
        return out

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        text = self._windows(prompt)
        assertions = self._assertions(prompt)
        elements: list[dict[str, Any]] = []
        for element_id in self._elements(prompt):
            assertion = assertions.get(element_id, "")
            keywords = self._keywords(assertion)
            quote = ""
            for sentence in SENTENCE_END.split(text):
                cleaned = sentence.strip()
                if not cleaned or cleaned.startswith("[window offset"):
                    continue
                lowered = cleaned.lower()
                if any(k in lowered for k in keywords):
                    quote = " ".join(cleaned.split())
                    break
            elements.append(
                {
                    "id": element_id,
                    "supported": bool(quote),
                    "quote": quote,
                    "note": "" if quote else "no keyword overlap in the supplied windows",
                }
            )
        return {"elements": elements}
