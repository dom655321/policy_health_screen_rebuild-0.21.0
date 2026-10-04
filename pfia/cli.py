"""Command line entry point.

    python -m pfia coverage  --profile data/profiles/water_authority.json
    python -m pfia review    --profile ... --policy ... --facts ... --out ledger.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import coverage as coverage_module
from . import loader
from . import profile as profile_module
from . import instruments as instruments_module
from .adapter import run_extraction
from .adapter.base import AdapterError
from .errors import RegisterLoadError
from .adapter.providers import AnthropicAdapter, GeminiAdapter, HeuristicAdapter, ReplayAdapter
from .evaluate import review
from .extraction import KeywordExtractor, NullExtractor, PrecomputedExtractor
from .ingest import IngestError, SourceDocument, ingest_path
from .ledger import build_ledger, write_ledger

def _default_root() -> Path:
    """Locate the register.

    The register is data, not code: it is reviewed, diffed and amended on a legislative
    cycle rather than a release cycle, so it lives at the repository root rather than
    inside the package. That means an installed wheel cannot assume a repo-relative path.

    Resolution order: an explicit environment variable, then the repository layout, then
    a copy shipped inside the package if one was built. Nothing is guessed - a caller that
    lands on none of these gets a path that fails loudly at load time rather than a silent
    empty register.
    """
    override = os.environ.get("PFIA_REGISTER_ROOT")
    if override:
        return Path(override)
    repo = Path(__file__).resolve().parents[2] / "data" / "registers"
    if repo.exists():
        return repo
    packaged = Path(__file__).resolve().parent / "data" / "registers"
    if packaged.exists():
        return packaged
    return repo


DEFAULT_ROOT = _default_root()


def _load_json(path: str | None) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def _ingest(args) -> SourceDocument:
    """Load the policy through the ingestion path, whatever format it arrived in."""
    try:
        source = ingest_path(args.policy, backend=getattr(args, "ingest_backend", None),
                             force=getattr(args, "force_ingest", False))
    except IngestError as exc:
        raise SystemExit(str(exc))
    for warning in source.warnings:
        print(f"  ingest warning: {warning}")
    return source


def _add_ingest_args(parser) -> None:
    parser.add_argument("--ingest-backend", choices=["pdftotext", "pypdf", "stdlib-pdf", "plaintext"],
                        help="force a specific extraction backend instead of the best available")
    parser.add_argument("--force-ingest", action="store_true",
                        help="proceed even when extraction quality is UNUSABLE")


def _build_adapter(args):
    """Construct a model adapter. Credentials come from the environment, never the CLI."""
    name = args.adapter
    if name == "heuristic":
        return HeuristicAdapter()
    if name == "replay":
        if not args.cassette:
            raise SystemExit("--adapter replay requires --cassette")
        return ReplayAdapter(args.cassette)
    if name in ("anthropic", "gemini"):
        # No built-in default model (ADR 0012). --model, or PFIA_MODEL in the environment:
        # either is an explicit, recorded choice.
        model = args.model or os.environ.get("PFIA_MODEL")
        if not model:
            raise SystemExit(f"--adapter {name} requires --model or PFIA_MODEL (for example gemini-3.8-flash)")
        return (AnthropicAdapter if name == "anthropic" else GeminiAdapter)(model)
    raise SystemExit(f"unknown adapter {name!r}")


def _render_output(context, template: str, args) -> int:
    from .report import extras_available, render_html, render_pdf
    ok, missing = extras_available()
    if "jinja2" in missing:
        raise SystemExit("Rendering needs Jinja2:\n    pip install jinja2")
    if not args.out and not args.html:
        raise SystemExit("give --html PATH, --out PATH (PDF), or both")
    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(render_html(context, template), encoding="utf-8")
        print(f"HTML written to {args.html}")
    if args.out:
        if "weasyprint" in missing:
            raise SystemExit("PDF output needs WeasyPrint (pip install weasyprint); use --html and print from a browser.")
        render_pdf(context, args.out, template)
        print(f"PDF written to {args.out}")
    return 0


def cmd_redline(args) -> int:
    """Proposed amendments from a ledger (Core provisions and authorized-investment terms)."""
    from .report.outputs import redline_context
    ledger = _load_json(args.ledger)
    ctx = redline_context(ledger, args.root, args.entity, statutory_only=args.statutory_only)
    c = ctx["counts"]
    print(f"{len(ctx['amendments'])} amendment(s): {c['revisions']} revision(s), {c['additions']} addition(s); "
          f"{c['optional']} optional restatement(s); {c['held']} held for verification")
    return _render_output(ctx, "redline.html", args)


def cmd_mandate_fit(args) -> int:
    """Internal onboarding view: can a strategy run under the policy?"""
    from .conditions import load_catalogue
    from .report.outputs import StrategyError, load_strategy, mandate_fit_context
    ledger = _load_json(args.ledger)
    cat = load_catalogue(Path(args.root) / "instrument-conditions" / "register.json")
    try:
        strategy = load_strategy(args.strategy, cat)
    except StrategyError as exc:
        raise SystemExit(str(exc))
    limits = _load_json(args.policy_limits) if args.policy_limits else None
    ctx = mandate_fit_context(ledger, strategy, args.root, args.entity, limits)
    t = ctx["tally"]
    print(f"{ctx['strategy_name']}: {t['Blocks']} block(s), {t['Constrains'] + t['portfolio_constrains']} constraint(s), "
          f"{t['Fits']} fit(s), {t['Cannot determine']} to confirm")
    return _render_output(ctx, "mandate_fit.html", args)


def _build_second(args):
    """Second reader for Schedule B v2 two-reader mode (ADR 0012)."""
    if not getattr(args, "second_adapter", None):
        return None
    if not args.second_model:
        raise SystemExit("--second-adapter requires --second-model")
    return (AnthropicAdapter if args.second_adapter == "anthropic" else GeminiAdapter)(args.second_model)


def _add_adapter_args(parser) -> None:
    parser.add_argument("--adapter", default=os.environ.get("PFIA_ADAPTER", "heuristic"),
                        choices=["heuristic", "replay", "anthropic", "gemini"])
    parser.add_argument("--model", help="provider model id, for live adapters")
    parser.add_argument("--cassette", help="recorded responses, for --adapter replay")
    parser.add_argument("--cache", help="directory for the extraction response cache")
    parser.add_argument("--second-adapter", choices=["anthropic", "gemini"],
                        help="second reader for Schedule B v2 (two-reader mode); disagreements read UNKNOWN")
    parser.add_argument("--second-model", help="model id for --second-adapter")


def _build_extractor(args) -> object:
    if getattr(args, "extraction", None):
        payload = _load_json(args.extraction)
        meta = payload.pop("_extraction", None) or {}
        # Without provenance the reader is unknown, so the review treats it as not
        # review-grade (every finding is queued for verification) rather than trusting it.
        source = meta.get("adapter") or f"unlabelled:{Path(args.extraction).name}"
        return PrecomputedExtractor(payload, source=source)
    if getattr(args, "extractor", None) == "null":
        return NullExtractor()
    return KeywordExtractor()


def cmd_version(args) -> int:
    """Report what is actually running.

    Every component that changes behaviour carries its own version, and they move
    independently: the package, each register, the instrument lexicon and the coverage
    inventory. A stale editable install or an extraction over the top of an older tree
    looks identical from the outside, and the only way to be sure which code produced a
    result is to ask it.
    """
    from . import __version__

    print(f"tx-pfia-register {__version__}")
    print(f"  package     {Path(__file__).resolve().parent}")
    print(f"  register root {Path(args.root)}")
    try:
        rs = loader.load(Path(args.root), args.registers or None)
    except Exception as exc:  # noqa: BLE001 - the point is to report, not to raise
        print(f"  registers   FAILED to load: {exc}")
        return 1
    for register in rs.registers:
        print(f"  schedule {register.schedule}  version {register.version}  "
              f"{len(register.controls)} controls  law in force {register.law_in_force_as_of}")
    print(f"  predicates  {len(rs.predicates)}")
    print(f"  entity classes {len(rs.entity_classes)}")
    try:
        from .instruments import load_lexicon

        lexicon = load_lexicon(Path(args.root))
        print(f"  lexicon     version {lexicon['version']}  "
              f"{len(lexicon['instruments'])} instrument codes  "
              f"{len(lexicon['section_directives'])} section directives")
    except Exception as exc:  # noqa: BLE001
        print(f"  lexicon     FAILED to load: {exc}")
    try:
        from .coverage import load_inventory

        inventory = load_inventory(Path(args.root))
        print(f"  coverage    version {inventory['version']}  "
              f"{len(inventory['sections'])} sections")
    except Exception as exc:  # noqa: BLE001
        print(f"  coverage    FAILED to load: {exc}")
    try:
        from .profile import load_field_specs

        specs = load_field_specs(Path(args.root).parent / "profiles")
        print(f"  profile     {len(specs)} questions")
    except Exception as exc:  # noqa: BLE001
        print(f"  profile     FAILED to load: {exc}")

    available, missing = __import__("pfia.report.render", fromlist=["x"]).extras_available()
    print(f"  report extras {'all present' if available else 'missing ' + ', '.join(missing)}")
    return 0


def cmd_adapter_check(args) -> int:
    """Smoke-test a live provider against one real control before spending a run on it."""
    from .adapter.base import AdapterError
    from .adapter.payload import normalize_response, verify
    from .adapter.prompt import build as build_prompt, response_schema

    rs = loader.load(Path(args.root), args.registers or None)
    control = rs.control(args.control)
    if control is None:
        raise SystemExit(f"unknown control {args.control!r}")
    # A probe passage that plainly satisfies the control, so a failure here is a provider
    # or parsing problem rather than a judgement call.
    document = (
        "SETTLEMENT. This policy contains a settlement requirement stated as a mandate. "
        "All securities transactions, other than investment pool funds and mutual funds, "
        "shall be settled on a delivery versus payment basis. The only carve-out is "
        "limited to investment pool funds and mutual funds."
    )
    prompt = build_prompt(control, [(0, document)])
    if args.show_prompt:
        print(prompt)
        print("\n" + "-" * 72 + "\n")
    try:
        adapter = _build_adapter(args)
        raw = adapter.ask(prompt, control.control_id, response_schema(control))
    except AdapterError as exc:
        raise SystemExit(f"adapter check FAILED: {exc}")

    entry = verify(control, normalize_response(control, raw), document)
    print(f"adapter: {getattr(adapter, 'name', 'unknown')}")
    print(f"control: {control.control_id} ({control.cite_label})")
    print(f"raw response keys: {sorted(raw)}")
    for element in control.elements:
        print(f"  {element.id}: satisfied={entry['elements_satisfied'].get(element.id)}")
    for line in entry["retrieval_trace"]:
        print(f"    {line}")
    if not any(entry["elements_satisfied"].values()):
        print("\nNo element was supported. Either the provider returned an unusable shape or "
              "it declined to quote; inspect the raw response before running a benchmark.")
        return 1
    print("\nResponse shape parsed and at least one quote verified against the document.")
    return 0


def cmd_purge(args) -> int:
    """Delete derived client material. The ledger is the only artifact meant to survive."""
    import shutil

    targets = [Path(p) for p in (args.paths or [])]
    if not targets:
        raise SystemExit("name at least one directory to purge")
    removed = 0
    for target in targets:
        if not target.exists():
            print(f"  absent {target}")
            continue
        if not args.yes:
            print(f"  would remove {target}")
            continue
        shutil.rmtree(target) if target.is_dir() else target.unlink()
        removed += 1
        print(f"  removed {target}")
    if not args.yes:
        print("\nDry run. Re-run with --yes to delete.")
    else:
        print(f"\n{removed} path(s) removed. Ledgers and rendered reports are unaffected "
              "unless you named their directory.")
    return 0


def cmd_coverage_map(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    classes: list[str] = []
    if args.profile:
        classes = rs.expand_classes(list(_load_json(args.profile).get("classes", [])))
    report = coverage_module.build(rs, Path(args.root), classes)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_instruments(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    document = _ingest(args).text
    resolution = instruments_module.detect(rs, document, Path(args.root))
    print(json.dumps(resolution.report(), indent=2))
    return 0


def cmd_profile(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    profiles_dir = Path(args.root).parent / "profiles"
    specs = profile_module.load_field_specs(profiles_dir)
    missing, orphaned = profile_module.reconcile(rs, specs)
    if args.action == "init":
        blank = profile_module.questionnaire(rs, specs, args.entity or "")
        Path(args.out).write_text(json.dumps(blank, indent=2) + "\n", encoding="utf-8")
        print(f"Questionnaire written to {args.out} ({len(specs) - 1} question(s) plus entity classes; "
              "see _how_to_answer in the file)")
        return 0

    if missing:
        print("Register facts with no profile question: " + ", ".join(sorted(missing)))
    if orphaned:
        print("Profile questions with no consumer: " + ", ".join(sorted(orphaned)))
    try:
        _entity, report = profile_module.load(rs, args.profile, profiles_dir)
    except profile_module.ProfileError as exc:
        raise SystemExit(str(exc))
    print(report.summary())
    for note in report.normalized:
        print(f"  normalized {note}")
    if report.unanswered:
        raw = _load_json(args.profile)
        effect = profile_module.impact(rs, raw, specs)
        print("\nUnanswered questions, and what each one costs:\n")
        for path in report.unanswered:
            blocked = effect.get(path, [])
            spec = specs[path]
            if not blocked:
                print(f"  {path}")
                print("      no control for these entity classes depends on it; any value is "
                      "safe, and false or 0 is the conventional answer")
            else:
                print(f"  {path}  ->  leaves {len(blocked)} control(s) unresolved")
                for control_id in blocked[:6]:
                    print(f"      {control_id}")
                if len(blocked) > 6:
                    print(f"      ... and {len(blocked) - 6} more")
            print(f"      Q: {spec.question}")
            if spec.cite:
                print(f"      cite: {spec.cite}")
            print()
    return 0 if (report.complete and not missing and not orphaned) else 1


def cmd_extract(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    document = _ingest(args).text
    # Same preparation as review: unanswered profile questions become UNKNOWN rather than
    # false, and the authorized-investment set is read from the document unless supplied.
    # Without this, extract silently skipped every instrument control.
    entity, _profile_report, facts, _resolution = _prepare(rs, args, document)
    try:
        adapter = _build_adapter(args)
    except AdapterError as exc:
        raise SystemExit(str(exc))
    run = run_extraction(rs, adapter, document, entity, facts, cache_dir=args.cache)
    from datetime import datetime, timezone
    from . import __version__
    # Provenance travels with the payload, so a later `review --extraction` knows which
    # reader produced it (a heuristic payload is never treated as review-grade).
    payload = {**run.payload, "_extraction": {
        "adapter": run.adapter, "context_adapter": run.context_adapter or None,
        "package_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(run.summary())
    for control_id, message in sorted(run.failures.items()):
        print(f"  FAILED {control_id}: {message}")
    print(f"Extraction payload written to {args.out}")
    return 0


def cmd_coverage(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    profile = _load_json(args.profile)
    facts = _load_json(args.facts)
    result = review(rs, profile, facts, document="", extractor=NullExtractor())
    print(f"{'CONTROL':<32} {'SCH':<4} {'SEV':<9} {'STATUS':<16} GATING REASON")
    for f in result.findings:
        applicable = f.in_scope
        status = ("APPLICABLE" if applicable
                  else "UNRESOLVED" if f.unresolved else "NOT_APPLICABLE")
        # Coverage reports gating only. Extraction-stage reasons belong to `review`.
        reason = "" if applicable else (f.reasons[0] if f.reasons else "")
        if f.substitutes:
            reason += f" -> {', '.join(f.substitutes)}"
        print(f"{f.control_id:<32} {f.schedule:<4} {f.severity:<9} {status:<16} {reason}")
    applicable = len(result.in_scope())
    unresolved = len(result.unresolved())
    print(f"\n{applicable} of {len(result.findings)} controls applicable to this entity profile"
          + (f"; {unresolved} unresolved without a policy document to read the authorized-"
             "investment set from" if unresolved else "") + ".")
    return 0


def cmd_report(args) -> int:
    from .report import build_context, extras_available, render_html, render_pdf

    if not args.out and not args.html:
        raise SystemExit("name an output: --out for PDF, --html for HTML, or both")

    # HTML needs Jinja2 alone. WeasyPrint is only required to paginate into a PDF, and it
    # carries system library dependencies that HTML output should not be held hostage to.
    _available, missing = extras_available()
    if "jinja2" in missing:
        raise SystemExit("Report rendering needs Jinja2:\n    pip install jinja2")
    want_pdf = bool(args.out)
    if want_pdf and "weasyprint" in missing:
        if args.html:
            print("  WeasyPrint is not installed, so the PDF was skipped. The HTML below "
                  "carries the same print styling; open it in a browser and print to PDF.")
            want_pdf = False
        else:
            raise SystemExit(
                "PDF output needs WeasyPrint, which needs system libraries:\n"
                "    brew install pango gdk-pixbuf libffi\n"
                "    pip install weasyprint\n"
                "Or render HTML instead and print it from a browser:\n"
                "    pfia report --ledger ... --entity ... --html report.html"
            )
    from .report.render import TEMPLATES

    ledger = _load_json(args.ledger)
    if args.template == "screen":
        # The current screen (ADR 0014), built on the same view layer as the redline and
        # mandate fit. The earlier designs stay available for ledgers reviewed with them.
        from .report.outputs import screen_context
        ctx = screen_context(ledger, args.root, args.entity, entity_class=args.entity_class,
                             policy_version=args.policy_version, distribution=args.distribution)
        if args.html:
            Path(args.html).parent.mkdir(parents=True, exist_ok=True)
            Path(args.html).write_text(render_html(ctx, "screen.html"), encoding="utf-8")
            print(f"HTML written to {args.html}")
        if want_pdf:
            render_pdf(ctx, args.out, "screen.html")
            print(f"PDF written to {args.out}")
        print(f"  result: {ctx['headline']}")
        for t in ctx["tiles"]:
            print(f"  {t['label']}: {t['status']}")
        for r in ctx["reliability"]:
            print(f"  WARNING: {r}")
        return 0
    context = build_context(
        ledger,
        entity_name=args.entity,
        policy_version=args.policy_version,
        entity_class_label=args.entity_class,
    )
    context["distribution"] = args.distribution
    template = TEMPLATES[args.template]
    if args.html:
        Path(args.html).write_text(render_html(context, template), encoding="utf-8")
        print(f"HTML written to {args.html}")
    destination = render_pdf(context, args.out, template) if want_pdf else Path(args.html)
    print(f"Report written to {destination} ({destination.stat().st_size:,} bytes)")
    print(f"  result: {context['report'].statutory_verdict.value} ({context['overall_label']})")
    for name, label in context["section_labels"].items():
        print(f"  {name}: {label}")
    print(f"  statutory {context['statutory']['passed']}/{context['statutory']['reviewed']} addressed, "
          f"{context['deficiency_count']} item(s) for review")
    if not context["report"].citations_validated:
        print(f"  citation verification: {len(context['report'].unverified_quotes)} unmatched quote(s); "
              "executive summary withheld")
    return 0


def cmd_ingest(args) -> int:
    source = _ingest(args)
    provenance = source.provenance()
    print(json.dumps(provenance, indent=2))
    if args.out:
        Path(args.out).write_text(source.text, encoding="utf-8")
        print(f"\nDerived text written to {args.out}")
    return 0


def _prepare(rs, args, document: str):
    """Resolve the entity profile and the policy's authorized-investment set."""
    profiles_dir = Path(args.root).parent / "profiles"
    try:
        entity, profile_report = profile_module.load(rs, args.profile, profiles_dir)
    except profile_module.ProfileError as exc:
        raise SystemExit(str(exc))
    if profile_report.unanswered:
        print(f"  profile: {profile_report.summary()}")
        for path in profile_report.unanswered:
            blocked = profile_report.blocked_controls.get(path, [])
            print(f"    unanswered {path}"
                  + (f" -> unresolves {len(blocked)} control(s)" if blocked else ""))

    resolution = None
    if args.facts:
        facts = _load_json(args.facts)
    else:
        resolution = instruments_module.detect(rs, document, Path(args.root))
        facts = resolution.to_facts()
        print(f"  instruments: {resolution.state}, {len(resolution.authorized)} type(s) detected"
              + (" (set not closed)" if resolution.unresolved else ""))
        for reason in resolution.reasons:
            print(f"    {reason}")
    return entity, profile_report, facts, resolution


