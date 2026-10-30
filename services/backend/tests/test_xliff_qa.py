import pytest

from app.xliff import FindingLevel, check_xml, parse
from app.xliff.parse import XliffError


def x12(*units: str, extra: str = "") -> str:
    return (
        '<?xml version="1.0"?><xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        f'<file original="post-433" source-language="en" target-language="fr" datatype="html"{extra}><body>'
        + "".join(units)
        + "</body></file></xliff>"
    )


def tu(source: str, target: str | None, uid: str = "u-001", attrs: str = "") -> str:
    tgt = f"<target>{target}</target>" if target is not None else ""
    return f'<trans-unit id="{uid}"{attrs}><source>{source}</source>{tgt}</trans-unit>'


def codes(source: str, target: str | None, attrs: str = "") -> dict[str, FindingLevel]:
    _, findings = check_xml(x12(tu(source, target, attrs=attrs)))
    return {f.code: f.level for f in findings}


def test_parse_xliff_12():
    doc = parse(x12(tu('Hello <g id="1">world</g>', "Bonjour <g id=\"1\">monde</g>"), tu("Two", None, "u-002")))
    assert (doc.version, doc.source_lang, doc.target_lang, doc.original) == ("1.2", "en", "fr", "post-433")
    first, second = doc.units
    assert first.source == "Hello world" and first.source_tags == ["g#1"]
    assert first.source_markup == 'Hello <g id="1">world</g>'
    assert second.target is None and doc.words == 3


def test_parse_xliff_20_segments():
    doc = parse(
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0" srcLang="en" trgLang="de">'
        '<file id="f1"><unit id="1"><segment id="a"><source>One <ph id="p1"/></source><target>Eins <ph id="p1"/></target></segment>'
        '<segment id="b"><source>Two</source></segment></unit></file></xliff>'
    )
    assert [u.unit_id for u in doc.units] == ["1/a", "1/b"]
    assert doc.units[0].target_tags == ["ph#p1"] and (doc.source_lang, doc.target_lang) == ("en", "de")


@pytest.mark.parametrize("xml", ["<xliff><file>", "<html/>"])
def test_malformed_or_not_xliff(xml):
    with pytest.raises(XliffError):
        parse(xml)
    doc, findings = check_xml(xml)
    assert doc is None and [(f.code, f.level) for f in findings] == [("MALFORMED_XML", FindingLevel.BLOCKING)]


def test_clean_segment_has_no_findings():
    assert codes("Spring collection: 12 new pieces", "Collection printemps : 12 nouvelles pièces") == {}


@pytest.mark.parametrize(
    ("source", "target", "code", "level"),
    [
        ("Hello", None, "EMPTY_TARGET", "BLOCKING"),
        ("Hello", "   ", "EMPTY_TARGET", "BLOCKING"),
        ("Hi {name}", "Salut", "PLACEHOLDER_MISMATCH", "BLOCKING"),
        ("Page {0} of %d", "Page %d", "PLACEHOLDER_MISMATCH", "BLOCKING"),
        ("%1$s items", "%s articles", "PLACEHOLDER_MISMATCH", "BLOCKING"),
        ('Read <g id="1">more</g>', "Lire la suite", "TAG_MISMATCH", "BLOCKING"),
        ('Line<x id="2"/>break', '<x id="3"/>Ligne', "TAG_MISMATCH", "BLOCKING"),
        ("Free shipping on every order", "Free shipping on every order", "SAME_AS_SOURCE", "WARNING"),
        ("Only 3 left in stock", "Plus que 4 en stock", "NUMBER_MISMATCH", "WARNING"),
        ("Short label text", "Un libellé beaucoup trop long pour cet endroit", "LENGTH", "WARNING"),
        ("Hello world", " Bonjour le monde", "WHITESPACE", "WARNING"),
        ("Hello world", "Bonjour  le monde", "WHITESPACE", "WARNING"),
    ],
)
def test_rules(source, target, code, level):
    assert codes(source, target).get(code) == level


def test_number_formats_are_normalised():
    assert "NUMBER_MISMATCH" not in codes("1,240 words, 3.5 hours", "1 240 mots, 3,5 heures")


def test_same_as_source_ignores_short_segments():
    assert "SAME_AS_SOURCE" not in codes("Linen shirt", "Linen shirt")


def test_maxwidth_overrides_ratio():
    assert codes("OK", "D'accord", attrs=' maxwidth="5" size-unit="char"').get("LENGTH") == "WARNING"
    assert "LENGTH" not in codes("Save changes now", "Enregistrer les modifications", attrs=' maxwidth="40"')


def test_empty_target_skips_other_checks():
    assert codes("Hi {name}", "") == {"EMPTY_TARGET": "BLOCKING"}


def test_findings_carry_unit_ids():
    _, findings = check_xml(x12(tu("A b c d", "A b c d", "u-007"), tu("Ok", "Ok", "u-008")))
    assert [(f.unit_id, f.code) for f in findings] == [("u-007", "SAME_AS_SOURCE")]
