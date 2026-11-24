"""Turn comps into a price. Pure and deterministic, so every number can be explained."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from statistics import median

from .config import Settings
from .models import Comp, ListingOptions, Pricing

HALF_LIFE_DAYS = 30
MAX_AGE_DAYS = 365


def _age(c: Comp, today: date) -> int | None:
    try:
        return max(0, (today - date.fromisoformat((c.date or "")[:10])).days)
    except ValueError:
        return None


def weighted_median(pairs: list[tuple[float, float]]) -> float:
    pairs = sorted(pairs)
    half, run = sum(w for _, w in pairs) / 2, 0.0
    for i, (v, w) in enumerate(pairs):
        run += w
        if math.isclose(run, half) and i + 1 < len(pairs):
            return (v + pairs[i + 1][0]) / 2
        if run > half:
            return v
    return pairs[-1][0]


def drop_outliers(comps: list[Comp]) -> list[Comp]:
    if len(comps) < 5:
        return comps
    logs = [math.log(c.price_local) for c in comps]
    m = median(logs)
    mad = median(abs(x - m) for x in logs) or 0.05
    return [c for c, x in zip(comps, logs) if abs(x - m) / (1.4826 * mad) <= 3.5]


def quantile(vals: list[float], q: float) -> float:
    vals = sorted(vals)
    pos = (len(vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def charm(x: float) -> float:
    """19.6 -> 19.99, 123 -> 124.99"""
    if x < 100:
        return max(0.99, round(x) - 0.01)
    return round(x / 5) * 5 - 0.01


def price(comps: list[Comp], opts: ListingOptions, s: Settings, today: date | None = None) -> Pricing:
    today = today or datetime.now(timezone.utc).date()
    p = Pricing(currency=s.currency, start_price=round(s.auction_start, 2))
    auction = opts.format == "AUCTION"
    use = [c for c in comps if c.included and c.price_local and c.price_local > 0]
    sold_all = [c for c in use if c.kind == "sold" and (_age(c, today) is None or _age(c, today) <= MAX_AGE_DAYS)]
    sold = drop_outliers(sold_all)
    active = [c.price_local for c in use if c.kind == "active"]
    guide = [c.price_local for c in use if c.kind == "guide"]
    # Asking prices run above sale prices; use the cheap end, discounted.
    asking = quantile(active, 0.25) * 0.93 if len(active) >= 3 else None

    value, parts = None, []
    if sold:
        ages = [_age(c, today) for c in sold]
        weighted = [(c.price_local, 0.5 ** ((HALF_LIFE_DAYS if a is None else a) / HALF_LIFE_DAYS))
                    for c, a in zip(sold, ages)]
        value = weighted_median(weighted)
        vals = [c.price_local for c in sold]
        p.low, p.high = quantile(vals, 0.25), quantile(vals, 0.75)
        parts.append(f"{len(sold)} sold (recency-weighted median {value:.2f})")
        if len(sold_all) > len(sold):
            parts.append(f"{len(sold_all) - len(sold)} outlier(s) dropped")
    if len(sold) >= 3:
        known = [a for a in ages if a is not None]
        spread = (p.high - p.low) / value if value else 1
        p.confidence = "high" if len(sold) >= 6 and known and min(known) <= 45 and spread <= 0.25 else "medium"
    else:
        others = []
        if guide:
            others.append(median(guide))
            parts.append(f"{len(guide)} price guide(s) (median {median(guide):.2f})")
        if asking:
            others.append(asking)
            parts.append(f"{len(active)} active listings (low end, discounted: {asking:.2f})")
        if value is not None and others:
            value = 0.6 * value + 0.4 * median(others)
        elif others:
            value = median(others)
        p.confidence = "low" if value is not None else "none"
    if value is None:
        p.basis = "No usable comparable found."
        p.warnings.append("No market value found, so the auction start is unchecked. Paste comps to compare." if auction
                          else "Not enough data to price this item. Paste comps or enter a price.")
        return p

    p.market_value = round(value, 2)
    ship = opts.shipping
    extra = ship.us_cost if ship.free_domestic and ship.us else 0.0
    target = value * s.bin_markup
    if len(active) >= 3:
        # Do not list far above the cheapest live competition.
        target = min(target, max(quantile(active, 0.25), value * 0.9))
    p.list_price = charm(target + extra)
    if opts.best_offer:
        p.auto_accept = round(min((value + extra) * 0.97, p.list_price - 0.01), 2)
        p.auto_decline = round(min((value + extra) * 0.80, p.auto_accept - 0.01), 2)
    p.basis = "; ".join(parts)
    if extra and not auction:
        p.basis += f"; {extra:.2f} added for free US shipping"
    p.low, p.high = (round(p.low, 2) if p.low else None), (round(p.high, 2) if p.high else None)
    if p.confidence == "low":
        p.warnings.append("Few or no exact sales found. Check the research links before listing.")
    if auction and p.start_price >= value:
        p.warnings.append(f"The {p.start_price:.2f} start is at or above market value; it may get no bids.")
    elif auction and p.start_price < value / 2:
        p.warnings.append(f"The {p.start_price:.2f} start is under half of market value; one bid could win it.")
    return p
