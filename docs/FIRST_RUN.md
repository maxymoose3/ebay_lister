# First run

Status as of November 23, 2026. Run every command from the project folder.

**Update, November 26, 2026 (later):** listings moved from eBay.com (USD) to eBay.ca (CAD) so eBay International
Shipping can be used. Sections below are updated to match.

**Update, November 26, 2026:** market research and automatic pricing were removed. You enter prices yourself, and Pokemon cards
get a fixed title format (see README). Sections below are updated to match; the test status table is as of November 23.

## What is built

A local app (web page and command line) that turns photos into eBay.ca listing drafts.

| Stage | What it does |
|---|---|
| Photos | Reads JPG, PNG, WebP and HEIC. Removes GPS and other metadata before a photo leaves this Mac. |
| Identify | Claude groups photos into items and reads name, set, number, grade, cert, platform and so on. You can correct any field. |
| Draft | Title (80 characters max; fixed format for Pokemon cards), concise description, item specifics, eBay condition and category. You enter the price. |
| eBay | Uploads photos and creates an **unpublished** offer. Publishing is a separate step you confirm for each listing. |

### Settings in place

- eBay.ca (`EBAY_CA`), CAD, items sent from Squamish, BC.
- eBay International Shipping (eIS) for buyers outside Canada. This is an account setting, not part of each listing (see step 4).
- No returns. Times are America/Vancouver.
- Auctions start at $20 unless you enter another start price. You enter Buy It Now prices.
- Flat shipping (CAD): Canada $18 (on). US $25 and International $25 are off, so eIS handles those buyers.

### What has and has not been tested

| | Status |
|---|---|
| Automated tests | 22 pass, with Claude and eBay simulated (after the November 26 change) |
| Web page | Rendered at desktop and phone width; not clicked through by hand |
| Claude: identification, descriptions | **Never run live** (no API key yet) |
| eBay: sign-in, photo upload, offers, publishing | **Never run live** (no keys yet) |

## Next steps

### 1. Set up the Claude key (required)

1. Create a key at https://platform.claude.com/settings/keys.
2. Create a file named `.env` in the project folder.
3. Add the line `ANTHROPIC_API_KEY=your-key` to `.env`. This is billed per use; cost per item has not been measured, so check usage after the first few.

The virtual environment already exists in `.venv`. Restart the app whenever `.env` changes.

### 2. Try one card

```sh
.venv/bin/python ebay_lister.py serve
```

1. Open http://127.0.0.1:8765 and select `IMG_2825.jpg`, `IMG_2826.jpg` and `J6556419.jpg`.
2. Choose **Auction** or **Buy It Now**, check shipping, and click **Identify items**.
3. Expect: Blastoise & Piplup GX, 38/236, Cosmic Eclipse, TAG 10 Gem Mint, cert J6556419. Correct anything wrong under **Item details and options**.
4. Click **Write draft**, then enter a price and click **Save**.

### 3. Run the rest of the photos

Select the remaining photos and identify them together. Check these by hand:

- **The two Charmanders** (`IMG_2827`/`2828` and `IMG_2829`/`2830`) are identical. Their reports are D5261062 and M8015011.
  Scan the QR code on each slab to see which cert is which, and enter it.
- **Milotic and Raikou** have no report in `photos/`, so no cert number unless you enter one.
- **Grading reports** are used for reading only and are not uploaded to eBay.

### 4. Connect eBay

Not needed for drafting; you can use **Copy listing** and paste into eBay yourself.

1. Get a **production** keyset at https://developer.ebay.com/my/keys. eBay may ask you to subscribe to, or opt out of, account
   deletion notifications before the keys work.
2. Create a RuName under User Tokens.
3. Fill in `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_RUNAME` and `EBAY_LOCATION_POSTAL` in `.env`.
4. Make sure your eBay account is opted in to business policies, and check eIS under My eBay > Account > Shipping preferences.
   eBay enrols eligible eBay.ca sellers automatically; if it shows as opted out, opt back in there.
5. Run `.venv/bin/python ebay_lister.py auth`, sign in, and paste back the full address you land on. Do this promptly; the code expires.
6. Run `.venv/bin/python ebay_lister.py shipping-services` and confirm these codes are listed:
   `CA_PostExpeditedParcel`, `CA_PostTrackedPacketsUSA`, `CA_PostTrackedPacketsInternational`. Change them in `.env` if not
   (`EBAY_SHIP_CA_SERVICE`, `EBAY_SHIP_US_SERVICE`, `EBAY_SHIP_INTL_SERVICE`; eBay.ca codes start with `CA_`).

The app creates its own shipping, payment and no-returns policies on the first send. To use existing **eBay.ca** policies instead,
set the `EBAY_..._POLICY_ID` values. A fixed shipping policy ID overrides the per-item shipping options.

### 5. Send one listing, then publish

1. Choose a low-value item and click **Send to eBay (not live)**. The result will not appear under Seller Hub drafts.
2. If eBay reports an error, note the exact message; this is the first real test of this step.
3. Check title, price, category, condition and start time in the app, then **Publish…** and confirm.
4. Open the live listing and check photos, shipping within Canada, that a US buyer sees eIS shipping, returns and item location before sending more.

## Decisions for you

- [ ] **Shipping rates.** CAD 18 / 25 / 25 are your old rates, not current postage. With eIS, the Canada rate also covers
      sending to the Mississauga hub.
- [ ] **eBay International Shipping.** Confirm your account is enrolled (step 4). eIS covers eBay.ca listings only.
- [ ] **Categories and card conditions on eBay.ca.** Category IDs and card condition descriptors were written for eBay.com
      and have not been checked against eBay.ca. The first send will show whether eBay.ca accepts them.
- [ ] **$20 starts.** Now CAD 20, which is lower than the old USD 20. Fine for the cheaper cards. Consider a higher start or Buy It Now for valuable ones.

## Known limits

- The category is a default by item type and is not checked against eBay. Sealed product defaults to booster packs (183456), so change it for boxes and tins.
- Ungraded cards and opened games need a condition set before they can be sent.
- Item specifics are basic. eBay may require more for some categories and will say so when you send or publish.
- Any change after sending means sending again before you can publish.
- Live listings must be edited or ended on eBay. Deleting a draft here does not remove its offer from eBay.
- Everything runs on this Mac only. Drafts are in `data/drafts/`, which is not backed up or in version control (the project is not a git repository).
