/**
 * @file main.cpp
 * @brief Smart Power Outlet - PlatformIO (Arduino Framework)
 *
 * Port từ Smart_Power_Outlet_ESP (ESP-IDF) sang Arduino framework.
 * Hỗ trợ:
 *   - ESP32-WROOM-32  (env: esp32wroom, Reset button: GPIO 0 / BOOT)
 *   - ESP32-P4        (env: esp32p4,    Reset button: GPIO 35)
 *   - ESP8266         (env: esp8266,   Reset button: GPIO 0 / D3)
 *
 * Tính năng:
 *   1. WiFi Captive Portal Provisioning (WiFiManager)
 *   2. MQTT control relay qua topic "home/socket/cmd" (ON/OFF)
 *   3. Publish trạng thái relay lên "home/socket/status"
 *   4. Relay trên RELAY_GPIO (GPIO 20), khôi phục trạng thái sau reboot (Preferences)
 *   5. Reset button (giữ RESET_BTN_GPIO 3 giây) → xoá WiFi credentials → restart
 */

#if defined(BOARD_ESP8266) || defined(ARDUINO_ARCH_ESP8266)
#define SMART_OUTLET_ESP8266 1
#endif

#include <Arduino.h>
#include <PubSubClient.h>

#ifdef SMART_OUTLET_ESP8266
#include <EEPROM.h>
#include <ESP8266WiFi.h>
#else
#include <Preferences.h>
#include <WiFi.h>
#endif

#include "secrets.h"
#include "wifi_prov.h"
#include "debug_log.h"

// =========================================================================
// Cấu hình pin theo board (được truyền qua build_flags trong platformio.ini)
// =========================================================================
#ifndef RELAY_GPIO
#  define RELAY_GPIO     20
#endif

#ifndef RESET_BTN_GPIO
#  ifdef BOARD_ESP32P4
#    define RESET_BTN_GPIO  35
#  else
#    define RESET_BTN_GPIO   0   // GPIO 0 = BOOT button trên WROOM, có pull-up nội
#  endif
#endif

// =========================================================================
// Cấu hình MQTT
// =========================================================================
#define MQTT_HOST           "mqtt.toolhub.app"
#define MQTT_PORT           1883
#define MQTT_TOPIC_CMD      "home/socket/cmd"
#define MQTT_TOPIC_STATUS   "home/socket/status"
#define MQTT_TOPIC_PROV     "home/socket/provisioning"
#define MQTT_CLIENT_ID      "smart_outlet_01"

// =========================================================================
// Cấu hình Reset Button
// =========================================================================
#define RESET_BTN_HOLD_MS   3000   // Giữ 3 giây để reset WiFi

// =========================================================================
// Cấu hình NVS cho relay state
// =========================================================================
#define NVS_RELAY_NAMESPACE "relay"
#define NVS_RELAY_KEY       "state"

// =========================================================================
// Biến toàn cục
// =========================================================================
static WiFiClient   s_wifi_client;
static PubSubClient s_mqtt(s_wifi_client);
#ifndef SMART_OUTLET_ESP8266
static Preferences  s_relay_prefs;
#endif

// Trạng thái relay hiện tại
static bool s_relay_state = false;

// Reset button debounce
static bool          s_btn_pressed     = false;
static unsigned long s_btn_press_time  = 0;

// MQTT reconnect timing
static unsigned long s_mqtt_last_attempt = 0;
#define MQTT_RECONNECT_INTERVAL_MS 5000

#ifdef SMART_OUTLET_ESP8266
static bool s_eeprom_ready = false;

static void ensure_eeprom_ready()
{
    if (!s_eeprom_ready) {
        EEPROM.begin(ESP8266_EEPROM_SIZE);
        s_eeprom_ready = true;
    }
}
#endif

// =========================================================================
// Forward declarations
// =========================================================================
static void relay_state_save(bool state);
static bool relay_state_load();
static void relay_set(bool on);
static void publish_status(bool on);
static void mqtt_connect();
static void mqtt_callback(char *topic, byte *payload, unsigned int length);
static void reset_button_loop();
static void on_wifi_connected();
static void on_wifi_disconnected();

