"""
Builds JSON_LISTINGS_FEED request bodies from Module 3's validated
inventory rows.

Each row becomes one PATCH message that updates only
`fulfillment_availability` (quantity, and lead time if provided) for
an existing listing -- this never touches price, title, images, or any
other listing attribute, matching this project's narrow "just sync
quantity" purpose.

Amazon caps a single feed submission at MAX_MESSAGES_PER_FEED messages,
so a large file (e.g. the ~89,000-row full catalog) must be split
across multiple feed submissions. This module returns a list of
already-chunked feed bodies; submitter.py is responsible for
submitting each one as a separate feed.
"""

from src.amazon.schema import FALLBACK_PRODUCT_TYPE, MAX_MESSAGES_PER_FEED

DEFAULT_FULFILLMENT_CHANNEL_CODE = "DEFAULT"  # merchant-fulfilled (MFN) inventory


def _build_message(message_id: int, row: dict, product_type: str) -> dict:
    fulfillment_entry = {
        "fulfillment_channel_code": row.get("fulfillment-channel") or DEFAULT_FULFILLMENT_CHANNEL_CODE,
        "quantity": int(row["quantity"]),
    }

    lead_time = row.get("leadtime-to-ship")
    if lead_time:
        fulfillment_entry["lead_time_to_ship_max_days"] = int(lead_time)

    return {
        "messageId": message_id,
        "sku": row["sku"],
        "operationType": "PATCH",
        "productType": product_type,
        "patches": [
            {
                "op": "replace",
                "path": "/attributes/fulfillment_availability",
                "value": [fulfillment_entry],
            }
        ],
    }


def build_feed_batches(rows: list, seller_id: str, product_types: dict) -> list:
    """
    Build one or more complete JSON_LISTINGS_FEED bodies from `rows`
    (Module 3's cleaned valid_rows -- dicts with string values as
    written to the Amazon TXT). `product_types` maps sku -> productType
    (see product_type_cache.py); a SKU missing from that dict falls
    back to FALLBACK_PRODUCT_TYPE (see schema.py for the caveat about
    relying on that fallback).

    Returns a list of dicts, each a complete feed body ready to be
    JSON-serialized and uploaded, chunked so no single feed exceeds
    MAX_MESSAGES_PER_FEED messages.
    """
    batches = []
    current_messages = []

    for row in rows:
        product_type = product_types.get(row["sku"], FALLBACK_PRODUCT_TYPE)
        message_id = len(current_messages) + 1
        current_messages.append(_build_message(message_id, row, product_type))

        if len(current_messages) == MAX_MESSAGES_PER_FEED:
            batches.append(_build_feed_body(seller_id, current_messages))
            current_messages = []

    if current_messages:
        batches.append(_build_feed_body(seller_id, current_messages))

    return batches


def _build_feed_body(seller_id: str, messages: list) -> dict:
    return {
        "header": {"sellerId": seller_id, "version": "2.0"},
        "messages": messages,
    }