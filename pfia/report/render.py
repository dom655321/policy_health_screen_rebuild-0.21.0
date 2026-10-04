"""Jinja2 + WeasyPrint rendering.

Jinja2 and WeasyPrint are optional extras, not runtime dependencies. The register, the
evaluator, the adapter and the ingestion path stay importable with nothing installed;
only report rendering needs the extras, and it says so plainly when they are missing.

The environment uses StrictUndefined deliberately. The template carries a comment from the
earlier build recording a bug where a renamed field resolved to Undefined and printed a
fallback string on every card while the real quote silently vanished. Under
StrictUndefined that is a render-time error instead of a wrong report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

TEMPLATE_DIR = Path(__file__).parent / "templates"
# The redesigned template is the default. The inherited HSAM template is kept so an
# earlier ledger can still be rendered the way it was originally reviewed.
DEFAULT_TEMPLATE = "hsam_screen.html"
LEGACY_TEMPLATE = "audit_report_internal.html"
TEMPLATES = {"screen": "screen.html", "screen-0.19": DEFAULT_TEMPLATE, "legacy": LEGACY_TEMPLATE}

MISSING = (
    "Report rendering needs the optional extras. Install them with:\n"
    "    pip install 'tx-pfia-register[report]'\n"
    "or: pip install jinja2 weasyprint"
)


def _environment():
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(MISSING) from exc
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=True,
    )


def render_html(context: Mapping[str, Any], template: str = DEFAULT_TEMPLATE) -> str:
    env = _environment()
    # The scorecard is pre-rendered markup, so it is the one value allowed through unescaped.
    from markupsafe import Markup

    payload = dict(context)
    if "scorecard" in payload:
        payload["scorecard"] = Markup(payload["scorecard"])
    return env.get_template(template).render(**payload)


def render_pdf(context: Mapping[str, Any], out_path: str | Path,
               template: str = DEFAULT_TEMPLATE) -> Path:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(MISSING) from exc
    html = render_html(context, template)
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(str(destination))
    return destination


def extras_available() -> tuple[bool, list[str]]:
    """Report which optional extras are installed, for a clear CLI message."""
    missing: list[str] = []
    for module in ("jinja2", "weasyprint"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return (not missing), missing
