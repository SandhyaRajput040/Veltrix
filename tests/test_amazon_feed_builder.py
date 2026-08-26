"""
Tests for src.amazon.feed_builder

Verifies the JSON_LISTINGS_FEED message shape (PATCH on
fulfillment_availability only), correct fallback when a SKU's
productType isn't in the lookup, and correct chunking at the
25,000-message-per-feed limit.
"""

from unittest.mock import patch

from src.amazon.feed_builder import build_feed_batches
from src.amazon.schema import FALLBACK_PRODUCT_TYPE, MAX_MESSAGES_PER_FEED


def _row(sku, quantity, leadtime=None, channel=None):
    return {
        "sku": sku,
        "quantity": str(quantity),
        "leadtime-to-ship": leadtime,
        "fulfillment-channel": channel,
    }


def test_single_row_produces_one_batch_with_one_patch_message():
    rows = [_row("SKU-1", 10)]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={"SKU-1": "LUGGAGE"})

    assert len(batches) == 1
    batch = batches[0]
    assert batch["header"]["sellerId"] == "SELLER1"
    assert len(batch["messages"]) == 1

    message = batch["messages"][0]
    assert message["sku"] == "SKU-1"
    assert message["operationType"] == "PATCH"
    assert message["productType"] == "LUGGAGE"
    assert message["patches"][0]["path"] == "/attributes/fulfillment_availability"
    assert message["patches"][0]["value"][0]["quantity"] == 10


def test_message_never_touches_price_or_other_attributes():
    """This project only ever patches quantity -- never price, title, images, etc."""
    rows = [_row("SKU-1", 10)]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={"SKU-1": "LUGGAGE"})

    message = batches[0]["messages"][0]
    assert len(message["patches"]) == 1
    assert message["patches"][0]["path"] == "/attributes/fulfillment_availability"


def test_missing_product_type_falls_back_to_generic_value():
    rows = [_row("SKU-UNKNOWN", 5)]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={})

    assert batches[0]["messages"][0]["productType"] == FALLBACK_PRODUCT_TYPE


def test_leadtime_is_included_when_provided():
    rows = [_row("SKU-1", 10, leadtime="3")]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={"SKU-1": "LUGGAGE"})

    fulfillment_entry = batches[0]["messages"][0]["patches"][0]["value"][0]
    assert fulfillment_entry["lead_time_to_ship_max_days"] == 3


def test_leadtime_is_omitted_when_blank():
    rows = [_row("SKU-1", 10, leadtime="")]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={"SKU-1": "LUGGAGE"})

    fulfillment_entry = batches[0]["messages"][0]["patches"][0]["value"][0]
    assert "lead_time_to_ship_max_days" not in fulfillment_entry


def test_fulfillment_channel_defaults_to_default_when_blank():
    rows = [_row("SKU-1", 10, channel="")]
    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={"SKU-1": "LUGGAGE"})

    fulfillment_entry = batches[0]["messages"][0]["patches"][0]["value"][0]
    assert fulfillment_entry["fulfillment_channel_code"] == "DEFAULT"


def test_rows_are_chunked_at_max_messages_per_feed():
    """A file larger than the per-feed message limit must be split across multiple feed batches."""
    row_count = MAX_MESSAGES_PER_FEED + 10
    rows = [_row(f"SKU-{i}", 1) for i in range(row_count)]

    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={})

    assert len(batches) == 2
    assert len(batches[0]["messages"]) == MAX_MESSAGES_PER_FEED
    assert len(batches[1]["messages"]) == 10


def test_message_ids_restart_at_one_in_each_batch():
    row_count = MAX_MESSAGES_PER_FEED + 5
    rows = [_row(f"SKU-{i}", 1) for i in range(row_count)]

    batches = build_feed_batches(rows, seller_id="SELLER1", product_types={})

    assert batches[0]["messages"][0]["messageId"] == 1
    assert batches[1]["messages"][0]["messageId"] == 1