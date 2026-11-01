# Scanner integration: next hardware milestone

Deferred until the NETUM scanner arrives.

Required ADD behavior:
- Select ADD once and remain in ADD mode until the user exits explicitly.
- Accept successive barcodes without an OK/confirm tap between items.
- Briefly show product identity and the server-confirmed before/after count, then return to scan-ready ADD mode.
- Give each intentional scan a fresh request ID, including repeated scans of the same barcode for separate packages.
- Retry delivery of an uncertain request with its original persisted ID; never create a replacement operation.
- Pause acceptance while an operation is pending or show a clear busy/error state; do not silently lose scans.
- Validate rapid repeated scans, Wi-Fi/server outages, reconnection, power loss with a pending operation, and unknown products.

First establish scanner Bluetooth compatibility (SPP preferred if supported). The existing manual-entry prototype does not implement continuous scanning. Do not change ADD behavior ahead of the scanner task solely to mark this requirement complete.

Hardware progress reported by the user: diagnostic display/touch test passed; terminal Wi-Fi and reading product/count from Debian passed. Scanner transport and continuous scanning are not yet verified.
