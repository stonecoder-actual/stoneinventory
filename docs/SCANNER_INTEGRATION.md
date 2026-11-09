# Scanner integration: Bluetooth implementation and physical validation

The NETUM scanner has arrived. Bluetooth Classic/SPP input and continuous modes are implemented; physical pairing and end-to-end validation are the next step.

Required ADD behavior:
- Select ADD once and remain in ADD mode until the user exits explicitly.
- Accept successive barcodes without an OK/confirm tap between items.
- Briefly show product identity and the server-confirmed before/after count, then return to scan-ready ADD mode.
- Give each intentional scan a fresh request ID, including repeated scans of the same barcode for separate packages.
- Retry delivery of an uncertain request with its original persisted ID; never create a replacement operation.
- Pause acceptance while an operation is pending or show a clear busy/error state; do not silently lose scans.
- Validate rapid repeated scans, Wi-Fi/server outages, reconnection, power loss with a pending operation, and unknown products.

First establish scanner Bluetooth compatibility (SPP preferred if supported). The terminal now supports continuous ADD and REMOVE, with manual entry retained as a fallback. See firmware/cyd/BLUETOOTH.md for setup and explicit error recovery.

Hardware progress reported by the user: diagnostic display/touch test passed; terminal Wi-Fi and reading product/count from Debian passed. Scanner transport and continuous scanning are not yet verified.
