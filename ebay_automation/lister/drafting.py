"""Stage 3: title, description and item specifics."""
from __future__ import annotations

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


def tidy(t: ListingText, item: Identification) -> ListingText:
    title = " ".join(t.title.split())
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
