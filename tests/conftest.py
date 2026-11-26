import pytest

from lister.config import Settings
from lister.models import Identification


def make(**kw) -> Identification:
    base = dict(category="trading_card", photos=["a.jpg"], reference_photos=[], name="", franchise="Pokemon", set_name="",
                card_number="", year="", language="English", rarity="", grader="", grade="", grade_label="", cert_number="",
                raw_condition="", product_type="", platform="", region="", completeness="", game_condition="",
                condition_notes="", confidence="high", uncertainties=[])
    return Identification(**(base | kw))


BLASTOISE = make(name="Blastoise & Piplup GX", card_number="38/236", set_name="Cosmic Eclipse", year="2019",
                 rarity="Tag Team Ultra Rare", grader="TAG", grade="10", grade_label="GEM MINT", cert_number="J6556419")
CHARMANDER = make(name="Charmander", card_number="038", set_name="Mega Evolution Black Star Promos", grader="TAG",
                  grade="10", grade_label="GEM MINT", rarity="Holo")


@pytest.fixture
def settings(tmp_path):
    s = Settings(photos_dir=tmp_path / "photos", data_dir=tmp_path / "data", token_file=tmp_path / "tok.json",
                 state_file=tmp_path / "state.json")
    s.client_id, s.client_secret, s.runame, s.currency, s.marketplace = "id", "secret", "ru", "CAD", "EBAY_CA"
    s.fulfillment_policy_id = s.return_policy_id = s.payment_policy_id = ""
    s.include_subtitle, s.ebay_env, s.auction_start = False, "production", 20.0
    s.ship_ca_service, s.ship_us_service, s.ship_intl_service = "CA_PostExpeditedParcel", "CA_PostTrackedPacketsUSA", "CA_PostTrackedPacketsInternational"
    return s
