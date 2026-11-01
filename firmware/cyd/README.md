# StoneInventory CYD firmware

Target: common ESP32-2432S028R (original ESP32), 320x240 ILI9341 display and XPT2046 resistive touch.
The bare ESP32-2432S028 marking does not confirm every revision; verify the diagnostics on your board.
Do not use this pin profile for an ESP32-S3, capacitive-touch board, or a different display without review.

## Start here: first flash on Windows

1. Connect the board to the laptop using a USB **data** cable. Leave the scanner disconnected initially.
2. Open a **local Windows VS Code window**, not SSH: select File > New Window.
3. File > Open Folder, choose this firmware/cyd directory on the laptop.
4. PlatformIO IDE must be installed locally. Let its first setup/download finish.
5. Select the PlatformIO alien-head icon, expand cyd-diagnostics > General, click Build.
   Build compiles the code into a binary; it does not change the board.
6. Expand cyd-diagnostics > General, click Upload.
   Upload writes the diagnostic program to the ESP32, replacing the factory/demo program.
   No erase-flash command is needed.
7. If upload stalls on Connecting, hold BOOT, briefly press/release RESET, then release BOOT
   once writing starts. Do this only when automatic programming does not work.
8. After Upload reports SUCCESS, press RESET if the display has not restarted.
9. You should see red, green, blue, then DISPLAY OK. Tap using a fingertip/fingernail or plastic stylus.
   Raw X/Y/pressure should change. Serial Monitor uses 115200 baud.
10. Report blank screen, inverted colors, or missing touch before trying the terminal.

Use a normal USB port; no external wiring or power supply is needed for these tests.
If the board does not appear under Windows Device Manager > Ports (COM & LPT), first try a known
data cable and another port. A CH340/CP210x driver may be needed depending on the actual USB chip;
identify that chip before choosing a vendor driver. Never install a random driver bundle.
Close Serial Monitor before an upload if the COM port is reported busy.
PlatformIO normally detects the port. If needed, use pio run -e cyd-diagnostics -t upload --upload-port COMx. Do not guess COM numbers.

## Terminal build (after display/touch verification)

Copy include/config.example.h to include/stoneinventory_config.h and fill in:
- the household 2.4 GHz Wi-Fi network name and password;
- the API base address (http://YOUR_SERVER_LAN_IP:8765, no trailing slash);
- a device ID using only letters, digits, underscores, hyphens, or periods.
Do not share the password in chat. stoneinventory_config.h is Git-ignored but compiled firmware contains it.
The backend must be reachable from the Wi-Fi network. Original ESP32 does not support 5 GHz Wi-Fi.

Build/Upload cyd-terminal explicitly. Diagnostics remains the default environment to prevent
accidentally flashing an inventory writer for your first hardware test.
On first boot, tap each calibration cross. Calibration is retained in ESP32 nonvolatile storage.
Home CAL repeats calibration. There is no SD card dependency.

ADD/REMOVE: select action, type the full numeric barcode including leading zeros, press ENTER.
These are REAL inventory operations, quantity one. Unknown ADD retains count and flags the barcode.
EDIT COUNT: type barcode, read current count, enter actual quantity, REVIEW then CONFIRM.
EDIT sends RECONCILE plus the count observed when editing began. Stale edits are rejected.
Only Debian decides counts; the firmware never maintains authoritative inventory.

Each operation gets a random UUID. Before sending it, the firmware saves the request to nonvolatile
storage. Lost reply/Wi-Fi failure/reboot displays RETRY SAFELY and reuses the same ID.
Do not rescan an item whose previous operation is pending. Successful or definitive 4xx replies clear
the pending request; a timeout, malformed reply, or server failure preserves it.
Flashing the app normally retains this nonvolatile storage; do not erase flash to resolve a pending request.
No automatic offline inventory queue or Bluetooth implementation is included yet.

Product responses are parsed with a streaming JSON filter to avoid loading full cached source payloads.
HTTP uses the trusted LAN service. Firmware cannot contact Open Food Facts directly.
No OTA updater or unrequested network service is enabled.

## Compile verification

A compile check may run on Debian in an isolated container. This does not flash the board:
```sh
docker build -f firmware/cyd/Dockerfile.build -t stoneinventory-firmware-builder .
docker run --rm -v "$PWD/firmware/cyd:/project" -v stoneinventory-pio-cache:/root/.platformio stoneinventory-firmware-builder
```

Physical display, touch, Wi-Fi, and scan behavior must still be verified on the board.
Scanner Bluetooth Classic/SPP compatibility is pending physical NETUM testing.

Hardware references:
- https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display
- https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display/blob/main/PINS.md
- https://docs.platformio.org/en/latest/integration/ide/vscode.html
