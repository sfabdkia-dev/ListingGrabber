"""Extract main product details from an Amazon product page capture JSON file.

The capture file has five top-level keys: capturedAt, url, title, html, text.
Extraction works from `text` (innerText) and `title` (page title).

Key patterns used:
  - Title          : page `title` field with the " : Amazon.ca/com: ..." suffix stripped
  - Price          : "$X.XX with N percent savings" line (buy-box price)
  - Was price      : "Was: $X.XX" line
  - Discount       : standalone "-N%" line
  - Deal type      : "Limited-time deal" / "Lightning Deal" standalone line
  - Amazon's Choice: presence of "Amazon's Choice" line
  - Bought recently: "N+ bought in past month" line
  - Rating         : "N.N out of 5 stars" line
  - Reviews        : "(N,NNN)" line immediately following the rating
  - Availability   : "In Stock" / "Out of Stock" standalone line
  - Ships from     : label line "Ships from" followed by value
  - Sold by        : label line "Sold by" followed by value
  - Specs          : all tab-separated "Key\tValue" lines (product attribute table)
  - Brand          : "Brand\tValue" from the spec table
  - Selected variant: "Colour Name: X" / "Size: X" lines near the buy box
  - ASIN           : "ASIN ... B0XXXXXXXXX" in the product details section
  - Manufacturer   : "Manufacturer ... value" in the product details section
  - Best sellers   : "Best Sellers Rank: #N in Category" line
  - Description    : bullet lines between "About this item" and "› See more product details"
"""

import json
import re

# Module-level compiled patterns and constant sets (avoid recompiling on every call)
_SAVINGS_RE = re.compile(r'(\$[\d,]+\.\d{2})\s+with\s+(\d+)\s+percent\s+savings')
_PRICE_RE = re.compile(r'^\$[\d,]+\.\d{2}$')
_WAS_RE = re.compile(r'^Was:\s*(\$[\d,]+\.\d{2})$')
_RATING_RE = re.compile(r'(\d+\.?\d*)\s+out of 5 stars')
_REVIEW_RE = re.compile(r'^\(?([\d,]+)\)?$')
_BOUGHT_RE = re.compile(r'^([\d,]+\+?\s+bought in past month)$')
_ASIN_RE = re.compile(r'ASIN\b[^\w]*([A-Z0-9]{10})\b')
_MFR_RE = re.compile(r'^Manufacturer\b[^\w]*(.+)$')
_BSR_RE = re.compile(r'Best Sellers Rank:\s*(#[\d,]+\s+in\s+[^(]+)')

_DEAL_LABELS = {"Limited-time deal", "Lightning Deal", "Deal of the Day", "Coupon"}
_AVAILABILITY_STATES = {"In Stock", "Out of Stock", "Temporarily out of stock"}
_SPEC_EXCLUDE = {"Customer Reviews"}
_VARIANT_KEYS = ("Colour Name", "Size", "Style", "Configuration",
                 "Pattern Name", "Material", "Flavour Name", "Scent Name")
_VARIANT_RE = re.compile(
    r'^(' + '|'.join(re.escape(k) for k in _VARIANT_KEYS) + r'):\s*(.+)$'
)


