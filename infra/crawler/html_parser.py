"""SelectolaxParser — parses Bulbapedia HTML into PokemonData.

Selectors target the Bulbapedia MediaWiki layout. The parse() method returns
None for any page that does not look like a Pokémon species article so workers
can silently skip non-target pages.

Layout notes (verified against live pages):
- The infobox is `table.roundy.infobox`.
- Types live inside the first <td> (no display:none) that contains
  `a[href*="_(type)"]` links. The Unknown type href is skipped — it is a
  catch-all redirect used for alternate forms, not a real type.
- Base stats are in the table that immediately follows the `<h4>` whose
  inner `<span>` has id="Base_stats". Each stat row has a single `<th>`
  whose text is "StatName: VALUE" (label and number in the same cell,
  separated by a colon).
"""

from __future__ import annotations

from selectolax.parser import HTMLParser, Node

from domain.models import PokemonData
from domain.ports import Parser

_TITLE_SELECTOR = "h1#firstHeading"
_INFOBOX_SELECTOR = "table.roundy.infobox"
_BASE_STATS_ANCHOR = "span#Base_stats"

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
        raw = node.text(strip=True)
        # Bulbapedia appends "(Pokémon)" to species page titles.
        return raw.replace("(Pokémon)", "").strip() or None

    def _extract_types(self, tree: HTMLParser) -> list[str]:
        infobox = tree.css_first(_INFOBOX_SELECTOR)
        if infobox is None:
            return []

        # Walk every <td> in the infobox and take the first one that:
        #   1. is not hidden (no "display:none" in its inline style), and
        #   2. contains at least one type link that is not Unknown.
        for td in infobox.css("td"):
            style = td.attributes.get("style") or ""
            if "display:none" in style.replace(" ", ""):
                continue

            types: list[str] = []
            for a in td.css("a[href*='_(type)']"):
                href = a.attributes.get("href") or ""
                # Unknown_(type) is a redirect used for hidden/alternate forms.
                if "Unknown" in href:
                    continue
                label = a.text(strip=True)
                if label and label not in types:
                    types.append(label)

            if types:
                return types

        return []

    def _extract_stats(self, tree: HTMLParser) -> dict[str, int]:
        anchor = tree.css_first(_BASE_STATS_ANCHOR)
        if anchor is None:
            return {}

        # The anchor is a <span> inside an <h4>. Walk forward from the <h4>
        # to find the immediately following <table>.
        stats_table = self._next_sibling_table(anchor.parent)
        if stats_table is None:
            return {}

        stats: dict[str, int] = {}
        for th in stats_table.css("th"):
            text = th.text(strip=True)
            if ":" not in text:
                continue
            # Format is "StatName: VALUE" — both in the same <th>.
            label, _, raw_value = text.partition(":")
            key = _STAT_LABELS.get(label.strip())
            if key is None:
                continue
            value = raw_value.strip()
            if value.isdigit():
                stats[key] = int(value)

        return stats

    def _next_sibling_table(self, node: Node | None) -> Node | None:
        """Return the first <table> sibling after *node*."""
        if node is None:
            return None
        current = node.next
        while current is not None:
            if current.tag == "table":
                return current
            current = current.next
        return None