// =========================================================================
// Relay helpers
// =========================================================================

static void relay_state_save(bool state)
{
#ifdef SMART_OUTLET_ESP8266
    struct RelayState {
        uint32_t magic;
        uint8_t state;
        uint8_t reserved[3];
    } rs = {0};

    rs.magic = ESP8266_EEPROM_RELAY_MAGIC;
    rs.state = state ? 1 : 0;

    ensure_eeprom_ready();
    EEPROM.put(ESP8266_EEPROM_RELAY_OFFSET, rs);
    EEPROM.commit();
    LOGF("[relay] State saved to EEPROM: %s\n", state ? "ON" : "OFF");
#else
    s_relay_prefs.begin(NVS_RELAY_NAMESPACE, /*readOnly=*/ false);
    s_relay_prefs.putBool(NVS_RELAY_KEY, state);
    s_relay_prefs.end();
    LOGF("[relay] State saved to NVS: %s\n", state ? "ON" : "OFF");
#endif
}

static bool relay_state_load()
{
#ifdef SMART_OUTLET_ESP8266
    struct RelayState {
        uint32_t magic;
        uint8_t state;
        uint8_t reserved[3];
    } rs = {0};

    ensure_eeprom_ready();
    EEPROM.get(ESP8266_EEPROM_RELAY_OFFSET, rs);

    bool state = (rs.magic == ESP8266_EEPROM_RELAY_MAGIC) ? (rs.state != 0) : false;
    LOGF("[relay] State loaded from EEPROM: %s\n", state ? "ON" : "OFF");
    return state;
#else
    s_relay_prefs.begin(NVS_RELAY_NAMESPACE, /*readOnly=*/ true);
    bool state = s_relay_prefs.getBool(NVS_RELAY_KEY, false);
    s_relay_prefs.end();
    LOGF("[relay] State loaded from NVS: %s\n", state ? "ON" : "OFF");
    return state;
#endif
}

static void relay_set(bool on)
{
    s_relay_state = on;
    digitalWrite(RELAY_GPIO, on ? HIGH : LOW);
    relay_state_save(on);
    publish_status(on);
    LOGF("[relay] Set to: %s\n", on ? "ON" : "OFF");
}

// =========================================================================
// MQTT helpers
// =========================================================================

static void publish_status(bool on)
{
    if (!s_mqtt.connected()) {
        return;
    }
    const char *payload = on ? "ON" : "OFF";
    s_mqtt.publish(MQTT_TOPIC_STATUS, payload, /*retain=*/ true);
}

static void mqtt_callback(char *topic, byte *payload, unsigned int length)
{
    char buf[16] = {0};
    if (length >= sizeof(buf)) {
        length = sizeof(buf) - 1;
    }
    memcpy(buf, payload, length);
    buf[length] = '\0';

    LOGF("[mqtt] Received [%s]: %s\n", topic, buf);

    if (strcmp(buf, "ON") == 0) {
        relay_set(true);
    } else if (strcmp(buf, "OFF") == 0) {
        relay_set(false);
    } else {
        LOGLN("[mqtt] Unknown command, ignoring.");
    }
}

static void mqtt_connect()
{
    if (s_mqtt.connected()) {
        return;
    }

    unsigned long now = millis();
    if (now - s_mqtt_last_attempt < MQTT_RECONNECT_INTERVAL_MS) {
        return;  // Chưa đến lúc retry
    }
    s_mqtt_last_attempt = now;

    LOGF("[mqtt] Connecting to %s:%d ...\n", MQTT_HOST, MQTT_PORT);

    bool ok = s_mqtt.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD);
    if (ok) {
        LOGLN("[mqtt] Connected!");
        s_mqtt.subscribe(MQTT_TOPIC_CMD, /*qos=*/ 1);
        s_mqtt.publish(MQTT_TOPIC_PROV, "Started", /*retain=*/ true);
        // Publish trạng thái relay hiện tại ngay khi kết nối lại
        publish_status(s_relay_state);
    } else {
        LOGF("[mqtt] Failed, rc=%d, retry in %dms\n",
                      s_mqtt.state(), MQTT_RECONNECT_INTERVAL_MS);
    }
}

