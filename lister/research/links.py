"""Search queries and one-click research links."""
from __future__ import annotations

from urllib.parse import quote_plus

from ..models import Identification


def query(item: Identification) -> str:
    if item.category == "trading_card":
        bits = [item.name, item.card_number, f"{item.grader} {item.grade}" if item.graded else item.set_name]
    elif item.category == "sealed_product":
        bits = [item.franchise, item.set_name, item.name, item.product_type]
    else:
        bits = [item.name, item.platform, {"complete": "CIB", "sealed": "sealed", "loose": "loose"}.get(item.completeness, "")]
    seen: list[str] = []
    for w in " ".join(b for b in bits if b).replace("&", " ").split():
        if w.lower() not in (s.lower() for s in seen):
            seen.append(w)
    return " ".join(seen)


def plain_query(item: Identification) -> str:
    """Without the grade, for price-guide sites."""
    return " ".join(b for b in [item.name, item.card_number.split("/")[0], item.set_name or item.platform] if b)


def links(item: Identification) -> dict[str, str]:
    q, p = quote_plus(query(item)), quote_plus(plain_query(item))
    return {
        "eBay sold": f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1",
        "Terapeak": f"https://www.ebay.com/sh/research?marketplace=EBAY-US&keywords={q}&tabName=SOLD",
        "130point": "https://130point.com/sales/",
        "Collectr": "https://app.getcollectr.com/",
        "PriceCharting": f"https://www.pricecharting.com/search-products?q={p}&type=prices",
        "TCGplayer": f"https://www.tcgplayer.com/search/all/product?q={p}",
    }
