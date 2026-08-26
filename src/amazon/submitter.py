"""
Orchestrates submitting validated inventory rows to Amazon -- or, in
fallback mode, preparing them for manual upload instead.

FALLBACK MODE (default until SP-API is authorized): writes the feed
content that WOULD be submitted into a ready_to_upload/ folder and
stops there. This never calls Amazon and never pretends an upload
happened -- see submit_fallback()'s docstring.

LIVE MODE: authenticates, looks up each SKU's productType, builds
JSON_LISTINGS_FEED batches, and submits/polls/parses results via
src/amazon/client.py.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List

from src.amazon.auth import get_access_token
from src.amazon.client import (
    create_feed,
    create_feed_document,
    get_feed,
    get_feed_document,
    download_feed_document,
    upload_feed_document,
)
from src.amazon.feed_builder import build_feed_batches
from src.amazon.product_type_cache import get_product_types
from src.amazon.report_parser import SkuResult, parse_feed_result
from src.amazon.schema import FEED_TYPE


class SubmissionError(Exception):
    """Raised when a live feed submission fails or never reaches a terminal status."""


@dataclass
class SubmissionResult:
    mode: str  # "fallback" or "live"
    total_messages: int = 0
    feed_ids: List[str] = field(default_factory=list)
    total_accepted: int = 0
    total_invalid: int = 0
    sku_results: List[SkuResult] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)


def submit_fallback(rows: list, seller_id: str, product_types: dict, output_dir: str, source_name: str) -> SubmissionResult:
    """
    FALLBACK MODE: write the JSON_LISTINGS_FEED batches that would be
    submitted into `output_dir` (ready_to_upload/) instead of calling
    Amazon. This is the safe default until SP-API is authorized, and
    remains a legitimate permanent option since Amazon's Seller
    Central UI still accepts manual uploads.

    Never marks anything as "submitted" or "uploaded" -- the returned
    SubmissionResult only reports what was written to disk.
    """
    os.makedirs(output_dir, exist_ok=True)
    batches = build_feed_batches(rows, seller_id, product_types)

    output_paths = []
    for index, batch in enumerate(batches, start=1):
        path = os.path.join(output_dir, f"{source_name}_feed_batch_{index}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(batch, fh, indent=2)
        output_paths.append(path)

    return SubmissionResult(
        mode="fallback",
        total_messages=len(rows),
        output_paths=output_paths,
    )


def wait_for_feed_completion(
    access_token: str,
    endpoint: str,
    feed_id: str,
    poll_interval_seconds: int = 30,
    max_poll_attempts: int = 40,
) -> dict:
    """
    Poll getFeed until it reaches a terminal status (DONE, CANCELLED,
    or FATAL), or raise SubmissionError if it never does within
    max_poll_attempts. Terminal-but-not-DONE statuses are returned to
    the caller (not raised here) so the caller can decide how to
    report a cancelled/fatal feed -- only "never finished" is this
    function's own failure.
    """
    for _ in range(max_poll_attempts):
        feed = get_feed(access_token, endpoint, feed_id)
        if feed["processingStatus"] in ("DONE", "CANCELLED", "FATAL"):
            return feed
        time.sleep(poll_interval_seconds)

    raise SubmissionError(
        f"Feed {feed_id} did not reach a terminal status within {max_poll_attempts} poll attempts."
    )


def submit_live(
    rows: list,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    seller_id: str,
    marketplace_id: str,
    endpoint: str,
    product_type_cache_file: str,
    poll_interval_seconds: int = 30,
    max_poll_attempts: int = 40,
) -> SubmissionResult:
    """
    LIVE MODE: authenticate, look up productTypes, build feed batches,
    and actually submit them to Amazon, waiting for each to finish
    processing and parsing the result.

    Raises SubmissionError if any batch ends in a CANCELLED or FATAL
    status, or never finishes -- a partial/ambiguous outcome must never
    be silently treated as success.
    """
    access_token = get_access_token(client_id, client_secret, refresh_token)

    skus = [row["sku"] for row in rows]
    product_types = get_product_types(
        skus, access_token, endpoint, seller_id, marketplace_id, product_type_cache_file
    )

    batches = build_feed_batches(rows, seller_id, product_types)
    result = SubmissionResult(mode="live", total_messages=len(rows))

    for batch in batches:
        content = json.dumps(batch).encode("utf-8")

        document_info = create_feed_document(access_token, endpoint)
        upload_feed_document(document_info["url"], content, "application/json; charset=UTF-8")

        feed_id = create_feed(
            access_token, endpoint, FEED_TYPE, [marketplace_id], document_info["feedDocumentId"]
        )
        result.feed_ids.append(feed_id)

        final_feed_state = wait_for_feed_completion(
            access_token, endpoint, feed_id, poll_interval_seconds, max_poll_attempts
        )
        status = final_feed_state["processingStatus"]
        if status != "DONE":
            raise SubmissionError(f"Feed {feed_id} ended with status {status!r}, not DONE.")

        result_document_id = final_feed_state.get("resultFeedDocumentId")
        if result_document_id:
            document_meta = get_feed_document(access_token, endpoint, result_document_id)
            content_text = download_feed_document(
                document_meta["url"], document_meta.get("compressionAlgorithm")
            )
            batch_summary = parse_feed_result(content_text)
            result.total_accepted += batch_summary.accepted
            result.total_invalid += batch_summary.invalid
            result.sku_results.extend(batch_summary.sku_results)

    return result


def _read_amazon_txt_rows(txt_path: str) -> list:
    """
    Read rows back out of a Module 3-generated Amazon TXT file, for
    the manual smoke test below. Not used anywhere in the tested
    pipeline logic -- Module 5 will wire modules together in memory
    instead of round-tripping through a file.
    """
    with open(txt_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(dict(zip(header, values)))
    return rows


if __name__ == "__main__":
    # Manual smoke-test entry point: submits (or fallback-writes) every
    # Amazon TXT file currently sitting in data/output/ (produced by
    # Module 3). Respects AMAZON_FALLBACK_MODE from .env -- defaults to
    # fallback (safe) unless explicitly set to False.
    import glob

    from src.config.settings import settings

    txt_files = glob.glob("data/output/*.txt")
    if not txt_files:
        print("No Amazon TXT files found in data/output/. Run Module 3's pipeline first.")

    for txt_path in txt_files:
        rows = _read_amazon_txt_rows(txt_path)
        source_name = os.path.splitext(os.path.basename(txt_path))[0]

        if settings.amazon_fallback_mode:
            result = submit_fallback(
                rows,
                seller_id=settings.amazon_seller_id or "UNKNOWN_SELLER_ID",
                product_types={},
                output_dir="ready_to_upload",
                source_name=source_name,
            )
            print(
                f"[FALLBACK MODE -- NOT submitted to Amazon] {source_name}: "
                f"{result.total_messages} rows written to {result.output_paths}"
            )
        else:
            result = submit_live(
                rows,
                client_id=settings.amazon_lwa_client_id,
                client_secret=settings.amazon_lwa_client_secret,
                refresh_token=settings.amazon_refresh_token,
                seller_id=settings.amazon_seller_id,
                marketplace_id=settings.amazon_marketplace_id,
                endpoint=settings.amazon_sp_api_endpoint,
                product_type_cache_file="state/amazon_product_type_cache.json",
            )
            print(
                f"[LIVE] {source_name}: feeds {result.feed_ids}, "
                f"accepted {result.total_accepted}, invalid {result.total_invalid}"
            )