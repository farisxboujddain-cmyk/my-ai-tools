# my-ai-tools

AI utilities and scripts.

## Property listings scraper (simple)

This repo includes a minimal Python script, `scrape_listings.py`, that scrapes listing “cards” from a property listings page using **CSS selectors**, then exports to **CSV or JSON**.

### Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Run (example)

```bash
python scrape_listings.py --start-url "https://example.com/properties" --pages 3 --out listings.csv --format csv
```

### Adapt to a specific website

Update the CSS selectors (either in `scrape_listings.py` in `DEFAULT_SELECTORS`, or via a JSON file):

`selectors.json`

```json
{
  "card": ".property-card",
  "title": ".property-card__title",
  "price": ".property-card__price",
  "location": ".property-card__location",
  "link": "a",
  "next_page": "a[rel='next']"
}
```

Then run:

```bash
python scrape_listings.py --start-url "https://example.com/properties" --pages 5 --selectors selectors.json --out listings.json --format json
```

### Notes

- Be sure your scraping complies with the website’s **Terms of Service** and **robots.txt**.
- Some sites render listings with JavaScript; this script only handles **server-rendered HTML** pages.
