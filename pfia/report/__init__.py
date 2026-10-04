"""Report rendering.

Optional extra. The core pipeline does not import this package, and nothing here is
required to produce a finding ledger.
"""

from .viewmodel import build as build_context
from .render import extras_available, render_html, render_pdf

__all__ = ["build_context", "render_html", "render_pdf", "extras_available"]
