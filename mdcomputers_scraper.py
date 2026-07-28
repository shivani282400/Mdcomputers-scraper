#!/usr/bin/env python3
"""
mdcomputers_scraper.py

Scrapes product listing details from mdcomputers.in for a given search term.

MDComputers runs on OpenCart, so search results live at:
    https://mdcomputers.in/?route=product/search&search=<term>&page=<n>

For each product card on the results page this script pulls:
    - name
    - product url
    - image url
    - price (current / discounted)
    - old price (if the item is on sale)
    - discount percentage (if shown)
    - stock/availability text, when present

Usage:
    python mdcomputers_scraper.py "external harddrive"
    python mdcomputers_scraper.py "external harddrive" --pages 2 --out results.csv
    python mdcomputers_scraper.py "external harddrive" --format json --out results.json

Notes:
    - This only reads publicly served search-result pages (no login, no
      private data). Please respect mdcomputers.in's robots.txt / Terms of
      Use and keep request rates low (the script already sleeps between
      pages).
    - Site markup can change at any time; if a field starts coming back
      empty, the CSS selectors below are the first place to check.
"""

import argparse
import csv
import json
import re
import sys
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mdcomputers.in/"
SEARCH_ROUTE = "product/search"

HEADERS = {
    # A normal desktop-browser UA avoids being served a stripped-down page.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_search_url(term: str, page: int = 1) -> str:
    params = {"route": SEARCH_ROUTE, "search": term}
    if page > 1:
        params["page"] = page
    return BASE_URL + "?" + urlencode(params)


def fetch_page(url: str, session: requests.Session, timeout: int = 20) -> str:
    resp = session.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_price(text: str):
    """Turn '₹12,000' into 12000 (int). Returns None if nothing numeric found."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def find_total_pages(soup: BeautifulSoup) -> int:
    """Look at the pagination links / 'Showing X to Y of Z' text."""
    pagination = soup.select_one("ul.pagination")
    if pagination:
        page_numbers = [
            int(a.get_text(strip=True))
            for a in pagination.select("a")
            if a.get_text(strip=True).isdigit()
        ]
        if page_numbers:
            return max(page_numbers)

    results_text = soup.find(string=re.compile(r"Showing \d+ to \d+ of \d+"))
    if results_text:
        match = re.search(
            r"Showing \d+ to (\d+) of (\d+)", clean_text(str(results_text))
        )
        if match:
            per_page, total = int(match.group(1)), int(match.group(2))
            if per_page:
                return max(1, -(-total // per_page))  # ceil division
    return 1


def parse_products(soup: BeautifulSoup):
    """
    OpenCart themes vary a bit, so we try a couple of container selectors
    and fall back gracefully if one doesn't match this theme.
    """
    products = []
    cards = soup.select(".product-thumb, .product-layout, .product-item")

    if not cards:
        # Fallback: MDComputers wraps each result in a div containing an
        # <h4>/<h3> product title link + price block.
        cards = soup.select("div.product-thumb, div[class*='product']")

    for card in cards:
        name_tag = card.select_one("h4 a, h3 a, .product-name a, .caption a")
        if not name_tag:
            continue

        name = clean_text(name_tag.get_text())
        url = name_tag.get("href", "").strip()

        img_tag = card.select_one("img")
        image_url = img_tag.get("data-src") or img_tag.get("src") if img_tag else None

        price_new_tag = card.select_one(".price-new, .price-normal, .price")
        price_old_tag = card.select_one(".price-old")

        price_new_text = clean_text(price_new_tag.get_text()) if price_new_tag else ""
        price_old_text = clean_text(price_old_tag.get_text()) if price_old_tag else ""

        # If there's no explicit "price-new" span, the plain ".price" block
        # sometimes contains both old+new prices concatenated; split on ₹.
        if not price_old_text and price_new_text.count("₹") > 1:
            parts = [p for p in price_new_text.split("₹") if p.strip()]
            if len(parts) == 2:
                price_old_text, price_new_text = "₹" + parts[0], "₹" + parts[1]

        discount_tag = card.select_one(".discount-label, .special-tag, .label-danger")
        discount_text = clean_text(discount_tag.get_text()) if discount_tag else ""

        stock_tag = card.select_one(".stock, .availability")
        stock_text = clean_text(stock_tag.get_text()) if stock_tag else ""

        products.append(
            {
                "name": name,
                "url": url,
                "image_url": image_url,
                "price": parse_price(price_new_text),
                "price_text": price_new_text,
                "old_price": parse_price(price_old_text),
                "old_price_text": price_old_text,
                "discount": discount_text,
                "stock": stock_text,
            }
        )

    return products


def scrape(term: str, max_pages: int = None, delay: float = 1.5):
    session = requests.Session()
    all_products = []

    first_url = build_search_url(term, page=1)
    html = fetch_page(first_url, session)
    soup = BeautifulSoup(html, "html.parser")

    total_pages = find_total_pages(soup)
    if max_pages:
        total_pages = min(total_pages, max_pages)

    all_products.extend(parse_products(soup))
    print(f"Page 1/{total_pages}: {len(all_products)} products so far", file=sys.stderr)

    for page in range(2, total_pages + 1):
        time.sleep(delay)
        url = build_search_url(term, page=page)
        html = fetch_page(url, session)
        soup = BeautifulSoup(html, "html.parser")
        page_products = parse_products(soup)
        all_products.extend(page_products)
        print(
            f"Page {page}/{total_pages}: +{len(page_products)} "
            f"({len(all_products)} total)",
            file=sys.stderr,
        )

    return all_products


def save_csv(products, path):
    fieldnames = [
        "name",
        "price",
        "price_text",
        "old_price",
        "old_price_text",
        "discount",
        "stock",
        "url",
        "image_url",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)


def save_json(products, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape product details from mdcomputers.in for a search term."
    )
    parser.add_argument("search_term", help="e.g. \"external harddrive\"")
    parser.add_argument(
        "--pages", type=int, default=None, help="Max number of result pages to fetch"
    )
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Seconds to wait between page requests"
    )
    parser.add_argument(
        "--format", choices=["csv", "json"], default="csv", help="Output file format"
    )
    parser.add_argument("--out", default=None, help="Output file path")
    args = parser.parse_args()

    products = scrape(args.search_term, max_pages=args.pages, delay=args.delay)

    if not products:
        print("No products found (site markup may have changed, or no results).")
        return

    out_path = args.out or (
        f"mdcomputers_{re.sub(r'[^a-z0-9]+', '_', args.search_term.lower()).strip('_')}"
        f".{args.format}"
    )

    if args.format == "csv":
        save_csv(products, out_path)
    else:
        save_json(products, out_path)

    print(f"Saved {len(products)} products to {out_path}")


if __name__ == "__main__":
    main()
