"""Route a capture JSON to the correct parser based on its URL."""

import json
from pathlib import Path

from .parse_marketplace import parse_marketplace_ad
from .parse_amazon import parse_amazon_product


def parse_capture(json_path):
    """Dispatch to the right parser based on the capture's URL."""
    url = json.loads(Path(json_path).read_text(encoding="utf-8")).get("url", "")
    if "amazon." in url:
        return parse_amazon_product(json_path)
    return parse_marketplace_ad(json_path)
