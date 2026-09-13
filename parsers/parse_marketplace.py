"""Extract the main details of a Facebook Marketplace ad from a page-capture JSON file.

The capture file has 5 top-level keys: capturedAt, url, title, html, text.
The readable `text` field is used here since it already contains the ad's
info in a predictable order (title, price, listed-date/location, condition,
brand, description, seller info, ...).
"""

import json
import re


def parse_marketplace_ad(json_path):
    """Parse a Facebook Marketplace capture JSON file and return the ad's main info."""
    with open(json_path, encoding="utf-8") as f:
        capture = json.load(f)

    text = capture.get("text", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    ad = {
        "url": capture.get("url"),
        "captured_at": capture.get("capturedAt"),
        "title": None,
        "price": None,
        "original_price": None,
        "listed": None,
        "location": None,
        "condition": None,
        "brand": None,
        "description": None,
        "seller_name": None,
        "seller_rating_count": None,
        "seller_joined": None,
    }

    def value_after(label):
        """Return the line right after a standalone label line, if present."""
        if label in lines:
            i = lines.index(label)
            if i + 1 < len(lines):
                return lines[i + 1]
        return None

    # Title = first line that isn't a feed header like "New posts"
    for line in lines:
        if line.lower() not in ("new posts",):
            ad["title"] = line
            break

    # Price: one amount ("CA$90") or two concatenated when reduced ("CA$200CA$250").
    # When two are present the first is the sale price, the second is the original.
    price_re = re.compile(r"^([A-Z]{0,3}\$\s?[\d,.]+)([A-Z]{0,3}\$\s?[\d,.]+)?$")
    for line in lines:
        m = price_re.match(line)
        if m:
            ad["price"] = m.group(1)
            if m.group(2):
                ad["original_price"] = m.group(2)
            break

    # "Listed 4 days ago in Montréal, QC"
    listed_re = re.compile(r"^Listed .+ in (.+)$")
    for line in lines:
        m = listed_re.match(line)
        if m:
            ad["listed"] = line
            ad["location"] = m.group(1)
            break

    ad["condition"] = value_after("Condition")
    ad["brand"] = value_after("Brand")

    # Description: the free-text block between Brand/Condition and the
    # "Location is approximate" line.
    try:
        start = lines.index(ad["brand"]) + 1 if ad["brand"] else lines.index("Condition") + 2
        end = next(i for i, l in enumerate(lines) if "Location is approximate" in l)
        ad["description"] = "\n".join(lines[start:end]).strip() or None
    except (ValueError, StopIteration):
        pass

    # Seller info
    if "Seller details" in lines:
        i = lines.index("Seller details")
        if i + 1 < len(lines):
            ad["seller_name"] = lines[i + 1]
        if i + 2 < len(lines):
            m = re.match(r"^\((\d+)\)$", lines[i + 2])
            if m:
                ad["seller_rating_count"] = int(m.group(1))

    for line in lines:
        m = re.match(r"^Joined Facebook in (\d{4})$", line)
        if m:
            ad["seller_joined"] = m.group(1)
            break

    return ad


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "1789180289387_capture.json"
    result = parse_marketplace_ad(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
