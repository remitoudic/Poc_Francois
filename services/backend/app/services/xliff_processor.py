import re
from typing import Any
from xml.etree import ElementTree as ET


class XLIFFProcessor:
    """Service to parse, validate, calculate metrics, and transform XLIFF files."""

    @staticmethod
    def _strip_ns(tag: str) -> str:
        """Remove XML namespace prefix from tag."""
        return tag.split("}")[-1] if "}" in tag else tag

    @classmethod
    def parse_xliff(cls, xml_content: str) -> dict[str, Any]:
        """
        Parse XLIFF 1.2 or 2.0 XML content.
        Returns parsed metadata and list of translation units.
        """
        if isinstance(xml_content, bytes):
            xml_content = xml_content.decode("utf-8")

        root = ET.fromstring(xml_content.encode("utf-8"))
        root_tag = cls._strip_ns(root.tag).lower()

        if root_tag != "xliff":
            raise ValueError(f"Root tag is <{root.tag}>, expected <xliff>")

        version = root.attrib.get("version", "1.2")
        source_lang = "en"
        target_lang = "fr"
        original_file = "unknown"
        segments: list[dict[str, Any]] = []

        # Find file nodes
        for elem in root.iter():
            tag = cls._strip_ns(elem.tag).lower()

            if tag == "file":
                source_lang = elem.attrib.get("source-language", source_lang)
                target_lang = elem.attrib.get("target-language", target_lang)
                original_file = elem.attrib.get("original", original_file)

            elif tag in ("trans-unit", "unit"):
                unit_id = elem.attrib.get("id", str(len(segments) + 1))
                resname = elem.attrib.get("resname", "")

                source_text = ""
                target_text = ""
                notes = ""

                for child in elem:
                    child_tag = cls._strip_ns(child.tag).lower()
                    if child_tag in ("source", "segment"):
                        source_text = "".join(child.itertext()).strip()
                    elif child_tag == "target":
                        target_text = "".join(child.itertext()).strip()
                    elif child_tag in ("note", "notes"):
                        notes = "".join(child.itertext()).strip()

                segments.append(
                    {
                        "unit_id": unit_id,
                        "resname": resname,
                        "source_text": source_text,
                        "target_text": target_text,
                        "notes": notes,
                        "status": "translated" if target_text else "needs-translation",
                    }
                )

        total_words = sum(len(re.findall(r"\b\w+\b", s["source_text"])) for s in segments)

        return {
            "version": version,
            "source_language": source_lang,
            "target_language": target_lang,
            "original_file": original_file,
            "segment_count": len(segments),
            "word_count": total_words,
            "segments": segments,
        }

    @classmethod
    def transform_xliff(
        cls, xml_content: str, target_lang: str = None
    ) -> tuple[str, dict[str, Any]]:
        """
        Transform XLIFF:
        - Ensures all segments have valid target elements.
        - Validates placeholders and tags.
        - Updates target-language attribute if specified.
        Returns the updated XML string and transformation summary.
        """
        if isinstance(xml_content, bytes):
            xml_content = xml_content.decode("utf-8")

        parsed = cls.parse_xliff(xml_content)
        root = ET.fromstring(xml_content.encode("utf-8"))

        warnings = []
        enriched_count = 0

        # Register default namespace if needed to avoid ns0 prefixes
        for elem in root.iter():
            tag = cls._strip_ns(elem.tag).lower()

            if tag == "file" and target_lang:
                elem.attrib["target-language"] = target_lang

            elif tag in ("trans-unit", "unit"):
                source_elem = None
                target_elem = None

                for child in elem:
                    child_tag = cls._strip_ns(child.tag).lower()
                    if child_tag == "source":
                        source_elem = child
                    elif child_tag == "target":
                        target_elem = child

                if source_elem is not None:
                    src_text = "".join(source_elem.itertext()).strip()

                    # Check placeholders (e.g. {0}, %s, etc.)
                    placeholders = re.findall(r"\{[0-9]+\}|%[sd]|<ph[^>]*>", src_text)

                    if target_elem is None or not (target_elem.text and target_elem.text.strip()):
                        # Enrich missing target
                        if target_elem is None:
                            # Create target element matching source namespace
                            ns = (
                                source_elem.tag.split("}")[0] + "}"
                                if "}" in source_elem.tag
                                else ""
                            )
                            target_elem = ET.SubElement(elem, f"{ns}target")
                        target_elem.text = f"[FOX_MLO_PROCESSED] {src_text}"
                        enriched_count += 1

                    # Verify placeholder retention
                    tgt_text = "".join(target_elem.itertext()).strip()
                    for ph in placeholders:
                        if ph not in tgt_text:
                            warnings.append(
                                f"Unit {elem.attrib.get('id')}: Placeholder '{ph}' missing in target."
                            )

        transformed_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

        summary = {
            "enriched_segments": enriched_count,
            "total_segments": parsed["segment_count"],
            "total_words": parsed["word_count"],
            "warnings": warnings,
            "source_language": parsed["source_language"],
            "target_language": target_lang or parsed["target_language"],
        }

        return transformed_xml, summary
