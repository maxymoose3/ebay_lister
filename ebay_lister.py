#!/usr/bin/env python3
"""eBay listing automation.

  ebay_lister.py serve                   open the local app
  ebay_lister.py draft PHOTO...          identify and draft from the terminal
  ebay_lister.py auth                    sign in to eBay
  ebay_lister.py shipping-services       list valid shipping service codes
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lister.ebay import EbayError
from lister.llm import LLMError
from lister.pipeline import Pipeline, check_options


def show(d) -> None:
    print(f"\n{'=' * 78}\n{d.text.title if d.text else d.item.summary()}\n{'-' * 78}")
    if d.text:
        print(d.text.description, "\n")
    label = "Auction start" if d.options.format == "AUCTION" else "Buy It Now"
    print(f"{label}: {f'{d.price:.2f}' if d.price else 'not set'}")
    if d.options.start_time:
        print(f"Starts: {d.options.start_time:%a %d %b %Y %H:%M %Z}")
    for w in [*d.item.uncertainties, *([d.error] if d.error else [])]:
        print(f"  ! {w}")
    print(f"Draft {d.id}: {d.status}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8765)
    dr = sub.add_parser("draft")
    dr.add_argument("photos", nargs="+", help="files in photos/, e.g. IMG_2825.jpg")
    dr.add_argument("--auction", action="store_true", help="auction instead of Buy It Now")
    dr.add_argument("--start", help="local start time, e.g. '2026-11-29 18:00'")
    dr.add_argument("--days", type=int, default=7, choices=[1, 3, 5, 7, 10], help="auction length")
    dr.add_argument("--no-canada", action="store_true")
    dr.add_argument("--intl", action="store_true")
    dr.add_argument("--price", type=float, help="Buy It Now price, or auction start (default: LISTER_AUCTION_START)")
    sub.add_parser("auth")
    sub.add_parser("shipping-services")
    a = ap.parse_args()
    pipe = Pipeline()
    try:
        if a.cmd == "serve":
            import uvicorn
            from lister.web import create_app
            print(f"Open http://127.0.0.1:{a.port}")
            uvicorn.run(create_app(pipe), host="127.0.0.1", port=a.port, log_level="warning")
        elif a.cmd == "draft":
            o = pipe.default_options()
            o.format, o.duration_days = ("AUCTION" if a.auction else "FIXED_PRICE"), a.days
            if a.start:
                o.start_time = datetime.fromisoformat(a.start).replace(tzinfo=ZoneInfo(pipe.s.timezone))
            o.shipping.ca, o.shipping.intl = not a.no_canada, a.intl
            check_options(o)
            drafts, left = pipe.identify([Path(p).name for p in a.photos], o)
            for d in drafts:
                if a.price:
                    d.price_override = a.price
                    pipe.store.save(d)
                show(pipe.draft(d.id))
            if left:
                print("\nNot matched to an item:", ", ".join(left))
        elif a.cmd == "auth":
            print("Open this address, sign in, then paste the address you land on:\n\n" + pipe.ebay.consent_url() + "\n")
            pipe.ebay.finish_consent(input("Address: "))
            print("Signed in.")
        else:
            for x in pipe.ebay.shipping_services():
                print(x.get("shippingService", ""), "-", x.get("description", ""))
    except (EbayError, LLMError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
