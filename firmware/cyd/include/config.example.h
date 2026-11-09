#pragma once
// Copy this file to stoneinventory_config.h and edit locally. stoneinventory_config.h is excluded from Git.
#define INVENTORY_WIFI_SSID "YOUR_2_4_GHZ_WIFI_NAME"
#define INVENTORY_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define INVENTORY_API_BASE "http://YOUR_SERVER_LAN_IP:8765"
#define INVENTORY_DEVICE_ID "kitchen-cyd-01"

// Optional Bluetooth overrides. Existing private config files do not need these defaults.
#define INVENTORY_SCANNER_NAME "Netum Bluetooth"
#define INVENTORY_SCANNER_MAC "" // optional exact scanner MAC address, otherwise connect by name
#define INVENTORY_SCANNER_PIN "" // optional pairing PIN from your scanner manual
