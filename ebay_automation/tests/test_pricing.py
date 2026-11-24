from datetime import date, datetime, timedelta, timezone

import pytest

from lister.models import Comp, ListingOptions, Shipping
from lister.pipeline import check_options
from lister.pricing import charm, price, weighted_median

T = date(2026, 11, 23)


def c(p, kind="sold", days=5, **k):
    return Comp(source="x", kind=kind, title="t", price=p, price_local=p, currency="USD",
                date=(T - timedelta(days=days)).isoformat() if kind == "sold" else None, **k)


def test_sold_drive_price(settings):
    p = price([c(100), c(102), c(98), c(101), c(99), c(100), c(900)], ListingOptions(), settings, T)
    assert p.confidence == "high" and 99 <= p.market_value <= 101 and "outlier" in p.basis
    assert p.list_price == 104.99 and p.auto_decline < p.auto_accept < p.list_price and p.start_price == 20


def test_recent_sales_weigh_more(settings):
    p = price([c(50, days=200), c(50, days=210), c(80, days=2), c(82, days=3)], ListingOptions(), settings, T)
    assert p.market_value >= 80


def test_excluded_and_unconverted_ignored(settings):
    bad = c(1)
    bad.price_local = None
    assert price([c(5, included=False), bad], ListingOptions(), settings, T).confidence == "none"


def test_no_data_gives_no_price(settings):
    p = price([], ListingOptions(), settings, T)
    assert p.list_price is None and p.warnings


def test_active_only_is_low_confidence_and_below_asking(settings):
    p = price([c(x, "active") for x in (100, 110, 120, 130)], ListingOptions(), settings, T)
    assert p.confidence == "low" and p.market_value < 110


def test_live_competition_caps_bin(settings):
    p = price([c(100)] * 6 + [c(95, "active")] * 3, ListingOptions(), settings, T)
    assert p.list_price <= 95


def test_free_shipping_moves_into_price(settings):
    comps = [c(100)] * 6
    a = price(comps, ListingOptions(), settings, T)
    b = price(comps, ListingOptions(shipping=Shipping(free_domestic=True, us_cost=20)), settings, T)
    assert b.list_price == a.list_price + 20


def test_math():
    assert charm(19.6) == 19.99 and charm(0.2) == 0.99 and charm(123) == 124.99
    assert weighted_median([(1, 1), (2, 1), (3, 1)]) == 2 and weighted_median([(1, 1), (3, 1)]) == 2


@pytest.mark.parametrize("delta,ok", [(timedelta(minutes=5), False), (timedelta(days=2), True), (timedelta(days=22), False)])
def test_start_time(delta, ok):
    now = datetime.now(timezone.utc)
    o = ListingOptions(format="AUCTION", start_time=now + delta)
    if ok:
        check_options(o, now)
    else:
        with pytest.raises(ValueError):
            check_options(o, now)


@pytest.mark.parametrize("value,text", [(15, "no bids"), (30, None), (100, "under half")])
def test_auction_starts_at_20(settings, value, text):
    o = ListingOptions(format="AUCTION", shipping=Shipping(free_domestic=True))
    p = price([c(value)] * 6, o, settings, T)
    assert p.start_price == 20
    assert any(text in w for w in p.warnings) if text else not p.warnings


def test_auction_without_comps_still_starts_at_20(settings):
    p = price([], ListingOptions(format="AUCTION"), settings, T)
    assert p.start_price == 20 and p.warnings


def test_us_shipping_required():
    with pytest.raises(ValueError):
        check_options(ListingOptions(shipping=Shipping(us=False)))
