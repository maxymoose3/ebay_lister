# eBay Lister

Photos in, priced eBay.com listing drafts (USD, shipped from Canada, no returns) out. For trading cards, sealed product and video games.

## Setup

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env        # then add ANTHROPIC_API_KEY
.venv/bin/python ebay_lister.py serve
```

Open http://127.0.0.1:8765. eBay keys are only needed for active-listing prices and for sending drafts to eBay.
After adding them, sign in once with `.venv/bin/python ebay_lister.py auth`.

## Workflow

1. Select or upload photos. Several items at once is fine; fronts, backs and grading reports are grouped per item.
2. Choose auction (start time, length) or Buy It Now, and shipping.
3. Identify, then **Research and draft** each item. Fix any detail first if the photos were misread.
4. Review price, comps and text. Tick comps on or off and the price updates.
5. Copy the listing, or **Send to eBay** as an unpublished offer. **Publish** is a separate, confirmed step.

Unpublished offers do not appear under Seller Hub drafts. They live in the Inventory API until published.

From the terminal: `ebay_lister.py draft IMG_2825.jpg IMG_2826.jpg --auction --start "2026-11-29 18:00" --days 7`

## Price sources

| Source | Access | Data |
|---|---|---|
| eBay active | eBay keys | Asking prices |
| eBay sold | Marketplace Insights, only if eBay granted it | Sales |
| 130point, Collectr, Terapeak, eBay sold pages | Open the link, paste the results | Sales, guide |
| Claude web search | Anthropic key, best effort | Public pages |
| PriceCharting | Paid token | Guide, including TAG 10 and games |
| TCGdex | Free | Ungraded Pokemon guide prices |

130point and Collectr have no public API, and 130point blocks scripts, so the app does not scrape them.

## How prices are set

Comps must match name, number, grader and grade, language, platform and completeness. Mismatches stay visible with the reason.
Market value is the recency-weighted median of sales (30-day half-life, outliers dropped). With fewer than three sales it blends
in guides and discounted asking prices and reports low confidence. With nothing usable it gives no Buy It Now price.

- Buy It Now: value x 1.05, held near the cheapest live listings when there are three or more.
- Auction start: USD 20, with a warning when that is far from market value.
- Free US shipping adds the shipping cost to the Buy It Now price.

## Layout

`lister/identify.py` photos to items, `lister/research/` sources and matching, `lister/pricing.py`, `lister/drafting.py`,
`lister/ebay.py`, `lister/web.py`. Drafts are JSON in `data/drafts/`. Tests: `.venv/bin/python -m pytest`.
