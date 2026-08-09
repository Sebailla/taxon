from pathlib import Path
from urllib.parse import quote_plus

from taxon.search_links import build_search_links, load_templates

TEMPLATES = Path(__file__).parents[2] / "docs" / "sources" / "templates.md"


def test_load_templates_preserves_exact_order_and_verbatim_urls() -> None:
    templates = load_templates(TEMPLATES)

    assert tuple(template.source for template in templates) == (
        "Wikipedia",
        "Google",
        "BHL",
        "ResearchGate",
        "Plos",
        "Academia",
        "Scielo",
        "Scholar",
        "Youtube",
        "Zootaxa",
        "Photos",
        "Sci-hub",
    )
    assert len(templates) == 12
    assert templates[-1].url_template == "https://sci-hub.ru/match/{q}"
    assert "&newwindow=1&sca_esv=" in templates[-2].url_template
    assert "Q:1786299735760&source=lnt" in templates[-2].url_template


def test_build_search_links_uses_quote_plus_for_every_template() -> None:
    species = "Acanthogyrus (Acanthosentis) & test"
    encoded = quote_plus(species, safe="")

    links = build_search_links(species, load_templates(TEMPLATES))

    assert len(links) == 12
    assert all(link.url.count(encoded) == 1 for link in links)
    assert all("{q}" not in link.url for link in links)
    assert links[0].url == f"http://es.Wikipedia.org/wiki/Special:Search?search={encoded}"
    assert links[-1].url == f"https://sci-hub.ru/match/{encoded}"
    assert links[0].source == "Wikipedia"
    assert links[0].label == "Wikipedia"
