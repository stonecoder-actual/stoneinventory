# NETUM NT-1228BL Bluetooth setup

Use Bluetooth Classic SPP (serial), not HID keyboard, BLE, or the USB dongle.
Official scanner settings reference:
https://cf2.scandocs.net/nt-1228bl/en/wireless-bluetooth-settings
https://www.netum.net/pages/user-manuals

## First check: no stock changes

1. Charge/wake the scanner. Unplug its USB receiver/dongle from the laptop.
2. If already paired to a phone/laptop, forget that scanner on that host so it cannot take the connection.
3. In the scanner's own manual, scan Bluetooth transmission mode and Bluetooth SPP Serial Port / SPP Mode.
   Use Normal/instant transmission mode, not storage/batch upload mode.
4. Configure an Enter/CR or CR+LF suffix; disable custom prefixes/suffixes.
5. In local Windows VS Code, choose Project Tasks > cyd-scanner-test > General > Build, then Upload.
   This build only displays received barcodes; it never calls the inventory API or alters saved requests.
6. The ESP32 searches for Netum Bluetooth and initiates the SPP connection. It retries in a background task.
   No Windows Bluetooth pairing is required.
7. Wake the scanner if it sleeps while searching. Wait for BT connected.
8. Scan a product. Its entire barcode (including leading zeros) and a received-scan count should appear.
   Scanner beeps acknowledge reading, not saving an inventory operation.

Your existing private stoneinventory_config.h is preserved. Optional overrides are in config.example.h:
- INVENTORY_SCANNER_NAME if the scanner advertises a different name.
- INVENTORY_SCANNER_MAC to connect to one exact scanner instead of finding it by name.
- INVENTORY_SCANNER_PIN only if the scanner manual specifies a pairing PIN.
Do not paste Wi-Fi passwords or private configuration into chat/Git.
If pairing fails, report the scanner model, LED/beep behavior, and serial status at 115200 baud.
SPP support is documented, but actual pairing/authentication can vary by scanner revision.

## Inventory operation after the scanner test passes

Upload cyd-terminal. Calibration/Wi-Fi configuration and old pending requests are retained.
Select ADD once, then scan item after item; no OK tap is needed.
Each accepted item receives a distinct UUID (including repeated scans of the same product).
A brief product/count confirmation is shown while the next item may be accepted.
REMOVE works the same way. EXIT MODE returns home after accepted requests finish.
BT TEST on the home screen is also available without leaving the terminal build.
EDIT reads the current product/count, then requires quantity entry and explicit confirmation.

Up to eight accepted requests, including the in-flight one, are saved before sending.
A background HTTP worker keeps the scanner input responsive while Debian responds.
The queue is not authoritative inventory; only the server's saved response confirms success.
Every retry and reboot replay uses the same persisted ID. Older single pending requests are migrated on load.
Wi-Fi/server failure suspends sending. RETRY SAFELY resumes saved requests after connection recovery.
When the queue is full, framing fails, or a scan arrives outside an active scan mode, the display reports
that the scan was not accepted and pauses. Saved entries are retained. Resume/retry the saved requests,
then rescan the rejected items. Never rescan an already accepted or uncertain item as a replacement.
Normal successful scanning requires no confirmation; error recovery can require a resume/retry tap.

Barcode input is numeric 8–14 digits, terminated by CR/LF. Split packets and CRLF are supported.
A partial frame times out after 2 seconds and reports a missing suffix rather than inventing a barcode.
Bluetooth receive-buffer overflow is reported and pauses scanning.
Some tasks (touch calibration, USB flashing, reset) are not scanning sessions; do not scan during them.
Use trigger-per-item for initial testing. Scanner auto-trigger can repeatedly read an item and creates
a genuine new operation each time; request deduplication does not deduplicate intentional scanner events.

Bluetooth + Wi-Fi firmware uses the standard huge_app partition table on the 4 MB ESP32.
The existing NVS partition remains at offset 0x9000 / size 0x5000 so calibration and pending requests persist.
No erase-flash action is needed. Before flashing, finish any pending operations in the current firmware.

## Verification

Portable parser/outbox tests on Debian:
g++ -std=c++17 -Wall -Wextra -pedantic -Ifirmware/cyd/include firmware/cyd/tests/scanner_protocol_test.cpp -o /tmp/stoneinventory-scanner-protocol-test
/tmp/stoneinventory-scanner-protocol-test

Compile environments: cyd-diagnostics, cyd-scanner-test, cyd-terminal.
Physical acceptance checks remain: pairing, barcode preservation, two identical product scans producing
two adds, several rapid different scans, offline/server loss/reboot retry, disconnect/reconnect,
unknown products, and zero-stock removal. Compare server history after each intentional operation.
