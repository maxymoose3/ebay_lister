"""Data shared between pipeline stages."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field

Category = Literal["trading_card", "sealed_product", "video_game"]


def _blank_to_none(v):
    return None if v == "" else v


# A choice that may not apply. Gemini rejects "" as an enum value, so "not applicable" is null;
# "" (from the UI or older saved drafts) is still accepted and read as null.
def Choice(*values: str):
    return Annotated[Optional[Literal[values]], BeforeValidator(_blank_to_none)]


class Identification(BaseModel):
    """What the photos show. Filled in by the photo-ID model, editable by the seller."""

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
    raw_condition: Choice("near_mint", "lightly_played", "moderately_played", "heavily_played") = Field(
        None, description="Ungraded cards only; null otherwise.")
    product_type: str = Field(description="Sealed product: Booster Box, Elite Trainer Box, Tin, Booster Pack ...")
    platform: str = Field(description="Video games: Nintendo Switch, PS2, Game Boy Advance ...")
    region: str = Field(description="Video games: NTSC, PAL, NTSC-J. '' if unknown.")
    completeness: Choice("loose", "complete", "sealed") = Field(None, description="Video games only; null otherwise.")
    game_condition: Choice("like_new", "very_good", "good", "acceptable") = Field(
        None, description="Opened video games only; null otherwise.")
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
    """Flat-rate shipping in the listing currency (CAD). Canada is domestic on eBay.ca.

    US and International are seller-shipped options, off by default so eBay International Shipping serves
    buyers abroad. A destination that is off is not offered by the seller."""

    ca: bool = True
    ca_cost: float = Field(18.0, ge=0)
    us: bool = False
    us_cost: float = Field(25.0, ge=0)
    intl: bool = False
    intl_cost: float = Field(25.0, ge=0)
    local_pickup: bool = False
    handling_days: int = Field(1, ge=0, le=30)


class ListingOptions(BaseModel):
    format: Literal["AUCTION", "FIXED_PRICE"] = "FIXED_PRICE"
    start_time: Optional[datetime] = None  # timezone-aware
    duration_days: Literal[1, 3, 5, 7, 10] = 7
    best_offer: bool = True
    shipping: Shipping = Field(default_factory=Shipping)


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
    price_override: Optional[float] = None  # the seller's price: Buy It Now price or auction start
    default_start: Optional[float] = None  # auction start used when the seller sets none
    category_id: str = ""
    status: Literal["identified", "drafting", "ready", "error", "pushed", "published"] = "identified"
    error: str = ""
    offer_id: str = ""
    listing_id: str = ""

    @property
    def price(self) -> Optional[float]:
        """The item price sent to eBay. Shipping is charged separately, through the shipping policy."""
        if self.price_override is not None:
            return self.price_override
        return self.default_start if self.options.format == "AUCTION" else None
