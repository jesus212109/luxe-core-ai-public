#include <BLEDevice.h>
#include <BLEAdvertising.h>
#include <BLEScan.h>
#include <BLEClient.h>
#include <BLEUtils.h>

/**
 * ESP32 FanLamp BLE Bridge — Public Release Version
 *
 * Firmware for the ESP32 DevKit V1 that acts as a BLE advertising bridge
 * to control the FanLamp Pro F8808 ceiling fan/light.
 *
 * PROTOCOL NOTICE:
 * The 22 byte arrays (11 commands x 2 groups) that encode each BLE
 * advertisement payload are omitted from this public release. They were
 * obtained through original reverse engineering effort and constitute
 * proprietary protocol knowledge.
 *
 * The full firmware source (including byte arrays) is available in the
 * private repository (main-private branch) or by contacting the author.
 *
 * Hardware setup:
 *   - ESP32 DevKit V1
 *   - Connected via USB to the orchestrator server (115200 baud)
 *   - Receives single-character commands over Serial
 *
 * Serial command protocol:
 *   '0'  -> power off       'l' -> light on
 *   '1'..'5' -> fan speed   'm' -> light off
 *   'f' -> fan on           'n' -> night mode
 *   'x' -> fan off          's' -> scan Xiaomi sensor
 */

// =========================================================================
// BLE Advertisement payloads (REDACTED for public release)
// =========================================================================
// The 22 byte arrays (11 commands x 2 groups G1/G2) that encode the BLE
// advertisement payload for each FanLamp command have been removed from
// this public version. They are the result of original reverse engineering.
//
// Each array is 31 bytes long. The structure follows:
//   G1 (0x08F0 group) — fan control
//   G2 (0xF877 group) — light / additional control
//
// The private repository (main-private branch) contains the complete set
// with all arrays verified against the physical F8808 device.
// =========================================================================

const uint8_t COMMAND_COUNT = 0;

// Original arrays redacted. Structure preserved to show the firmware
// interface without exposing the proprietary protocol payloads.
// Contact the author for the complete source.

// -- Xiaomi sensor --
static const char* SENSOR_ADDR = "a4:c1:38:84:03:1c";
static BLEUUID serviceUUID("ebe0ccb0-7a0a-4b0c-8a1a-6ff2997da3a6");
static BLEUUID charUUID("ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6");

void broadcast(const uint8_t* raw) {
    std::string s((const char*)raw, 31);
    BLEAdvertisementData ad;
    ad.addData(s);
    BLEDevice::getAdvertising()->stop();