// =========================================================================
// WiFi event callbacks (được gọi từ wifi_prov)
// =========================================================================

static void on_wifi_connected()
{
    LOGLN("[main] WiFi connected → starting MQTT");
    mqtt_connect();
}

static void on_wifi_disconnected()
{
    LOGLN("[main] WiFi disconnected → MQTT will stop");
    // PubSubClient sẽ tự nhận ra mất kết nối qua WiFiClient
}

// =========================================================================
// Reset button logic
// =========================================================================

static void reset_button_loop()
{
    // RESET_BTN_GPIO là active LOW (có pull-up nội hoặc ngoài)
    int level = digitalRead(RESET_BTN_GPIO);

    if (level == LOW) {
        // Nút đang được nhấn
        if (!s_btn_pressed) {
            s_btn_pressed    = true;
            s_btn_press_time = millis();
            LOGF("[btn] Button pressed (GPIO %d), hold 3s to reset WiFi...\n",
                          RESET_BTN_GPIO);
        } else {
            unsigned long hold = millis() - s_btn_press_time;
            if (hold >= RESET_BTN_HOLD_MS) {
                LOGLN("[btn] 3s hold detected! Erasing WiFi credentials...");
                wifi_prov_erase_credentials();
                LOGLN("[btn] Restarting in 2 seconds...");
                delay(2000);
                ESP.restart();
            }
        }
    } else {
        // Nút đã thả
        if (s_btn_pressed) {
            unsigned long hold = millis() - s_btn_press_time;
            LOGF("[btn] Button released after %lu ms\n", hold);
            s_btn_pressed = false;
        }
    }
}

// =========================================================================
// Setup & Loop
// =========================================================================

void setup()
{
    Serial.begin(115200);
    delay(200);

    LOGLN("\n========================================");

#ifdef BOARD_ESP8266
    LOGLN("[main] Board: ESP8266");
#elif defined(BOARD_ESP32P4)
    LOGLN("[main] Board: ESP32-P4");
#else
    LOGLN("[main] Board: ESP32-WROOM-32");
#endif

    LOGF("[main] Relay GPIO: %d | Reset Button GPIO: %d\n",
                  RELAY_GPIO, RESET_BTN_GPIO);
    LOGLN("========================================\n");

    // --- Khởi tạo Relay GPIO ---
    pinMode(RELAY_GPIO, OUTPUT);
    s_relay_state = relay_state_load();
    digitalWrite(RELAY_GPIO, s_relay_state ? HIGH : LOW);
    LOGF("[main] Relay initialized to: %s\n", s_relay_state ? "ON" : "OFF");

    // --- Khởi tạo Reset Button GPIO ---
#if defined(BOARD_ESP32P4)
    // GPIO 35 trên P4: input-only, cần pull-up ngoài trên mạch
    pinMode(RESET_BTN_GPIO, INPUT);
#else
    // GPIO 0 trên WROOM/ESP8266: có pull-up nội (INPUT_PULLUP)
    pinMode(RESET_BTN_GPIO, INPUT_PULLUP);
#endif

    // --- Cấu hình MQTT ---
    s_mqtt.setServer(MQTT_HOST, MQTT_PORT);
    s_mqtt.setCallback(mqtt_callback);
    s_mqtt.setKeepAlive(60);
    s_mqtt.setBufferSize(256);

    // --- Khởi động WiFi Provisioning ---
    wifi_prov_start(on_wifi_connected, on_wifi_disconnected);

    LOGLN("[main] Smart outlet started.");
    LOGF("[main] Hold GPIO %d for 3s to reset WiFi credentials.\n",
                  RESET_BTN_GPIO);
}

void loop()
{
    // Xử lý WiFi provisioning (non-blocking)
    wifi_prov_loop();

    // Xử lý MQTT loop và reconnect
    if (wifi_prov_is_connected()) {
        if (!s_mqtt.connected()) {
            mqtt_connect();
        }
        s_mqtt.loop();
    }

    // Xử lý nút reset
    reset_button_loop();

    // Nhường CPU nhẹ (FreeRTOS task yielding)
    delay(10);
}