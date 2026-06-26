"""Constants for the Python Amazon Buddy port."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PRODUCT_LIMIT = 1000
REVIEW_LIMIT = 2000
DEFAULT_ITEM_LIMIT = 15

REVIEW_FILTER = {
    "sortBy": {"recent": "recent", "helpful": "helpful"},
    "filterByStar": {
        "positive": "positive",
        "critical": "critical",
        1: "one_star",
        2: "two_star",
        3: "three_star",
        4: "four_star",
        5: "five_star",
        "1": "one_star",
        "2": "two_star",
        "3": "three_star",
        "4": "four_star",
        "5": "five_star",
    },
    "formatType": {"all_formats": "all_formats", "current_format": "current_format"},
}

PRODUCT_INFORMATION_IDS = [
    "#detailBullets_feature_div > ul",
    "#productDetails_detailBullets_sections1",
    "#productDetails_techSpec_section_1",
    "#productDetails_techSpec_section_2",
    "#detailBulletsWrapper_feature_div > ul:nth-child(5)",
]

PRODUCT_INFORMATION_FIELDS = {
    "Amazon Best Sellers Rank": {"key": "", "rank": True},
    "Best-sellers rank": {"key": "", "rank": True},
    "Best Sellers Rank": {"key": "", "rank": True},
    "Package Dimensions": {"key": "dimensions"},
    "Product Dimensions": {"key": "dimensions"},
    "Parcel Dimensions": {"key": "dimensions"},
    "Item Weight": {"key": "weight"},
    "Manufacturer": {"key": "manufacturer"},
    "Release date": {"key": "available_from"},
    "Date First Available": {"key": "available_from"},
    "Item model number": {"key": "model_number"},
    "Department": {"key": "department"},
    "Language": {"key": "language"},
    "Publisher": {"key": "publisher"},
    "Reading level": {"key": "reading_level"},
    "Grade Level": {"key": "grade_level"},
    "Hardcover": {"key": "hardcover"},
    "Paperback": {"key": "paperback"},
    "ISBN-10": {"key": "ISBN-10"},
    "ISBN-13": {"key": "ISBN-13"},
}

def best_seller(text: str) -> dict[str, Any] | str:
    match = re.search(r"(#[\d,|]+) in[\s\n ]([\w&'\s]+)", text or "")
    if not match:
        return ""
    return {"rank": int(re.sub(r"[^\d]", "", match.group(1))), "category": match.group(2).strip()}

def review_date(date: str) -> dict[str, Any] | str:
    match = re.search(r"on (.+)$", date or "")
    if not match:
        return ""
    value = match.group(1)
    try:
        dt = datetime.strptime(f"{value} 02:00:00", "%B %d, %Y %H:%M:%S").replace(tzinfo=timezone.utc)
        unix = int(dt.timestamp())
    except ValueError:
        unix = 0
    return {"date": value, "unix": unix}

def price_format(price: str, decimal_comma: bool = False) -> float:
    cleaned = re.sub(r"[^\d,.]", "", price or "")
    if decimal_comma:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(",") and cleaned.rfind(",") > cleaned.rfind("."):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def _geo(country: str, currency: str, symbol: str, host: str, split_text: str = "Click to select ") -> dict[str, Any]:
    return {
        "country": country,
        "currency": currency,
        "symbol": symbol,
        "host": host,
        "variants": {"split_text": split_text},
        "best_seller": best_seller,
        "review_date": review_date,
        "price_format": price_format,
        "product_information": {"id": PRODUCT_INFORMATION_IDS, "fields": PRODUCT_INFORMATION_FIELDS},
    }

GEO = {
    "US": _geo("United States of America", "USD", "$", "www.amazon.com"),
    "AU": _geo("Australia", "AUD", "$", "www.amazon.com.au"),
    "BR": _geo("Brazil", "BRL", "R$", "www.amazon.com.br"),
    "CA": _geo("Canada", "CAD", "$", "www.amazon.ca"),
    "DE": _geo("Germany", "EUR", "€", "www.amazon.de"),
    "ES": _geo("Spain", "EUR", "€", "www.amazon.es"),
    "FR": _geo("France", "EUR", "€", "www.amazon.fr"),
    "GB": _geo("United Kingdom", "GBP", "£", "www.amazon.co.uk"),
    "IN": _geo("India", "INR", "₹", "www.amazon.in"),
    "IT": _geo("Italy", "EUR", "€", "www.amazon.it"),
    "JP": _geo("Japan", "JPY", "¥", "www.amazon.co.jp"),
    "MX": _geo("Mexico", "MXN", "$", "www.amazon.com.mx"),
    "NL": _geo("Netherlands", "EUR", "€", "www.amazon.nl"),
    "PL": _geo("Poland", "PLN", "zł", "www.amazon.pl"),
    "SE": _geo("Sweden", "SEK", "kr", "www.amazon.se"),
}
