"""Adapter protocol and response contract.

An adapter answers one question about one control: which required elements does this
document window support, quoted verbatim, plus any facts the control asks for. It is
never told the verdict vocabulary, the control's severity, its weight, or how the answer
will be scored. That separation is what keeps two different models comparable — they are
answering a retrieval question, not exercising judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class AdapterError(RuntimeError):
    """Raised when a provider fails or returns an unusable payload."""


@dataclass
class ElementClaim:
    """One element assertion as answered by the model."""

    element_id: str
    supported: bool
    quote: str = ""
    note: str = ""


@dataclass
class ModelResponse:
    """Normalized provider output, before span verification."""

    control_id: str
    elements: list[ElementClaim] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class ModelAdapter(Protocol):
    """Any object that can answer an extraction prompt."""

    name: str

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        """Return the provider's JSON object for this prompt."""
        ...
