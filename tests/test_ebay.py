import json
import time
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

from conftest import BLASTOISE, make
from lister.ebay import Ebay, EbayError, condition, default_category, description_html, fulfillment_payload, offer_payload
from lister.models import Draft, ListingOptions, ListingText, Shipping


def draft(**kw):
    base = dict(id="abc123", created=datetime.now(timezone.utc), item=BLASTOISE, options=ListingOptions(), category_id="183454",
                text=ListingText(title="T", subtitle="", description="Hi\n- a <b>"),
                price_override=104.99, default_start=20.00)
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
    b = offer_payload(draft(options=o, price_override=None), {}, settings)
    assert b["listingStartDate"] == "2026-11-30T02:00:00Z" and b["listingDuration"] == "DAYS_5"
    assert b["pricingSummary"] == {"auctionStartPrice": {"value": "20.00", "currency": "CAD"}}
    assert "availableQuantity" not in b and "bestOfferTerms" not in b["listingPolicies"]


def test_fixed_price_offer(settings):
    b = offer_payload(draft(), {}, settings)
    assert b["listingDuration"] == "GTC" and b["pricingSummary"]["price"]["value"] == "104.99"
    assert b["listingPolicies"]["bestOfferTerms"] == {"bestOfferEnabled": True}
    with pytest.raises(EbayError):  # Buy It Now has no default price
        offer_payload(draft(price_override=None), {}, settings)


def test_shipping_is_not_added_to_price(settings):
    o = ListingOptions(shipping=Shipping(ca_cost=18))
    assert offer_payload(draft(options=o, price_override=100), {}, settings)["pricingSummary"]["price"]["value"] == "100.00"
    a = offer_payload(draft(options=o.model_copy(update={"format": "AUCTION"}), price_override=None), {}, settings)
    assert a["pricingSummary"]["auctionStartPrice"]["value"] == "20.00"


def test_shipping_and_html(settings):
    b = fulfillment_payload(Shipping(us=True, intl=True), settings)
    dom, intl = b["shippingOptions"]
    assert not dom["shippingServices"][0]["freeShipping"] and dom["shippingServices"][0]["shippingCost"] == {"value": "18.00", "currency": "CAD"}
    assert dom["shippingServices"][0]["shippingServiceCode"] == "CA_PostExpeditedParcel"
    assert [x["shipToLocations"]["regionIncluded"][0]["regionName"] for x in intl["shippingServices"]] == ["US", "Worldwide"]
    assert b["marketplaceId"] == "EBAY_CA"
    assert [x["sortOrder"] for x in intl["shippingServices"]] == [1, 2] and len(b["name"]) <= 64
    assert description_html("Hi\n- a <b>") == "<p>Hi</p><ul><li>a &lt;b&gt;</li></ul>"


def test_default_shipping_is_canada_only_for_eis(settings):
    b = fulfillment_payload(Shipping(), settings)
    assert [o["optionType"] for o in b["shippingOptions"]] == ["DOMESTIC"]


def test_ebay_com_codes_are_rejected(settings):
    settings.ship_ca_service = "StandardInternational"
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
