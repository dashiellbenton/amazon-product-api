"""Python implementation of the Amazon Buddy scraper API."""
from __future__ import annotations

import csv
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

from .constants import DEFAULT_ITEM_LIMIT, GEO, PRODUCT_LIMIT, REVIEW_FILTER, REVIEW_LIMIT

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - exercised only in uninstalled environments.
    BeautifulSoup = None

DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36"


def safe_output_stem(scrape_type: str, identifier: str, timestamp: int | None = None) -> str:
    """Return a clear, portable output file stem without parentheses."""
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(identifier or "output")).strip("-._") or "output"
    return f"{scrape_type}-{clean}-{timestamp or int(time.time() * 1000)}"


def _text(node: Any) -> str:
    if not node:
        return ""
    return node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip()


@dataclass
class AmazonScraper:
    keyword: str = ""
    number: int = DEFAULT_ITEM_LIMIT
    sponsored: bool = False
    proxy: str | list[str] | None = None
    cli: bool = False
    filetype: str = ""
    scrape_type: str = "products"
    asin: str = ""
    sort: bool = False
    discount: bool = False
    rating: list[float] = field(default_factory=lambda: [1, 5])
    ua: str = DEFAULT_UA
    timeout: int = 0
    random_ua: bool = False
    page: int = 1
    bulk: bool = True
    category: str = "aps"
    cookie: str = ""
    geo: dict[str, Any] = field(default_factory=lambda: GEO["US"])
    async_tasks: int = 5
    review_filter: dict[str, Any] = field(default_factory=lambda: {"sortBy": "recent", "verifiedPurchaseOnly": False, "filterByStar": "", "formatType": "all_formats"})
    referer: list[str] | str | None = None
    collector: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.number = int(self.number)
        self.main_host = f"https://{self.geo['host']}"
        self.init_time = int(time.time() * 1000)
        self.total_products = 0
        self.review_metadata = {"total_reviews": 0, "stars_stat": {}}
        self.min_rating = 1.0
        self.max_rating = 5.0

    @property
    def user_agent(self) -> str:
        if not self.random_ua:
            return self.ua or DEFAULT_UA
        oses = ["Macintosh; Intel Mac OS X 10_15_7", "Macintosh; Intel Mac OS X 10_11_6", "Windows NT 10.0; Win64; x64", "Windows NT 10.0"]
        return f"Mozilla/5.0 ({random.choice(oses)}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(100, 103)}.0.{random.randint(4100, 4289)}.{random.randint(140, 189)} Safari/537.36"

    @property
    def file_name(self) -> str:
        identifier = self.keyword if self.scrape_type == "products" else self.asin
        return safe_output_stem(self.scrape_type, identifier, self.init_time)

    @property
    def request_endpoint(self) -> str:
        if self.scrape_type == "products":
            return "s"
        if self.scrape_type == "reviews":
            rf = self.review_filter
            return "product-reviews/{}/ref=cm_cr_arp_d_viewopt_srt?formatType={}&sortBy={}{}{}".format(
                self.asin,
                REVIEW_FILTER["formatType"].get(rf.get("formatType"), "all_formats"),
                REVIEW_FILTER["sortBy"].get(rf.get("sortBy"), ""),
                "&reviewerType=avp_only_reviews" if rf.get("verifiedPurchaseOnly") else "",
                f"&filterByStar={REVIEW_FILTER['filterByStar'].get(rf.get('filterByStar'), '')}" if rf.get("filterByStar") else "",
            )
        if self.scrape_type == "asin":
            return f"dp/{self.asin}/ref=sspa_dk_detail_3&th=1&psc=1?th=1&psc=1"
        return ""

    def http_request(self, uri: str = "", qs: dict[str, Any] | None = None) -> str:
        url = f"{self.main_host}/{uri}" if uri else self.main_host
        if qs:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(qs)}"
        headers = {"User-Agent": self.user_agent, "Cookie": self.cookie, "Accept-Language": "en-US,en;q=0.9"}
        opener = build_opener(ProxyHandler({"http": self.proxy, "https": self.proxy}) if isinstance(self.proxy, str) and self.proxy else ProxyHandler({}))
        with opener.open(Request(url, headers=headers), timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
        if self.timeout:
            time.sleep(self.timeout / 1000)
        return body

    def build_request(self, page: int | None = None) -> str:
        qs: dict[str, Any] = {}
        if self.scrape_type == "products":
            qs.update({"k": self.keyword})
            if self.category:
                qs["i"] = self.category
            if page and page > 1:
                qs.update({"page": page, "ref": f"sr_pg_{page}"})
        elif self.scrape_type == "reviews" and page and page > 1:
            qs["pageNumber"] = page
        return self.http_request(self.request_endpoint, qs)

    def start_scraper(self) -> dict[str, Any]:
        self._validate()
        async_page = 1 if self.scrape_type == "asin" else -(-self.number // (15 if self.scrape_type == "products" else 10))
        pages = [self.page] if not self.bulk else range(1, async_page + 1)
        with ThreadPoolExecutor(max_workers=max(1, int(self.async_tasks))) as executor:
            futures = {executor.submit(self.build_request, page): page for page in pages}
            for future in as_completed(futures):
                body = future.result()
                if self.scrape_type == "products":
                    self.grab_products(body, futures[future])
                elif self.scrape_type == "reviews":
                    self.grab_reviews(body)
                else:
                    self.grab_asin_details(body)
        self.sort_and_filter_result()
        self.save_result_to_file()
        result = {"result": self.collector}
        if self.scrape_type == "products":
            result.update({"totalProducts": self.total_products, "category": self.category})
        if self.scrape_type == "reviews":
            result.update(self.review_metadata)
        return result

    def _validate(self) -> None:
        if self.scrape_type == "products" and not self.keyword:
            raise ValueError("Keyword is missing")
        if self.scrape_type == "products" and self.number > PRODUCT_LIMIT:
            raise ValueError(f"Wow.... slow down cowboy. Maximum you can get is {PRODUCT_LIMIT} products")
        if self.scrape_type in {"reviews", "asin"} and not self.asin:
            raise ValueError("ASIN is missing")
        if self.scrape_type == "reviews" and self.number > REVIEW_LIMIT:
            raise ValueError(f"Wow.... slow down cowboy. Maximum you can get is {REVIEW_LIMIT} reviews")
        if len(self.rating) != 2:
            raise ValueError("rating can only be an array with length of 2")
        self.min_rating, self.max_rating = map(float, self.rating)
        if self.min_rating > self.max_rating:
            raise ValueError("min rating can't be larger then max rating")

    def _soup(self, body: str) -> Any:
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 is required. Install with: pip install beautifulsoup4")
        return BeautifulSoup(re.sub(r"\s\s+", " ", body), "html.parser")

    def grab_products(self, body: str, page: int) -> None:
        soup = self._soup(body)
        match = re.search(r'"totalResultCount":\w*(\d+)', body)
        if match:
            self.total_products = int(match.group(1))
        for idx, item in enumerate(soup.select("div[data-index][data-asin]"), start=1):
            asin = item.get("data-asin")
            if not asin:
                continue
            price_text = _text(item.select_one('span[data-a-size="xl"], span[data-a-size="l"], span[data-a-size="m"]'))
            strike_text = _text(item.select_one('span[data-a-strike="true"]'))
            rating_text = _text(item.select_one(".a-icon-star-small, .a-icon-star"))
            rating = float(re.search(r"\d+(?:\.\d+)?", rating_text).group(0)) if re.search(r"\d+(?:\.\d+)?", rating_text) else 0
            reviews_text = item.select_one("[aria-label]")
            reviews = int(re.sub(r"\D", "", reviews_text.get("aria-label", "") or "0") or 0) if reviews_text else 0
            current = self.geo["price_format"](price_text)
            before = self.geo["price_format"](strike_text) if strike_text else 0
            discounted = bool(before and before > current)
            image = item.select_one('[data-image-source-density="1"], img.s-image')
            self.collector.append({
                "position": {"page": page, "position": idx, "global_position": int(f"{page}{idx}")},
                "asin": asin,
                "title": image.get("alt", "") if image else "",
                "thumbnail": image.get("src", "") if image else "",
                "price": {"discounted": discounted, "current_price": current, "currency": self.geo["currency"], "before_price": before, "savings_amount": round(before - current, 2) if discounted else 0, "savings_percent": round((100 / before) * (before - current), 2) if discounted else 0},
                "reviews": {"total_reviews": reviews, "rating": rating},
                "url": f"{self.main_host}/dp/{asin}",
                "score": round(rating * reviews, 2),
                "sponsored": bool(item.select_one('[aria-label="Sponsored"]')),
                "amazonChoice": bool(item.select_one(f'span[id="{asin}-amazons-choice"]')),
                "bestSeller": bool(item.select_one(f'span[id="{asin}-best-seller"]')),
                "amazonPrime": bool(item.select_one(".s-prime")),
            })

    def grab_reviews(self, body: str) -> None:
        soup = self._soup(body)
        total = re.sub(r"\D", "", _text(soup.select_one(".averageStarRatingNumerical")) or "0")
        self.review_metadata["total_reviews"] = int(total or 0)
        for row in soup.select("#histogramTable tr"):
            cells = row.select("td")
            if len(cells) >= 3:
                star = re.sub(r"\D", "", _text(cells[0]))
                if star:
                    self.review_metadata["stars_stat"][int(star)] = _text(cells[2])
        for item in soup.select("#cm_cr-review_list [id]"):
            if len(self.collector) >= self.number and self.bulk:
                break
            rid = item.get("id")
            rating_text = _text(item.select_one('[data-hook="review-star-rating"], [data-hook="cmps-review-star-rating"]'))
            rating_match = re.search(r"\d+(?:\.\d+)?", rating_text)
            date_text = _text(item.select_one('[data-hook="review-date"]'))
            self.collector.append({"id": rid, "asin": {"original": self.asin, "variant": ""}, "review_data": date_text, "date": self.geo["review_date"](date_text), "name": _text(item.select_one(".a-profile-name")), "rating": float(rating_match.group(0)) if rating_match else 0, "title": _text(item.select_one('[data-hook="review-title"]')), "review": _text(item.select_one('[data-hook="review-body"]')), "verified_purchase": bool(item.select_one('[data-reftag="cm_cr_arp_d_rvw_rvwer"]')), "media": [img.get("src", "").replace("_SY88", "_SL1600_") for img in item.select(".review-image-tile-section img")]})

    def grab_asin_details(self, body: str) -> None:
        soup = self._soup(body)
        images = [img.get("src", "") for img in soup.select('span[data-action="thumb-action"] img') if img.get("src")]
        rating_text = _text(soup.select_one("span.reviewCountTextLinkedHistogram.noUnderline, #acrPopover"))
        rating_match = re.search(r"\d+(?:\.\d+)?", rating_text)
        self.collector.append({"title": _text(soup.select_one("#productTitle, .qa-title-text")), "description": _text(soup.select_one("#productDescription, #bookDescription_feature_div")), "feature_bullets": [_text(x) for x in soup.select("#feature-bullets .a-list-item") if _text(x)], "categories": [{"category": _text(a), "url": f"{self.main_host}{a.get('href', '')}"} for a in soup.select("#wayfinding-breadcrumbs_feature_div a")], "asin": self.asin, "url": f"{self.main_host}/dp/{self.asin}", "reviews": {"total_reviews": int(re.sub(r"\D", "", _text(soup.select_one("#acrCustomerReviewText")) or "0") or 0), "rating": float(rating_match.group(0)) if rating_match else 0, "answered_questions": int(re.sub(r"\D", "", _text(soup.select_one("#askATFLink")) or "0") or 0)}, "price": {"symbol": self.geo["symbol"], "currency": self.geo["currency"], "current_price": self.geo["price_format"](_text(soup.select_one("span.a-price.priceToPay, span.a-price.apexPriceToPay, .a-price"))), "discounted": bool(soup.select_one("span.savingsPercentage")), "before_price": self.geo["price_format"](_text(soup.select_one("span.a-price.a-text-price"))), "savings_amount": 0, "savings_percent": 0}, "main_image": images[0] if images else "", "total_images": len(images), "images": images, "badges": {"amazon_сhoice": bool(soup.select_one("div.ac-badge-wrapper")), "amazon_prime": bool(soup.select_one("#priceBadging_feature_div")), "best_seller": bool(soup.select_one("i.p13n-best-seller-badge"))}})

    def sort_and_filter_result(self) -> None:
        if self.scrape_type == "products":
            self.collector.sort(key=lambda item: item["position"]["global_position"])
            for idx, item in enumerate(self.collector, start=1):
                item["position"]["global_position"] = idx
            if self.sort:
                self.collector.sort(key=lambda item: item.get("score", 0), reverse=True)
            if self.discount:
                self.collector = [item for item in self.collector if item["price"].get("discounted")]
            if self.sponsored:
                self.collector = [item for item in self.collector if item.get("sponsored")]
            self.collector = [item for item in self.collector if self.min_rating <= item["reviews"].get("rating", 0) <= self.max_rating]
        elif self.scrape_type == "reviews":
            if self.sort:
                self.collector.sort(key=lambda item: item.get("rating", 0), reverse=True)
            self.collector = [item for item in self.collector if self.min_rating <= item.get("rating", 0) <= self.max_rating]

    def save_result_to_file(self) -> None:
        if not self.collector or not self.filetype:
            return
        if self.filetype in {"json", "all"}:
            Path(f"{self.file_name}.json").write_text(json.dumps(self.collector, ensure_ascii=False), encoding="utf-8")
        if self.filetype in {"csv", "all"}:
            keys = sorted({key for row in self.collector for key in row})
            with Path(f"{self.file_name}.csv").open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.collector)
