"""Recovering the policy's own authorized-investment list.

Every control in Schedule B activates on `policy.authorized_instruments`. Supplying that
list by hand defeats the point of the review: the tool would then be scoring the reviewer's
belief about what the policy authorizes rather than the policy. This module reads it out of
the document.

Three states matter, and the difference between them is the whole design:

  * **enumerated** - instrument types were identified in an authorizing passage. Schedule B
    gates on them normally.
  * **blanket incorporation** - the policy authorizes whatever the chapter permits. The
    authorized set is genuinely indeterminate from the document, and saying so is the
    finding. Blanket-incorporation phrasing is read from the anti-pattern library of
    TX-PFIA-2256.005-b-4-A-001 rather than restated here, so the two cannot drift.
  * **not located** - no authorizing passage was found at all.

The last two both resolve to `unresolved`, which drives every Schedule B control to
APPLICABILITY_UNRESOLVED. The alternative - returning an empty list - is the dangerous
outcome: an empty authorized set silently deactivates eleven controls and reads, in every
downstream artifact, exactly like a policy that authorizes nothing improper.

Detection proposes; it never concludes. A term found in an authorizing sentence is a
candidate with a span. Where a model adapter is supplied, each candidate is confirmed
against the passage before it enters the set.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .loader import RegisterSet

LEXICON_FILE = "instrument_lexicon.json"
LIST_CONTROL = "TX-PFIA-2256.005-b-4-A-001"
SECTION_WINDOW = 2600
SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+|\n{2,}")
# An enumerated item: (a), (1), (iv), a., 1., a bullet or a dash at the start of a line.
LIST_ITEM = re.compile(r"^\s*(?:\(\s*[a-zA-Z0-9ivxIVX]{1,4}\s*\)|[a-zA-Z0-9]{1,3}[.)]|[-\u2022\u2013])\s+\S")
# A top-level heading, which ends a list's reach: "(J) Proxy Voting.", "SECTION V.", "V. ".
HEADING = re.compile(
    r"^\s*(?:\([A-Z]\)\s+[A-Z]|SECTION\b|ARTICLE\b|[IVXL]+\.\s+[A-Z]|[A-Z][A-Z ]{8,}$)"
)
STEM_REACH = 14000
# How far past the last enumerated item a list's reach may run before it is treated as
# ended. This, not indentation, is what bounds a list.
ITEM_TAIL = 1800
# A marker anywhere after sentence-ending punctuation, for text whose indented block was
# reflowed into running prose during extraction. Line anchoring alone misses these.
INLINE_MARKER = re.compile(r"(?:(?<=[.;:])|(?<=\n))\s*\(\s*[a-zA-Z0-9ivxIVX]{1,4}\s*\)\s+\S")
MARKER_GAP = 2500


@dataclass
class Mention:
    code: str
    term: str
    start: int
    end: int
    sentence: str
    polarity: str  # authorizing | excluding | restricted | indeterminate
    inherited: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "term": self.term, "start": self.start, "end": self.end,
            "polarity": self.polarity, "inherited": self.inherited,
            "sentence": " ".join(self.sentence.split())[:280],
        }


@dataclass
class Resolution:
    authorized: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    restricted: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    incorporation: dict[str, Any] | None = None
    state: str = "not_located"
    unresolved: bool = True
    reasons: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    sections: list[tuple[int, int]] = field(default_factory=list)
    stems: list[dict[str, Any]] = field(default_factory=list)
    directive_trace: list[str] = field(default_factory=list)
    lexicon_version: str = ""
    package_version: str = ""
    detector: str = "lexicon"

    def to_facts(self) -> dict[str, Any]:
        """The policy fact block the evaluator gates on."""
        facts: dict[str, Any] = {
            "authorized_instruments": sorted(self.authorized),
            "authorization_state": self.state,
            "incorporates_statutory_conditions": bool(
                self.incorporation and self.incorporation.get("applies", True)
            ),
        }
        if self.unresolved:
            facts["authorization_unresolved"] = True
        return facts

    def report(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "unresolved": self.unresolved,
            "detector": self.detector,
            "lexicon_version": self.lexicon_version,
            "package_version": self.package_version,
            "authorized": sorted(self.authorized),
            "excluded": sorted(self.excluded),
            "restricted": sorted(self.restricted),
            "contradictions": sorted(self.contradictions),
            "incorporation": self.incorporation,
            "reasons": list(self.reasons),
            "sections": [{"start": s, "end": e} for s, e in self.sections],
            "stems": list(self.stems),
            "directive_trace": list(self.directive_trace),
            "mentions": [m.as_dict() for m in self.mentions],
        }


def load_lexicon(registers_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(registers_dir) / LEXICON_FILE).read_text(encoding="utf-8"))


def _pattern(phrase: str) -> re.Pattern[str]:
    """Compile a phrase, whitespace-tolerantly. A `*` token allows up to three words.

    Headings interpose the entity's own name more often than not - "Authorized NTTA System
    Investments" - and a literal match on "authorized investments" never sees it.
    """
    parts = []
    for token in phrase.split():
        parts.append(r"(?:\S+\s+){0,3}" if token == "*" else re.escape(token) + r"\s+")
    joined = "".join(parts).rstrip()
    if joined.endswith(r"\s+"):
        joined = joined[: -len(r"\s+")]
    return re.compile(joined.replace(r"\s+", r"\s+"), re.IGNORECASE)


def _find(phrase: str, text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _pattern(phrase).finditer(text)]


def _sentence_at(document: str, offset: int) -> tuple[int, int]:
    start = 0
    for match in SENTENCE_SPLIT.finditer(document, 0, offset):
        start = match.end()
    end = len(document)
    match = SENTENCE_SPLIT.search(document, offset)
    if match:
        end = match.start() + 1
    return start, end


def _mask_exclusions(sentence: str, lexicon: Mapping[str, Any]) -> str:
    lowered = " ".join(sentence.split()).lower()
    for cue in lexicon["exclusion_cues"]:
        lowered = lowered.replace(cue, " ")
    return lowered


def _is_scoped(sentence: str, lexicon: Mapping[str, Any]) -> bool:
    """Whether an exclusion restricts a use rather than forbidding the instrument.

    "Such no-load mutual funds are not authorized for bond proceeds, reserves, and funds
    held for debt service" does not de-authorize mutual funds; it confines them to other
    money. Reading it as a prohibition removes an instrument the policy plainly permits and
    suppresses the control that would have tested its conditions.
    """
    lowered = " ".join(sentence.split()).lower()
    return any(phrase in lowered for phrase in lexicon.get("scope_phrases", []))


def _list_stems(document: str, lexicon: Mapping[str, Any]) -> list[tuple[int, int]]:
    """Spans over which an enumerated list inherits its stem's authorization.

    A stem is a sentence that authorizes and then introduces a list, either by ending in a
    colon or by being followed immediately by an enumerated item. Its reach ends at the
    next top-level heading, the next stem, or a hard character cap.
    """
    # Two kinds of stem. A sentence that authorizes and then introduces a list, and a
    # bare section heading that does the same with no verb at all - "Authorized
    # Investments:" followed straight into (a), (b), (c) is as common in practice as the
    # fully drafted stem, and carries exactly the same meaning.
    cues = list(lexicon.get("list_stem_cues", [])) + list(lexicon["section_directives"])
    positions: list[int] = []
    for cue in cues:
        for start, end in _find(cue, document):
            s_start, s_end = _sentence_at(document, start)
            sentence = document[s_start:s_end]
            if not _mask_exclusions(sentence, lexicon).strip():
                continue
            introduces = False
            lookahead = document[s_end: s_end + 240]
            for line in lookahead.splitlines():
                if not line.strip():
                    continue
                if HEADING.match(line):
                    break
                introduces = bool(LIST_ITEM.match(line))
                break
            if not introduces and sentence.rstrip().endswith(":"):
                # A colon with no enumerated item after it introduces prose, and prose gets
                # no reach; the sentence's own polarity already covers what it names.
                introduces = False
            if introduces:
                positions.append(s_end)
    positions = sorted(set(positions))

    stems: list[tuple[int, int]] = []
    for index, start in enumerate(positions):
        limit = min(len(document), start + STEM_REACH)
        if index + 1 < len(positions):
            limit = min(limit, positions[index + 1])

        # Reach ends where the list ends. A stem introduced by a colon whose following
        # text is a prose sentence rather than an enumerated list has no reach at all -
        # otherwise a single "the following are authorized:" swallows the remainder of the
        # document and every instrument named anywhere in it inherits authorization,
        # including one named only in a settlement or reporting clause.
        end = start
        cursor = start
        seen_item = False
        prose_lines = 0
        last_item_end = start
        for line in document[start:limit].splitlines(keepends=True):
            stripped = line.strip()
            if not stripped:
                cursor += len(line)
                continue
            if HEADING.match(line):
                break
            if LIST_ITEM.match(line):
                seen_item = True
                prose_lines = 0
                cursor += len(line)
                end = cursor
                last_item_end = cursor
                continue
            if not seen_item:
                prose_lines += 1
                if prose_lines >= 2:
                    break
                cursor += len(line)
                continue
            # A continuation of the current item. Indentation cannot be the test: text
            # extracted from a PDF routinely arrives with every line at column zero, and
            # requiring a leading space ends the reach at the first wrapped line - which
            # truncated a real twelve-item list to its first item.
            cursor += len(line)
            end = cursor
            if cursor - last_item_end > ITEM_TAIL:
                # Far enough past the last item that the list has plainly ended.
                end = last_item_end
                break
        if not seen_item:
            # Line anchoring found nothing. Try markers wherever they fall, which is how
            # an indented list arrives when a PDF extractor reflows it into prose.
            cursor = start
            accepted = 0
            for match in INLINE_MARKER.finditer(document, start, limit):
                gap = MARKER_GAP if accepted else 400
                if match.start() - cursor > gap:
                    break
                segment = document[cursor: match.start()]
                if any(HEADING.match(line) for line in segment.splitlines()):
                    break
                # A marker that is itself a top-level heading - "(I) Authorized System
                # Investments." - is the start of a section, not an item in a list.
                line_start = document.rfind("\n", 0, match.start()) + 1
                if HEADING.match(document[line_start: match.end() + 40]):
                    break
                accepted += 1
                cursor = match.end()
                end = match.end()
            # One marker is not a list. Requiring two keeps an unrelated parenthetical
            # from turning any authorizing sentence into a stem.
            seen_item = accepted >= 2
            if seen_item:
                # Extend to the end of the final item's text.
                tail = document.find("\n\n", end)
                end = min(limit, tail if tail != -1 else limit)
        if seen_item and end > start:
            stems.append((start, end))
    return stems


def _polarity(sentence: str, lexicon: Mapping[str, Any]) -> str:
    """Decide whether a sentence authorizes or excludes what it names.

    A sentence carrying both cues is treated as authorizing. That is not a fudge: the
    common construction is "the following are authorized ... and investments not listed
    are not authorized", where the exclusion governs the residual category and the
    enumeration governs the named instruments. Reading such a sentence as an exclusion
    would empty the authorized set of exactly the policies that drafted it most carefully.
    """
    lowered = " ".join(sentence.split()).lower()
    excluding = any(cue in lowered for cue in lexicon["exclusion_cues"])
    # Mask the exclusion cues before looking for authorization cues. Without this the
    # phrase "not authorized" satisfies the "authorized" cue by substring, and a policy
    # that expressly excludes the prohibited mortgage derivatives reads as authorizing
    # them - a CRITICAL false positive on the most consequential control in Schedule B.
    masked = _mask_exclusions(sentence, lexicon)
    authorizing = any(cue in masked for cue in lexicon["authorization_cues"])
    if authorizing:
        return "authorizing"
    if excluding:
        return "restricted" if _is_scoped(sentence, lexicon) else "excluding"
    return "indeterminate"


def _locate_sections(
    document: str, lexicon: Mapping[str, Any]
) -> tuple[list[tuple[int, int]], list[str]]:
    """Locate authorizing sections, and record every directive tried.

    The trace is the diagnostic that matters when a real policy comes back with no section
    located: it tells a reviewer which headings were looked for, so the heading the policy
    actually uses can be added to the lexicon rather than guessed at.
    """
    spans: list[tuple[int, int]] = []
    trace: list[str] = []
    for directive in lexicon["section_directives"]:
        hits = _find(directive, document)
        if hits:
            trace.append(f"{directive!r}: {len(hits)} hit(s) at {[h[0] for h in hits][:5]}")
        for start, _end in hits:
            spans.append((max(0, start - 120), min(len(document), start + SECTION_WINDOW)))
    if not spans:
        trace.append(
            f"none of the {len(lexicon['section_directives'])} section directives matched; "
            "add the heading this policy uses to section_directives in the lexicon"
        )
        return [], trace
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged, trace


def _incorporation(document: str, lexicon: Mapping[str, Any],
                   stems: list[tuple[int, int]],
                   sections: list[tuple[int, int]]) -> dict[str, Any] | None:
    """Locate a clause incorporating the statutory conditions by reference.

    The clause only means what it means where it governs the authorization. "As further
    defined by the PFIA" in a stem or in an authorized-investment section incorporates each
    listed type's statutory conditions; the same words in a recital do not. So the search is
    confined to those spans rather than run over the whole document.
    """
    regions = list(stems) + list(sections)
    if not regions:
        return None
    stem_starts = {start for start, _end in stems}
    candidates: list[dict[str, Any]] = []
    for cue in lexicon.get("incorporation_cues", []):
        for start, end in _find(cue, document):
            in_stem = any(lo <= start < hi for lo, hi in stems)
            if not in_stem and not any(lo <= start < hi for lo, hi in sections):
                continue
            s_start, s_end = _sentence_at(document, start)
            # Scope matters. A cue in the sentence that introduces the list governs every
            # item under it; the same words inside one item govern that item alone. Only
            # the first can stand for the whole schedule, and treating an item-level clause
            # as document-wide would pass conditions for instruments it never mentioned.
            scope = "list" if s_end in stem_starts else "item"
            candidates.append({
                "cue": cue,
                "start": start,
                "end": end,
                "scope": scope,
                "in_stem": in_stem,
                "sentence": " ".join(document[s_start:s_end].split())[:400],
                "effect": (
                    "Each authorized type's statutory conditions are incorporated by "
                    "reference. An officer reading the policy is directed to the chapter, so "
                    "the conditions are in the policy by reference rather than by recitation "
                    "- and they track amendments without a rewrite."
                ),
                "limit": (
                    "Incorporation cannot supply what Sec. 2256.005(b) requires the policy "
                    "itself to decide: the maximum stated maturity, the dollar-weighted "
                    "average maturity for pooled fund groups, the market price monitoring "
                    "method and the fund strategies are entity choices, and no reference to "
                    "the chapter answers them."
                ),
            })
    if not candidates:
        return None
    for candidate in candidates:
        if candidate["scope"] == "list":
            return candidate
    # Only item-level clauses were found. Recorded, but not treated as governing the
    # schedule: mapping a clause to the single instrument it sits with is a separate piece
    # of work, and over-generalising it would pass conditions the policy never addressed.
    first = candidates[0]
    first["effect"] = (
        "An incorporation clause was found inside a single authorized-investment item "
        "rather than in the sentence introducing the list. It is recorded but not applied: "
        "it governs that item only, and the register does not yet map an item-level clause "
        "to its instrument."
    )
    first["applies"] = False
    return first


def _blanket_hits(rs: RegisterSet, document: str) -> list[str]:
    """Blanket-incorporation phrasing, taken from the listing control's own anti-patterns."""
    control = rs.control(LIST_CONTROL)
    if control is None:
        return []
    hits: list[str] = []
    for pattern in control.test.get("anti_patterns", []):
        if _pattern(pattern).search(document):
            hits.append(pattern)
    return hits


