"""SelectolaxParser — parses Bulbapedia HTML into PokemonData.

Selectors target the Bulbapedia MediaWiki layout. The parse() method returns
None for any page that does not look like a Pokémon species article so workers
can silently skip non-target pages.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser

from domain.models import PokemonData
from domain.ports import Parser

# Bulbapedia renders the Pokémon infobox with this class.
_INFOBOX_SELECTOR = "table.roundy"
# The page title h1 contains the Pokémon name.
_TITLE_SELECTOR = "h1#firstHeading"
# Type cells sit inside the infobox and link to type articles.
_TYPE_SELECTOR = "a[href*='_(type)'] span"
# Base-stats table rows: each <tr> has a <th> label and the first <td> value.
_STAT_ROW_SELECTOR = "table.roundy tr"

_STAT_LABELS: dict[str, str] = {
    "HP": "hp",
    "Attack": "attack",
    "Defense": "defense",
    "Sp. Atk": "sp_atk",
    "Sp. Def": "sp_def",
    "Speed": "speed",
}


class SelectolaxParser(Parser):
    """Implements Parser for Bulbapedia Pokémon pages using selectolax."""

    def parse(self, html: str) -> PokemonData | None:
        tree = HTMLParser(html)

        name = self._extract_name(tree)
        if name is None:
            return None

        types = self._extract_types(tree)
        if not types:
            return None

        stats = self._extract_stats(tree)

        return PokemonData(name=name, types=types, stats=stats)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_name(self, tree: HTMLParser) -> str | None:
        node = tree.css_first(_TITLE_SELECTOR)
        if node is None:
            return None
        # Strip the "(Pokémon)" suffix that Bulbapedia appends.
        raw = node.text(strip=True)
        return raw.replace("(Pokémon)", "").strip() or None

    def _extract_types(self, tree: HTMLParser) -> list[str]:
        seen: list[str] = []
        for node in tree.css(_TYPE_SELECTOR):
            label = node.text(strip=True)
            if label and label not in seen:
                seen.append(label)
        return seen

    def _extract_stats(self, tree: HTMLParser) -> dict[str, int]:
        stats: dict[str, int] = {}
        for row in tree.css(_STAT_ROW_SELECTOR):
            cells = row.css("th, td")
            if len(cells) < 2:
                continue
            label = cells[0].text(strip=True)
            key = _STAT_LABELS.get(label)
            if key is None:
                continue
            raw_value = cells[1].text(strip=True)
            if raw_value.isdigit():
                stats[key] = int(raw_value)
        return stats
