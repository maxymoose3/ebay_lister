"""Local web app. Binds to 127.0.0.1 only."""
from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import llm, photos
from .ebay import EbayError
from .models import Draft, Identification, ListingOptions, ListingText
from .pipeline import Pipeline, check_options

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class IdentifyIn(BaseModel):
    photos: list[str] = Field(min_length=1, max_length=40)
    options: Optional[ListingOptions] = None


class PatchIn(BaseModel):
    item: Optional[Identification] = None
    options: Optional[ListingOptions] = None
    text: Optional[ListingText] = None
    aspects: Optional[dict[str, list[str]]] = None
    category_id: Optional[str] = None
    price_override: Optional[float] = Field(None, gt=0)
    clear_price_override: bool = False


class PublishIn(BaseModel):
    confirm: bool
    expected_price: float


def create_app(pipe: Pipeline | None = None) -> FastAPI:
    pipe = pipe or Pipeline()
    app = FastAPI(title="eBay lister", docs_url=None, redoc_url=None, openapi_url=None)
    jobs: dict[str, dict] = {}
    slots = threading.BoundedSemaphore(3)
    publishing = threading.Lock()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Stops other websites from driving this app through the browser (CSRF, DNS rebinding).
        if (request.url.hostname or "") not in LOCAL_HOSTS:
            return JSONResponse({"detail": "local access only"}, 403)
        if request.method not in {"GET", "HEAD"} and request.headers.get("x-lister") != "1":
            return JSONResponse({"detail": "missing header"}, 403)
        return await call_next(request)

    @app.exception_handler(EbayError)
    @app.exception_handler(llm.LLMError)
    @app.exception_handler(ValueError)
    async def bad(_: Request, e: Exception):
        return JSONResponse({"detail": str(e)}, 400)

    def get(id: str) -> Draft:
        try:
            return pipe.store.get(id)
        except KeyError:
            raise HTTPException(404, "Draft not found")

    def out(d: Draft) -> dict:
        return d.model_dump(mode="json") | {"price": d.price}

    def start(fn) -> dict:
        jid = uuid.uuid4().hex
        jobs[jid] = {"state": "running"}

        def work():
            with slots:
                try:
                    jobs[jid] = {"state": "done", "result": fn()}
                except Exception as e:
                    jobs[jid] = {"state": "error", "error": str(e) or type(e).__name__}

        threading.Thread(target=work, daemon=True).start()
        return {"job": jid}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    def state():
        return {"photos": photos.list_photos(pipe.s.photos_dir), "drafts": [out(d) for d in pipe.store.all()],
                "defaults": pipe.default_options().model_dump(mode="json"), "currency": pipe.s.currency,
                "timezone": pipe.s.timezone, "ebay_keys": pipe.s.has_ebay_keys, "ebay_signed_in": pipe.s.token_file.exists()}

    @app.get("/api/photo/{name}")
    def photo(name: str, size: int = 500):
        data = photos.jpeg_bytes(photos.resolve(pipe.s.photos_dir, name), max(64, min(size, 2000)), 82)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.post("/api/photos")
    async def upload(files: list[UploadFile] = File()):
        saved = []
        for f in files:
            data = await f.read(30_000_001)
            if len(data) > 30_000_000:
                raise ValueError(f"{f.filename} is larger than 30 MB")
            try:
                saved.append(photos.save_upload(pipe.s.photos_dir, f.filename or "photo.jpg", data))
            except OSError:
                raise ValueError(f"{f.filename} is not a readable image")
        return {"saved": saved}

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        if jid not in jobs:
            raise HTTPException(404, "Job not found")
        return jobs[jid]

    @app.post("/api/identify")
    def identify(body: IdentifyIn):
        for n in body.photos:
            photos.resolve(pipe.s.photos_dir, n)
        if body.options:
            check_options(body.options)

        def work():
            drafts, left = pipe.identify(body.photos, body.options)
            return {"drafts": [d.id for d in drafts], "unassigned": left}
        return start(work)

    @app.post("/api/drafts/{id}/draft")
    def write_draft(id: str):
        d = get(id)
        check_options(d.options)
        if d.status == "published":
            raise ValueError("This draft is already live.")
        return start(lambda: out(pipe.draft(id)))

    @app.patch("/api/drafts/{id}")
    def patch(id: str, body: PatchIn):
        d = get(id)
        if d.status == "published":
            raise ValueError("This draft is already live; edit it on eBay.")
        if d.status == "drafting":
            raise ValueError("The draft is being written; wait for it to finish.")
        if body.options:
            check_options(body.options)
            if body.options.format != d.options.format:
                d.price_override = None  # a Buy It Now price is not an auction start
            d.options = body.options
        if body.item:
            for n in body.item.photos:
                photos.resolve(pipe.s.photos_dir, n)
            d.item = body.item
        if body.text:
            if not 1 <= len(body.text.title) <= 80:
                raise ValueError("Title must be 1 to 80 characters.")
            d.text = body.text
        if body.aspects is not None:
            d.aspects = body.aspects
        if body.category_id is not None:
            if not body.category_id.isdigit():
                raise ValueError("Category must be a number.")
            d.category_id = body.category_id
        if body.price_override is not None:
            d.price_override = body.price_override
        if body.clear_price_override:
            d.price_override = None
        return out(pipe.changed(d))

    @app.delete("/api/drafts/{id}")
    def delete(id: str):
        get(id)
        pipe.store.delete(id)
        return {"ok": True}

    @app.post("/api/drafts/{id}/push")
    def push(id: str):
        get(id)

        def work():
            with publishing:
                d = pipe.store.get(id)
                check_options(d.options)
                d.offer_id, d.status, d.error = pipe.ebay.push(d), "pushed", ""
                return out(pipe.store.save(d))
        return start(work)

    @app.post("/api/drafts/{id}/publish")
    def publish(id: str, body: PublishIn):
        get(id)

        def work():
            with publishing:
                d = pipe.store.get(id)
                if not body.confirm or d.price is None or abs(body.expected_price - d.price) > 0.004:
                    raise EbayError("The price changed since you confirmed. Review it and confirm again.")
                if d.status != "pushed":
                    raise EbayError("Send the latest version to eBay before publishing.")
                check_options(d.options)
                d.listing_id, d.status = pipe.ebay.publish(d), "published"
                return out(pipe.store.save(d))
        return start(work)

    return app
