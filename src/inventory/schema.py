"""
Shared constants for the inventory validation/conversion pipeline.

Single source of truth for the Amazon Inventory Loader column order --
reader.py, validator.py, and writer.py all import from here so the
column list can never drift out of sync between "what we read" and
"what we write".
"""

# Exact column order from the "Template" sheet of Baapstore's Amazon
# Inventory Loader flat files. DO NOT reorder, rename, or drop any of
# these -- Amazon's flat-file upload depends on this exact order.
EXPECTED_COLUMNS = [
    "sku",
    "price",
    "minimum-seller-allowed-price",
    "maximum-seller-allowed-price",
    "quantity",
    "leadtime-to-ship",
    "fulfillment-channel",
    "merchant_shipping_group_name",
]

# The only sheet that contains real inventory data -- every other
# sheet in Baapstore's file (icons, Instructions, Data Validation,
# etc.) is Amazon template metadata and must be ignored.
TEMPLATE_SHEET_NAME = "Template"

# Amazon's SKU limit is 40 BYTES, not 40 characters. A SKU with
# multi-byte characters (e.g. Devanagari, emoji) can be well under 40
# characters and still exceed 40 bytes.
MAX_SKU_BYTES = 40