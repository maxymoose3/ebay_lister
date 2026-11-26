"""Settings, read from .env / the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _s(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _f(name: str, default: float) -> float:
    return float(_s(name) or default)


def _b(name: str) -> bool:
    return _s(name).lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Paths
    photos_dir: Path = ROOT / "photos"
    data_dir: Path = ROOT / "data"
    token_file: Path = ROOT / ".ebay_tokens.json"
    state_file: Path = ROOT / ".ebay_state.json"

    # Claude
    model: str = field(default_factory=lambda: _s("LISTER_MODEL", "claude-opus-5-5"))

    # eBay
    ebay_env: str = field(default_factory=lambda: _s("EBAY_ENV", "production"))
    client_id: str = field(default_factory=lambda: _s("EBAY_CLIENT_ID"))
    client_secret: str = field(default_factory=lambda: _s("EBAY_CLIENT_SECRET"))
    runame: str = field(default_factory=lambda: _s("EBAY_RUNAME"))
    # Listings go on eBay.com, so "domestic" shipping means to the US.
    marketplace: str = "EBAY_US"
    currency: str = "USD"
    timezone: str = field(default_factory=lambda: _s("LISTER_TIMEZONE", "America/Vancouver"))
    include_subtitle: bool = field(default_factory=lambda: _b("EBAY_INCLUDE_SUBTITLE"))

    # Location
    location_key: str = field(default_factory=lambda: _s("EBAY_LOCATION_KEY", "squamish-bc"))
    location_city: str = field(default_factory=lambda: _s("EBAY_LOCATION_CITY", "Squamish"))
    location_province: str = field(default_factory=lambda: _s("EBAY_LOCATION_PROVINCE", "BC"))
    location_postal: str = field(default_factory=lambda: _s("EBAY_LOCATION_POSTAL"))

    # Shipping defaults (USD). eBay.com service codes, for items sent from Canada.
    handling_days: int = field(default_factory=lambda: int(_f("EBAY_HANDLING_DAYS", 1)))
    ship_ca_service: str = field(default_factory=lambda: _s("EBAY_SHIP_CA_SERVICE", "StandardInternational"))
    ship_ca_cost: float = field(default_factory=lambda: _f("EBAY_SHIP_CA_COST", 12.5))
    ship_us_service: str = field(default_factory=lambda: _s("EBAY_SHIP_US_SERVICE", "StandardShippingFromOutsideUS"))
    ship_us_cost: float = field(default_factory=lambda: _f("EBAY_SHIP_US_COST", 17.5))
    ship_intl_service: str = field(default_factory=lambda: _s("EBAY_SHIP_INTL_SERVICE", "OtherInternational"))
    ship_intl_cost: float = field(default_factory=lambda: _f("EBAY_SHIP_INTL_COST", 17.5))

    # Existing business policies (optional)
    fulfillment_policy_id: str = field(default_factory=lambda: _s("EBAY_FULFILLMENT_POLICY_ID"))
    return_policy_id: str = field(default_factory=lambda: _s("EBAY_RETURN_POLICY_ID"))
    payment_policy_id: str = field(default_factory=lambda: _s("EBAY_PAYMENT_POLICY_ID"))

    # Pricing
    auction_start: float = field(default_factory=lambda: _f("LISTER_AUCTION_START", 20.0))

    @property
    def has_ebay_keys(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def api_base(self) -> str:
        return "https://api.sandbox.ebay.com" if self.ebay_env == "sandbox" else "https://api.ebay.com"

    @property
    def media_base(self) -> str:
        return "https://apim.sandbox.ebay.com" if self.ebay_env == "sandbox" else "https://apim.ebay.com"

    @property
    def auth_base(self) -> str:
        return "https://auth.sandbox.ebay.com" if self.ebay_env == "sandbox" else "https://auth.ebay.com"
