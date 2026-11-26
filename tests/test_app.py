import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import BLASTOISE, make
from lister import drafting, llm, photos, pipeline
from lister.identify import reconcile
from lister.models import IdentifiedBatch, ListingText
from lister.web import create_app

H = {"X-Lister": "1"}


@pytest.fixture
def ctx(settings, monkeypatch):
    settings.photos_dir.mkdir()
    for n in ("a.jpg", "b.jpg"):
        Image.new("RGB", (300, 300), "red").save(settings.photos_dir / n)
    pipe = pipeline.Pipeline(settings)
    item = BLASTOISE.model_copy(update={"photos": ["a.jpg"]})
    monkeypatch.setattr(pipeline, "identify", lambda *a: IdentifiedBatch(items=[item], unassigned_photos=["b.jpg"]))
    monkeypatch.setattr(drafting, "write", lambda item, m: drafting.tidy(ListingText(title="Blastoise TAG 10", subtitle="", description="d"), item))
    return TestClient(create_app(pipe), base_url="http://127.0.0.1"), pipe


def wait(c, r):
    assert r.status_code == 200, r.text
    for _ in range(100):
        j = c.get("/api/jobs/" + r.json()["job"]).json()
        if j["state"] != "running":
            return j
        time.sleep(0.02)
    raise AssertionError("job hung")


def test_photo_to_draft(ctx):
    c, _ = ctx
    j = wait(c, c.post("/api/identify", json={"photos": ["a.jpg", "b.jpg"]}, headers=H))
    did = j["result"]["drafts"][0]
    assert j["result"]["unassigned"] == ["b.jpg"]
    d = wait(c, c.post(f"/api/drafts/{did}/draft", headers=H))["result"]
    assert d["status"] == "ready" and d["category_id"] == "183454" and d["price"] is None
    assert d["text"]["title"] == "2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236 TAG 10 Gem Mint"
    opts = d["options"] | {"format": "AUCTION"}
    assert c.patch(f"/api/drafts/{did}", json={"options": opts}, headers=H).json()["price"] == 20
    r = c.patch(f"/api/drafts/{did}", json={"price_override": 60}, headers=H)
    assert r.json()["price"] == 60
    # not signed in, not pushed: must refuse to publish
    assert wait(c, c.post(f"/api/drafts/{did}/publish", json={"confirm": True, "expected_price": 60}, headers=H))["state"] == "error"
    assert wait(c, c.post(f"/api/drafts/{did}/push", headers=H))["state"] == "error"


def test_publish_guards(ctx, monkeypatch):
    c, pipe = ctx
    d = pipe.create(BLASTOISE)
    d.price_override, d.status, d.offer_id = 60, "pushed", "1"
    pipe.store.save(d)
    monkeypatch.setattr(pipe.ebay, "publish", lambda d: "L1")
    url = f"/api/drafts/{d.id}/publish"
    assert wait(c, c.post(url, json={"confirm": True, "expected_price": 50}, headers=H))["state"] == "error"
    assert wait(c, c.post(url, json={"confirm": False, "expected_price": 60}, headers=H))["state"] == "error"
    assert wait(c, c.post(url, json={"confirm": True, "expected_price": 60}, headers=H))["result"]["listing_id"] == "L1"


def test_request_guards(ctx):
    c, _ = ctx
    assert c.post("/api/identify", json={"photos": ["a.jpg"]}).status_code == 403
    assert TestClient(c.app, base_url="http://evil.example").get("/api/state").status_code == 403
    assert c.get("/api/photo/..%2f.env").status_code in (400, 404)
    assert c.get("/api/drafts/zzzz").status_code in (404, 405)
    assert c.post("/api/photos", files={"files": ("x.jpg", b"nope")}, headers=H).status_code == 400
    assert c.get("/").status_code == 200