def parse_amazon_product(json_path):
    """Parse an Amazon product page capture JSON and return structured product info."""
    with open(json_path, encoding="utf-8") as f:
        capture = json.load(f)

    text = capture.get("text", "")
    page_title = capture.get("title", "")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    ad = {
        "url": capture.get("url"),
        "captured_at": capture.get("capturedAt"),
        "source": "amazon",
        "title": None,
        "price": None,
        "original_price": None,
        "discount_percent": None,
        "deal_type": None,
        "amazon_choice": False,
        "bought_recently": None,
        "rating": None,
        "review_count": None,
        "availability": None,
        "ships_from": None,
        "sold_by": None,
        "brand": None,
        "selected_variant": None,
        "asin": None,
        "manufacturer": None,
        "best_sellers_rank": None,
        "specs": None,
        "description": None,
    }

    # Title: strip " : Amazon.ca: Category" / " : Amazon.com: Category" from page title
    if page_title:
        clean = re.sub(r'\s*:\s*Amazon\.[a-z.]+:.*$', '', page_title).strip()
        ad["title"] = clean or None

    # Price + discount_percent — anchored to the savings line to avoid picking up
    # prices from the comparison / related-products section.
    savings_idx = None
    for i, line in enumerate(lines):
        m = _SAVINGS_RE.search(line)
        if m:
            ad["price"] = m.group(1)
            ad["discount_percent"] = int(m.group(2))
            savings_idx = i
            break

    # Fallback price: first standalone "$X.XX" line near buy-box markers.
    # Look only forward (not backward) so an adjacent sponsored product's delivery
    # line cannot anchor the wrong price.  The buy-box pattern is always:
    #   $X.XX  →  $X  →  .  →  XX  →  Tomorrow  →  FREE delivery …
    # so the delivery keyword lands exactly 5 lines after the price (index i+5).
    if ad["price"] is None:
        for i, line in enumerate(lines):
            if _PRICE_RE.match(line):
                window = " ".join(lines[i:i + 6])
                if any(k in window for k in ("delivery", "Add to cart", "In Stock", "Buy Now")):
                    ad["price"] = line
                    break

    # Original price: search within 15 lines of the savings line only.
    # Accept either "Was: $X.XX" or the first standalone price larger than the current price.
    if savings_idx is not None:
        cur_val = float(ad["price"].replace("$", "").replace(",", ""))
        for line in lines[savings_idx + 1: savings_idx + 16]:
            m = _WAS_RE.match(line)
            if m:
                ad["original_price"] = m.group(1)
                break
            m = _PRICE_RE.match(line)
            if m:
                val = float(line.replace("$", "").replace(",", ""))
                if val > cur_val:
                    ad["original_price"] = line
                    break

    for line in lines:
        if line in _DEAL_LABELS:
            ad["deal_type"] = line
            break

    ad["amazon_choice"] = "Amazon's Choice" in lines

    for line in lines:
        m = _BOUGHT_RE.match(line)
        if m:
            ad["bought_recently"] = m.group(1)
            break

    for i, line in enumerate(lines):
        m = _RATING_RE.search(line)
        if m:
            ad["rating"] = m.group(1)
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = _REVIEW_RE.match(lines[j])
                if m2 and len(lines[j].strip("(),")) >= 2:
                    ad["review_count"] = int(m2.group(1).replace(",", ""))
                    break
            break

    for line in lines:
        if line in _AVAILABILITY_STATES:
            ad["availability"] = line
            break

    # Ships from / Sold by — two layouts:
    #   Two-line:  "Ships from" \n "Amazon"
    #   One-line:  "Ships from: Amazon"
    for i, line in enumerate(lines):
        if ad["ships_from"] is None:
            if line == "Ships from" and i + 1 < len(lines):
                ad["ships_from"] = lines[i + 1]
            elif line.startswith("Ships from:"):
                ad["ships_from"] = line.split(":", 1)[1].strip()
        if ad["sold_by"] is None:
            if line == "Sold by" and i + 1 < len(lines):
                ad["sold_by"] = lines[i + 1]
            elif line.startswith("Sold by:"):
                ad["sold_by"] = line.split(":", 1)[1].strip()
        if ad["ships_from"] and ad["sold_by"]:
            break

    # Specs: tab-separated "Key\tValue" lines from the product attribute table.
    # Filters out comparison-table noise: digit-only keys, em-dash values,
    # and rows where the value itself contains tabs (multi-column comparison rows).
    specs = {}
    for line in lines:
        if "\t" not in line:
            continue
        key, _, val = line.partition("\t")
        key, val = key.strip(), val.strip()
        if (not key or not val
                or key in _SPEC_EXCLUDE
                or key.isdigit()
                or val in ("—", "no data")
                or "\t" in val):
            continue
        specs[key] = val
    ad["specs"] = specs or None
    ad["brand"] = specs.get("Brand") if specs else None

    # Selected variant: keep the FIRST match per key — later occurrences come from
    # the comparison table and may be malformed.
    variants = {}
    for line in lines:
        m = _VARIANT_RE.match(line)
        if m and m.group(1) not in variants:
            variants[m.group(1)] = m.group(2).strip()
    ad["selected_variant"] = variants or None

    for line in lines:
        m = _ASIN_RE.search(line)
        if m:
            ad["asin"] = m.group(1)
            break

    for line in lines:
        m = _MFR_RE.search(line)
        if m:
            val = m.group(1).strip().lstrip('‎‏ :')
            if val:
                ad["manufacturer"] = val
                break

    for line in lines:
        m = _BSR_RE.search(line)
        if m:
            ad["best_sellers_rank"] = m.group(1).strip()
            break

    # Description: bullet lines between "About this item" and "› See more product details".
    # The first "About this item" is always the page nav header (next line: "Buying options").
    try:
        starts = [i for i, l in enumerate(lines) if l == "About this item"]
        start = next(
            i + 1 for i in starts
            if i + 1 < len(lines) and lines[i + 1] != "Buying options"
        )
        end = next(i for i, l in enumerate(lines) if l.startswith("›") and i > start)
        ad["description"] = "\n".join(lines[start:end]).strip() or None
    except StopIteration:
        pass

    return ad


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python parse_amazon.py <capture.json>")
    else:
        result = parse_amazon_product(path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
