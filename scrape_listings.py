from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


@dataclass
class Listing:
    title: str
    price: str
    location: str
    url: str
    source_page: str


DEFAULT_SELECTORS: Dict[str, Any] = {
    # Update these CSS selectors for your target site.
    "card": ".listing-card",
    "title": ".listing-title",
    "price": ".listing-price",
    "location": ".listing-location",
    "link": "a",
    # Optional: selector for a "next page" link/button.
    "next_page": "a[rel='next']",
}


def _read_text(el) -> str:
    if not el:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def _safe_url(href: str, base_url: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(base_url, href)


def can_fetch(url: str, user_agent: str, timeout_s: float) -> bool:
    """
    Best-effort robots.txt check. Some sites block scraping in ToS even if robots allows it.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # If robots is unreachable, we don't hard-fail (many sites rate-limit robots.txt).
        return True

    return rp.can_fetch(user_agent, url)


def fetch_html(
    session: requests.Session,
    url: str,
    *,
    timeout_s: float,
    user_agent: str,
) -> str:
    resp = session.get(
        url,
        timeout=timeout_s,
        headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"},
    )
    resp.raise_for_status()
    return resp.text


def parse_listings(
    html: str,
    *,
    page_url: str,
    selectors: Dict[str, Any],
) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(selectors["card"])
    results: List[Listing] = []

    for card in cards:
        title = _read_text(card.select_one(selectors["title"]))
        price = _read_text(card.select_one(selectors["price"]))
        location = _read_text(card.select_one(selectors["location"]))

        link_el = card.select_one(selectors["link"])
        href = ""
        if link_el and getattr(link_el, "get", None):
            href = link_el.get("href") or ""
        listing_url = _safe_url(href, page_url)

        # Keep empty strings if missing—easier for downstream cleaning.
        results.append(
            Listing(
                title=title,
                price=price,
                location=location,
                url=listing_url,
                source_page=page_url,
            )
        )

    return results


def parse_next_page_url(html: str, *, page_url: str, selectors: Dict[str, Any]) -> str:
    soup = BeautifulSoup(html, "lxml")
    sel = selectors.get("next_page")
    if not sel:
        return ""
    next_el = soup.select_one(sel)
    if not next_el:
        return ""
    href = next_el.get("href") if getattr(next_el, "get", None) else ""
    return _safe_url(href or "", page_url)


def write_csv(path: str, rows: Iterable[Listing]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["title", "price", "location", "url", "source_page"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_json(path: str, rows: Iterable[Listing]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in rows], f, ensure_ascii=False, indent=2)


def load_selectors(selectors_path: Optional[str]) -> Dict[str, Any]:
    if not selectors_path:
        return dict(DEFAULT_SELECTORS)
    with open(selectors_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_SELECTORS)
    merged.update(data or {})
    return merged


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(
        description="Simple property listings scraper (HTML pages, CSS selectors)."
    )
    p.add_argument("--start-url", required=True, help="First listings page URL")
    p.add_argument("--pages", type=int, default=1, help="Max pages to scrape")
    p.add_argument("--delay", type=float, default=1.5, help="Base delay between requests (seconds)")
    p.add_argument("--jitter", type=float, default=0.5, help="Random +/- jitter added to delay (seconds)")
    p.add_argument("--timeout", type=float, default=20.0, help="Request timeout (seconds)")
    p.add_argument("--out", default="listings.csv", help="Output file path")
    p.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format")
    p.add_argument(
        "--selectors",
        help="Path to a JSON file with CSS selectors (overrides defaults)",
    )
    p.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (compatible; SimpleListingsScraper/1.0; +https://example.com/bot)",
        help="User-Agent header to send",
    )
    args = p.parse_args(argv)

    selectors = load_selectors(args.selectors)
    url = args.start_url
    all_rows: List[Listing] = []

    with requests.Session() as session:
        for i in range(args.pages):
            if not url:
                break

            if not can_fetch(url, args.user_agent, args.timeout):
                print(f"Blocked by robots.txt: {url}", file=sys.stderr)
                break

            try:
                html = fetch_html(
                    session,
                    url,
                    timeout_s=args.timeout,
                    user_agent=args.user_agent,
                )
            except requests.RequestException as e:
                print(f"Request failed for {url}: {e}", file=sys.stderr)
                break

            rows = parse_listings(html, page_url=url, selectors=selectors)
            all_rows.extend(rows)

            next_url = parse_next_page_url(html, page_url=url, selectors=selectors)
            print(f"Page {i + 1}: {len(rows)} listings (total {len(all_rows)}). Next: {next_url or '-'}")
            url = next_url

            # Polite delay
            sleep_s = max(0.0, args.delay + random.uniform(-args.jitter, args.jitter))
            if i < args.pages - 1 and url:
                time.sleep(sleep_s)

    if args.format == "csv":
        write_csv(args.out, all_rows)
    else:
        write_json(args.out, all_rows)

    print(f"Wrote {len(all_rows)} listings to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
