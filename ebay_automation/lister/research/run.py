"""Run every source, then convert, match and label the results."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor

from .. import fx, llm
from ..config import Settings
from ..models import Comp, Identification, SourceStatus
from . import sources, websearch
from .matching import match

SOURCES = [("eBay sold", sources.ebay_sold), ("eBay active", sources.ebay_active), ("Web search", websearch.web),
           ("PriceCharting", sources.pricecharting), ("TCGdex", sources.tcgdex)]


def finalize(item: Identification, comps: list[Comp], s: Settings) -> list[Comp]:
    """Convert currency, apply matching, assign ids and drop duplicates."""
    rates = {}
    if any(c.currency != s.currency for c in comps):
        try:
            rates = fx.rates_to_cad(s.data_dir / "fx.json")
        except Exception:  # comps in other currencies are excluded below, with the reason shown
            rates = {}
    out: dict[str, Comp] = {}
    for c in comps:
        c.id = c.id or hashlib.sha1(f"{c.source}|{c.kind}|{c.title}|{c.price}|{c.date}|{c.url}".encode()).hexdigest()[:12]
        c.price_local = fx.convert(c.price, c.currency, s.currency, rates)
        if c.price_local is None:
            c.included, c.note = False, f"no exchange rate for {c.currency}"
        elif c.included:
            c.price_local = round(c.price_local, 2)
            if c.source.endswith("(TCGdex)"):
                if item.graded:
                    c.included, c.note = False, "ungraded price, shown for context"
            elif c.source != "PriceCharting":
                ok, why = match(item, c.title)
                c.included, c.note = ok, why
        out.setdefault(c.id, c)
    # The same sale often appears through two sources.
    seen: set[tuple] = set()
    for c in out.values():
        k = (c.kind, c.title.lower(), c.price, c.date)
        if c.kind == "sold" and c.date and c.included and k in seen:
            c.included, c.note = False, "duplicate sale"
        seen.add(k)
    return list(out.values())


def run(item: Identification, s: Settings, token) -> tuple[list[Comp], list[SourceStatus]]:
    def one(entry):
        name, fn = entry
        try:
            got = fn(item, s, token)
            return got, SourceStatus(source=name, status="ok" if got else "empty", detail=f"{len(got)} result(s)")
        except sources.Skip as e:
            return [], SourceStatus(source=name, status="skipped", detail=str(e))
        except llm.LLMError as e:
            return [], SourceStatus(source=name, status="error", detail=str(e))
        except Exception as e:
            return [], SourceStatus(source=name, status="error", detail=f"{type(e).__name__}: {e}"[:200])

    with ThreadPoolExecutor(len(SOURCES)) as pool:
        results = list(pool.map(one, SOURCES))
    statuses = [st for _, st in results]
    statuses.append(SourceStatus(source="130point / Collectr / Terapeak", status="skipped",
                                 detail="no public API; open the link and paste the results"))
    return finalize(item, [c for got, _ in results for c in got], s), statuses
