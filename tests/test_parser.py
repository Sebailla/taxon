from io import StringIO

import pytest

from taxon.parser import parse_taxa


def source_id(number: int) -> str:
    return f"urn:lsid:marinespecies.org:taxname:{number}"


def test_parser_extracts_markers_and_preserves_display_name() -> None:
    source = StringIO(
        "Biota [superdomain] {ID=" + source_id(1) + "}\n"
        "  †Animalia [kingdom] {ID=" + source_id(2) + "}\n"
        "    =Metazoa [subkingdom] {ID=" + source_id(3) + "}\n"
        "    ?Mystery taxon [phylum] {ID=" + source_id(4) + "}\n"
        "    [unassigned] Incertae sedis [phylum] {ID=" + source_id(5) + "}\n"
    )

    parsed = list(parse_taxa(source))

    assert [parent for parent, _ in parsed] == [None, source_id(1), source_id(2), source_id(2), source_id(2)]
    assert parsed[1][1]["name"] == "Animalia"
    assert parsed[1][1]["display_name"] == "†Animalia [kingdom]"
    assert parsed[1][1]["is_extinct"] is True
    assert parsed[2][1]["is_synonym"] is True
    assert parsed[3][1]["is_uncertain"] is True
    assert parsed[4][1]["is_unassigned"] is True


def test_parser_handles_candidatus_and_deep_irregular_nesting() -> None:
    source = StringIO(
        "Biota [superdomain] {ID=" + source_id(10) + "}\n"
        "  Bacteria [kingdom] {ID=" + source_id(11) + "}\n"
        "      \"Candidatus Pelagibacter ubique\" [species] {ID=" + source_id(12) + "}\n"
        "    Proteobacteria [phylum] {ID=" + source_id(13) + "}\n"
    )

    parsed = list(parse_taxa(source))

    assert parsed[2][0] == source_id(11)
    assert parsed[2][1]["name"] == '"Candidatus Pelagibacter ubique"'
    assert parsed[2][1]["rank"] == "species"
    assert parsed[3][0] == source_id(11)


def test_parser_rejects_odd_indentation() -> None:
    source = StringIO(" Bad [species] {ID=" + source_id(20) + "}\n")

    with pytest.raises(ValueError, match="multiple of two"):
        list(parse_taxa(source))
