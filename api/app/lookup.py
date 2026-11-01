"""Read-only Open Food Facts adapter. Network responses are untrusted enrichment."""
import http.client
import json
import logging
import math
import os
import urllib.error
import urllib.request

log = logging.getLogger("stoneinventory.lookup")
USER_AGENT = "StoneInventory/0.2 (https://github.com/stonecoder-actual/stoneinventory)"
MAX_BYTES = 2_000_000


def text(value, limit=10000):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize(product):
    name = text(product.get("product_name_en") or product.get("product_name"), 300)
    if not name:
        return None
    nutriments = product.get("nutriments")
    nutriments = nutriments if isinstance(nutriments, dict) else {}
    serving_size = text(product.get("serving_size"), 100)
    suffix = "serving" if serving_size and any(number(nutriments.get(k + "_serving")) is not None for k in ("energy-kcal", "proteins", "fat", "carbohydrates")) else "100g"
    nutrition = {"basis": "per_serving" if suffix == "serving" else "per_100g_or_100ml"}
    for local, remote in {
        "calories_kcal": "energy-kcal", "protein_g": "proteins",
        "carbohydrates_g": "carbohydrates", "fat_g": "fat",
        "fiber_g": "fiber", "sugars_g": "sugars", "sodium_mg": "sodium",
    }.items():
        value = number(nutriments.get(remote + "_" + suffix))
        nutrition[local] = value * 1000 if local == "sodium_mg" and value is not None else value
    if nutrition["calories_kcal"] is None:
        kj = number(nutriments.get("energy-kj_" + suffix))
        if kj is not None:
            nutrition["calories_kcal"] = kj / 4.184
    if all(v is None for k, v in nutrition.items() if k != "basis"):
        nutrition = {}
    quantity = number(product.get("product_quantity"))
    serving = number(product.get("serving_quantity"))
    package_unit = text(product.get("product_quantity_unit"))
    serving_unit = text(product.get("serving_quantity_unit"))
    servings = quantity / serving if quantity and serving and package_unit and package_unit == serving_unit else None
    image = text(product.get("image_front_url") or product.get("image_url"), 2000)
    if image and not image.startswith("https://"):
        image = None
    return {
        "name": name, "brand": text(product.get("brands"), 200),
        "package_size": text(product.get("quantity"), 100),
        "category": text(product.get("categories"), 100),
        "image_url": image, "ingredients": text(product.get("ingredients_text_en") or product.get("ingredients_text")),
        "allergens": text(product.get("allergens"), 2000),
        "dietary_labels": text(product.get("labels"), 2000),
        "serving_size": serving_size, "servings_per_package": servings,
        "nutrition_json": json.dumps(nutrition, allow_nan=False),
        "source_product_id": text(product.get("code"), 100),
        "source_payload_json": json.dumps(product, allow_nan=False),
    }


def fetch_product(barcode):
    """Return (outcome, normalized fields). Never send household quantities or history."""
    # Only allow the official production or staging host; input cannot choose a URL.
    staging = os.environ.get("OFF_STAGING", "0") == "1"
    host = "world.openfoodfacts.net" if staging else "world.openfoodfacts.org"
    request = urllib.request.Request(
        f"https://{host}/api/v3/product/{barcode}.json",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if staging:
        authorization = os.environ.get("OFF_STAGING_AUTH")
        if not authorization:
            return "unavailable", None
        request.add_header("Authorization", authorization)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return "invalid_response", None
        data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(data, dict):
            return "invalid_response", None
        if data.get("status") == 0 or data.get("result", {}).get("id") == "product_not_found":
            return "not_found", None
        product = data.get("product")
        if not isinstance(product, dict):
            return "invalid_response", None
        code = product.get("code")
        # OFF may normalize a UPC by padding with leading zeros; preserve our original key.
        if not isinstance(code, str) or code.lstrip("0") != barcode.lstrip("0"):
            return "invalid_response", None
        fields = normalize(product)
        return ("found", fields) if fields else ("incomplete", None)
    except urllib.error.HTTPError as exc:
        exc.close()
        return ("not_found" if exc.code == 404 else "unavailable"), None
    except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        log.warning("event=lookup_failure barcode=%s", barcode)
        return "unavailable", None
