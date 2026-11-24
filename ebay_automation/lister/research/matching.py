"""Decide whether a listing title is really the same item.

Deterministic on purpose: the seller can see why a comp was excluded and override it.
"""
from __future__ import annotations

import re
import unicodedata

from ..models import Identification

GRADERS = ["PSA", "BGS", "BVG", "CGC", "SGC", "TAG", "ACE", "HGA", "GMA", "KSA", "ARS", "BECKETT", "AGS", "MNT", "PCA"]
# grader, then up to three label words, then a number: "TAG Gem Mint 10", "PSA 9"
_GRADE_WORDS = r"(?:GEM|MINT|MT|GM|PRISTINE|GRADED|GRADE|PERFECT|BLACK|LABEL|NM)"
_GRADE = re.compile(
    rf"\b({'|'.join(GRADERS)})\b[\s:\-]*(?:{_GRADE_WORDS}[\s:\-]+){{0,3}}(10|[1-9](?:\.5)?)(?![\d/.])", re.I)
_JUNK = re.compile(r"\b(proxy|custom|orica|replica|repro|reproduction|fan ?made|digital|read desc\w*|damaged|"
                   r"you pick|u pick|pick your|choose|lot|bundle|playset|empty|sticker|metal)\b", re.I)
_LANGS = ["japanese", "korean", "chinese", "german", "french", "italian", "spanish", "portuguese", "thai", "indonesian"]
_STOP = {"the", "of", "and", "a", "an", "for", "in", "edition", "game", "video"}
PLATFORM_ALIASES = {
    "nintendo switch": ["switch"], "nintendo switch 2": ["switch 2"], "game boy advance": ["gba", "gameboy advance", "game boy advance"],
    "game boy color": ["gbc", "gameboy color", "game boy color"], "game boy": ["game boy", "gameboy", "gb"],
    "nintendo ds": ["nintendo ds", "nds", "ds"], "nintendo 3ds": ["3ds"], "nintendo 64": ["n64", "nintendo 64"],
    "gamecube": ["gamecube", "game cube", "gcn", "ngc"], "super nintendo": ["snes", "super nintendo"],
    "nes": ["nes", "nintendo entertainment system"], "wii": ["wii"], "wii u": ["wii u", "wiiu"],
    "playstation": ["ps1", "psx", "playstation 1", "playstation"], "playstation 2": ["ps2", "playstation 2"],
    "playstation 3": ["ps3", "playstation 3"], "playstation 4": ["ps4", "playstation 4"],
    "playstation 5": ["ps5", "playstation 5"], "psp": ["psp"], "xbox": ["xbox"], "xbox 360": ["xbox 360", "x360"],
    "xbox one": ["xbox one"], "sega genesis": ["genesis"], "sega dreamcast": ["dreamcast"], "sega saturn": ["saturn"],
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", norm(s)) if t not in _STOP]


def has_word(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(norm(phrase))}(?![a-z0-9])", text) is not None


def grades_in(title: str) -> set[tuple[str, str]]:
    return {("BGS" if g.upper() == "BECKETT" else g.upper(), n) for g, n in _GRADE.findall(title)}


def bare_number(s: str) -> str:
    """'038' -> '38', '38/236' -> '38', 'TG02/TG30' -> 'tg2'."""
    m = re.match(r"#?\s*([a-z]*)0*(\d+)([a-z]?)", norm(s).strip())
    return f"{m[1]}{m[2]}{m[3]}" if m else ""


def _numbers_in(title: str) -> set[str]:
    """Card numbers written explicitly: '#038', '38/236', 'TG02'."""
    t = norm(title)
    found = re.findall(r"#\s*([a-z]*\d+[a-z]?)", t) + re.findall(r"\b([a-z]*\d+)\s*/\s*[a-z]*\d+", t) \
        + re.findall(r"\b((?:tg|gg|sv|swsh|sm|xy|bw|mep|svp)\d{1,3})\b", t)
    return {bare_number(f) for f in found}


def match(item: Identification, title: str) -> tuple[bool, str]:
    """(is a comparable, reason if not)"""
    t = norm(title)
    wanted = item.name + " " + item.rarity + " " + item.product_type + " " + item.set_name
    for m in _JUNK.finditer(t):
        if not has_word(norm(wanted), m[0]):
            return False, f"contains '{m[0]}'"
    missing = [w for w in tokens(item.name) if w not in tokens(title)]
    allowed = 0 if item.category == "trading_card" else max(0, len(tokens(item.name)) // 4)
    if len(missing) > allowed:
        return False, f"title lacks '{' '.join(missing)}'"
    lang = norm(item.language or "english")
    for other in _LANGS:
        if has_word(t, other) and other != lang:
            return False, f"{other} version"
    if lang in _LANGS and not has_word(t, lang):
        return False, f"not marked {lang}"
    return {"trading_card": _card, "sealed_product": _sealed, "video_game": _game}[item.category](item, title, t)


def _card(item: Identification, title: str, t: str) -> tuple[bool, str]:
    found = grades_in(title)
    if item.graded:
        if (item.grader.upper(), item.grade) not in found:
            return False, f"not {item.grader} {item.grade}"
        if len(found) > 1:
            return False, "several grades in title"
        pristine = has_word(t, "pristine") or has_word(t, "black label")
        if pristine != ("pristine" in norm(item.grade_label) or "black label" in norm(item.grade_label)):
            return False, "pristine and gem mint are not comparable"
    elif found:
        return False, "graded copy"
    if item.card_number:
        nums, want = _numbers_in(title), bare_number(item.card_number)
        if nums and want not in nums:
            return False, f"different card number ({', '.join(sorted(nums))})"
        if not nums:
            in_title = want in {bare_number(x) for x in tokens(title)} if len(want) > 1 else False
            in_set = item.set_name and all(w in tokens(title) for w in tokens(item.set_name))
            if not (in_title or in_set):
                return False, "cannot confirm card number or set"
    if has_word(t, "1st edition") != has_word(norm(item.rarity + " " + item.name), "1st edition"):
        return False, "1st edition mismatch"
    if has_word(t, "reverse") != has_word(norm(item.rarity), "reverse"):
        return False, "reverse holo mismatch"
    return True, ""


_SEALED_TYPES = ["elite trainer box", "etb", "booster box", "booster bundle", "booster pack", "blister", "tin",
                 "collection box", "premium collection", "ultra premium", "upc", "build and battle", "case", "display",
                 "starter deck", "theme deck", "commander deck"]


def _sealed(item: Identification, title: str, t: str) -> tuple[bool, str]:
    own = norm(f"{item.name} {item.product_type}")
    alias = {"etb": "elite trainer box", "upc": "ultra premium", "display": "booster box"}
    mine = {alias.get(x, x) for x in _SEALED_TYPES if has_word(own, x)}
    theirs = {alias.get(x, x) for x in _SEALED_TYPES if has_word(t, x)}
    if theirs - mine:
        return False, f"different product ({', '.join(sorted(theirs - mine))})"
    if mine and not (mine & theirs):
        return False, "product type not confirmed"
    set_words = tokens(item.set_name)
    if set_words and not all(w in tokens(title) for w in set_words):
        return False, "different set"
    if grades_in(title) or has_word(t, "opened") or has_word(t, "code card"):
        return False, "not a sealed unit"
    q = re.search(r"\b(?:x\s*([2-9]|\d{2})|([2-9]|\d{2})\s*x)\b", t)
    if q:
        return False, "multiple units"
    return True, ""


def _game(item: Identification, title: str, t: str) -> tuple[bool, str]:
    if item.platform:
        names = PLATFORM_ALIASES.get(norm(item.platform), [item.platform])
        if not any(has_word(t, n) for n in [*names, item.platform]):
            return False, f"not marked {item.platform}"
    for part in ("case only", "manual only", "box only", "no game", "cover only", "no disc"):
        if has_word(t, part):
            return False, part
    loose = any(has_word(t, x) for x in ("loose", "cartridge only", "cart only", "disc only", "game only"))
    sealed = any(has_word(t, x) for x in ("sealed", "brand new", "factory sealed", "bnib", "wata", "vga"))
    cib = any(has_word(t, x) for x in ("cib", "complete", "with manual", "w/ manual"))
    if item.completeness == "sealed" and not sealed:
        return False, "not sealed"
    if item.completeness in ("loose", "complete") and sealed:
        return False, "sealed copy"
    if item.completeness == "complete" and loose:
        return False, "loose copy"
    if item.completeness == "loose" and cib:
        return False, "complete copy"
    if item.region and norm(item.region) != "pal" and has_word(t, "pal"):
        return False, "PAL copy"
    return True, ""
