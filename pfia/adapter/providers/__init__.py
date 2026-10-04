"""Provider implementations.

All providers satisfy the same `ModelAdapter` protocol and return the same JSON shape.
Swapping providers is a constructor change; nothing downstream is aware of which one ran,
beyond the adapter name recorded in the ledger.
"""

from .heuristic import HeuristicAdapter
from .replay import ReplayAdapter
from .http_json import AnthropicAdapter, GeminiAdapter

__all__ = ["HeuristicAdapter", "ReplayAdapter", "AnthropicAdapter", "GeminiAdapter"]
