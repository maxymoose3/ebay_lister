"""Photos -> items -> research -> priced draft."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from . import drafting, llm, pricing
from .config import Settings
from .ebay import Ebay, default_category
from .identify import identify
from .models import Comp, Draft, Identification, ListingOptions, Shipping
from .research import pasted, run as research_run
from .research.links import links
from .store import Store


class Pipeline:
    def __init__(self, s: Settings | None = None):
        self.s = s or Settings()
        self.store = Store(self.s.data_dir / "drafts")
        self.ebay = Ebay(self.s)

    def default_options(self) -> ListingOptions:
        s = self.s
        return ListingOptions(shipping=Shipping(ca_cost=s.ship_ca_cost, us_cost=s.ship_us_cost, intl_cost=s.ship_intl_cost,
                                                handling_days=s.handling_days))

    def create(self, item: Identification, opts: ListingOptions | None = None) -> Draft:
        d = Draft(id=uuid.uuid4().hex[:12], created=datetime.now(timezone.utc), item=item,
                  options=opts or self.default_options(), links=links(item))
        return self.store.save(d)

    def identify(self, names: list[str], opts: ListingOptions | None = None) -> tuple[list[Draft], list[str]]:
        batch = identify(self.s.photos_dir, names, self.s.model)
        return [self.create(i, opts.model_copy(deep=True) if opts else None) for i in batch.items], batch.unassigned_photos

    def research(self, id: str) -> Draft:
        """Market research, price and text for one draft."""
        d = self.store.get(id)
        check_options(d.options)
        d.status, d.error = "researching", ""
        self.store.save(d)
        try:
            d.links = links(d.item)
            kept = [c for c in d.comps if c.source.endswith("(pasted)")]
            found, d.sources = research_run.run(d.item, self.s, self.ebay.app_token)
            # Pasted comps keep the seller's include/exclude choices.
            d.comps = found + [c for c in kept if c.id not in {f.id for f in found}]
            d.pricing = pricing.price(d.comps, d.options, self.s)
            d.aspects = drafting.aspects(d.item)
            d.category_id = d.category_id or default_category(d.item)
            try:
                d.text = drafting.write(d.item, self.s.model)
            except llm.LLMError as e:
                d.text = drafting.template(d.item)
                d.error = f"Used the plain template for the text: {e}"
            d.status = "ready"
        except Exception as e:
            d.status, d.error = "error", f"{type(e).__name__}: {e}"[:400]
        return self.store.save(d)

    def add_pasted(self, id: str, text: str, source: str, dollar_currency: str) -> Draft:
        d = self.store.get(id)
        new = research_run.finalize(d.item, pasted.parse(text, source, dollar_currency, self.s.model), self.s)
        have = {c.id for c in d.comps}
        d.comps += [c for c in new if c.id not in have]
        return self.reprice(d)

    def add_manual(self, id: str, comp: Comp) -> Draft:
        d = self.store.get(id)
        d.comps += research_run.finalize(d.item, [comp], self.s)
        return self.reprice(d)

    def toggle(self, id: str, comp_id: str, included: bool) -> Draft:
        d = self.store.get(id)
        for c in d.comps:
            if c.id == comp_id:
                c.included = included and c.price_local is not None
        return self.reprice(d)

    def reprice(self, d: Draft) -> Draft:
        d.pricing = pricing.price(d.comps, d.options, self.s)
        if d.status == "pushed":
            d.status = "ready"  # eBay still has the old version; it must be sent again before publishing
        return self.store.save(d)


def check_options(o: ListingOptions, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    sh = o.shipping
    if not (sh.ca or sh.us or sh.intl or sh.local_pickup):
        raise ValueError("Choose at least one shipping option.")
    if not sh.us and (sh.ca or sh.intl):
        raise ValueError("eBay.com needs a US shipping option alongside Canadian or international shipping.")
    if o.start_time is None:
        return
    if o.start_time.tzinfo is None:
        raise ValueError("Start time needs a timezone.")
    if o.start_time < now + timedelta(minutes=15):
        raise ValueError("Start time must be at least 15 minutes from now.")
    if o.start_time > now + timedelta(days=21):
        raise ValueError("eBay allows scheduling up to 3 weeks ahead.")
