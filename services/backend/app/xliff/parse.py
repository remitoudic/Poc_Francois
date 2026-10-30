"""Parse XLIFF 1.2 and 2.0 into units with plain text, inline markup and inline-tag signatures."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from pydantic import BaseModel

from app.integrations.errors import BusinessError

# Inline elements: XLIFF 1.2 (g, x, bx, ex, ph, bpt, ept, it, mrk) and 2.0 (pc, sc, ec, ph, mrk, sm, em, cp).
INLINE_TAGS = {"g", "x", "bx", "ex", "ph", "bpt", "ept", "it", "mrk", "pc", "sc", "ec", "sm", "em", "cp"}
_WORD = re.compile(r"\b\w+\b")


class XliffError(BusinessError):
    """The file is not well-formed XML or not an XLIFF document."""


class XliffUnit(BaseModel):
    unit_id: str
    resname: str | None = None
    source: str  # plain text, whitespace preserved
    target: str | None  # None when the unit has no <target>
    source_markup: str  # inner XML without namespace prefixes
    target_markup: str | None
    source_tags: list[str]  # inline tags as "name#id", in document order
    target_tags: list[str]
    maxwidth: int | None = None
    size_unit: str | None = None

    @property
    def words(self) -> int:
        return len(_WORD.findall(self.source))


class XliffDocument(BaseModel):
    version: str
    source_lang: str | None
    target_lang: str | None
    original: str | None
    units: list[XliffUnit]

    @property
    def words(self) -> int:
        return sum(u.words for u in self.units)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _strip_ns(el: ET.Element) -> ET.Element:
    copy = ET.Element(_local(el.tag), {_local(k): v for k, v in el.attrib.items()})
    copy.text, copy.tail = el.text, el.tail
    copy.extend(_strip_ns(child) for child in el)
    return copy


def _inner_markup(el: ET.Element) -> str:
    clean = _strip_ns(el)
    return (clean.text or "") + "".join(ET.tostring(c, encoding="unicode") for c in clean)


def _tags(el: ET.Element) -> list[str]:
    return [
        f"{_local(e.tag)}#{e.get('id', '')}"
        for e in el.iter()
        if e is not el and _local(e.tag) in INLINE_TAGS
    ]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _local(c.tag) == name), None)


def _unit(unit_id: str, resname: str | None, attrs: dict[str, str], src: ET.Element, tgt: ET.Element | None) -> XliffUnit:
    maxwidth = attrs.get("maxwidth")
    return XliffUnit(
        unit_id=unit_id,
        resname=resname or None,
        source="".join(src.itertext()),
        target="".join(tgt.itertext()) if tgt is not None else None,
        source_markup=_inner_markup(src),
        target_markup=_inner_markup(tgt) if tgt is not None else None,
        source_tags=_tags(src),
        target_tags=_tags(tgt) if tgt is not None else [],
        maxwidth=int(maxwidth) if maxwidth and maxwidth.isdigit() else None,
        size_unit=attrs.get("size-unit"),
    )


def parse(xml: str | bytes) -> XliffDocument:
    """Parse an XLIFF 1.2 or 2.0 document. Raises XliffError if it is malformed."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise XliffError(f"Not well-formed XML: {exc}") from exc
    if _local(root.tag) != "xliff":
        raise XliffError(f"Root element is <{_local(root.tag)}>, expected <xliff>")

    version = root.get("version", "1.2")
    units: list[XliffUnit] = []
    source_lang = root.get("srcLang")  # 2.0 keeps languages on the root
    target_lang = root.get("trgLang")
    original = None

    for file_el in (e for e in root.iter() if _local(e.tag) == "file"):
        source_lang = file_el.get("source-language", source_lang)
        target_lang = file_el.get("target-language", target_lang)
        original = original or file_el.get("original")
        for el in file_el.iter():
            name = _local(el.tag)
            if name == "trans-unit":  # 1.2
                src = _child(el, "source")
                if src is None:
                    raise XliffError(f"trans-unit {el.get('id')} has no <source>")
                units.append(_unit(el.get("id", str(len(units) + 1)), el.get("resname"), el.attrib, src, _child(el, "target")))
            elif name == "unit":  # 2.0: one entry per <segment>
                segments = [s for s in el if _local(s.tag) == "segment"]
                for i, seg in enumerate(segments, start=1):
                    src = _child(seg, "source")
                    if src is None:
                        continue
                    seg_id = seg.get("id") or (str(i) if len(segments) > 1 else None)
                    unit_id = f"{el.get('id')}/{seg_id}" if seg_id else el.get("id", str(len(units) + 1))
                    units.append(_unit(unit_id, el.get("name"), el.attrib, src, _child(seg, "target")))

    return XliffDocument(
        version=version, source_lang=source_lang, target_lang=target_lang, original=original, units=units
    )
