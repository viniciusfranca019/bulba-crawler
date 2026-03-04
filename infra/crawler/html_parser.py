"""SelectolaxParser — parses Bulbapedia HTML into PokemonData.

Selectors target the Bulbapedia MediaWiki layout. The parse() method returns
None for any page that does not look like a Pokémon species article so workers
can silently skip non-target pages.

Layout notes (verified against live pages):
- The infobox is `table.roundy.infobox`.
- Pokédex number: first <a href*="National_Pok"> whose text matches #NNNN.
- Category: first <a href*="Pokémon_category"> in the infobox.
- Types live inside the first <td> (no display:none) that contains
  `a[href*="_(type)"]` links. The Unknown type href is skipped — it is a
  catch-all redirect used for alternate forms, not a real type.
- Base stats are in the table that immediately follows the `<h4>` whose
  inner `<span>` has id="Base_stats". Each stat row has a single `<th>`
  whose text is "StatName: VALUE" (label and number in the same cell,
  separated by a colon).
- Abilities: the infobox <td> that contains an <a href="/wiki/Ability">.
  Visible <td> cells inside it carry one ability link each. A <small> sibling
  containing "Hidden Ability" marks that ability as hidden. Cells with
  display:none are alternate-form abilities and are skipped.
- Evolution: the <div> that immediately follows <span#Evolution>'s parent
  <h3>. Each stage is a nested <table> labelled by a <small> element
  ("Unevolved", "First Evolution", …). The current Pokémon's stage is
  identified by an <a class="mw-selflink"> link; antecessor and successor
  are the adjacent stages.
- Image URL: extracted from the first `<meta property="og:image">` tag in
  the document head. Bulbapedia sets this to the full-resolution PNG of the
  Pokémon's official artwork.
"""

from __future__ import annotations

import re
from typing import Any, Callable, TypeVar

import structlog
from selectolax.parser import HTMLParser, Node

from domain.models import Ability, Evolution, PokemonData
from domain.ports import Parser

log = structlog.get_logger(__name__)

_TITLE_SELECTOR = "h1#firstHeading"
_INFOBOX_SELECTOR = "table.roundy.infobox"
_BASE_STATS_ANCHOR = "span#Base_stats"
_EVOLUTION_ANCHOR = "span#Evolution"
_NATIONAL_DEX_HREF = "National_Pok"
_CATEGORY_HREF = "Pok%C3%A9mon_category"
_ABILITY_HUB_HREF = "/wiki/Ability"
_OG_IMAGE_SELECTOR = "meta[property='og:image']"

_EVOLUTION_STAGES = (
    "Unevolved",
    "First Evolution",
    "Second Evolution",
    "Third Evolution",
)

_STAT_LABELS: dict[str, str] = {
    "HP": "hp",
    "Attack": "attack",
    "Defense": "defense",
    "Sp. Atk": "sp_atk",
    "Sp. Def": "sp_def",
    "Speed": "speed",
}

