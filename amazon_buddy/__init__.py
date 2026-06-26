"""Public API for the Python Amazon Buddy port."""
from __future__ import annotations

from typing import Any

from .constants import DEFAULT_ITEM_LIMIT, GEO
from .scraper import AmazonScraper, safe_output_stem

INIT_OPTIONS: dict[str, Any] = {
    "bulk": True,
    "number": DEFAULT_ITEM_LIMIT,
    "filetype": "",
    "rating": [1, 5],
    "page": 1,
    "category": "aps",
    "cookie": "",
    "async_tasks": 5,
    "sponsored": False,
    "cli": False,
    "sort": False,
    "discount": False,
    "review_filter": {"sortBy": "recent", "verifiedPurchaseOnly": False, "filterByStar": "", "formatType": "all_formats"},
}


def _options(options: dict[str, Any] | None, scrape_type: str | None = None) -> dict[str, Any]:
    merged = {**INIT_OPTIONS, **(options or {})}
    country = str(merged.get("country", "US")).upper()
    merged["geo"] = GEO.get(country, GEO["US"])
    if scrape_type:
        merged["scrape_type"] = scrape_type
    if not merged.get("bulk"):
        merged["async_tasks"] = 1
    return merged


def products(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return AmazonScraper(**_options(options, "products")).start_scraper()


def reviews(options: dict[str, Any] | None = None) -> dict[str, Any]:
    return AmazonScraper(**_options(options, "reviews")).start_scraper()


def asin(options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = _options(options, "asin")
    opts["async_tasks"] = 1
    return AmazonScraper(**opts).start_scraper()


def categories(options: dict[str, Any] | None = None) -> dict[str, Any]:
    scraper = AmazonScraper(**_options(options, "products"))
    body = scraper.build_request()
    soup = scraper._soup(body)
    select = soup.select_one("#searchDropdownBox")
    if not select:
        raise ValueError("Can't find category selector")
    output = {}
    for option in select.select("option[value]"):
        category = option.get("value", "").split("search-alias=")[-1]
        output[category] = {"name": option.get_text(strip=True), "category": category}
    return output


def countries() -> list[dict[str, str]]:
    return [{"country": geo["country"], "country_code": code, "currency": geo["currency"], "host": geo["host"]} for code, geo in GEO.items()]

__all__ = ["AmazonScraper", "asin", "categories", "countries", "products", "reviews", "safe_output_stem"]
