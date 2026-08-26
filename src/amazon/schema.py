"""
Shared constants for the Amazon SP-API feed submission module.

IMPORTANT: the feed type and endpoints below were verified against
current Amazon SP-API documentation as of this module's creation (see
README.md, Module 4 section, for the deprecation history). Amazon can
and does change these -- if submissions start failing with an
"unsupported feed type" or similar error, re-verify against
https://developer-docs.amazon.com/sp-api/docs/feed-type-values before
assuming the code is broken.
"""

# The modern replacement for the deprecated flat-file inventory feed
# types (POST_FLAT_FILE_INVLOADER_DATA, POST_INVENTORY_AVAILABILITY_DATA,
# POST_FLAT_FILE_PRICEANDQUANTITYONLY_UPDATE_DATA -- all sunset since
# March 31, 2025, per Amazon's deprecation announcement).
FEED_TYPE = "JSON_LISTINGS_FEED"

# JSON_LISTINGS_FEED accepts at most 25,000 messages per submission.
# The full Baapstore catalog (~89,000 SKUs) must be split across
# multiple feed submissions.
MAX_MESSAGES_PER_FEED = 25000

# Amazon.in is served by the EU region SP-API endpoint.
DEFAULT_SP_API_ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"

# Amazon.in's marketplace ID. Double-check this against your own
# Seller Central account / SP-API sandbox before going live --
# marketplace IDs are stable but should never be hardcoded from memory
# alone in a financial-impact system like inventory sync.
DEFAULT_MARKETPLACE_ID = "A21TJRUUN4KGV"

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# A conservative default productType for PATCH operations that only
# touch fulfillment_availability. Amazon's own forum guidance is
# inconsistent about whether a generic value works here -- this
# project looks up each SKU's REAL productType via the Listings Items
# API and caches it (see product_type_cache.py), using this generic
# value only if that lookup is unavailable. Treat reliance on this
# fallback as a signal to investigate, not a normal path.
FALLBACK_PRODUCT_TYPE = "PRODUCT"