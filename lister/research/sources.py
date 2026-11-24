"""API-backed price sources. Each returns raw Comps; matching happens in `run`."""
from __future__ import annotations

import time

import httpx

from ..config import Settings
from ..models import Comp, Identification
from . import links
from .matching import bare_number, norm, tokens

TIMEOUT = 25


def fetch(url: str, **kw) -> httpx.Response:
    """GET with retries on rate limits, server errors and dropped connections."""
    for attempt in range(4):
        try:
            r = httpx.get(url, timeout=TIMEOUT, **kw)
            if r.status_code != 429 and r.status_code < 500:
                return r
        except httpx.TransportError:
            if attempt == 3:
                raise
        if attempt < 3:
            time.sleep(1.5 * 2 ** attempt)
    return r


class Skip(Exception):
    """Source is not configured or does not apply."""


def ebay_active(item: Identification, s: Settings, token) -> list[Comp]:
    if not s.has_ebay_keys:
        raise Skip("needs EBAY_CLIENT_ID / EBAY_CLIENT_SECRET")
    r = fetch(f"{s.api_base}/buy/browse/v1/item_summary/search",
                  headers={"Authorization": f"Bearer {token()}", "X-EBAY-C-MARKETPLACE-ID": s.marketplace},
                  params={"q": links.query(item), "limit": 60, "filter": "buyingOptions:{FIXED_PRICE}"})
    r.raise_for_status()
    return [Comp(source="eBay active", kind="active", title=x["title"], price=float(x["price"]["value"]),
                 currency=x["price"]["currency"], url=x.get("itemWebUrl", ""))
            for x in r.json().get("itemSummaries", []) if "price" in x]


def ebay_sold(item: Identification, s: Settings, token) -> list[Comp]:
    """Marketplace Insights. eBay grants this per account and is closed to new applicants."""
    if not (s.has_ebay_keys and s.insights):
        raise Skip("eBay restricts sold data (Marketplace Insights API); set EBAY_INSIGHTS_ENABLED=true if you have access")
    r = fetch(f"{s.api_base}/buy/marketplace_insights/v1_beta/item_sales/search",
                  headers={"Authorization": f"Bearer {token()}", "X-EBAY-C-MARKETPLACE-ID": s.marketplace},
                  params={"q": links.query(item), "limit": 100})
    r.raise_for_status()
    return [Comp(source="eBay sold", kind="sold", title=x["title"], price=float(x["lastSoldPrice"]["value"]),
                 currency=x["lastSoldPrice"]["currency"], date=(x.get("lastSoldDate") or "")[:10] or None,
                 url=x.get("itemWebUrl", ""))
            for x in r.json().get("itemSales", []) if "lastSoldPrice" in x]


def tcgdex(item: Identification, s: Settings, token=None) -> list[Comp]:
    """Free Pokemon prices (TCGplayer, Cardmarket). Raw cards only."""
    if item.category != "trading_card" or "pokemon" not in norm(item.franchise):
        raise Skip("Pokemon cards only")
    if norm(item.language or "english") != "english":
        raise Skip("English cards only")
    base = "https://api.tcgdex.net/v2/en"
    # The API matches names literally, so send the longest word and filter here.
    word = max(tokens(item.name), key=len)
    r = fetch(f"{base}/cards", params={"name": word})
    r.raise_for_status()
    want = bare_number(item.card_number)
    hits = [c for c in r.json() if want and bare_number(c["localId"]) == want
            and all(w in tokens(c["name"]) for w in tokens(item.name))]
    cards = []
    for c in hits[:6]:
        d = fetch(f"{base}/cards/{c['id']}")
        if d.is_success:
            cards.append(d.json())
    if len(cards) > 1:
        total = item.card_number.split("/")[1].lstrip("0") if "/" in item.card_number else ""
        by_set = [c for c in cards if set(tokens(c["set"]["name"])) & set(tokens(item.set_name))]
        by_total = [c for c in cards if total and str(c["set"].get("cardCount", {}).get("official")) == total]
        cards = by_total or by_set
    if len(cards) != 1:
        return []
    c, out = cards[0], []
    title = f"{c['name']} {c['set']['name']} {c['localId']}"
    price = c.get("pricing") or {}
    variants = {k: v for k, v in (price.get("tcgplayer") or {}).items() if isinstance(v, dict) and v.get("marketPrice")}
    wanted = norm(item.rarity)
    for name, v in variants.items():
        is_reverse = "reverse" in name.lower()
        first = "1st" in name.lower()
        if is_reverse != ("reverse" in wanted) or first != ("1st edition" in wanted):
            continue
        out.append(Comp(source="TCGplayer market (TCGdex)", kind="guide", title=f"{title} {name}",
                        price=v["marketPrice"], currency="USD",
                        url=f"https://www.tcgplayer.com/product/{v['productId']}" if v.get("productId") else ""))
    cm = price.get("cardmarket") or {}
    if cm.get("avg30") and "reverse" not in wanted:
        out.append(Comp(source="Cardmarket 30-day avg (TCGdex)", kind="guide", title=title,
                        price=cm["avg30"], currency=cm.get("unit", "EUR")))
    return out


_PC_CARD = {("PSA", "10"): "manual-only-price", ("BGS", "10"): "bgs-10-price", ("CGC", "10"): "condition-17-price",
            ("SGC", "10"): "condition-18-price", ("TAG", "10"): "condition-21-price", ("ACE", "10"): "condition-22-price"}
_PC_ANY = {"9.5": "box-only-price", "9": "graded-price", "8.5": "new-price", "8": "new-price", "7.5": "cib-price",
           "7": "cib-price", "6": "condition-16-price", "5": "condition-15-price", "4": "condition-14-price",
           "3": "condition-13-price", "2": "condition-10-price", "1": "condition-9-price"}


def pricecharting_key(item: Identification) -> str | None:
    if item.category == "video_game":
        return {"loose": "loose-price", "complete": "cib-price", "sealed": "new-price"}.get(item.completeness)
    if item.category == "sealed_product" or not item.graded:
        return "loose-price"
    if item.grade == "10" and ("pristine" in norm(item.grade_label) or "black" in norm(item.grade_label)):
        return {"CGC": "condition-19-price", "BGS": "condition-20-price"}.get(item.grader.upper())
    if item.grade == "10":
        return _PC_CARD.get((item.grader.upper(), "10"))
    return _PC_ANY.get(item.grade)


def pricecharting(item: Identification, s: Settings, token=None) -> list[Comp]:
    if not s.pricecharting_token:
        raise Skip("needs PRICECHARTING_TOKEN (paid subscription)")
    key = pricecharting_key(item)
    if not key:
        raise Skip("no PriceCharting grade for this item")
    time.sleep(1.1)  # documented limit: one call per second
    r = fetch("https://www.pricecharting.com/api/product",
                  params={"t": s.pricecharting_token, "q": links.plain_query(item)})
    if r.status_code in (401, 403):
        raise RuntimeError("PriceCharting rejected the token")
    d = r.json()
    if d.get("status") != "success" or not d.get(key):
        return []
    title = f"{d.get('product-name', '')} {d.get('console-name', '')}"
    have = tokens(title)
    if not all(w in have for w in tokens(item.name)):
        return []
    if item.card_number and bare_number(item.card_number) not in {bare_number(x) for x in have}:
        return []
    generic = item.graded and item.grade != "10"
    return [Comp(source="PriceCharting", kind="guide", title=title + (" (any grader)" if generic else ""),
                 price=d[key] / 100, currency="USD",
                 url=f"https://www.pricecharting.com/game/{d['id']}" if d.get("id") else "")]

