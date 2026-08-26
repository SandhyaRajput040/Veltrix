"""
Tests for src.amazon.product_type_cache

Verifies the cache round-trips correctly and that get_product_types
only calls Amazon for SKUs not already cached -- the whole point of
caching is to avoid a full re-lookup of ~89,000 SKUs every single day.
"""

import json
from unittest.mock import patch

from src.amazon.product_type_cache import get_product_types, load_cache, save_cache


def test_load_cache_returns_empty_dict_when_missing(tmp_path):
    assert load_cache(str(tmp_path / "missing.json")) == {}


def test_save_then_load_roundtrip(tmp_path):
    cache_file = str(tmp_path / "cache.json")
    save_cache(cache_file, {"SKU-1": "LUGGAGE"})
    assert load_cache(cache_file) == {"SKU-1": "LUGGAGE"}


def test_get_product_types_uses_cache_and_skips_amazon_call_for_cached_skus(tmp_path):
    cache_file = str(tmp_path / "cache.json")
    save_cache(cache_file, {"SKU-CACHED": "LUGGAGE"})

    with patch("src.amazon.product_type_cache.fetch_product_type") as mock_fetch:
        result = get_product_types(
            ["SKU-CACHED"], "token", "https://endpoint", "SELLER1", "MKT1", cache_file
        )

    assert result == {"SKU-CACHED": "LUGGAGE"}
    mock_fetch.assert_not_called()


def test_get_product_types_fetches_and_caches_new_skus(tmp_path):
    cache_file = str(tmp_path / "cache.json")

    with patch("src.amazon.product_type_cache.fetch_product_type", return_value="SHOES") as mock_fetch:
        result = get_product_types(
            ["SKU-NEW"], "token", "https://endpoint", "SELLER1", "MKT1", cache_file
        )

    assert result == {"SKU-NEW": "SHOES"}
    mock_fetch.assert_called_once()

    saved = json.loads(open(cache_file).read())
    assert saved == {"SKU-NEW": "SHOES"}


def test_get_product_types_mixes_cached_and_new_skus():
    cache_file_content = {"SKU-OLD": "LUGGAGE"}

    def fake_fetch(access_token, endpoint, seller_id, marketplace_id, sku):
        assert sku == "SKU-NEW"
        return "ELECTRONICS"

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_file = os.path.join(tmp_dir, "cache.json")
        save_cache(cache_file, cache_file_content)

        with patch("src.amazon.product_type_cache.fetch_product_type", side_effect=fake_fetch):
            result = get_product_types(
                ["SKU-OLD", "SKU-NEW"], "token", "https://endpoint", "SELLER1", "MKT1", cache_file
            )

    assert result == {"SKU-OLD": "LUGGAGE", "SKU-NEW": "ELECTRONICS"}