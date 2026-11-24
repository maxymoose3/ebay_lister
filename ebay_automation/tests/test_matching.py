import pytest

from conftest import BLASTOISE, CHARMANDER, make
from lister.research.links import query
from lister.research.matching import bare_number, grades_in, match
from lister.research.sources import pricecharting_key


@pytest.mark.parametrize("title,ok", [
    ("Pokemon Blastoise & Piplup GX 38/236 Cosmic Eclipse TAG 10 Gem Mint", True),
    ("2019 Blastoise and Piplup GX Cosmic Eclipse #38 TAG GEM MINT 10", True),
    # "TAG TEAM" is the card type, not the grader
    ("Blastoise & Piplup GX Tag Team 38/236 Cosmic Eclipse PSA 10", False),
    ("Blastoise & Piplup GX Tag Team 10 card 38/236 Cosmic Eclipse", False),
    ("Blastoise & Piplup GX 38/236 Cosmic Eclipse TAG 9", False),
    ("Blastoise & Piplup GX 38/236 TAG 10 Pristine", False),
    ("Blastoise & Piplup GX 38/236 Cosmic Eclipse NM", False),
    ("Blastoise & Piplup GX 215/236 Cosmic Eclipse TAG 10", False),
    ("Blastoise GX 38/236 TAG 10", False),
    ("Blastoise & Piplup GX 38/236 Japanese TAG 10", False),
    ("Blastoise & Piplup GX 38/236 TAG 10 custom proxy", False),
    ("TAG 10 PSA 9 Blastoise & Piplup GX 38/236", False),
])
def test_graded_card(title, ok):
    assert match(BLASTOISE, title)[0] is ok, match(BLASTOISE, title)


def test_number_or_set_is_needed():
    assert not match(CHARMANDER, "Charmander TAG 10")[0]
    assert match(CHARMANDER, "Charmander #038 TAG 10")[0]
    assert match(CHARMANDER, "Charmander MEP 038 TAG 10 First Partner")[0]
    assert not match(CHARMANDER, "Charmander 4/102 TAG 10")[0]


def test_raw_card_excludes_slabs_and_reverse():
    raw = make(name="Raikou", card_number="50/185", set_name="Vivid Voltage", rarity="Amazing Rare")
    assert match(raw, "Raikou 050/185 Amazing Rare Vivid Voltage NM")[0]
    assert not match(raw, "Raikou 050/185 Vivid Voltage PSA 10")[0]
    assert not match(raw, "Raikou 050/185 Vivid Voltage Reverse Holo")[0]


def test_sealed():
    etb = make(category="sealed_product", name="Evolving Skies Elite Trainer Box", set_name="Evolving Skies", product_type="Elite Trainer Box")
    assert match(etb, "Pokemon Evolving Skies Elite Trainer Box Sealed")[0]
    assert not match(etb, "Pokemon Evolving Skies Booster Box Elite Trainer Box")[0]
    assert not match(etb, "Evolving Skies Elite Trainer Box EMPTY")[0]
    assert not match(etb, "Evolving Skies Elite Trainer Box x4")[0]


def test_games():
    g = make(category="video_game", name="Pokemon Emerald", platform="Game Boy Advance", completeness="loose")
    assert match(g, "Pokemon Emerald GBA Authentic Cartridge Only")[0]
    assert not match(g, "Pokemon Emerald GBA CIB Complete")[0]
    assert not match(g, "Pokemon Emerald GBA reproduction")[0]
    assert not match(g, "Pokemon Emerald Nintendo DS cartridge only")[0]


def test_helpers():
    assert bare_number("038") == bare_number("38/236") == "38" and bare_number("TG02/TG30") == "tg2"
    assert grades_in("Beckett 9.5") == {("BGS", "9.5")} and grades_in("PSA 100") == set()
    assert query(BLASTOISE) == "Blastoise Piplup GX 38/236 TAG 10"
    assert pricecharting_key(BLASTOISE) == "condition-21-price"
    assert pricecharting_key(make(grader="PSA", grade="10")) == "manual-only-price"
    assert pricecharting_key(make(grader="TAG", grade="10", grade_label="PRISTINE")) is None
