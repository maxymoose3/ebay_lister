# First run

Status as of November 23, 2026. Run every command from the project folder.

## What is built

A local app (web page and command line) that turns photos into priced eBay.com listing drafts.

| Stage | What it does |
|---|---|
| Photos | Reads JPG, PNG, WebP and HEIC. Removes GPS and other metadata before a photo leaves this Mac. |
| Identify | Claude groups photos into items and reads name, set, number, grade, cert, platform and so on. You can correct any field. |
| Research | Collects prices, converts them to USD and keeps only comparables that match the item. Excluded results stay visible with the reason. |
| Price | Recency-weighted median of sales, outliers dropped. Shows confidence and how the price was reached. |
| Draft | Title (80 characters max), concise description, item specifics, eBay condition and category. |
| eBay | Uploads photos and creates an **unpublished** offer. Publishing is a separate step you confirm for each listing. |

### Settings in place

- eBay.com (`EBAY_US`), USD, items sent from Squamish, BC.
- No returns. Times are America/Vancouver.
- Auctions start at $20. Buy It Now is market value x 1.05, held near the cheapest live listings.
- Flat shipping: US $17.50, Canada $12.50, International $17.50 (off by default).

### What has and has not been tested

| | Status |
|---|---|
| Automated tests | 54 pass, with Claude and eBay simulated |
| TCGdex prices, exchange rates | Run live; TCGdex found the right card for all six different cards in `photos/` |
| Web page | Rendered at desktop and phone width; not clicked through by hand |
| Claude: identification, web search, descriptions, reading pasted comps | **Never run live** (no API key yet) |
| eBay: sign-in, active prices, photo upload, offers, publishing | **Never run live** (no keys yet) |
| PriceCharting | **Never run live** (no token yet) |

## Next steps

### 1. Set up the Claude key (required)

1. Create a key at https://platform.claude.com/settings/keys.
2. Run `cp .env.example .env`.
3. Set `ANTHROPIC_API_KEY` in `.env`. This is billed per use; cost per item has not been measured, so check usage after the first few.

The virtual environment already exists in `.venv`. Restart the app whenever `.env` changes.

### 2. Try one card

```sh
.venv/bin/python ebay_lister.py serve
```

1. Open http://127.0.0.1:8765 and select `IMG_2825.jpg`, `IMG_2826.jpg` and `J6556419.jpg`.
2. Choose **Auction** or **Buy It Now**, check shipping, and click **Identify items**.
3. Expect: Blastoise & Piplup GX, 38/236, Cosmic Eclipse, TAG 10 Gem Mint, cert J6556419. Correct anything wrong under **Item details and options**.
4. Click **Research and draft**.

### 3. Add sold prices

Slabs will usually show low confidence or no Buy It Now price until you do this. Automatic sold data is limited: eBay's sold-data API
is closed to new developers, and 130point and Collectr have no public API.

1. Under **Add comps from 130point, Collectr and others**, open a link. Copy the search text shown there for 130point and Collectr.
2. Copy the results, paste them in, choose the source and what `$` means, then **Add pasted results**.
3. Check which results are ticked under **Market research**.

Optional: a paid PriceCharting token (`PRICECHARTING_TOKEN`) adds TAG 10 and video game guide prices automatically.

### 4. Run the rest of the photos

Select the remaining photos and identify them together. Check these by hand:

- **The two Charmanders** (`IMG_2827`/`2828` and `IMG_2829`/`2830`) are identical. Their reports are D5261062 and M8015011.
  Scan the QR code on each slab to see which cert is which, and enter it.
- **Milotic and Raikou** have no report in `photos/`, so no cert number unless you enter one.
- **Grading reports** are used for reading only and are not uploaded to eBay.

### 5. Connect eBay

Not needed for drafting; you can use **Copy listing** and paste into eBay yourself.

1. Get a **production** keyset at https://developer.ebay.com/my/keys. eBay may ask you to subscribe to, or opt out of, account
   deletion notifications before the keys work.
2. Create a RuName under User Tokens.
3. Fill in `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_RUNAME` and `EBAY_LOCATION_POSTAL` in `.env`.
4. Make sure your eBay account can sell on eBay.com and is opted in to business policies.
5. Run `.venv/bin/python ebay_lister.py auth`, sign in, and paste back the full address you land on. Do this promptly; the code expires.
6. Run `.venv/bin/python ebay_lister.py shipping-services` and confirm these codes are listed:
   `StandardShippingFromOutsideUS`, `StandardInternational`, `OtherInternational`. Change them in `.env` if not.

The app creates its own shipping, payment and no-returns policies on the first send. To use existing **eBay.com** policies instead,
set the `EBAY_..._POLICY_ID` values. A fixed shipping policy ID overrides the per-item shipping options.

### 6. Send one listing, then publish

1. Choose a low-value item and click **Send to eBay (not live)**. The result will not appear under Seller Hub drafts.
2. If eBay reports an error, note the exact message; this is the first real test of this step.
3. Check title, price, category, condition and start time in the app, then **Publish…** and confirm.
4. Open the live listing and check photos, shipping to the US and Canada, returns and item location before sending more.

## Decisions for you

- [ ] **Shipping rates.** $17.50 / $12.50 / $17.50 are your old CAD rates converted (25 / 18 / 25 at about 1.437), not current postage.
      Check actual cost, including any duties or brokerage on parcels to the US.
- [ ] **eBay International Shipping.** Sources found say it covers Canadian sellers only on eBay.ca. If you rely on it, confirm with eBay.
- [ ] **$20 starts.** Fine for the cheaper cards; the app warns when $20 is under half of market value. Consider a higher start or Buy It Now for those.
- [ ] **PriceCharting.** Worth paying for or not.

## Known limits

- The category is a default by item type and is not checked against eBay. Sealed product defaults to booster packs (183456), so change it for boxes and tins.
- Ungraded cards and opened games need a condition set before they can be sent.
- Item specifics are basic. eBay may require more for some categories and will say so when you send or publish.
- Any change after sending means sending again before you can publish.
- Live listings must be edited or ended on eBay. Deleting a draft here does not remove its offer from eBay.
- Web search is best effort. Prices it cannot tie to a page it opened are excluded.
- Everything runs on this Mac only. Drafts are in `data/drafts/`, which is not backed up or in version control (the project is not a git repository).
