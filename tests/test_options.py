from datetime import datetime, timedelta, timezone

import pytest

from lister.models import ListingOptions, Shipping
from lister.pipeline import check_options


@pytest.mark.parametrize("delta,ok", [(timedelta(minutes=5), False), (timedelta(days=2), True), (timedelta(days=22), False)])
def test_start_time(delta, ok):
    now = datetime.now(timezone.utc)
    o = ListingOptions(format="AUCTION", start_time=now + delta)
    if ok:
        check_options(o, now)
    else:
        with pytest.raises(ValueError):
            check_options(o, now)


def test_us_shipping_required():
    with pytest.raises(ValueError):
        check_options(ListingOptions(shipping=Shipping(us=False)))