def detect(
    rs: RegisterSet,
    document: str,
    registers_dir: str | Path,
    confirm: Any | None = None,
    lexicon: Mapping[str, Any] | None = None,
) -> Resolution:
    """Read the authorized-investment set out of a policy document.

    `confirm` is an optional callable (code, sentence, span) -> bool used to have a model
    confirm each candidate against its passage. Without it the lexicon result stands and
    the resolution records that no confirmation pass ran.
    """
    from . import __version__

    # A caller may supply a merged lexicon (Schedule B v2 adds codes on top of the base
    # lexicon); the base file is never modified, so the 0.18.0 detection is unchanged.
    lexicon = lexicon if lexicon is not None else load_lexicon(registers_dir)
    resolution = Resolution(lexicon_version=lexicon["version"], package_version=__version__)
    sections, trace = _locate_sections(document, lexicon)
    resolution.sections = sections
    resolution.directive_trace = trace

    blanket = _blanket_hits(rs, document)

    scan_regions = sections or [(0, len(document))]
    stems = _list_stems(document, lexicon)
    if stems:
        resolution.directive_trace.append(
            f"{len(stems)} enumerated list stem(s) found; items within them inherit the "
            "stem's authorization"
        )
    else:
        resolution.directive_trace.append(
            "no enumerated list stem was found. If the policy authorizes its instruments "
            "as a list under a single introductory sentence, that list is not being read: "
            "check the `stems` field and the text after each section span."
        )
    # A stem's reach is also a scan region, unconditionally: a list routinely runs past the
    # window opened by the section heading, and the tail of it is where the less common
    # instruments sit.
    scan_regions = list(scan_regions) + list(stems)
    seen: set[tuple[str, int]] = set()
    for code, entry in lexicon["instruments"].items():
        for term in entry["terms"]:
            for start, end in _find(term, document):
                if not any(lo <= start < hi for lo, hi in scan_regions):
                    continue
                if (code, start) in seen:
                    continue
                seen.add((code, start))
                s_start, s_end = _sentence_at(document, start)
                sentence = document[s_start:s_end]
                polarity = _polarity(sentence, lexicon)
                inherited = False
                if polarity == "indeterminate" and any(lo <= start < hi for lo, hi in stems):
                    polarity = "authorizing"
                    inherited = True
                resolution.mentions.append(
                    Mention(code, term, start, end, sentence, polarity, inherited=inherited)
                )

    # Record what each stem actually reached, which is the diagnostic that matters when a
    # real policy comes back short: a stem with zero items means the reach ended before
    # the list, and the preview shows what the extractor produced there.
    for start, end in stems:
        inherited = [m for m in resolution.mentions if m.inherited and start <= m.start < end]
        markers = len(INLINE_MARKER.findall(document, start, end))
        resolution.stems.append({
            "start": start, "end": end, "chars": end - start,
            "enumerated_markers": markers,
            "instruments_inherited": sorted({m.code for m in inherited}),
            "preview": " ".join(document[start: start + 220].split()),
        })

    resolution.incorporation = _incorporation(document, lexicon, stems, sections)
    if resolution.incorporation and resolution.incorporation.get("applies", True):
        resolution.reasons.append(
            "the authorizing clause incorporates each type's statutory conditions by "
            f"reference ({resolution.incorporation['cue']!r}); the conditions are in the "
            "policy by reference rather than by recitation, and they track amendments to "
            "the chapter without a rewrite"
        )
    elif resolution.incorporation:
        resolution.reasons.append(
            "an incorporation clause was found inside a single authorized-investment item "
            f"({resolution.incorporation['cue']!r}); it is recorded but not applied, since "
            "it governs that item alone"
        )

    authorizing = {m.code for m in resolution.mentions if m.polarity == "authorizing"}
    excluding = {m.code for m in resolution.mentions if m.polarity == "excluding"}
    restricted = {m.code for m in resolution.mentions if m.polarity == "restricted"}

    if confirm is not None:
        resolution.detector = "lexicon+model"
        confirmed: set[str] = set()
        for code in sorted(authorizing):
            mention = next(m for m in resolution.mentions
                           if m.code == code and m.polarity == "authorizing")
            if confirm(code, mention.sentence, (mention.start, mention.end)):
                confirmed.add(code)
            else:
                resolution.reasons.append(
                    f"{code}: lexicon candidate rejected on confirmation against the passage"
                )
        authorizing = confirmed

    # An affirmative authorization anywhere settles the question. An instrument named only
    # in an exclusion is not authorized, which is what the prohibition control depends on:
    # a policy that expressly excludes the Sec. 2256.009(b) derivatives must not be read as
    # authorizing them. Where a policy does both, the instrument stays authorized and the
    # conflict is recorded, because the conditions control should still run.
    resolution.authorized = sorted(authorizing)
    resolution.excluded = sorted(excluding - authorizing)
    resolution.restricted = sorted(restricted & authorizing)
    resolution.contradictions = sorted(authorizing & excluding)
    if resolution.contradictions:
        resolution.reasons.append(
            "authorized and excluded in different passages: "
            + ", ".join(resolution.contradictions)
            + "; treated as authorized so the conditions control still runs"
        )
    if resolution.restricted:
        resolution.reasons.append(
            "authorized but restricted as to which funds may hold them: "
            + ", ".join(resolution.restricted)
        )

    if not sections and resolution.authorized:
        # Types were named in authorizing language, but outside any recognisable
        # authorized-investment section. What was found is authorized; whether the list is
        # complete cannot be answered, so the set is a lower bound.
        resolution.state = "authorized_without_section"
        resolution.unresolved = True
        resolution.reasons.append(
            "no authorized-investment section heading was recognised, but "
            f"{len(resolution.authorized)} type(s) appear in authorizing language; the set "
            "is a lower bound, not a list"
        )
    elif not sections:
        resolution.state = "section_not_located"
        resolution.unresolved = True
        resolution.reasons.append(
            "no authorized-investment section could be located in the document; see "
            "directive_trace for the headings that were tried"
        )
    elif blanket:
        # Naming some types alongside a blanket incorporation does not close the set. What
        # was detected is authorized; whether anything else is cannot be answered from the
        # document, so the set is a lower bound rather than a list.
        resolution.state = "blanket_incorporation"
        resolution.unresolved = True
        resolution.reasons.append(
            "the policy incorporates the chapter by reference rather than enumerating a "
            "closed list: " + "; ".join(repr(b) for b in blanket)
        )
        if resolution.authorized:
            resolution.reasons.append(
                f"{len(resolution.authorized)} type(s) were named explicitly and are treated "
                "as authorized; the set is a lower bound, not a list"
            )
    elif not resolution.authorized:
        resolution.state = "no_instruments_recognized"
        resolution.unresolved = True
        resolution.reasons.append(
            "an authorized-investment section was located but no instrument type in the "
            "lexicon was recognized in an authorizing passage; treat as a lexicon gap, not "
            "as a policy that authorizes nothing"
        )
    else:
        resolution.state = "enumerated"
        resolution.unresolved = False
        if blanket:
            resolution.reasons.append(
                "types were enumerated, but blanket-incorporation language is also present: "
                + "; ".join(repr(b) for b in blanket)
            )
    return resolution
