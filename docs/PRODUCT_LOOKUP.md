# Phase 2 product lookup

New unresolved ADD scans attempt a read-only Open Food Facts product lookup before the atomic inventory operation.
Only the barcode is sent; counts, history, device IDs, and household information are never sent.
Successful identity, nutrition, ingredients, allergens, labels, image URL, and full source product JSON
are stored on Debian. Images themselves are not downloaded. Source fields and fetched time are retained.
Provider data is unverified community information; missing values remain unknown.
Manually entered product records always win, even if saved while a lookup is in flight.

GET endpoints use only local data. POST /api/products/{barcode}/resolve explicitly attempts
resolution (or returns the cache/cooldown result) without changing count or transaction history.
PUT /api/products/{barcode} remains the manual identification workflow until the web UI exists.
There is no bulk refresh or unattended retry worker. Deferred unresolved records retry on a later ADD
or explicit resolution request. Existing known products are never refreshed automatically.

Lookup outcomes: cached, found, not_found, incomplete, unavailable, invalid_response, pending,
deferred, disabled. A lookup failure still permits a valid ADD, retaining its unresolved barcode/count.
The first unresolved scan may wait up to the provider socket timeout (3 seconds; large responses capped at 2 MB).
Network calls do not hold an inventory database write lock. Concurrent scans share a persistent per-barcode
60-second reservation; later simultaneous requests can return the unresolved placeholder while enrichment finishes.
A saved duplicate-request response remains unchanged even if the product is identified afterward;
fetch the current product endpoint for updated details.

Successful records are cached indefinitely. Not-found/incomplete results have a 24-hour cooldown;
network/invalid-response results retry after 60 seconds. A database-persisted global budget spaces
provider attempts by at least 5 seconds (12/minute), below the documented 15/minute product-read limit.
Other apps on the same internet connection may also consume the provider's allowance.
Rate-limited requests fail safely; there are no immediate retry loops.

Nutrition prefers per-serving values where serving information and nutrient values exist.
Otherwise OFF's generic _100g fields are labeled per_100g_or_100ml because the source field alone
does not establish whether the label uses mass or volume. Do not calculate portions from that ambiguous basis.
Sodium grams are converted to milligrams. Energy kJ is converted to kcal only when kcal is absent.
Servings per package are derived only when both quantities have matching explicit units.
The complete original product data preserves micronutrients and other fields for future normalization.

Environment variables:
- LOOKUP_ENABLED=0 disables provider calls (local inventory remains functional).
- OFF_STAGING=1 selects the official staging API and requires OFF_STAGING_AUTH supplied through a private environment variable. Never commit its value.
- Default is the official production API v3 and a project-identifying User-Agent.
No paid providers or API keys are configured.

Schema v2 adds product_lookups and lookup_budget; existing products, quantities, audit records,
and idempotency responses are untouched. A pre-upgrade snapshot is taken before deployment.

Data attribution: Product data from Open Food Facts, https://world.openfoodfacts.org/.
Database: ODbL; individual contents: Database Contents License; product images: CC BY-SA.
Source payloads are runtime data and are not published in this source repository.
Future household UI must display attribution and source links alongside imported information.
Redistribution of the enriched database requires reviewing the applicable share-alike terms.

Official references:
- https://openfoodfacts.github.io/openfoodfacts-server/api/
- https://openfoodfacts.github.io/openfoodfacts-server/api/ref-v3/

Tests mock all provider/network requests. The optional scripts/provider-check.py is a separate,
explicit one-product staging integration check; automated tests never require internet access.