def cmd_review(args) -> int:
    rs = loader.load(Path(args.root), args.registers or None)
    source = _ingest(args)
    document = source.text
    entity, profile_report, facts, resolution = _prepare(rs, args, document)
    extractor = _build_extractor(args)
    result = review(rs, entity, facts, document, extractor)
    cover = coverage_module.build(rs, Path(args.root), entity.get("classes", []))
    v2_block = None
    if getattr(args, "schedule_b_v2", False):
        from .conditions import load_catalogue, wiring
        from .conditions.standin import ConditionStandIn
        cat = load_catalogue(Path(args.root) / "instrument-conditions" / "register.json")
        live = getattr(args, "adapter", "heuristic") in ("anthropic", "gemini", "replay")
        reader = _build_adapter(args) if live else ConditionStandIn()
        v2 = wiring.run(cat, rs, document, entity.get("classes", []), reader, Path(args.root),
                        authorized_override=facts.get("authorized_instruments") if args.facts else None,
                        second_adapter=_build_second(args) if live else None)
        v2_block = wiring.ledger_block(cat, v2)
    ledger = build_ledger(rs, result, document, Path(args.policy).name,
                          getattr(extractor, "name", "unknown"), source=source,
                          coverage=cover, profile_report=profile_report,
                          instruments=resolution, instrument_conditions=v2_block)

    if args.out:
        write_ledger(args.out, ledger)

    print(f"{ledger['in_scope_controls']}/{ledger['total_controls']} controls in scope\n")
    from .report.phrasing import SECTION_LABELS as labels
    for name, section in ledger["sections"].items():
        print(f"{labels[name]}: {section['status']}")
        for part, counts in sorted(section["counts"].items()):
            print(f"  {part}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if section["conflicts"]:
            print(f"  Conflicts with statute: {', '.join(section['conflicts'])}")
        if section["additions"]:
            print(f"  Required content not addressed: {', '.join(section['additions'])}")

    unresolved = ledger.get("unresolved_controls", 0)
    if unresolved:
        print(f"\nUNRESOLVED: {unresolved} control(s) could not be determined; each section they "
              "fall in reads REVIEW_IN_PROGRESS. This is not a finding of compliance.")
    cov = ledger.get("coverage") or {}
    if cov:
        print(f"\nCOVERAGE: {cov['sections_covered']}/{cov['sections_testable']} testable sections "
              f"of Subchapter A carry a control for this entity class")
        if cov["uncovered"]:
            print("  not evaluated: " + ", ".join(u["section"] for u in cov["uncovered"]))

    doc = ledger["document"]
    if doc.get("backend"):
        print(f"\nSource: {doc['label']} via {doc['backend']}, {doc.get('pages', 0)} page(s), "
              f"quality {doc.get('quality', {}).get('verdict', 'n/a')}")
    if ledger.get("instrument_conditions"):
        block = ledger["instrument_conditions"]
        print(f"\nSCHEDULE B v2 (proposed, {block['adapter']}): {block['section_status_if_adopted']}")
        for inst in block["instruments"]:
            print(f"  {inst['code']}: {inst['status']}"
                  + (f"; conflicts {', '.join(inst['contradicted'])}" if inst["contradicted"] else "")
                  + (f"; undetermined {', '.join(inst['unknown'])}" if inst["unknown"] else ""))
    if args.out:
        print(f"\nLedger written to {args.out} (sha256 {ledger['ledger_sha256'][:16]}...)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pfia", description="Texas PFIA policy review")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="register root directory")
    parser.add_argument("--registers", nargs="*", help="register subdirectories to load")
    parser.add_argument("--version", action="store_true",
                        help="report the running versions and exit")
    sub = parser.add_subparsers(dest="command", required=True)

    cov = sub.add_parser("coverage", help="show which controls apply to an entity profile")
    cov.add_argument("--profile", required=True)
    cov.add_argument("--facts", help="extracted policy facts JSON")
    cov.set_defaults(func=cmd_coverage)

    rev = sub.add_parser("review", help="evaluate a policy document")
    rev.add_argument("--profile", required=True)
    rev.add_argument("--policy", required=True)
    rev.add_argument("--facts", help="policy facts JSON; omit to detect the authorized-investment "
                                     "set from the document itself")
    rev.add_argument("--extraction", help="precomputed extraction payload JSON from a model adapter")
    rev.add_argument("--extractor", choices=["keyword", "null"], default="keyword")
    rev.add_argument("--out", help="path to write the finding ledger")
    rev.add_argument("--schedule-b-v2", action="store_true",
                     help="also run the proposed Schedule B v2 condition catalogue (ADR 0009) and "
                          "record it in the ledger; it never changes a section status")
    rev.add_argument("--adapter", default=os.environ.get("PFIA_ADAPTER", "heuristic"), choices=["heuristic", "replay", "anthropic", "gemini"],
                     help="reader for the Schedule B v2 run (Schedule A uses --extraction from `pfia extract`)")
    rev.add_argument("--model", help="provider model id, for a live --adapter")
    rev.add_argument("--cassette", help="recorded responses, for --adapter replay")
    rev.add_argument("--second-adapter", choices=["anthropic", "gemini"],
                     help="second reader for Schedule B v2; disagreements read UNKNOWN")
    rev.add_argument("--second-model", help="model id for --second-adapter")
    _add_ingest_args(rev)
    rev.set_defaults(func=cmd_review)

    ing = sub.add_parser("ingest", help="extract and inspect a policy document without reviewing it")
    ing.add_argument("--policy", required=True)
    ing.add_argument("--out", help="path to write the derived text")
    _add_ingest_args(ing)
    ing.set_defaults(func=cmd_ingest)

    rep = sub.add_parser("report", help="render a finding ledger as an internal working paper")
    rep.add_argument("--ledger", required=True)
    rep.add_argument("--entity", required=True, help="entity name as it should appear on the cover")
    rep.add_argument("--entity-class", help="entity class label shown under the entity name")
    rep.add_argument("--policy-version", help="policy version or adoption date, as stated in the document")
    rep.add_argument("--out", help="PDF output path; needs WeasyPrint")
    rep.add_argument("--html", help="also write the intermediate HTML")
    rep.add_argument("--template", choices=["screen", "screen-0.19", "legacy"], default="screen",
                     help="screen is the current design (ADR 0014); screen-0.19 is the earlier screen; "
                          "legacy is the inherited template")
    rep.add_argument("--distribution", choices=["internal", "client-draft"], default="internal",
                     help="marks page one. client-draft renders 'Draft - pending compliance "
                          "review' in place of the internal-use chip")
    rep.set_defaults(func=cmd_report)

    red = sub.add_parser("redline", help="proposed amendments from a ledger (draft, for reviewer approval)")
    red.add_argument("--ledger", required=True)
    red.add_argument("--entity", required=True)
    red.add_argument("--statutory-only", action="store_true",
                     help="leave out optional restatements of Core provisions the Act binds regardless")
    red.add_argument("--out", help="PDF output path; needs WeasyPrint")
    red.add_argument("--html", help="HTML output path")
    red.set_defaults(func=cmd_redline)

    mf = sub.add_parser("mandate-fit", help="internal onboarding view: can a strategy run under the policy?")
    mf.add_argument("--ledger", required=True, help="a ledger from `pfia review ... --schedule-b-v2`")
    mf.add_argument("--strategy", required=True, help="strategy parameters (see data/mandates/*.example.json)")
    mf.add_argument("--policy-limits", help="reviewer-entered portfolio figures from the policy")
    mf.add_argument("--entity", required=True)
    mf.add_argument("--out", help="PDF output path; needs WeasyPrint")
    mf.add_argument("--html", help="HTML output path")
    mf.set_defaults(func=cmd_mandate_fit)

    cmap = sub.add_parser("coverage-map",
                          help="report which sections of the subchapter carry controls")
    cmap.add_argument("--profile", help="restrict to sections relevant to this entity profile")
    cmap.set_defaults(func=cmd_coverage_map)

    ins = sub.add_parser("instruments", help="detect the policy's authorized-investment set")
    ins.add_argument("--policy", required=True)
    _add_ingest_args(ins)
    ins.set_defaults(func=cmd_instruments)

    pro = sub.add_parser("profile", help="create or check an entity profile")
    pro.add_argument("action", choices=["init", "check"])
    pro.add_argument("--profile", help="profile to check")
    pro.add_argument("--entity", help="entity name, for init")
    pro.add_argument("--out", default="profile.json", help="output path, for init")
    pro.set_defaults(func=cmd_profile)

    ver = sub.add_parser("version", help="report the running package, register and lexicon versions")
    ver.set_defaults(func=cmd_version)

    chk = sub.add_parser("adapter-check",
                         help="smoke-test a live provider on one control before a real run")
    chk.add_argument("--control", default="TX-PFIA-2256.005-b-4-E-001")
    chk.add_argument("--show-prompt", action="store_true")
    _add_adapter_args(chk)
    chk.set_defaults(func=cmd_adapter_check)

    pur = sub.add_parser("purge", help="delete derived client material (cache, derived text)")
    pur.add_argument("paths", nargs="*", help="directories or files to remove")
    pur.add_argument("--yes", action="store_true", help="actually delete; omit for a dry run")
    pur.set_defaults(func=cmd_purge)

    ext = sub.add_parser("extract", help="run the model adapter and write an extraction payload")
    ext.add_argument("--profile", required=True)
    ext.add_argument("--policy", required=True)
    ext.add_argument("--facts", help="extracted policy facts JSON")
    ext.add_argument("--out", required=True)
    _add_adapter_args(ext)
    _add_ingest_args(ext)
    ext.set_defaults(func=cmd_extract)

    if argv is None:
        import sys as _sys

        argv = _sys.argv[1:]
    if "--version" in argv:
        # Usable before a subcommand, which is where anyone reaches for it.
        stub = parser.parse_args(["--version", "version"] if "version" not in argv else argv)
        return cmd_version(stub)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AdapterError as exc:
        # A configuration or provider failure (missing key, unknown model, rate limit after
        # retries) is a message for the operator, not a traceback.
        print(f"model adapter error: {exc}", file=sys.stderr)
        return 2
    except (profile_module.ProfileError, RegisterLoadError) as exc:
        print(f"profile error: {exc}" if isinstance(exc, profile_module.ProfileError)
              else f"register error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # `pfia version | head` closes the pipe early. Python then reports the broken pipe
        # on interpreter shutdown, which looks like a crash in a command that worked.
        # Redirecting stdout to devnull suppresses the second write.

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
