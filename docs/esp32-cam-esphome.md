# ESP32-CAM with ESPHome

[Back to the getting-started guide](../README.md)

Use an **AI Thinker ESP32-CAM with an OV2640 camera** to supply meter images to Analog Meter Reader. ESPHome provides a camera and an illumination light in Home Assistant. HA AI Studio captures images through those entities and runs recognition locally on the Studio host. The ESP32 runs ESPHome; it does not need the AI-on-the-edge-device firmware or a microSD card.

This guide uses the project's supplied camera configuration, with private names and credentials replaced. Its exposure and lighting values are a starting point for that installation, not universal calibration values. The supplied camera startup reset header is included below.

## Hardware and placement

- AI Thinker ESP32-CAM with OV2640 and PSRAM. A purchase reference is the [ESP32-CAM Development Board including OV2640 at BerryBase](https://www.berrybase.de/esp32-cam-development-board-inkl.-ov2640-kameramodul). The listed package contains the board and camera; plan for a separate USB programming base or UART adapter. It was listed as unavailable when checked on November 1, 2026. Other ESP32 camera boards need their own pin assignments.
- A compatible USB programming base, or a USB-to-UART adapter with **3.3 V logic**. The example uses the stackable **ESP32-CAM-MB Micro-USB base**. For the board, camera and base together, see the [Waveshare ESP32-CAM + OV2640 + ESP32-CAM-MB kit](https://www.waveshare.com/ESP32-CAM.htm). The camera board goes inside the meter housing; check clearance if the USB base remains attached. Plan for a separate housing, USB cable and power supply.
- A stable regulated 5 V supply connected to the board's **5V** input and GND. Use short power leads; choose a supply with headroom for Wi-Fi and the illumination LED (a 1 A supply is a practical starting point). Do not feed 5 V into the 3V3 pin or UART pins.
- A rigid camera mount, usable 2.4 GHz Wi-Fi at the meter, and a way to illuminate the face without glare.

Frame all digits, dials and two fixed alignment features. Keep the camera close to perpendicular to the face. Inspect actual captures at full size: increasing resolution does not repair poor focus. If your lens supports focus adjustment, adjust it carefully at the final mounting distance without forcing glued parts. Keep the meter accessible and its seals intact.

The onboard LED is convenient for initial setup. If it creates a white reflection across the numbers, move or diffuse the light, or use a separate Home Assistant-controlled light. Keep the board dry and allow heat to escape.

## Print or buy a housing

Choose a housing that fits your meter and holds the camera at a fixed, focusable distance. Two starting points:

| Option | Reference | What to check |
| --- | --- | --- |
| Print it yourself | [Water-meter housing on Thingiverse](https://www.thingiverse.com/thing:4573481), linked by the [original AI-on-the-edge project's casing section](https://github.com/jomjol/AI-on-the-edge-device#casing-%EF%B8%8F) | Compare the model dimensions and mounting method with your meter. Follow the designer's printing, assembly and license instructions. |
| Buy a printed housing / adapter | [eBay housing reference](https://www.ebay.de/itm/388457251223?var=655983925792) | Select the matching meter diameter and confirm the chosen variant's contents. Do not assume electronics are included. Current availability and contents could not be independently verified. |

Measure the meter at the housing's attachment point before printing or ordering. Check clearance for the lid, cable exit, camera lens and illumination. A housing for another meter model may need a different adapter even if it looks similar. These links are hardware references, not a claim that these housings fit every meter or every board-and-base combination.

**No microSD card is required for this ESPHome + HA AI Studio setup.** You do not need to buy or insert one, even if a seller bundles a card for the original AI-on-the-edge-device firmware.

If buying an assembled reader, confirm the board and camera model and access for USB/serial flashing. A reader supplied with AI-on-the-edge-device firmware needs to be flashed with ESPHome to follow this guide; buying the hardware does not automatically provide the ESPHome camera and light entities used here.

## 1. Create the ESPHome device

Install and open ESPHome Device Builder using the [official getting-started guide](https://esphome.io/install/getting-started/). Create a device for this camera and edit its YAML.

Use a current stable ESPHome version. The example uses ESP-IDF and encrypted OTA; older installations may not accept that OTA configuration. For an existing device, follow the [official OTA migration instructions](https://esphome.io/components/ota/esphome/#enabling-encryption-on-an-existing-device) before changing its update configuration. A first USB flash can install the encrypted configuration directly.

Keep Wi-Fi credentials, a generated API encryption key and a strong fallback hotspot password in your private ESPHome `secrets.yaml`:

```yaml
wifi_ssid: "YOUR_WIFI_NAME"
wifi_password: "YOUR_WIFI_PASSWORD"
watermeter_camera_api_key: "YOUR_GENERATED_BASE64_API_KEY"
watermeter_camera_ap_password: "YOUR_UNIQUE_FALLBACK_PASSWORD"
```

These are placeholders, not usable credentials. Use the API key generated by Device Builder for this device, or generate a key using the [ESPHome API documentation](https://esphome.io/components/api/#configuration-variables). Preserve the existing key when updating an already paired device. Do not commit your secrets file.

## 2. Camera configuration

Save this as the device configuration, for example `watermeter-camera.yaml`. It preserves the supplied example's camera settings, LED channel and initial brightness. Use a unique device name if you install several cameras.

```yaml
esphome:
  includes:
    - camera_power_reset.h
  on_boot:
    priority: 1100
    then:
      - lambda: camera_power_reset();
  name: watermeter-camera
  friendly_name: Watermeter Camera

esp32:
  variant: esp32
  flash_size: 4MB
  framework:
    type: esp-idf

logger:

api:
  encryption:
    key: !secret watermeter_camera_api_key

ota:
  - platform: esphome
    encryption:

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: Watermeter Camera Fallback
    password: !secret watermeter_camera_ap_password

captive_portal:

psram:
  mode: quad
  speed: 40MHz

i2c:
  - id: camera_i2c
    sda: GPIO26
    scl: GPIO27

esp32_camera:
  name: "Camera"
  external_clock:
    pin: GPIO0
    frequency: 20MHz
  i2c_id: camera_i2c
  data_pins: [GPIO5, GPIO18, GPIO19, GPIO21, GPIO36, GPIO39, GPIO34, GPIO35]
  vsync_pin: GPIO25
  href_pin: GPIO23
  pixel_clock_pin: GPIO22
  power_down_pin: GPIO32
  resolution: 640x480
  jpeg_quality: 12
  max_framerate: 2 fps
  idle_framerate: 0.1 fps
  aec_mode: auto
  ae_level: 2

output:
  - platform: ledc
    pin: GPIO4
    channel: 2
    id: camera_illumination_led

light:
  - platform: monochromatic
    name: "Illumination"
    output: camera_illumination_led
    default_transition_length: 0s
    initial_state:
      state: "OFF"
      brightness: 100%

button:
  - platform: restart
    name: "Restart ESP32"
    entity_category: diagnostic
```

The pin assignment follows the [ESPHome AI Thinker camera example](https://esphome.io/components/esp32_camera/#configuration-examples). Keep GPIO16 reserved for PSRAM. GPIO4 controls the onboard illumination LED; this setup does not use the SD card interface. LEDC channel 2 avoids the camera PWM timer conflict documented by ESPHome.

The explicit [PSRAM configuration](https://esphome.io/components/psram/) uses quad mode at 40 MHz. The empty OTA `encryption:` block inherits the API encryption key, as described in the [OTA documentation](https://esphome.io/components/ota/esphome/#encryption).

### Camera startup reset header

Create `camera_power_reset.h` in the same directory as `watermeter-camera.yaml`. Copy the supplied implementation below unchanged. This file is required by the YAML's `includes` entry; ESPHome does not generate it automatically.

```text
/config/esphome/
├── watermeter-camera.yaml
├── camera_power_reset.h
└── secrets.yaml
```

The path above is the usual Home Assistant ESPHome configuration location. For another installation, use the directory containing your device YAML.

```cpp
#pragma once
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Runs before I2C and camera setup, never against a running camera driver.
inline void camera_power_reset() {
  gpio_set_direction(GPIO_NUM_32, GPIO_MODE_OUTPUT);
  gpio_set_level(GPIO_NUM_32, 1);
  vTaskDelay(pdMS_TO_TICKS(500));
  gpio_set_level(GPIO_NUM_32, 0);
  vTaskDelay(pdMS_TO_TICKS(100));
}
```

The boot callback uses priority `1100` to run this routine before I2C and camera setup. It drives the camera's power-down pin GPIO32 high for 500 ms, then low and waits another 100 ms before initialization continues. This is a camera power-down sequence, not a power cycle of the entire ESP32 board.

Keep this call in the early boot callback only; do not invoke it from a button or automation while the camera driver is running. The GPIO32 assignment is specific to the AI Thinker wiring used here. Verify camera initialization after both a cold power-on and a software restart.

## 3. Flash and connect to Home Assistant

For a USB programming base, follow its boot/reset procedure. With a separate USB-to-UART adapter, disconnect power before wiring:

| Adapter / supply | ESP32-CAM |
| --- | --- |
| Adapter TX, 3.3 V logic | U0R / GPIO3 |
| Adapter RX | U0T / GPIO1 |
| Common ground | GND |
| Regulated 5 V supply | 5V |
| Temporary boot jumper | GPIO0 to GND |

Use one power source; do not connect competing adapter and external power outputs. A small adapter's 3.3 V output is not a suitable camera power supply.

1. Validate the YAML in Device Builder, then choose **Install** and the USB/serial method appropriate to where your adapter is connected. If downloading firmware for a separate flasher, use the factory image for the initial installation.
2. For manual wiring, hold GPIO0 at GND while resetting or powering up to enter the serial bootloader.
3. After flashing, disconnect power, remove the GPIO0-to-GND jumper, and power up normally. GPIO0 is also the camera clock during normal operation.
4. Check logs for successful Wi-Fi, PSRAM and camera initialization.
5. In Home Assistant, open **Settings → Devices & services** and configure the discovered ESPHome device. If discovery is unavailable, add the ESPHome integration using its local IP address. Enter the matching encryption key if requested. See the [Home Assistant ESPHome integration](https://www.home-assistant.io/integrations/esphome/).
6. Open the new camera entity and toggle its **Illumination** light. Record the actual entity IDs; Home Assistant may choose different IDs from the examples below.

A separate camera HTTP server is not needed for this integration. Home Assistant must be able to reach the ESPHome device over the local network.

## 4. Set focus, illumination and exposure

Use the illumination that will also be used for recognition. The example starts the light off with an initial brightness of 100%; this is the supplied installation's setting, not a recommendation to run the LED continuously. Set a lower brightness in Home Assistant if necessary and verify the brightness used on subsequent captures.

**`ae_level: 2` brightens automatic exposure; it does not prevent overexposure.** ESPHome allows compensation from -2 to 2 in automatic mode. See the [camera exposure settings](https://esphome.io/components/esp32_camera/#configuration-variables).

If digits disappear into white areas:

1. Remove direct reflections by adjusting the mount or illumination angle.
2. Reduce LED brightness and take another capture.
3. Lower `ae_level` from `2` toward `0`, then try `-1` or `-2` if needed. Change one setting at a time.
4. Wait for exposure to settle after switching on the light. Judge the captured image, not only the live preview.

Start with the supplied 640×480 image size. If small digits remain too small despite sharp focus and good framing, try a higher resolution and check capture reliability. After changing resolution, orientation or mounting, capture a new reference and recheck every reading and alignment frame.

## 5. Configure Analog Meter Reader

1. Open the Action configuration and select the ESPHome camera under **Camera settings**, for example `camera.watermeter_camera_camera`.
2. Select its illumination entity, for example `light.watermeter_camera_illumination`, or the separate light illuminating the meter.
3. Start with a **2-second wait before capture**. If the first image is dark or stale, enable **Discard first camera image** and start with a **1-second interval between captures**. Adjust using actual captures.
4. Choose **Capture reference images**, then configure alignment, digits and dials using the [main guide](../README.md#3-draw-and-assign-frames).
5. Use **Capture & recognize** repeatedly, including after the camera has been idle. When requiring two matching captures, configure two images and check both results.
6. Save the Action and configure the Device's measurement interval only after recognition is reliable.

The Action restores illumination after capture; a light already on stays on. Draft camera tests operate the selected real camera/light but do not update Device readings or publish MQTT. ESPHome frame rates control camera acquisition, while the Studio Device measurement interval controls scheduled readings.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Serial upload cannot connect | Cross TX/RX, share GND, use 3.3 V UART logic, and reset with GPIO0 grounded. Check the USB cable and selected serial port. |
| Board does not start after flashing | Remove the GPIO0 boot jumper and reset. |
| Camera initialization or PSRAM fails | Check the exact board variant, pin mapping, PSRAM configuration and camera ribbon seating with power disconnected. |
| Resets when Wi-Fi or the LED starts | Check power supply, cable length and voltage drop before changing camera settings. |
| White reflections or washed-out digits | Reduce illumination, change its angle and lower exposure compensation. |
| First image is dark or old | Increase the capture wait, discard the first image and test again after an idle period. |
| Images work after power cycling but not after restart | Check that the supplied header and priority-1100 boot callback are both present, then compare cold boot and software restart logs. |
| Camera works in Home Assistant but not Studio | Check Studio's Home Assistant connection and the exact selected camera entity. |
| OTA refuses an older device | Follow the encrypted OTA migration guide linked above, or flash by USB. |
| Reading fails despite a clear image | Inspect alignment and reading frames using the recognition report. |

The example was checked against the linked ESPHome documentation. It still requires configuration validation, a firmware build and testing on your physical board; this guide does not claim hardware validation.