def test_reconcile_uses_each_photo_once():
    b = IdentifiedBatch(items=[make(photos=["1", "2"]), make(photos=["2", "3", "ghost"]), make(photos=["1"], reference_photos=["4"])],
                        unassigned_photos=[])
    got = reconcile(b, ["1", "2", "3", "4"])
    assert [i.photos for i in got.items] == [["1", "2"], ["3"]] and got.unassigned_photos == ["4"]


def test_photos_lose_gps(tmp_path):
    im = Image.new("RGB", (50, 40))
    ex = im.getexif()
    ex[0x8825] = {1: "N", 2: (49.0, 1.0, 1.0)}
    ex[0x010F] = "Apple"
    im.save(tmp_path / "g.jpg", exif=ex)
    (tmp_path / "out.jpg").write_bytes(photos.jpeg_bytes(tmp_path / "g.jpg", 100))
    assert dict(Image.open(tmp_path / "out.jpg").getexif()) == {}


def test_title_keeps_grade_when_clipped():
    game = make(category="video_game", franchise="Nintendo", name="Zelda", platform="Nintendo Switch", grader="WATA", grade="9.8")
    t = drafting.tidy(ListingText(title="x" * 60 + " Some Very Long Trailing Words Here WATA 9.8", subtitle="", description=""), game)
    assert len(t.title) <= 80 and t.title.endswith("WATA 9.8")
    assert len(drafting.template(BLASTOISE).title) <= 80
    assert drafting.aspects(BLASTOISE)["Certification Number"] == ["J6556419"]


@pytest.mark.parametrize("kw, want", [
    ({}, "2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236 TAG 10 Gem Mint"),
    ({"grader": "", "grade": "", "grade_label": ""}, "2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236"),
    ({"franchise": "Pokémon", "set_name": "Pokémon GO", "grader": "PSA", "grade": "9", "grade_label": "MINT"},
     "2019 Pokemon GO Blastoise & Piplup GX 38/236 PSA 9 Mint"),
    ({"grader": "PSA", "grade_label": "GEM MT"}, "2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236 PSA 10 Gem Mint"),
    ({"grader": "BGS", "grade": "8", "grade_label": "NM-MT"}, "2019 Pokemon Cosmic Eclipse Blastoise & Piplup GX 38/236 BGS 8 NM-MT"),
])
def test_pokemon_title_format(kw, want):
    item = BLASTOISE.model_copy(update=kw)
    assert drafting.tidy(ListingText(title="anything", subtitle="", description=""), item).title == want
    assert drafting.template(item).title == want


def test_long_pokemon_title_drops_label_then_shortens_set():
    item = BLASTOISE.model_copy(update={"set_name": "Sword & Shield Evolving Skies Expansion", "name": "Umbreon VMAX Alternate Art"})
    t = drafting.pokemon_title(item)
    assert len(t) <= 80 and t.startswith("2019 Pokemon Sword") and t.endswith("Umbreon VMAX Alternate Art 38/236 TAG 10")


def test_draft_survives_missing_llm(ctx, monkeypatch):
    c, pipe = ctx

    def boom(*a):
        raise llm.LLMError("no key")
    monkeypatch.setattr(drafting, "write", boom)
    d = pipe.draft(pipe.create(BLASTOISE).id)
    assert d.status == "ready" and d.text.title and "template" in d.error


def test_any_change_after_sending_requires_resending(ctx, monkeypatch):
    c, pipe = ctx
    d = pipe.create(BLASTOISE)
    d.price_override, d.status, d.offer_id = 50, "pushed", "1"
    pipe.store.save(d)
    monkeypatch.setattr(pipe.ebay, "publish", lambda d: "L1")
    url = f"/api/drafts/{d.id}"
    r = c.patch(url, json={"price_override": 70}, headers=H)
    assert r.json()["status"] == "ready"
    assert wait(c, c.post(url + "/publish", json={"confirm": True, "expected_price": 70}, headers=H))["state"] == "error"
