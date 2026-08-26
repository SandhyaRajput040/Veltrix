"""
Parses the JSON result document Amazon returns after processing a
JSON_LISTINGS_FEED submission.

IMPORTANT -- VERIFY BEFORE RELYING ON THIS IN PRODUCTION: this parser
is written against Amazon's documented Listings feed result schema,
but has not been exercised against a real Amazon response (no live
SP-API access exists yet for this project). Amazon's actual response
shape should be confirmed against a real sandbox/production result the
first time a feed is genuinely submitted -- see the Module 4 README
section for how to do that safely. If the real shape differs, only
this file should need updating; nothing else in the pipeline parses
feed results directly.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SkuResult:
    sku: str
    status: str  # "ACCEPTED" or "INVALID" (or whatever Amazon actually returns)
    issues: List[dict] = field(default_factory=list)


@dataclass
class FeedResultSummary:
    total: int = 0
    accepted: int = 0
    invalid: int = 0
    sku_results: List[SkuResult] = field(default_factory=list)


def parse_feed_result(document_text: str) -> FeedResultSummary:
    """
    Parse a feed result document's raw JSON text into a
    FeedResultSummary. Never raises on a per-SKU issue -- an
    individual rejected SKU is data to report, not a pipeline failure.
    Raises ValueError only if the document itself isn't valid JSON or
    is missing the expected top-level "results" list entirely (which
    would indicate Amazon's response shape has changed and this parser
    needs updating).
    """
    import json

    try:
        document = json.loads(document_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Feed result document is not valid JSON: {exc}") from exc

    results = document.get("results")
    if results is None:
        raise ValueError(
            "Feed result document has no 'results' field -- Amazon's response "
            "shape may have changed. Inspect the raw document and update "
            "report_parser.py accordingly. Raw document: " + document_text[:1000]
        )

    summary = FeedResultSummary()
    for entry in results:
        status = entry.get("status", "UNKNOWN")
        sku_result = SkuResult(
            sku=entry.get("sku", ""),
            status=status,
            issues=entry.get("issues", []),
        )
        summary.sku_results.append(sku_result)
        summary.total += 1
        if status == "ACCEPTED":
            summary.accepted += 1
        else:
            summary.invalid += 1

    return summary