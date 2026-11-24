"""eBay: OAuth, photo upload, unpublished offers and publishing."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
from datetime import timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx

from . import photos
from .config import Settings
from .models import Draft, Identification, Shipping

BASE_SCOPE = "https://api.ebay.com/oauth/api_scope"
INSIGHTS_SCOPE = BASE_SCOPE + "/buy.marketplace.insights"
USER_SCOPES = [BASE_SCOPE, BASE_SCOPE + "/sell.inventory", BASE_SCOPE + "/sell.account"]

CCG_SINGLES, SPORTS_SINGLES, SEALED_BOOSTERS, VIDEO_GAMES = "183454", "261328", "183456", "139973"
CARD_CATEGORIES = {CCG_SINGLES, SPORTS_SINGLES, "183050"}
_SPORTS = {"nhl", "hockey", "nba", "basketball", "nfl", "football", "mlb", "baseball", "soccer", "ufc", "wwe", "f1"}

# developer.ebay.com: condition descriptor IDs for trading cards
GRADER_IDS = {"PSA": "275010", "BCCG": "275011", "BVG": "275012", "BGS": "275013", "CSG": "275014", "CGC": "275015",
              "SGC": "275016", "KSA": "275017", "GMA": "275018", "HGA": "275019", "ISA": "2750110", "PCA": "2750111",
              "GSG": "2750112", "PGS": "2750113", "MNT": "2750114", "TAG": "2750115", "RARE": "2750116", "RCG": "2750117",
              "PCG": "2750118", "ACE": "2750119", "CGA": "2750120", "TCG": "2750121", "ARK": "2750122"}
OTHER_GRADER = "2750123"
GRADE_IDS = {"10": "275020", "9.5": "275021", "9": "275022", "8.5": "275023", "8": "275024", "7.5": "275025", "7": "275026",
             "6.5": "275027", "6": "275028", "5.5": "275029", "5": "2750210", "4.5": "2750211", "4": "2750212",
             "3.5": "2750213", "3": "2750214", "2.5": "2750215", "2": "2750216", "1.5": "2750217", "1": "2750218"}
RAW_CCG = {"near_mint": "400010", "lightly_played": "400015", "moderately_played": "400016", "heavily_played": "400017"}
RAW_SPORTS = {"near_mint": "400010", "lightly_played": "400011", "moderately_played": "400012", "heavily_played": "400013"}
GAME_CONDITION = {"like_new": "LIKE_NEW", "very_good": "USED_VERY_GOOD", "good": "USED_GOOD", "acceptable": "USED_ACCEPTABLE"}


class EbayError(RuntimeError):
    pass


def default_category(item: Identification) -> str:
    if item.category == "video_game":
        return VIDEO_GAMES
    if item.category == "sealed_product":
        return SEALED_BOOSTERS
    words = set(item.franchise.lower().replace(":", " ").split())
    return SPORTS_SINGLES if words & _SPORTS else CCG_SINGLES


def condition(item: Identification, category_id: str) -> dict:
    if item.category == "trading_card":
        if item.graded:
            grade = GRADE_IDS.get(item.grade)
            if not grade:
                raise EbayError(f"eBay has no grade '{item.grade}'.")
            ds = [{"name": "27501", "values": [GRADER_IDS.get(item.grader.upper(), OTHER_GRADER)]},
                  {"name": "27502", "values": [grade]}]
            if item.cert_number:
                ds.append({"name": "27503", "additionalInfo": item.cert_number[:30]})
            return {"condition": "LIKE_NEW", "conditionDescriptors": ds}
        table = RAW_CCG if category_id == CCG_SINGLES else RAW_SPORTS
        if item.raw_condition not in table:
            raise EbayError("Set the card's condition before sending it to eBay.")
        return {"condition": "USED_VERY_GOOD", "conditionDescriptors": [{"name": "40001", "values": [table[item.raw_condition]]}]}
    if item.category == "sealed_product" or item.completeness == "sealed":
        return {"condition": "NEW"}
    if item.game_condition not in GAME_CONDITION:
        raise EbayError("Set the game's condition before sending it to eBay.")
    out = {"condition": GAME_CONDITION[item.game_condition]}
    if item.condition_notes and out["condition"] != "LIKE_NEW":
        out["conditionDescription"] = item.condition_notes[:1000]
    return out


def description_html(text: str) -> str:
    out, bullets = [], []

    def flush():
        if bullets:
            out.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("- ", "• ")):
            bullets.append(html.escape(line[2:]))
        elif line:
            flush()
            out.append(f"<p>{html.escape(line)}</p>")
    flush()
    return "".join(out)


def sku(d: Draft) -> str:
    return f"LST-{d.id}"


def inventory_payload(d: Draft, image_urls: list[str], s: Settings) -> dict:
    if not d.text:
        raise EbayError("The draft has no title or description yet.")
    product = {"title": d.text.title, "description": description_html(d.text.description), "aspects": d.aspects,
               "imageUrls": image_urls}
    if s.include_subtitle and d.text.subtitle:
        product["subtitle"] = d.text.subtitle
    return {"availability": {"shipToLocationAvailability": {"quantity": 1}}, "product": product,
            **condition(d.item, d.category_id)}


def offer_payload(d: Draft, policies: dict[str, str], s: Settings) -> dict:
    price = d.price
    if not price or price <= 0:
        raise EbayError("Set a price first.")
    amount = {"value": f"{price:.2f}", "currency": s.currency}
    o = d.options
    body = {"sku": sku(d), "marketplaceId": s.marketplace, "format": o.format, "categoryId": d.category_id,
            "merchantLocationKey": s.location_key, "listingDescription": description_html(d.text.description),
            "listingPolicies": dict(policies)}
    if o.format == "AUCTION":
        body |= {"listingDuration": f"DAYS_{o.duration_days}", "pricingSummary": {"auctionStartPrice": amount}}
    else:
        body |= {"listingDuration": "GTC", "availableQuantity": 1, "pricingSummary": {"price": amount}}
        if o.best_offer:
            terms: dict = {"bestOfferEnabled": True}
            # The thresholds were worked out for the suggested price; skip them when they no longer fit.
            if d.pricing.auto_accept and d.pricing.auto_accept < price:
                terms["autoAcceptPrice"] = {"value": f"{d.pricing.auto_accept:.2f}", "currency": s.currency}
            if d.pricing.auto_decline and d.pricing.auto_decline < price:
                terms["autoDeclinePrice"] = {"value": f"{d.pricing.auto_decline:.2f}", "currency": s.currency}
            body["listingPolicies"]["bestOfferTerms"] = terms
    if o.start_time:
        body["listingStartDate"] = o.start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return body


def fulfillment_payload(sh: Shipping, s: Settings) -> dict:
    def money(v: float) -> dict:
        return {"value": f"{v:.2f}", "currency": s.currency}

    for on, code in ((sh.us, s.ship_us_service), (sh.ca, s.ship_ca_service), (sh.intl, s.ship_intl_service)):
        if on and code.startswith("CA_"):
            raise EbayError(f"{code} is an eBay.ca shipping service. Use an eBay.com code in .env (see .env.example).")
    options = []
    if sh.us:
        svc = {"sortOrder": 1, "shippingServiceCode": s.ship_us_service,
               "freeShipping": sh.free_domestic, "shippingCost": money(0 if sh.free_domestic else sh.us_cost)}
        options.append({"optionType": "DOMESTIC", "costType": "FLAT_RATE", "shippingServices": [svc]})
    abroad = []
    if sh.ca:
        abroad.append({"shippingServiceCode": s.ship_ca_service, "shippingCost": money(sh.ca_cost),
                       "shipToLocations": {"regionIncluded": [{"regionName": "CA"}]}})
    if sh.intl:
        abroad.append({"shippingServiceCode": s.ship_intl_service, "shippingCost": money(sh.intl_cost),
                       "shipToLocations": {"regionIncluded": [{"regionName": "Worldwide"}]}})
    if abroad:
        options.append({"optionType": "INTERNATIONAL", "costType": "FLAT_RATE",
                        "shippingServices": [{"sortOrder": i, **x} for i, x in enumerate(abroad, 1)]})
    body = {"marketplaceId": s.marketplace, "categoryTypes": [{"name": "ALL_EXCLUDING_MOTORS_VEHICLES"}],
            "handlingTime": {"unit": "DAY", "value": sh.handling_days}, "localPickup": sh.local_pickup,
            "shippingOptions": options}
    key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    return {"name": f"Lister shipping {key}", **body}


class Ebay:
    def __init__(self, s: Settings, transport: httpx.BaseTransport | None = None):
        self.s = s
        self.http = httpx.Client(timeout=60, transport=transport)
        self._app: tuple[str, float] = ("", 0)

    # --- auth -----------------------------------------------------------
    def _basic(self) -> dict:
        if not self.s.has_ebay_keys:
            raise EbayError("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env.")
        raw = f"{self.s.client_id}:{self.s.client_secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}

    def _token(self, data: dict) -> dict:
        r = self.http.post(f"{self.s.api_base}/identity/v1/oauth2/token", headers=self._basic(), data=data)
        return self._json(r, "sign-in")

    def app_token(self) -> str:
        tok, exp = self._app
        if time.time() < exp - 60:
            return tok
        scope = BASE_SCOPE + (f" {INSIGHTS_SCOPE}" if self.s.insights else "")
        d = self._token({"grant_type": "client_credentials", "scope": scope})
        self._app = (d["access_token"], time.time() + d["expires_in"])
        return d["access_token"]

    def consent_url(self) -> str:
        if not (self.s.has_ebay_keys and self.s.runame):
            raise EbayError("Set EBAY_CLIENT_ID, EBAY_CLIENT_SECRET and EBAY_RUNAME in .env.")
        state = secrets.token_urlsafe(16)
        self._save_state({"oauth_state": state})
        return (f"{self.s.auth_base}/oauth2/authorize?client_id={quote(self.s.client_id)}&response_type=code"
                f"&redirect_uri={quote(self.s.runame)}&scope={quote(' '.join(USER_SCOPES))}&state={state}")

    def finish_consent(self, pasted_url: str) -> None:
        q = parse_qs(urlparse(pasted_url.strip()).query)
        if "code" not in q:
            raise EbayError("That address has no authorization code. Paste the full address eBay sent you to.")
        if q.get("state", [""])[0] != self._state().get("oauth_state"):
            raise EbayError("Sign-in did not match this session. Run auth again.")
        d = self._token({"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": self.s.runame})
        self._write_private(self.s.token_file, {"refresh_token": d["refresh_token"], "access_token": d["access_token"],
                                                "expires": time.time() + d["expires_in"]})

    def user_token(self) -> str:
        if not self.s.token_file.exists():
            raise EbayError("Not signed in to eBay. Run: .venv/bin/python ebay_lister.py auth")
        t = json.loads(self.s.token_file.read_text())
        if time.time() < t.get("expires", 0) - 60:
            return t["access_token"]
        d = self._token({"grant_type": "refresh_token", "refresh_token": t["refresh_token"], "scope": " ".join(USER_SCOPES)})
        t |= {"access_token": d["access_token"], "expires": time.time() + d["expires_in"]}
        self._write_private(self.s.token_file, t)
        return t["access_token"]

    # --- helpers --------------------------------------------------------
    @staticmethod
    def _write_private(path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)

    def _state(self) -> dict:
        return json.loads(self.s.state_file.read_text()) if self.s.state_file.exists() else {}

    def _save_state(self, patch: dict) -> None:
        self._write_private(self.s.state_file, self._state() | patch)

    @staticmethod
    def _json(r: httpx.Response, what: str) -> dict:
        if r.is_success:
            return r.json() if r.content else {}
        try:
            body = r.json()
            errs = body.get("errors") or []
            msg = "; ".join(e.get("longMessage") or e.get("message", "") for e in errs) or body.get("error_description", "")
        except ValueError:
            msg = ""
        raise EbayError(f"eBay {what} failed ({r.status_code}): {msg or r.text[:200]}")

    def call(self, method: str, path: str, what: str, *, ok404: bool = False, **kw):
        headers = {"Authorization": f"Bearer {self.user_token()}", "Content-Language": "en-US",
                   "Accept-Language": "en-US"}
        r = self.http.request(method, self.s.api_base + path, headers=headers, **kw)
        if ok404 and r.status_code == 404:
            return None
        return self._json(r, what)

    # --- setup ----------------------------------------------------------
    def ensure_location(self) -> None:
        path = f"/sell/inventory/v1/location/{quote(self.s.location_key)}"
        if self.call("GET", path, "location lookup", ok404=True) is not None:
            return
        address = {"city": self.s.location_city, "stateOrProvince": self.s.location_province, "country": "CA"}
        if self.s.location_postal:
            address["postalCode"] = self.s.location_postal
        self.call("POST", path, "location setup", json={"location": {"address": address}, "name": self.s.location_key,
                                                        "merchantLocationStatus": "ENABLED", "locationTypes": ["WAREHOUSE"]})

    def _policy(self, kind: str, id_field: str, payload: dict) -> str:
        """Reuse a policy of the same name, else create it."""
        found = self.call("GET", f"/sell/account/v1/{kind}/get_by_policy_name", f"{kind} lookup", ok404=True,
                          params={"marketplace_id": self.s.marketplace, "name": payload["name"]})
        if found and found.get(id_field):
            return found[id_field]
        return self.call("POST", f"/sell/account/v1/{kind}/", f"{kind} setup", json=payload)[id_field]

    def policies(self, sh: Shipping) -> dict[str, str]:
        s, cat = self.s, [{"name": "ALL_EXCLUDING_MOTORS_VEHICLES"}]
        return {
            "fulfillmentPolicyId": s.fulfillment_policy_id
            or self._policy("fulfillment_policy", "fulfillmentPolicyId", fulfillment_payload(sh, s)),
            "paymentPolicyId": s.payment_policy_id
            or self._policy("payment_policy", "paymentPolicyId", {"name": "Lister payment", "marketplaceId": s.marketplace,
                                                                  "categoryTypes": cat}),
            "returnPolicyId": s.return_policy_id
            or self._policy("return_policy", "returnPolicyId", {"name": "Lister no returns", "marketplaceId": s.marketplace,
                                                                "categoryTypes": cat, "returnsAccepted": False}),
        }

    def shipping_services(self) -> list[dict]:
        r = self.http.get(f"{self.s.api_base}/sell/metadata/v1/shipping/marketplace/{self.s.marketplace}/get_shipping_services",
                          headers={"Authorization": f"Bearer {self.user_token()}"})
        return self._json(r, "shipping service lookup").get("shippingServices", [])

    def upload(self, path: Path) -> str:
        r = self.http.post(f"{self.s.media_base}/commerce/media/v1_beta/image/create_image_from_file",
                           headers={"Authorization": f"Bearer {self.user_token()}"},
                           files={"image": (path.stem + ".jpg", photos.jpeg_bytes(path, photos.EBAY_MAX, 90), "image/jpeg")})
        body = self._json(r, "photo upload")
        if body.get("imageUrl"):
            return body["imageUrl"]
        image_id = r.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
        g = self.http.get(f"{self.s.media_base}/commerce/media/v1_beta/image/{quote(image_id)}",
                          headers={"Authorization": f"Bearer {self.user_token()}"})
        return self._json(g, "photo lookup")["imageUrl"]

    # --- listing --------------------------------------------------------
    def push(self, d: Draft) -> str:
        """Create or update an UNPUBLISHED offer. Nothing goes live. Returns the offer id."""
        if d.status == "published":
            raise EbayError("This draft is already live.")
        if not d.category_id:
            raise EbayError("Choose an eBay category first.")
        condition(d.item, d.category_id)
        offer_payload(d, {}, self.s)  # fail on missing price/condition before uploading anything
        self.ensure_location()
        pol = self.policies(d.options.shipping)
        urls = [self.upload(photos.resolve(self.s.photos_dir, n)) for n in d.item.photos[:24]]
        self.call("PUT", f"/sell/inventory/v1/inventory_item/{sku(d)}", "item save", json=inventory_payload(d, urls, self.s))
        body = offer_payload(d, pol, self.s)
        existing = self.call("GET", "/sell/inventory/v1/offer", "offer lookup", ok404=True, params={"sku": sku(d)})
        for o in (existing or {}).get("offers", []):
            if o.get("format") == body["format"]:
                self.call("PUT", f"/sell/inventory/v1/offer/{o['offerId']}", "offer update", json=body)
                return o["offerId"]
            if o.get("status") == "UNPUBLISHED":  # format was switched since the last push
                self.call("DELETE", f"/sell/inventory/v1/offer/{o['offerId']}", "old offer removal")
        return self.call("POST", "/sell/inventory/v1/offer", "offer save", json=body)["offerId"]

    def publish(self, d: Draft) -> str:
        """Make the offer live (or scheduled). Only called after explicit confirmation."""
        if not d.offer_id:
            raise EbayError("Send the draft to eBay first.")
        return self.call("POST", f"/sell/inventory/v1/offer/{d.offer_id}/publish", "publish")["listingId"]
