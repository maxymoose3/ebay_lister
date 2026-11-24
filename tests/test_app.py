import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import BLASTOISE, make
from lister import drafting, llm, photos, pipeline
from lister.identify import reconcile
from lister.models import Comp, IdentifiedBatch, ListingText
from lister.research import pasted, run, websearch
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
    title = "Blastoise & Piplup GX 38/236 Cosmic Eclipse TAG 10"
    monkeypatch.setattr(run, "SOURCES", [("fake", lambda *a: [Comp(source="fake", kind="sold", title=title, price=50 + i, currency="USD",
                                                                   url=f"https://e/{i}") for i in range(4)]
                                          + [Comp(source="fake", kind="sold", title="other", price=5, currency="USD")])])
    monkeypatch.setattr(drafting, "write", lambda item, m: ListingText(title="Blastoise TAG 10", subtitle="", description="d"))
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
    d = wait(c, c.post(f"/api/drafts/{did}/research", headers=H))["result"]
    assert d["status"] == "ready" and 50 <= d["pricing"]["market_value"] <= 53 and d["category_id"] == "183454"
    assert sum(x["included"] for x in d["comps"]) == 4
    cid = next(x["id"] for x in d["comps"] if x["included"])
    assert c.post(f"/api/drafts/{did}/comps/{cid}", json={"included": False}, headers=H).json()["comps"]
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


def test_manual_comp(ctx):
    c, pipe = ctx
    d = pipe.create(BLASTOISE)
    r = c.post(f"/api/drafts/{d.id}/comps", json={"price": 40, "currency": "USD"}, headers=H).json()
    assert r["comps"][0]["included"] and r["pricing"]["market_value"] == 40


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


def test_web_comps_need_a_page_that_was_seen():
    row = dict(kind="sold", title="t", price=5, currency="USD", date=None)
    got = websearch.to_comps([row | {"url": "https://www.ebay.com/itm/1"}, row | {"url": "https://www.ebay.com/itm/2"},
                              row | {"url": "https://notebay.com/itm/1"}, {"bad": 1}],
                             {"https://ebay.com/itm/1?x=1", "https://notebay.com/itm/1"})
    assert [c.included for c in got] == [True, False, False]


def test_pasted_prices_must_be_in_the_text(monkeypatch):
    rows = pasted.Rows(rows=[pasted.Row(kind="sold", title="a", price=1234.5, currency="usd", date=None),
                             pasted.Row(kind="sold", title="b", price=99, currency="USD", date=None)])
    monkeypatch.setattr(llm, "structured", lambda *a, **k: rows)
    got = pasted.parse("Sold $1,234.50", "130point", "USD", "m")
    assert [(c.price, c.currency) for c in got] == [(1234.5, "USD")]


def test_title_keeps_grade_when_clipped():
    t = drafting.tidy(ListingText(title="x" * 60 + " Some Very Long Trailing Words Here TAG 10", subtitle="", description=""), BLASTOISE)
    assert len(t.title) <= 80 and t.title.endswith("TAG 10")
    assert len(drafting.template(BLASTOISE).title) <= 80
    assert drafting.aspects(BLASTOISE)["Certification Number"] == ["J6556419"]


def test_research_survives_missing_claude(ctx, monkeypatch):
    c, pipe = ctx

    def boom(*a):
        raise llm.LLMError("no key")
    monkeypatch.setattr(drafting, "write", boom)
    d = pipe.research(pipe.create(BLASTOISE).id)
    assert d.status == "ready" and d.text.title and "template" in d.error


@pytest.mark.parametrize("change", ["comp", "toggle", "patch"])
def test_any_change_after_sending_requires_resending(ctx, monkeypatch, change):
    c, pipe = ctx
    d = pipe.create(BLASTOISE)
    d = pipe.add_manual(d.id, Comp(source="x (pasted)", kind="sold", title="Blastoise & Piplup GX 38/236 TAG 10", price=50, currency="USD"))
    d.status, d.offer_id = "pushed", "1"
    pipe.store.save(d)
    monkeypatch.setattr(pipe.ebay, "publish", lambda d: "L1")
    url = f"/api/drafts/{d.id}"
    if change == "comp":
        r = c.post(url + "/comps", json={"price": 90}, headers=H)
    elif change == "toggle":
        r = c.post(f"{url}/comps/{d.comps[0].id}", json={"included": False}, headers=H)
    else:
        r = c.patch(url, json={"price_override": 70}, headers=H)
    assert r.json()["status"] == "ready"
    price = r.json()["price"] or 1
    assert wait(c, c.post(url + "/publish", json={"confirm": True, "expected_price": price}, headers=H))["state"] == "error"
