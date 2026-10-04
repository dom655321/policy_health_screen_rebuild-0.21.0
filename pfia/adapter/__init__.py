"""Model adapter layer.

The register decides what to ask; the adapter decides who to ask; the evaluator decides
what it means. Nothing in this package produces a verdict.
"""

from .base import AdapterError, ModelAdapter, ModelResponse
from .runner import ExtractionRun, run_extraction

__all__ = ["AdapterError", "ModelAdapter", "ModelResponse", "ExtractionRun", "run_extraction"]
