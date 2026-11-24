"""Exchange rates from the Bank of Canada (free, no key)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

SERIES = {"USD": "FXUSDCAD", "EUR": "FXEURCAD", "GBP": "FXGBPCAD", "JPY": "FXJPYCAD", "AUD": "FXAUDCAD"}
URL = "https://www.bankofcanada.ca/valet/observations/" + ",".join(SERIES.values()) + "/json"


def rates_to_cad(cache: Path) -> dict[str, float]:
    """CAD per unit of each currency. Uses a cache under 12 hours old. Raises if unavailable."""
    if cache.exists() and time.time() - cache.stat().st_mtime < 12 * 3600:
        return json.loads(cache.read_text())
    r = httpx.get(URL, params={"recent": 1}, timeout=20)
    r.raise_for_status()
    row = r.json()["observations"][-1]
    rates = {"CAD": 1.0} | {c: float(row[s]["v"]) for c, s in SERIES.items() if s in row}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rates))
    return rates


def convert(amount: float, src: str, dst: str, rates: dict[str, float]) -> float | None:
    if src == dst:
        return amount
    if src not in rates or dst not in rates:
        return None
    return amount * rates[src] / rates[dst]
