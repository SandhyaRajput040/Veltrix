"""
Looks up each SKU's Amazon "productType" (required by JSON_LISTINGS_FEED
PATCH messages) via the Listings Items API, and caches the result
locally so we don't re-fetch it for every SKU on every single run.

Design decision: a local JSON cache file, same reasoning as
src/drive/state.py -- a SKU's productType essentially never changes
once listed, this runs once a day, and a JSON file is trivial to
inspect or clear by hand if a SKU's category is ever genuinely
corrected on Amazon's side.
"""

import json
import os

import requests

USER_AGENT = "Veltrix/1.0 (Language=Python)"


class ProductTypeLookupError(Exception):
    """Raised when Amazon's Listings Items API can't return a productType for a SKU."""


def load_cache(cache_file: str) -> dict:
    """Load the local SKU -> productType cache. Returns {} if it doesn't exist yet."""
    if not os.path.isfile(cache_file):
        return {}
    with open(cache_file, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
    return json.loads(content) if content else {}


def save_cache(cache_file: str, cache: dict) -> None:
    """Persist the SKU -> productType cache, creating parent directories as needed."""
    parent_dir = os.path.dirname(cache_file)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, sort_keys=True)


def fetch_product_type(access_token: str, endpoint: str, seller_id: str, marketplace_id: str, sku: str) -> str:
    """
    Look up a single SKU's productType directly from Amazon via the
    Listings Items API's getListingsItem operation.
    """
    response = requests.get(
        f"{endpoint}/listings/2021-08-01/items/{seller_id}/{sku}",
        headers={"x-amz-access-token": access_token, "user-agent": USER_AGENT},
        params={"marketplaceIds": marketplace_id, "includedData": "summaries"},
        timeout=30,
    )
    if response.status_code != 200:
        raise ProductTypeLookupError(
            f"getListingsItem failed for SKU {sku!r} ({response.status_code}): {response.text}"
        )

    body = response.json()
    summaries = body.get("summaries", [])
    if not summaries or "productType" not in summaries[0]:
        raise ProductTypeLookupError(f"No productType found for SKU {sku!r} in response: {body}")

    return summaries[0]["productType"]


def get_product_types(
    skus: list,
    access_token: str,
    endpoint: str,
    seller_id: str,
    marketplace_id: str,
    cache_file: str,
) -> dict:
    """
    Return a {sku: productType} dict for every SKU in `skus`, using the
    local cache where possible and only calling Amazon for SKUs not
    already cached. Newly-looked-up values are saved back to the cache
    before returning, so a later crash doesn't lose already-fetched
    lookups.
    """
    cache = load_cache(cache_file)
    result = {}
    cache_changed = False

    for sku in skus:
        if sku in cache:
            result[sku] = cache[sku]
            continue

        product_type = fetch_product_type(access_token, endpoint, seller_id, marketplace_id, sku)
        cache[sku] = product_type
        result[sku] = product_type
        cache_changed = True

    if cache_changed:
        save_cache(cache_file, cache)

    return result