"""QA rules (architecture §5.3). A BLOCKING finding fails the QA task; warnings are only shown."""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel

from app.xliff.parse import XliffDocument, XliffError, XliffUnit, parse

# {0}, {name}, %s, %d, %1$s, %i, %f
_PLACEHOLDER = re.compile(r"\{\d+\}|\{[A-Za-z_][\w.]*\}|%(?:\d+\$)?[sdif]")
# Digit groups with thousand/decimal separators: 1,240 · 1.240 · 1 240 (nbsp) · 3,5
_NUMBER = re.compile(r"\d+(?:[.,'  ]\d+)*")
_WORD = re.compile(r"\b\w+\b")

SAME_AS_SOURCE_MIN_WORDS = 4  # "longer than 3 words"
LENGTH_RATIO = 1.5
LENGTH_MIN_SOURCE_CHARS = 10  # very short strings (buttons, labels) vary too much to compare


class FindingLevel(StrEnum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


class QaFinding(BaseModel):
    code: str
    level: FindingLevel
    unit_id: str
    message: str


def _finding(code: str, level: FindingLevel, unit: XliffUnit | str, message: str) -> QaFinding:
    unit_id = unit if isinstance(unit, str) else unit.unit_id
    return QaFinding(code=code, level=level, unit_id=unit_id, message=message)


def _diff(source: Counter[str], target: Counter[str]) -> str:
    missing = sorted((source - target).elements())
    extra = sorted((target - source).elements())
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("unexpected " + ", ".join(extra))
    return "; ".join(parts)


def _numbers(text: str) -> Counter[str]:
    text = _PLACEHOLDER.sub(" ", text)
    return Counter(re.sub(r"\D", "", n) for n in _NUMBER.findall(text))


def check_unit(unit: XliffUnit) -> list[QaFinding]:
    B, W = FindingLevel.BLOCKING, FindingLevel.WARNING
    source, target = unit.source, unit.target

    if target is None or (not target.strip() and not unit.target_tags):
        return [_finding("EMPTY_TARGET", B, unit, "Target is empty")]

    findings: list[QaFinding] = []

    placeholders = _diff(Counter(_PLACEHOLDER.findall(source)), Counter(_PLACEHOLDER.findall(target)))
    if placeholders:
        findings.append(_finding("PLACEHOLDER_MISMATCH", B, unit, f"Placeholders differ: {placeholders}"))

    tags = _diff(Counter(unit.source_tags), Counter(unit.target_tags))
    if tags:
        findings.append(_finding("TAG_MISMATCH", B, unit, f"Inline tags differ: {tags}"))

    if len(_WORD.findall(source)) >= SAME_AS_SOURCE_MIN_WORDS and target.strip() == source.strip():
        findings.append(_finding("SAME_AS_SOURCE", W, unit, "Target is identical to the source"))

    numbers = _diff(_numbers(source), _numbers(target))
    if numbers:
        findings.append(_finding("NUMBER_MISMATCH", W, unit, f"Numbers differ: {numbers}"))

    if unit.maxwidth and unit.size_unit in (None, "char"):
        if len(target) > unit.maxwidth:
            findings.append(_finding("LENGTH", W, unit, f"Target is {len(target)} characters, max {unit.maxwidth}"))
    elif len(source.strip()) >= LENGTH_MIN_SOURCE_CHARS and len(target.strip()) > LENGTH_RATIO * len(source.strip()):
        pct = round(100 * len(target.strip()) / len(source.strip()))
        findings.append(_finding("LENGTH", W, unit, f"Target is {pct}% of the source length"))

    whitespace = []
    if source[:1].isspace() != target[:1].isspace():
        whitespace.append("leading whitespace differs")
    if source[-1:].isspace() != target[-1:].isspace():
        whitespace.append("trailing whitespace differs")
    if "  " in target and "  " not in source:
        whitespace.append("double space in target")
    if whitespace:
        findings.append(_finding("WHITESPACE", W, unit, "; ".join(whitespace).capitalize()))

    return findings


def check_document(doc: XliffDocument) -> list[QaFinding]:
    return [f for unit in doc.units for f in check_unit(unit)]


def check_xml(xml: str | bytes) -> tuple[XliffDocument | None, list[QaFinding]]:
    """Parse then check. A malformed file gives one BLOCKING finding instead of an exception."""
    try:
        doc = parse(xml)
    except XliffError as exc:
        return None, [_finding("MALFORMED_XML", FindingLevel.BLOCKING, "file", str(exc))]
    return doc, check_document(doc)
