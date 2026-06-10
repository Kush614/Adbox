"""No-auth export adapters: turn a ListingRun into platform-ready feed files.

Each builder is a pure function ListingRun -> file text, so the same factory
output imports into Shopify (product CSV), Google Merchant Center (TSV feed —
free Shopping listings, zero ad spend) and Meta Commerce Manager (catalog CSV)
without any platform credentials. Live API pushes (Shopify Admin GraphQL,
Content API, Marketing API) slot in beside these as publishers/{platform}.py.

Image/link URLs are absolutized against the serving host; in production these
would point at a CDN.
"""
from __future__ import annotations

import csv
import io
import re

from ..models import ListingItem, ListingRun


def _price_number(price: str) -> str:
    """'$58' -> '58.00' (defaults to 0.00 if unparsable)."""
    m = re.search(r"[\d.]+", price or "")
    try:
        return f"{float(m.group()):.2f}" if m else "0.00"
    except ValueError:
        return "0.00"


def _abs(base_url: str, path: str | None) -> str:
    if not path:
        return ""
    return base_url.rstrip("/") + path


def _handle(item: ListingItem) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", item.title.lower()).strip("-")
    return slug[:60] or item.id


def _csv(rows: list[dict], fieldnames: list[str], *, delimiter: str = ",") -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=delimiter, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# --- Shopify product import CSV ---------------------------------------------
_SHOPIFY_FIELDS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Variant Price", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Image Src", "Image Alt Text", "Status",
]


def shopify_csv(run: ListingRun, base_url: str) -> str:
    rows = []
    for it in run.items:
        rows.append({
            "Handle": _handle(it),
            "Title": it.title,
            "Body (HTML)": f"<p>{it.description}</p>",
            "Vendor": "Ad-in-a-Box",
            "Type": it.category,
            "Tags": ", ".join(it.tags),
            "Published": "TRUE",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant Price": _price_number(it.suggested_price),
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Image Src": _abs(base_url, it.clean_url),
            "Image Alt Text": it.title,
            "Status": "active",
        })
    return _csv(rows, _SHOPIFY_FIELDS)


# --- Google Merchant Center feed (TSV) — free Shopping listings -------------
_MERCHANT_FIELDS = [
    "id", "title", "description", "link", "image_link", "availability",
    "price", "condition", "brand", "google_product_category", "identifier_exists",
]


def merchant_tsv(run: ListingRun, base_url: str) -> str:
    rows = []
    for it in run.items:
        rows.append({
            "id": f"adbox-{run.run_id}-{it.id}",
            "title": it.title,
            "description": it.description,
            "link": base_url.rstrip("/") + "/",
            "image_link": _abs(base_url, it.clean_url),
            "availability": "in stock",
            "price": f"{_price_number(it.suggested_price)} USD",
            "condition": "new",
            "brand": "Ad-in-a-Box",
            "google_product_category": it.category,
            "identifier_exists": "no",
        })
    return _csv(rows, _MERCHANT_FIELDS, delimiter="\t")


# --- Meta (Facebook/Instagram Shops) catalog CSV -----------------------------
_META_FIELDS = [
    "id", "title", "description", "availability", "condition", "price",
    "link", "image_link", "brand", "product_type",
]


def meta_csv(run: ListingRun, base_url: str) -> str:
    rows = []
    for it in run.items:
        rows.append({
            "id": f"adbox-{run.run_id}-{it.id}",
            "title": it.title,
            "description": it.description,
            "availability": "in stock",
            "condition": "new",
            "price": f"{_price_number(it.suggested_price)} USD",
            "link": base_url.rstrip("/") + "/",
            "image_link": _abs(base_url, it.clean_url),
            "brand": "Ad-in-a-Box",
            "product_type": it.category,
        })
    return _csv(rows, _META_FIELDS)


# --- Registry ----------------------------------------------------------------
EXPORTERS = {
    "shopify": (shopify_csv, "shopify_products.csv", "text/csv"),
    "merchant": (merchant_tsv, "google_merchant_feed.tsv", "text/tab-separated-values"),
    "meta": (meta_csv, "meta_catalog.csv", "text/csv"),
}


def export(run: ListingRun, platform: str, base_url: str) -> tuple[str, str, str]:
    """Returns (file_text, filename, mime). Raises KeyError on unknown platform."""
    builder, filename, mime = EXPORTERS[platform]
    return builder(run, base_url), filename, mime