T = TypeVar("T")


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

        stats = self._safe_extract("stats", self._extract_stats, tree, default={})
        pokedex_number = self._safe_extract(
            "pokedex_number", self._extract_pokedex_number, tree, default=None
        )
        category = self._safe_extract(
            "category", self._extract_category, tree, default=None
        )
        abilities = self._safe_extract(
            "abilities", self._extract_abilities, tree, default=[]
        )
        evolution = self._safe_extract(
            "evolution", self._extract_evolution, tree, name, default=Evolution()
        )
        image_url = self._safe_extract(
            "image_url", self._extract_image_url, tree, default=None
        )

        return PokemonData(
            name=name,
            pokedex_number=pokedex_number,
            category=category,
            types=types,
            stats=stats,
            evolution=evolution,
            abilities=abilities,
            image_path=image_url,
        )

    # ------------------------------------------------------------------
    # Safe extraction wrapper
    # ------------------------------------------------------------------

    def _safe_extract(
        self,
        field: str,
        extractor: Callable[..., T],
        *args: Any,
        default: T,
    ) -> T:
        """Call *extractor* with *args* and return its result.

        If the extractor raises any exception, log a warning with the field
        name and exception details and return *default* instead. This ensures
        that a broken optional field never causes the whole page to be dropped.
        """
        try:
            return extractor(*args)
        except Exception as exc:
            log.warning(
                "parser.field_failed",
                field=field,
                reason=f"{type(exc).__name__}: {exc}",
            )
            return default

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

    def _extract_pokedex_number(self, tree: HTMLParser) -> int | None:
        """Return the National Pokédex number as an integer (e.g. 1 for Bulbasaur).

        Bulbapedia renders it as an <a href*="National_Pok..."> whose visible
        text is "#NNNN". We strip the leading '#' and cast to int.
        """
        for a in tree.css(f"a[href*='{_NATIONAL_DEX_HREF}']"):
            text = a.text(strip=True)
            if re.match(r"^#\d+$", text):
                return int(text[1:])
        return None

    def _extract_category(self, tree: HTMLParser) -> str | None:
        """Return the Pokémon category / species string (e.g. "Seed Pokémon").

        The category is linked via <a href*="Pokémon_category"> inside the
        infobox.
        """
        node = tree.css_first(f"a[href*='{_CATEGORY_HREF}']")
        if node is None:
            return None
        text = node.text(strip=True)
        return text or None

    def _extract_abilities(self, tree: HTMLParser) -> list[Ability]:
        """Return visible abilities from the infobox abilities sub-table.

        The abilities block is the infobox <td> that contains a link to
        /wiki/Ability. Inside it, each visible <td> (no display:none) holds
        one ability link. A <small> child whose text contains "Hidden Ability"
        marks that entry as a hidden ability. Alternate-form abilities in
        hidden cells are skipped entirely.
        """
        infobox = tree.css_first(_INFOBOX_SELECTOR)
        if infobox is None:
            return []

        # Locate the outer <td> that acts as the abilities container.
        abilities_container: Node | None = None
        for td in infobox.css("td"):
            if td.css_first(f"a[href='{_ABILITY_HUB_HREF}']"):
                abilities_container = td
                break

        if abilities_container is None:
            return []

        abilities: list[Ability] = []
        seen: set[str] = set()

        for td in abilities_container.css("td"):
            style = td.attributes.get("style") or ""
            if "display:none" in style.replace(" ", ""):
                continue

            ability_link = td.css_first("a[href*='_(Ability)']")
            if ability_link is None:
                continue

            name = ability_link.text(strip=True)
            if not name or name in seen:
                continue

            small = td.css_first("small")
            is_hidden = bool(small and "Hidden Ability" in small.text())

            seen.add(name)
            abilities.append(Ability(name=name, is_hidden=is_hidden))

        return abilities

    def _extract_evolution(self, tree: HTMLParser, current_name: str) -> Evolution:
        """Return the direct antecessor and successor of *current_name*.

        Bulbapedia renders the evolution chain as a <div> of nested tables
        immediately after the <h3> containing <span#Evolution>. Each stage
        table is labelled by a <small> element ("Unevolved", "First Evolution",
        …). The current Pokémon is identified by a <a class="mw-selflink">.
        Antecessor and successor are the stages immediately before and after.
        """
        anchor = tree.css_first(_EVOLUTION_ANCHOR)
        if anchor is None:
            return Evolution()

        # Walk forward from the parent <h3> to find the first <div>.
        evo_div = self._next_sibling_tag(anchor.parent, "div")
        if evo_div is None:
            return Evolution()

        # Build an ordered map of stage label → Pokémon name.
        chain: dict[str, str] = {}
        for small in evo_div.css("small"):
            label = small.text(strip=True)
            if label not in _EVOLUTION_STAGES:
                continue

            # The <small> is inside a <td> inside the inner stage <table>.
            # Navigate up carefully: small → td → tr → tbody → table.
            # Each step may be None if the DOM is not shaped as expected.
            td_node = small.parent
            if td_node is None:
                continue
            tr_node = td_node.parent
            if tr_node is None:
                continue
            tbody_node = tr_node.parent
            if tbody_node is None:
                continue
            stage_table = tbody_node.parent
            if stage_table is None:
                continue

            # Current Pokémon is a selflink; others are normal wiki links.
            self_link = stage_table.css_first("a.mw-selflink")
            wiki_links = [
                a
                for a in stage_table.css("a")
                if "_(Pok" in (a.attributes.get("href") or "")
            ]
            if self_link:
                chain[label] = self_link.text(strip=True)
            elif wiki_links:
                chain[label] = wiki_links[0].text(strip=True)

        # Determine which stage the current Pokémon occupies.
        current_stage: str | None = None
        for stage, name in chain.items():
            if name == current_name:
                current_stage = stage
                break

        if current_stage is None:
            return Evolution()

        idx = _EVOLUTION_STAGES.index(current_stage)
        antecessor = chain.get(_EVOLUTION_STAGES[idx - 1]) if idx > 0 else None
        successor = (
            chain.get(_EVOLUTION_STAGES[idx + 1])
            if idx < len(_EVOLUTION_STAGES) - 1
            else None
        )
        return Evolution(antecessor=antecessor, successor=successor)

    def _extract_image_url(self, tree: HTMLParser) -> str | None:
        """Return the full-resolution image URL from the og:image meta tag.

        Bulbapedia sets the first `<meta property="og:image">` to the
        official artwork PNG for the Pokémon's default form, e.g.:
        https://archives.bulbagarden.net/media/upload/thumb/4/4a/0025Pikachu.png/1200px-0025Pikachu.png
        """
        node = tree.css_first(_OG_IMAGE_SELECTOR)
        if node is None:
            return None
        return node.attributes.get("content") or None

    def _next_sibling_table(self, node: Node | None) -> Node | None:
        """Return the first <table> sibling after *node*."""
        return self._next_sibling_tag(node, "table")

    def _next_sibling_tag(self, node: Node | None, tag: str) -> Node | None:
        """Return the first sibling of *node* whose tag matches *tag*."""
        if node is None:
            return None
        current = node.next
        while current is not None:
            if current.tag == tag:
                return current
            current = current.next
        return None
