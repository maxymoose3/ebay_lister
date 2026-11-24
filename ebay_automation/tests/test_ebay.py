import json
import time
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

from conftest import BLASTOISE, make
from lister.ebay import Ebay, EbayError, condition, default_category, description_html, fulfillment_payload, offer_payload
from lister.models import Draft, ListingOptions, ListingText, Pricing, Shipping


def draft(**kw):
    base = dict(id="abc123", created=datetime.now(timezone.utc), item=BLASTOISE, options=ListingOptions(), category_id="183454",
                text=ListingText(title="T", subtitle="", description="Hi\n- a <b>"),
                pricing=Pricing(list_price=104.99, start_price=20.00, auto_accept=97, auto_decline=80))
    return Draft(**(base | kw))


def test_tag_condition_descriptors():
    got = condition(BLASTOISE, "183454")
    assert got["condition"] == "LIKE_NEW"
    assert got["conditionDescriptors"] == [{"name": "27501", "values": ["2750115"]}, {"name": "27502", "values": ["275020"]},
                                           {"name": "27503", "additionalInfo": "J6556419"}]


def test_raw_card_uses_category_specific_values():
    raw = make(name="x", raw_condition="lightly_played")
    assert condition(raw, "183454")["conditionDescriptors"][0]["values"] == ["400015"]
    assert condition(raw, "261328")["conditionDescriptors"][0]["values"] == ["400011"]
    with pytest.raises(EbayError):
        condition(make(name="x"), "183454")
    assert default_category(make(franchise="NHL Hockey")) == "261328"


def test_scheduled_auction_offer(settings):
    o = ListingOptions(format="AUCTION", duration_days=5, start_time=datetime.fromisoformat("2026-11-29T18:00:00-08:00"))
    b = offer_payload(draft(options=o), {}, settings)
    assert b["listingStartDate"] == "2026-11-30T02:00:00Z" and b["listingDuration"] == "DAYS_5"
    assert b["pricingSummary"] == {"auctionStartPrice": {"value": "20.00", "currency": "USD"}}
    assert "availableQuantity" not in b and "bestOfferTerms" not in b["listingPolicies"]


def test_fixed_price_offer(settings):
    b = offer_payload(draft(), {}, settings)
    assert b["listingDuration"] == "GTC" and b["listingPolicies"]["bestOfferTerms"]["autoAcceptPrice"]["value"] == "97.00"
    low = offer_payload(draft(price_override=70), {}, settings)
    assert low["listingPolicies"]["bestOfferTerms"] == {"bestOfferEnabled": True}
    with pytest.raises(EbayError):
        offer_payload(draft(pricing=Pricing()), {}, settings)


def test_shipping_and_html(settings):
    b = fulfillment_payload(Shipping(intl=True, free_domestic=True), settings)
    dom, intl = b["shippingOptions"]
    assert dom["shippingServices"][0]["freeShipping"] and dom["shippingServices"][0]["shippingCost"]["value"] == "0.00"
    assert dom["shippingServices"][0]["shippingServiceCode"] == "StandardShippingFromOutsideUS"
    assert [x["shipToLocations"]["regionIncluded"][0]["regionName"] for x in intl["shippingServices"]] == ["CA", "Worldwide"]
    assert b["marketplaceId"] == "EBAY_US"
    assert [x["sortOrder"] for x in intl["shippingServices"]] == [1, 2] and len(b["name"]) <= 64
    assert description_html("Hi\n- a <b>") == "<p>Hi</p><ul><li>a &lt;b&gt;</li></ul>"


def test_ebay_ca_codes_are_rejected(settings):
    settings.ship_us_service = "CA_PostTrackedPacketsUSA"
    with pytest.raises(EbayError):
        fulfillment_payload(Shipping(), settings)


def test_push_never_publishes(settings):
    settings.photos_dir.mkdir()
    Image.new("RGB", (800, 800)).save(settings.photos_dir / "a.jpg")
    settings.token_file.write_text(json.dumps({"refresh_token": "r", "access_token": "t", "expires": time.time() + 999}))
    calls = []

    def handler(req: httpx.Request):
        p = req.url.path
        calls.append((req.method, p))
        if p.endswith("create_image_from_file"):
            return httpx.Response(201, headers={"Location": "https://apim.ebay.com/commerce/media/v1_beta/image/v1x"}, json={})
        if "/image/v1x" in p:
            return httpx.Response(200, json={"imageUrl": "https://i.ebayimg.com/x.jpg"})
        if "get_by_policy_name" in p:
            return httpx.Response(404, json={"errors": []})
        if "_policy" in p:
            k = p.strip("/").split("/")[-1]
            return httpx.Response(201, json={k.split("_")[0] + "PolicyId": "9"})
        if p.endswith("/offer") and req.method == "GET":
            return httpx.Response(404, json={"errors": []})
        if p.endswith("/offer"):
            assert json.loads(req.content)["listingPolicies"]["fulfillmentPolicyId"] == "9"
            return httpx.Response(201, json={"offerId": "777"})
        return httpx.Response(204)

    assert Ebay(settings, httpx.MockTransport(handler)).push(draft()) == "777"
    assert not any("publish" in p for _, p in calls)


def test_auth_state_must_match(settings):
    e = Ebay(settings)
    e.consent_url()
    with pytest.raises(EbayError):
        e.finish_consent("https://x/?code=1&state=wrong")
    assert oct(settings.state_file.stat().st_mode & 0o777) == "0o600"
