"""Stage 3: title, description and item specifics."""
from __future__ import annotations

import re
import unicodedata

from . import llm
from .models import Identification, ListingText

TITLE_MAX, SUBTITLE_MAX, DESC_MAX_WORDS = 80, 55, 120

SYSTEM = f"""You write eBay listings for collectibles.

title: at most {TITLE_MAX} characters. Put what buyers search for first: name, card number, set, variant, grader and grade; \
or game, platform, completeness; or set and product type. No emoji, no all-caps hype, no words like L@@K, RARE or INVEST.
subtitle: at most {SUBTITLE_MAX} characters.
description: concise, under {DESC_MAX_WORDS} words, plain text. One sentence saying what it is, then '- ' bullets for set/number, \
grade and cert number, condition, and what is included. Close with a line saying the photos show the actual item.

Use only the facts given. Do not add condition claims, rarity, population, investment potential, shipping or return terms. \
Never state a price. For ungraded items do not predict a grade."""


def write(item: Identification, model: str) -> ListingText:
    facts = item.model_dump_json(exclude={"photos", "reference_photos", "confidence", "uncertainties"}, indent=1)
    return tidy(llm.structured(model, SYSTEM, f"Facts:\n{facts}", ListingText, effort="low"), item)


def template(item: Identification) -> ListingText:
    """Plain fallback when Claude is unavailable."""
    grade = f"{item.grader} {item.grade} {item.grade_label.title()}".strip() if item.graded else ""
    if item.category == "trading_card":
        bits = [item.franchise, item.name, item.card_number, item.set_name, item.rarity, grade, item.year]
    elif item.category == "sealed_product":
        bits = [item.franchise, item.set_name, item.name, item.product_type, "Sealed"]
    else:
        bits = [item.name, item.platform, {"complete": "Complete CIB", "loose": "Loose", "sealed": "Sealed"}.get(item.completeness, "")]
    rows = [("Set", item.set_name), ("Number", item.card_number), ("Language", item.language), ("Grade", grade),
            ("Cert", item.cert_number), ("Platform", item.platform), ("Condition", item.condition_notes)]
    lines = [item.summary() + "."] + [f"- {k}: {v}" for k, v in rows if v] + ["Photos show the actual item."]
    return tidy(ListingText(title=" ".join(dict.fromkeys(b for b in bits if b)), subtitle="", description="\n".join(lines)), item)


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit + 1].rsplit(" ", 1)[0]
    return cut[:limit].rstrip(" -,|")


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def is_pokemon_card(item: Identification) -> bool:
    return item.category == "trading_card" and "pokemon" in _plain(item.franchise)


_ABBR = {"NM", "MT", "EX", "VG", "GD", "PR", "FR", "GM"}


def grade_words(label: str) -> str:
    """Slab label wording for a title: 'GEM MT' -> 'Gem Mint', 'NM-MT' stays 'NM-MT'."""
    label = re.sub(r"\bGEM[\s-]+MT\b", "GEM MINT", " ".join(label.upper().split()))
    return " ".join(w if all(p in _ABBR for p in w.split("-")) else w.capitalize() for w in label.split())


def pokemon_title(item: Identification) -> str:
    """{year} Pokemon {set} {card name} {number}, then {grader} {grade} {label} if graded."""
    set_name = re.sub(r"^pok[eé]mon\s+", "", item.set_name.strip(), flags=re.I)
    grade = [item.grader, item.grade] if item.graded else []

    def build(set_part: str, label: str) -> str:
        return " ".join(" ".join(b for b in [item.year, "Pokemon", set_part, item.name, item.card_number, *grade, label]
                                 if b).split())

    label = grade_words(item.grade_label) if item.graded else ""
    for lab in (label, ""):  # drop the label wording before cutting into the set name
        title = build(set_name, lab)
        if len(title) <= TITLE_MAX:
            return title
    room = TITLE_MAX - len(build("", "")) - 1
    return build(clip(set_name, room) if room > 0 else "", "")


def tidy(t: ListingText, item: Identification) -> ListingText:
    title = " ".join(t.title.split())
    if is_pokemon_card(item):
        title = pokemon_title(item)
    if item.graded:
        # The grade must survive clipping.
        tail = f"{item.grader} {item.grade}"
        if tail.lower() not in clip(title, TITLE_MAX).lower():
            title = f"{clip(title, TITLE_MAX - len(tail) - 1)} {tail}"
    return ListingText(title=clip(title, TITLE_MAX), subtitle=clip(t.subtitle, SUBTITLE_MAX), description=t.description.strip())


def aspects(item: Identification) -> dict[str, list[str]]:
    """eBay item specifics, from identified facts only."""
    if item.category == "video_game":
        rows = {"Game Name": item.name, "Platform": item.platform, "Region Code": item.region, "Release Year": item.year}
    elif item.category == "sealed_product":
        rows = {"Game": item.franchise, "Set": item.set_name, "Language": item.language, "Configuration": item.product_type,
                "Year Manufactured": item.year}
    else:
        rows = {"Game": item.franchise, "Card Name": item.name, "Set": item.set_name, "Card Number": item.card_number,
                "Language": item.language, "Rarity": item.rarity, "Year Manufactured": item.year,
                "Graded": "Yes" if item.graded else "No"}
        if item.graded:
            rows |= {"Professional Grader": item.grader, "Grade": item.grade, "Certification Number": item.cert_number}
    return {k: [v[:65]] for k, v in rows.items() if v}
