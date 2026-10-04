"""Schedule B v2: typed authorized-investment conditions.

One condition is one requirement a policy can state, contradict or omit independently.
The model extracts facts; every comparison (stricter, looser, outside the permitted set)
is made here, deterministically, so a replayed extraction always yields the same verdict.

    catalogue  load and validate the condition register against the statute snapshot
    scales     ordinal credit-rating scales across agencies
    evaluate   per-condition state and categorical instrument status
"""
from .catalogue import Catalogue, CatalogueError, load_catalogue
from .evaluate import (
    BY_REFERENCE, CONFORMING, CONTRADICTED, SILENT, STRICTER, UNKNOWN,
    ConditionResult, InstrumentResult, evaluate_condition, evaluate_instrument,
)

__all__ = [
    "Catalogue", "CatalogueError", "load_catalogue",
    "BY_REFERENCE", "CONFORMING", "CONTRADICTED", "SILENT", "STRICTER", "UNKNOWN",
    "ConditionResult", "InstrumentResult", "evaluate_condition", "evaluate_instrument",
]
