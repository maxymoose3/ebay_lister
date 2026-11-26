# eBay Lister

Photos in, eBay.ca listing drafts (CAD, shipped from Canada, no returns) out. Buyers outside Canada are served by
eBay International Shipping (eIS) when your account is enrolled. For trading cards, sealed product and video games.

## Setup

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
.venv/bin/python ebay_lister.py serve
```

Open http://127.0.0.1:8765. eBay keys are only needed for sending drafts to eBay.
After adding them, sign in once with `.venv/bin/python ebay_lister.py auth`.

## Workflow

1. Select or upload photos. Several items at once is fine; fronts, backs and grading reports are grouped per item.
2. Choose auction (start time, length) or Buy It Now, and shipping.
3. Identify, then **Write draft** for each item. Fix any detail first if the photos were misread.
4. Review the title and description, and enter your price.
5. Copy the listing, or **Send to eBay** as an unpublished offer. **Publish** is a separate, confirmed step.

Unpublished offers do not appear under Seller Hub drafts. They live in the Inventory API until published.

From the terminal: `ebay_lister.py draft IMG_2825.jpg IMG_2826.jpg --auction --start "2026-11-29 18:00" --days 7`, with `--price` to set the price

## Titles

Pokemon cards get a fixed title format: `{year} Pokemon {set} {card name} {card number}`, then `{grader} {grade} {label}` if graded,
for example `2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236 TAG 10 Gem Mint`. Blank fields are left out. If the title
is over 80 characters, the label wording is dropped first, then the set name is shortened. Other items get a title written by Claude.

## Prices

The app does not look up prices. Enter the Buy It Now price for each listing. Auctions start at `LISTER_AUCTION_START` (CAD 20)
unless you enter another start price. Shipping is charged separately at the flat rates in `.env`, as on eBay.

Canada shipping is on by default and is what you pay to reach the eIS hub for buyers abroad. US and International are
off by default; turn them on only to ship those buyers yourself instead of through eIS.

## Layout

`lister/identify.py` photos to items, `lister/drafting.py` titles and descriptions,
`lister/ebay.py`, `lister/web.py`. Drafts are JSON in `data/drafts/`. Tests: `.venv/bin/python -m pytest`.
