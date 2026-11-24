"""Data shared between pipeline stages."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["trading_card", "sealed_product", "video_game"]


class Identification(BaseModel):
    """What the photos show. Filled in by Claude, editable by the seller."""

    category: Category
    photos: list[str] = Field(description="File names of every photo of this one physical item, best front photo first.")
    reference_photos: list[str] = Field(
        description="Grading-company report screenshots for this item. Not listed on eBay.")
    name: str = Field(description="Card name, sealed product name or game title. No set, number or grade.")
    franchise: str = Field(description="e.g. Pokemon, Magic: The Gathering, NHL, Nintendo. '' if unknown.")
    set_name: str
    card_number: str = Field(description="As printed, e.g. 38/236, TG02/TG30, 038. '' if not a card.")
    year: str
    language: str
    rarity: str = Field(description="Rarity or variant, e.g. Full Art Secret Rare, Holo, 1st Edition.")
    grader: str = Field(description="PSA, BGS, CGC, SGC, TAG, ACE ... '' if not graded.")
    grade: str = Field(description="Number only, e.g. 10, 9.5. '' if not graded.")
    grade_label: str = Field(description="Label wording, e.g. GEM MINT, PRISTINE, MINT.")
    cert_number: str = Field(description="Only if legible in a photo or report; never guessed.")
    raw_condition: Literal["", "near_mint", "lightly_played", "moderately_played", "heavily_played"] = Field(
        description="Ungraded cards only.")
    product_type: str = Field(description="Sealed product: Booster Box, Elite Trainer Box, Tin, Booster Pack ...")
    platform: str = Field(description="Video games: Nintendo Switch, PS2, Game Boy Advance ...")
    region: str = Field(description="Video games: NTSC, PAL, NTSC-J. '' if unknown.")
    completeness: Literal["", "loose", "complete", "sealed"] = Field(description="Video games only.")
    game_condition: Literal["", "like_new", "very_good", "good", "acceptable"] = Field(
        description="Opened video games only.")
    condition_notes: str = Field(description="Only flaws or facts visible in the photos.")
    confidence: Literal["high", "medium", "low"]
    uncertainties: list[str] = Field(description="Anything the seller must confirm.")

    @property
    def graded(self) -> bool:
        return bool(self.grader and self.grade)

    def summary(self) -> str:
        bits = [self.year, self.franchise, self.name, self.card_number and f"#{self.card_number}", self.set_name,
                self.rarity, self.product_type, self.platform, self.completeness,
                f"{self.grader} {self.grade} {self.grade_label}".strip() if self.graded else ""]
        return " ".join(b for b in bits if b)


class IdentifiedBatch(BaseModel):
    items: list[Identification]
    unassigned_photos: list[str]


class Shipping(BaseModel):
    """Flat-rate shipping in the listing currency. A destination that is off is not offered."""

    us: bool = True
    us_cost: float = Field(17.5, ge=0)
    ca: bool = True
    ca_cost: float = Field(12.5, ge=0)
    intl: bool = False
    intl_cost: float = Field(17.5, ge=0)
    free_domestic: bool = False  # free to US buyers
    local_pickup: bool = False
    handling_days: int = Field(1, ge=0, le=30)


class ListingOptions(BaseModel):
    format: Literal["AUCTION", "FIXED_PRICE"] = "FIXED_PRICE"
    start_time: Optional[datetime] = None  # timezone-aware
    duration_days: Literal[1, 3, 5, 7, 10] = 7
    best_offer: bool = True
    shipping: Shipping = Field(default_factory=Shipping)


class Comp(BaseModel):
    id: str = ""
    source: str
    kind: Literal["sold", "active", "guide"]
    title: str
    price: float
    currency: str
    price_local: Optional[float] = None  # converted to the listing currency
    date: Optional[str] = None  # ISO date of sale
    url: str = ""
    included: bool = True
    note: str = ""


class SourceStatus(BaseModel):
    source: str
    status: Literal["ok", "empty", "skipped", "error"]
    detail: str = ""


class Pricing(BaseModel):
    currency: str = "USD"
    market_value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    list_price: Optional[float] = None  # Buy It Now
    start_price: Optional[float] = None  # auction
    auto_accept: Optional[float] = None
    auto_decline: Optional[float] = None
    confidence: Literal["high", "medium", "low", "none"] = "none"
    basis: str = ""
    warnings: list[str] = Field(default_factory=list)


class ListingText(BaseModel):
    title: str
    subtitle: str
    description: str = Field(description="Plain text, short paragraphs or '- ' bullets.")


class Draft(BaseModel):
    id: str
    created: datetime
    item: Identification
    options: ListingOptions
    text: Optional[ListingText] = None
    aspects: dict[str, list[str]] = Field(default_factory=dict)
    comps: list[Comp] = Field(default_factory=list)
    sources: list[SourceStatus] = Field(default_factory=list)
    pricing: Pricing = Field(default_factory=Pricing)
    price_override: Optional[float] = None
    links: dict[str, str] = Field(default_factory=dict)
    category_id: str = ""
    status: Literal["identified", "researching", "ready", "error", "pushed", "published"] = "identified"
    error: str = ""
    offer_id: str = ""
    listing_id: str = ""

    @property
    def price(self) -> Optional[float]:
        if self.price_override is not None:
            return self.price_override
        return self.pricing.start_price if self.options.format == "AUCTION" else self.pricing.list_price
